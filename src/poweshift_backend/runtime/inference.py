"""Resident recurrent policy inference with deadline-safe memory."""

from collections.abc import Callable
from pathlib import Path
import time

import torch

from poweshift_backend.contracts.action import ActionRequest, Manoeuvre
from poweshift_backend.contracts.powertrain import EnergyBundleCompatibility
from poweshift_backend.contracts.runtime import InferenceResult, ObservationFrame
from poweshift_backend.policy.checkpoint import PolicyCheckpointMetadata, load_policy_checkpoint
from poweshift_backend.policy.model import RecurrentActorCritic
from poweshift_backend.policy.schema import PolicySchema


class ResidentPolicy:
    """Load one compatible policy and retain only accepted memory."""

    def __init__(
        self,
        checkpoint: str | Path,
        schema: PolicySchema,
        energy_bundle: EnergyBundleCompatibility,
        pit_manifest_id: str,
        route_id: str,
        scenario_id: str,
        *,
        clock_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self.schema = schema
        self.energy_bundle = energy_bundle
        self.pit_manifest_id = pit_manifest_id
        self.route_id = route_id
        self.scenario_id = scenario_id
        self.clock_ns = clock_ns
        self.model = RecurrentActorCritic(schema)
        metadata = PolicyCheckpointMetadata.from_energy_bundle(schema, energy_bundle, pit_manifest_id, scenario_id)
        load_policy_checkpoint(checkpoint, self.model, metadata)
        self.model.eval()
        self.recurrent_state: torch.Tensor | None = None
        self.memory_version = 0

    def infer(
        self,
        run_id: str,
        request_id: str,
        observation: ObservationFrame,
        *,
        deadline_ns: int,
    ) -> InferenceResult:
        """Run deterministic inference and commit memory before the deadline."""
        if len(observation.values) != len(self.schema.feature_names):
            raise ValueError("observation features do not match the policy schema")
        if len(observation.action_mask) != len(self.schema.manoeuvres):
            raise ValueError("observation actions do not match the policy schema")
        if Manoeuvre.HOLD not in (
            manoeuvre for manoeuvre, available in zip(self.schema.manoeuvres, observation.action_mask) if available
        ):
            raise ValueError("runtime observation must retain the finite hold fallback")
        started = self.clock_ns()
        features = torch.tensor(observation.values, dtype=torch.float32).reshape(1, 1, -1)
        feature_mask = torch.tensor(observation.feature_mask, dtype=torch.bool).reshape(1, 1, -1)
        action_mask = torch.tensor(observation.action_mask, dtype=torch.bool).reshape(1, -1)
        with torch.inference_mode():
            logits, alpha, beta, _values, candidate_state = self.model(
                features, feature_mask, action_mask, self.recurrent_state
            )
            action_index = int(torch.argmax(logits, dim=-1).item())
            deployment = float((alpha / (alpha + beta)).item()) if observation.deployment_available else 0.0
        completed = self.clock_ns()
        finite = bool(
            torch.isfinite(logits.masked_select(action_mask)).all()
            and torch.isfinite(alpha).all()
            and torch.isfinite(beta).all()
            and torch.isfinite(candidate_state).all()
        )
        if completed > deadline_ns or not finite:
            reason = "INFERENCE_DEADLINE" if completed > deadline_ns else "INFERENCE_NONFINITE"
            return self._result(
                run_id, request_id, observation, "fallback", ActionRequest(Manoeuvre.HOLD, 0.0),
                started, completed, (reason,),
            )
        self.recurrent_state = candidate_state.detach().clone()
        self.memory_version += 1
        action = ActionRequest(self.schema.manoeuvres[action_index], round(deployment, 4))
        return self._result(run_id, request_id, observation, "accepted", action, started, completed, ())

    def _result(
        self,
        run_id: str,
        request_id: str,
        observation: ObservationFrame,
        status: str,
        action: ActionRequest,
        started: int,
        completed: int,
        reasons: tuple[str, ...],
    ) -> InferenceResult:
        return InferenceResult(
            run_id=run_id,
            request_id=request_id,
            sequence=observation.sequence,
            status=status,
            action=action,
            memory_version=self.memory_version,
            started_monotonic_ns=started,
            completed_monotonic_ns=completed,
            policy_id=self.schema.schema_id,
            energy_bundle_id=self.energy_bundle.bundle_id,
            continuous_profile_id=self.energy_bundle.continuous_profile_id,
            physics_id=self.energy_bundle.physics_id,
            rules_id=self.energy_bundle.rules_id,
            pit_manifest_id=self.pit_manifest_id,
            route_id=self.route_id,
            scenario_id=self.scenario_id,
            news_prior_ids=observation.news_prior_ids,
            binding_reasons=reasons,
        )
