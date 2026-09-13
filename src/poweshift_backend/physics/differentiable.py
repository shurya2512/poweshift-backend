"""Float64 tensor mechanics for supported recorded-control reconstruction."""

from dataclasses import dataclass
from math import isfinite
from typing import Callable

import torch
from torch.utils.checkpoint import checkpoint

from poweshift_backend.driver.controller import DriverDemand
from poweshift_backend.physics.forces import mechanics_derivative
from poweshift_backend.physics.state import MechanicsState, RoadInput, StateRate
from poweshift_backend.reconstruction.baseline import BaselineRuntime


PARAMETER_NAMES = (
    "max_drive_force_n",
    "max_brake_force_n",
    "drag_n_per_ms2",
    "rolling_resistance_n",
    "front_downforce_n_per_ms2",
    "rear_downforce_n_per_ms2",
    "longitudinal_mu",
    "lateral_mu",
)
STATE_SCALES = (0.1, 1.0, 1.0, 0.01)
PARAMETER_SCALES = (12000.0, 16000.0, 10.0, 2000.0, 1.0, 1.0, 3.0, 3.0)
GRADIENT_EPSILON = 1e-4
MIN_GRADIENT_SPEED_MS = 0.1
MAX_GRADIENT_LATERAL_RATIO = 0.98
CLIP_BOUNDARY_RELATIVE_MARGIN = 1e-6


class MechanicsUnsupported(ValueError):
    """Raised outside the finite, fixed-active-set mechanics support."""


@dataclass(frozen=True)
class GradientError:
    """Per-state normalized JVP and finite-difference comparison."""

    relative: tuple[float, ...]
    absolute: tuple[float | None, ...]


@dataclass(frozen=True)
class _ForceEvaluation:
    front_force_n: torch.Tensor
    rear_force_n: torch.Tensor
    drag_force_n: torch.Tensor
    rolling_force_n: torch.Tensor
    lateral_ratio_front: torch.Tensor
    lateral_ratio_rear: torch.Tensor
    front_headroom_n: torch.Tensor
    rear_headroom_n: torch.Tensor
    requested_front_n: torch.Tensor
    requested_rear_n: torch.Tensor
    front_load_n: torch.Tensor
    rear_load_n: torch.Tensor
    maximum_lateral_ratio: torch.Tensor
    converged: torch.Tensor
    iterations: torch.Tensor

    @property
    def net_force_n(self) -> torch.Tensor:
        """Return the signed longitudinal force after external resistance."""
        return self.front_force_n + self.rear_force_n - self.drag_force_n - self.rolling_force_n


class StaticRoadLookup:
    """Interpolate static curvature from the predicted metre-progress state."""

    def __init__(self, progress_m: torch.Tensor, curvature_m_inv: torch.Tensor) -> None:
        for value, name in ((progress_m, "road progress"), (curvature_m_inv, "road curvature")):
            DifferentiableMechanics._require_tensor(value, name, None)
        if progress_m.ndim != 1 or curvature_m_inv.shape != progress_m.shape or len(progress_m) < 2:
            raise MechanicsUnsupported("road lookup needs aligned one-dimensional source arrays")
        if not DifferentiableMechanics._finite(progress_m) or not DifferentiableMechanics._finite(curvature_m_inv):
            raise MechanicsUnsupported("road lookup source arrays must be finite")
        if DifferentiableMechanics._minimum(torch.diff(progress_m)) <= 0.0:
            raise MechanicsUnsupported("road lookup progress must strictly increase")
        self.progress_m = progress_m.detach().clone()
        self.curvature_m_inv = curvature_m_inv.detach().clone()

    def __call__(self, predicted_progress_m: torch.Tensor) -> torch.Tensor:
        """Return curvature and canonical progress ratio for predicted progress."""
        DifferentiableMechanics._require_tensor(predicted_progress_m, "predicted progress", None)
        if (
            DifferentiableMechanics._minimum(predicted_progress_m) < DifferentiableMechanics._scalar(self.progress_m[0])
            or DifferentiableMechanics._maximum(predicted_progress_m) > DifferentiableMechanics._scalar(self.progress_m[-1])
        ):
            raise MechanicsUnsupported("predicted progress is outside source-linked road support")
        indices = torch.searchsorted(self.progress_m, predicted_progress_m, right=True).clamp(1, len(self.progress_m) - 1)
        lower = indices - 1
        upper = indices
        start = self.progress_m[lower]
        end = self.progress_m[upper]
        fraction = (predicted_progress_m - start) / (end - start)
        curvature = self.curvature_m_inv[lower] + fraction * (self.curvature_m_inv[upper] - self.curvature_m_inv[lower])
        return torch.stack((curvature, torch.ones_like(curvature)), dim=-1)


class DifferentiableMechanics:
    """Advance canonical mechanics with float64 tensors and recorded controls."""

    def __init__(
        self,
        *,
        reference_no_fuel_mass_kg: float,
        fuel_burn_rate_kg_s: float,
        front_axle_distance_m: float,
        rear_axle_distance_m: float,
        cg_height_m: float,
        gravity_ms2: float,
        axle_tolerance_n: float,
        axle_max_iterations: int,
        step_s: float,
        front_brake_share: float = 0.5,
        runtime: BaselineRuntime | None = None,
    ) -> None:
        values = (
            reference_no_fuel_mass_kg,
            fuel_burn_rate_kg_s,
            front_axle_distance_m,
            rear_axle_distance_m,
            cg_height_m,
            gravity_ms2,
            axle_tolerance_n,
            step_s,
            front_brake_share,
        )
        if not all(isfinite(value) for value in values):
            raise ValueError("mechanics constants must be finite")
        if min(
            reference_no_fuel_mass_kg,
            front_axle_distance_m,
            rear_axle_distance_m,
            cg_height_m,
            gravity_ms2,
            axle_tolerance_n,
            step_s,
        ) <= 0.0:
            raise ValueError("mechanics constants must be positive")
        if isinstance(axle_max_iterations, bool) or not isinstance(axle_max_iterations, int):
            raise ValueError("axle iteration limit must be an integer")
        if fuel_burn_rate_kg_s < 0.0 or axle_max_iterations < 1 or not 0.0 <= front_brake_share <= 1.0:
            raise ValueError("mechanics constants are invalid")
        self._constants = torch.tensor(
            (
                reference_no_fuel_mass_kg,
                fuel_burn_rate_kg_s,
                front_axle_distance_m,
                rear_axle_distance_m,
                cg_height_m,
                gravity_ms2,
                axle_tolerance_n,
                step_s,
                front_brake_share,
            ),
            dtype=torch.float64,
        )
        self.axle_max_iterations = axle_max_iterations
        self._runtime = runtime

    @classmethod
    def from_runtime(cls, runtime: BaselineRuntime, *, front_brake_share: float = 0.5) -> "DifferentiableMechanics":
        """Copy declared runtime constants into the tensor-only mechanics boundary."""
        return cls(
            reference_no_fuel_mass_kg=runtime.mass.reference_no_fuel_mass_kg,
            fuel_burn_rate_kg_s=runtime.mass.fuel_policy.burn_rate_kg_s,
            front_axle_distance_m=runtime.geometry.front_axle_distance_m,
            rear_axle_distance_m=runtime.geometry.rear_axle_distance_m,
            cg_height_m=runtime.geometry.height_m,
            gravity_ms2=runtime.solve_config.gravity_ms2,
            axle_tolerance_n=runtime.solve_config.tolerance_n,
            axle_max_iterations=runtime.solve_config.max_iterations,
            step_s=runtime.integration.step_s,
            front_brake_share=front_brake_share,
            runtime=runtime,
        )

    def normalize_profile(self, profile: torch.Tensor) -> torch.Tensor:
        """Map physical parameters to the frozen numerical comparison basis."""
        self._require_tensor(profile, "profile", 8)
        return profile / self._parameter_scales(profile)

    def denormalize_profile(self, normalized: torch.Tensor) -> torch.Tensor:
        """Map normalized comparison coordinates back to physical parameters."""
        self._require_tensor(normalized, "normalized profile", 8)
        return normalized * self._parameter_scales(normalized)

    def derivative(
        self,
        state: torch.Tensor,
        controls: torch.Tensor,
        road: torch.Tensor,
        profile: torch.Tensor,
        *,
        allocated_axle_force_n: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Return the canonical rate for one supported tensor state."""
        self._validate_inputs(state, controls, road, profile)
        if allocated_axle_force_n is not None:
            self._require_tensor(allocated_axle_force_n, "allocated axle force", None)
            if allocated_axle_force_n.shape != state.shape[:-1] or not self._finite(allocated_axle_force_n):
                raise MechanicsUnsupported("allocated axle force must match the car batch shape and be finite")
            if self._maximum(torch.abs(controls[..., 0])) != 0.0:
                raise ValueError("effective and allocated propulsion are exclusive")
        evaluation = self._evaluate(state, controls, road, profile, allocated_axle_force_n)
        self._require_supported(evaluation, state, road)
        mass = self._constants_for(state)[0] + state[..., 3]
        return torch.stack((evaluation.net_force_n / mass, state[..., 0], state[..., 0] / road[..., 1], -self._constants_for(state)[1].expand_as(mass)), dim=-1)

    def assert_gradient_supported(
        self,
        state: torch.Tensor,
        controls: torch.Tensor,
        road: torch.Tensor,
        profile: torch.Tensor,
        *,
        event_times: tuple[float, ...] = (),
    ) -> None:
        """Reject values near hybrid boundaries before a gradient measurement."""
        if event_times:
            raise MechanicsUnsupported("event boundaries require value-only parity")
        self._validate_inputs(state, controls, road, profile)
        if self._minimum(torch.abs(state[..., 0])) <= MIN_GRADIENT_SPEED_MS:
            raise MechanicsUnsupported("speed is too near zero for a fixed rolling-force sign")
        evaluation = self._evaluate(state, controls, road, profile)
        self._require_supported(evaluation, state, road)
        if self._maximum(evaluation.maximum_lateral_ratio) >= MAX_GRADIENT_LATERAL_RATIO:
            raise MechanicsUnsupported("lateral support is too near the combined-grip boundary")
        for requested, headroom in (
            (evaluation.requested_front_n, evaluation.front_headroom_n),
            (evaluation.requested_rear_n, evaluation.rear_headroom_n),
        ):
            if self._minimum(torch.abs(torch.abs(requested) - headroom) / torch.maximum(torch.ones_like(headroom), headroom)) <= CLIP_BOUNDARY_RELATIVE_MARGIN:
                raise MechanicsUnsupported("tyre-force clipping is at its active-set boundary")

    def rk4_step(
        self,
        state: torch.Tensor,
        time_s: torch.Tensor,
        step_s: torch.Tensor,
        controls_at: Callable[[torch.Tensor], torch.Tensor],
        road_at: Callable[[torch.Tensor], torch.Tensor],
        profile: torch.Tensor,
    ) -> torch.Tensor:
        """Advance one tensor state with the canonical fixed RK4 stages."""
        self._require_tensor(time_s, "time", None)
        self._require_tensor(step_s, "step", None)
        if self._scalar(step_s) <= 0.0:
            raise MechanicsUnsupported("RK4 step must be positive")

        def rate(current: torch.Tensor, stage_time: torch.Tensor) -> torch.Tensor:
            controls = controls_at(stage_time)
            road = road_at(current[..., 2])
            return self.derivative(current, controls, road, profile)

        k1 = rate(state, time_s)
        k2 = rate(state + k1 * step_s * 0.5, time_s + step_s * 0.5)
        k3 = rate(state + k2 * step_s * 0.5, time_s + step_s * 0.5)
        k4 = rate(state + k3 * step_s, time_s + step_s)
        return state + step_s * (k1 + 2.0 * k2 + 2.0 * k3 + k4) / 6.0

    def integrate(
        self,
        initial_state: torch.Tensor,
        observation_times_s: torch.Tensor,
        controls_at: Callable[[torch.Tensor], torch.Tensor],
        road_at: Callable[[torch.Tensor], torch.Tensor],
        profile: torch.Tensor,
        *,
        checkpoint_observations: int | None = None,
    ) -> torch.Tensor:
        """Integrate at fixed internal steps and return declared observation times."""
        self._require_tensor(initial_state, "initial state", 4)
        self._require_tensor(observation_times_s, "observation times", None)
        self._require_tensor(profile, "profile", 8)
        if observation_times_s.ndim != 1 or len(observation_times_s) < 1:
            raise MechanicsUnsupported("observation times must be a nonempty vector")
        if not self._finite(observation_times_s) or self._scalar(observation_times_s[0]) < 0.0:
            raise MechanicsUnsupported("observation times must be finite and non-negative")
        if len(observation_times_s) > 1 and self._scalar(torch.min(torch.diff(observation_times_s))) <= 0.0:
            raise MechanicsUnsupported("observation times must strictly increase")
        self._validate_boundary(initial_state, observation_times_s[0], controls_at, road_at, profile)
        if checkpoint_observations is None:
            trajectory = self._integrate_span(initial_state, observation_times_s, controls_at, road_at, profile)
        else:
            trajectory = self._checkpointed_trajectory(
                initial_state,
                observation_times_s,
                controls_at,
                road_at,
                profile,
                checkpoint_observations,
            )
        self._validate_boundary(trajectory[-1], observation_times_s[-1], controls_at, road_at, profile)
        return trajectory

    def _integrate_span(
        self,
        initial_state: torch.Tensor,
        observation_times_s: torch.Tensor,
        controls_at: Callable[[torch.Tensor], torch.Tensor],
        road_at: Callable[[torch.Tensor], torch.Tensor],
        profile: torch.Tensor,
    ) -> torch.Tensor:
        state = initial_state
        states = [state]
        current_time = observation_times_s[0]
        internal_step = self._constants_for(initial_state)[7]
        for target_time in observation_times_s[1:]:
            while self._scalar(target_time - current_time) > 0.0:
                step = torch.minimum(internal_step, target_time - current_time)
                state = self.rk4_step(state, current_time, step, controls_at, road_at, profile)
                current_time = current_time + step
            states.append(state)
        return torch.stack(states)

    def _checkpointed_trajectory(
        self,
        initial_state: torch.Tensor,
        observation_times_s: torch.Tensor,
        controls_at: Callable[[torch.Tensor], torch.Tensor],
        road_at: Callable[[torch.Tensor], torch.Tensor],
        profile: torch.Tensor,
        checkpoint_observations: int,
    ) -> torch.Tensor:
        if isinstance(checkpoint_observations, bool) or not isinstance(checkpoint_observations, int) or checkpoint_observations < 1:
            raise MechanicsUnsupported("checkpoint observations must be a positive integer")
        state = initial_state
        blocks: list[torch.Tensor] = []
        start = 0
        while start < len(observation_times_s) - 1:
            stop = min(start + checkpoint_observations, len(observation_times_s) - 1)
            block_times = observation_times_s[start : stop + 1]
            block = checkpoint(
                self._checkpoint_block(block_times, controls_at, road_at),
                state,
                profile,
                use_reentrant=False,
            )
            blocks.append(block if start == 0 else block[1:])
            state = block[-1]
            start = stop
        return initial_state.unsqueeze(0) if not blocks else torch.cat(blocks)

    def _checkpoint_block(
        self,
        observation_times_s: torch.Tensor,
        controls_at: Callable[[torch.Tensor], torch.Tensor],
        road_at: Callable[[torch.Tensor], torch.Tensor],
    ) -> Callable[[torch.Tensor, torch.Tensor], torch.Tensor]:
        def integrate_block(state: torch.Tensor, profile: torch.Tensor) -> torch.Tensor:
            return self._integrate_span(state, observation_times_s, controls_at, road_at, profile)

        return integrate_block

    def canonical_derivative(self, state: MechanicsState, demand: DriverDemand, road: RoadInput) -> StateRate:
        """Evaluate the unchanged canonical float path for parity tests."""
        if self._runtime is None:
            raise MechanicsUnsupported("canonical parity needs a source runtime")
        return mechanics_derivative(
            state,
            demand,
            road,
            self._runtime.mass,
            self._runtime.geometry,
            self._runtime.forces,
            self._runtime.tyre,
            self._runtime.solve_config,
        )

    def _evaluate(
        self,
        state: torch.Tensor,
        controls: torch.Tensor,
        road: torch.Tensor,
        profile: torch.Tensor,
        allocated_axle_force_n: torch.Tensor | None = None,
    ) -> _ForceEvaluation:
        constants = self._constants_for(state)
        mass = constants[0] + state[..., 3]
        front_distance, rear_distance, height, gravity, tolerance, front_brake_share = (
            constants[2], constants[3], constants[4], constants[5], constants[6], constants[8]
        )
        wheelbase = front_distance + rear_distance
        drive, brake, drag_coefficient, rolling_resistance, front_aero, rear_aero, longitudinal_mu, lateral_mu = profile.unbind(dim=-1)
        speed = state[..., 0]
        drag = drag_coefficient * speed * torch.abs(speed)
        rolling = torch.where(speed == 0.0, torch.zeros_like(speed), torch.copysign(rolling_resistance, speed))
        front_downforce = front_aero * speed.square()
        rear_downforce = rear_aero * speed.square()
        lateral = mass * speed.square() * road[..., 0]
        front = mass * gravity * rear_distance / wheelbase + front_downforce
        rear = mass * gravity * front_distance / wheelbase + rear_downforce
        requested_front = -brake * controls[..., 1] * front_brake_share
        requested_drive = drive * controls[..., 0] if allocated_axle_force_n is None else allocated_axle_force_n
        requested_rear = requested_drive - brake * controls[..., 1] * (1.0 - front_brake_share)
        lateral_front = lateral * rear_distance / wheelbase / lateral_mu
        lateral_rear = lateral * front_distance / wheelbase / lateral_mu
        transfer_ratio = height / wheelbase

        def residual_and_slope(transfer: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
            force = -drag - rolling
            slope = torch.ones_like(transfer)
            for load, lateral_load, requested, direction in (
                (front - transfer, lateral_front, requested_front, -1.0),
                (rear + transfer, lateral_rear, requested_rear, 1.0),
            ):
                fraction = torch.sqrt(torch.clamp(1.0 - (lateral_load / load).square(), min=0.0))
                headroom = longitudinal_mu * load * fraction
                force = force + torch.clamp(requested, min=-headroom, max=headroom)
                force_slope = torch.sign(requested) * longitudinal_mu / fraction
                slope = slope - transfer_ratio * direction * torch.where(
                    torch.abs(requested) >= headroom, force_slope, torch.zeros_like(force_slope)
                )
            return transfer - transfer_ratio * force, slope

        with torch.no_grad():
            margin = torch.finfo(state.dtype).eps * (front + rear)
            lower = torch.abs(lateral_rear) + margin - rear
            upper = front - torch.abs(lateral_front) - margin
            if self._minimum(upper - lower) <= 0.0:
                raise MechanicsUnsupported("lateral demand leaves no supported axle-load interval")
            if self._maximum(residual_and_slope(lower)[0]) > 0.0 or self._minimum(residual_and_slope(upper)[0]) < 0.0:
                raise MechanicsUnsupported("axle consistency root is not bracketed within tyre support")
            transfer = torch.clamp(torch.zeros_like(speed), min=lower, max=upper)
            converged = torch.zeros_like(speed, dtype=torch.bool)
            iteration = torch.zeros_like(speed, dtype=torch.int64)
            for current_iteration in range(1, self.axle_max_iterations + 1):
                error, slope = residual_and_slope(transfer)
                first_converged = (~converged) & (torch.abs(error) <= tolerance)
                iteration = torch.where(first_converged, torch.full_like(iteration, current_iteration), iteration)
                converged = converged | first_converged
                if self._all(converged):
                    break
                lower = torch.where((error < 0.0) & ~converged, transfer, lower)
                upper = torch.where((error >= 0.0) & ~converged, transfer, upper)
                candidate = transfer - error / slope
                candidate = torch.where(
                    torch.isfinite(candidate) & (candidate > lower) & (candidate < upper),
                    candidate, (lower + upper) / 2.0,
                )
                transfer = torch.where(converged, transfer, candidate)
        # Differentiate the converged equation, not the discrete root-search decisions.
        transfer = transfer.detach()
        error, slope = residual_and_slope(transfer)
        transfer = transfer - (error - error.detach()) / slope.detach()
        final_front = front - transfer
        final_rear = rear + transfer
        front_ratio = lateral_front / final_front
        rear_ratio = lateral_rear / final_rear
        maximum_lateral_ratio = torch.maximum(torch.abs(front_ratio), torch.abs(rear_ratio))
        front_headroom = longitudinal_mu * final_front * torch.sqrt(torch.clamp(1.0 - front_ratio.square(), min=0.0))
        rear_headroom = longitudinal_mu * final_rear * torch.sqrt(torch.clamp(1.0 - rear_ratio.square(), min=0.0))
        front_force = torch.clamp(requested_front, min=-front_headroom, max=front_headroom)
        rear_force = torch.clamp(requested_rear, min=-rear_headroom, max=rear_headroom)
        return _ForceEvaluation(
            front_force_n=front_force,
            rear_force_n=rear_force,
            drag_force_n=drag,
            rolling_force_n=rolling,
            lateral_ratio_front=front_ratio,
            lateral_ratio_rear=rear_ratio,
            front_headroom_n=front_headroom,
            rear_headroom_n=rear_headroom,
            requested_front_n=requested_front,
            requested_rear_n=requested_rear,
            front_load_n=final_front,
            rear_load_n=final_rear,
            maximum_lateral_ratio=maximum_lateral_ratio,
            converged=converged,
            iterations=iteration,
        )

    def _validate_boundary(
        self,
        state: torch.Tensor,
        time_s: torch.Tensor,
        controls_at: Callable[[torch.Tensor], torch.Tensor],
        road_at: Callable[[torch.Tensor], torch.Tensor],
        profile: torch.Tensor,
    ) -> None:
        with torch.no_grad():
            boundary = state.detach()
            self.derivative(
                boundary,
                controls_at(time_s).detach(),
                road_at(boundary[..., 2]).detach(),
                profile.detach(),
            )

    def _validate_inputs(self, state: torch.Tensor, controls: torch.Tensor, road: torch.Tensor, profile: torch.Tensor) -> None:
        self._require_tensor(state, "state", 4)
        self._require_tensor(controls, "controls", 2)
        self._require_tensor(road, "road", 2)
        self._require_tensor(profile, "profile", 8)
        batch_shape = state.shape[:-1]
        if controls.shape[:-1] != batch_shape or road.shape[:-1] != batch_shape or profile.shape[:-1] != batch_shape:
            raise MechanicsUnsupported("state, controls, road and profile must share one car batch shape")
        if not all(self._finite(value) for value in (state, controls, road, profile)):
            raise MechanicsUnsupported("mechanics inputs must be finite")
        if self._minimum(state[..., 0]) < 0.0 or self._minimum(state[..., 3]) < 0.0:
            raise MechanicsUnsupported("speed and fuel mass must be non-negative")
        if self._minimum(controls) < 0.0 or self._maximum(controls) > 1.0:
            raise MechanicsUnsupported("recorded pedal controls must be between zero and one")
        if self._minimum(road[..., 1]) <= 0.0:
            raise MechanicsUnsupported("road progress ratio must be positive")
        if any(self._minimum(profile[..., index]) < 0.0 for index in range(6)) or any(
            self._minimum(profile[..., index]) <= 0.0 for index in (6, 7)
        ):
            raise MechanicsUnsupported("physical profile values are outside declared support")

    def _require_supported(self, evaluation: _ForceEvaluation, state: torch.Tensor, road: torch.Tensor) -> None:
        values = (
            evaluation.front_force_n,
            evaluation.rear_force_n,
            evaluation.drag_force_n,
            evaluation.rolling_force_n,
            evaluation.lateral_ratio_front,
            evaluation.lateral_ratio_rear,
            evaluation.front_load_n,
            evaluation.rear_load_n,
        )
        if not all(self._finite(value) for value in values):
            raise MechanicsUnsupported("mechanics evaluation is non-finite")
        if self._minimum(evaluation.front_load_n) <= 0.0 or self._minimum(evaluation.rear_load_n) <= 0.0:
            raise MechanicsUnsupported("an axle unloaded during the force solve")
        if self._maximum(evaluation.maximum_lateral_ratio) > 1.0:
            raise MechanicsUnsupported("lateral demand exceeds declared tyre support")
        if not self._all(evaluation.converged):
            raise MechanicsUnsupported("axle load consistency did not converge")

    def _constants_for(self, value: torch.Tensor) -> torch.Tensor:
        return self._constants.to(device=value.device)

    @staticmethod
    def _finite(value: torch.Tensor) -> bool:
        return bool(torch.isfinite(value).detach().cpu().all().item())

    @staticmethod
    def _all(value: torch.Tensor) -> bool:
        return bool(value.detach().cpu().all().item())

    @staticmethod
    def _scalar(value: torch.Tensor) -> float:
        return float(value.detach().cpu().item())

    @staticmethod
    def _minimum(value: torch.Tensor) -> float:
        return float(torch.min(value).detach().cpu().item())

    @staticmethod
    def _maximum(value: torch.Tensor) -> float:
        return float(torch.max(value).detach().cpu().item())

    @staticmethod
    def _require_tensor(value: torch.Tensor, name: str, size: int | None) -> None:
        if not isinstance(value, torch.Tensor) or value.dtype is not torch.float64 or value.device.type != "cpu":
            raise MechanicsUnsupported(f"{name} must be a CPU float64 tensor")
        if size is not None and (value.ndim < 1 or value.shape[-1] != size):
            raise MechanicsUnsupported(f"{name} must end in shape ({size},)")

    @staticmethod
    def _parameter_scales(value: torch.Tensor) -> torch.Tensor:
        return torch.tensor(PARAMETER_SCALES, dtype=torch.float64, device=value.device)


def normalized_jvp_error(jvp: torch.Tensor, finite_difference: torch.Tensor) -> GradientError:
    """Compare terminal-state JVP and finite difference one output at a time."""
    if jvp.shape != (4,) or finite_difference.shape != (4,):
        raise ValueError("gradient comparisons need one four-state terminal derivative")
    scales = torch.tensor(STATE_SCALES, dtype=torch.float64, device=jvp.device)
    normalized_jvp = jvp / scales
    normalized_fd = finite_difference / scales
    relative: list[float] = []
    absolute: list[float | None] = []
    for index in range(4):
        difference = float(torch.abs(normalized_jvp[index] - normalized_fd[index]).detach().cpu())
        magnitude = float(torch.abs(normalized_fd[index]).detach().cpu())
        if magnitude < 1e-6:
            relative.append(0.0)
            absolute.append(difference)
        else:
            relative.append(difference / magnitude)
            absolute.append(None)
    return GradientError(tuple(relative), tuple(absolute))


def normalized_state_error(actual: torch.Tensor, reference: torch.Tensor) -> tuple[float, ...]:
    """Return the declared scale-normalized error for each mechanics state."""
    if actual.shape != reference.shape or actual.shape[-1] != 4:
        raise ValueError("state comparisons need matching final state axes")
    scales = torch.tensor(STATE_SCALES, dtype=torch.float64, device=actual.device)
    difference = torch.abs((actual - reference) / scales)
    denominator = torch.maximum(torch.abs(reference / scales), torch.ones_like(reference))
    return tuple(float(value.detach().cpu()) for value in (difference / denominator).reshape(-1, 4).amax(dim=0))
