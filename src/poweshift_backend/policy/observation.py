"""Policy observations built from currently available fields."""

from dataclasses import dataclass

import torch

from poweshift_backend.contracts.action import ActionMask
from poweshift_backend.policy.schema import PolicySchema
from poweshift_backend.simulation.ego import EgoState


@dataclass(frozen=True)
class AvailableContext:
    """Values whose source availability is known at one time."""

    values: dict[str, float]
    available_fields: frozenset[str]
    available_at_s: float


def build_policy_observation(
    state: EgoState,
    context: AvailableContext,
    schema: PolicySchema,
) -> tuple[torch.Tensor, torch.Tensor, ActionMask]:
    """Emit schema-ordered values and availability masks."""
    mechanics = state.mechanics
    energy = state.energy
    state_values = {
        "time_s": mechanics.time_s,
        "speed_ms": mechanics.speed_ms,
        "distance_m": mechanics.distance_m,
        "progress_m": mechanics.progress_m,
        "fuel_mass_kg": mechanics.fuel_mass_kg,
        "stored_energy_j": energy.stored_energy_j,
        "recharge_throughput_j": energy.recharge_throughput_j,
        "discharge_throughput_j": energy.discharge_throughput_j,
    }
    values: list[float] = []
    masks: list[bool] = []
    context_ready = context.available_at_s <= mechanics.time_s
    for name in schema.feature_names:
        if name in state_values:
            values.append(state_values[name])
            masks.append(True)
        elif context_ready and name in context.available_fields and name in context.values:
            values.append(float(context.values[name]))
            masks.append(True)
        else:
            values.append(0.0)
            masks.append(False)
    def available_value(name: str, default: float) -> float:
        if context_ready and name in context.available_fields:
            return float(context.values.get(name, default))
        return default

    manoeuvres = frozenset(
        manoeuvre for manoeuvre in schema.manoeuvres
        if available_value(f"allow_{manoeuvre.value}", 1.0) > 0.0
    )
    deployment_available = available_value("deployment_available", 1.0) > 0.0
    return torch.tensor(values, dtype=torch.float32), torch.tensor(masks, dtype=torch.bool), ActionMask(manoeuvres, deployment_available)
