"""Independent ego state advanced only through shared admitted physics."""

from collections.abc import Callable
from dataclasses import dataclass

from poweshift_backend.contracts.action import ActionMask, ActionRequest
from poweshift_backend.contracts.powertrain import EnergyBundleCompatibility
from poweshift_backend.energy.state import EnergyState
from poweshift_backend.physics.state import MechanicsState


SharedAdvance = Callable[[MechanicsState, EnergyState, ActionRequest], tuple[MechanicsState, EnergyState]]


@dataclass(frozen=True)
class EgoState:
    """One ego identity with single mechanics and energy owners."""

    identity: str
    mechanics: MechanicsState
    energy: EnergyState
    energy_bundle_id: str


def advance_ego(
    state: EgoState,
    request: ActionRequest,
    mask: ActionMask,
    bundle: EnergyBundleCompatibility,
    advance: SharedAdvance,
) -> EgoState:
    """Advance through the injected shared-physics boundary."""
    mask.require(request)
    if not bundle.admitted:
        raise ValueError("ego advance requires an admitted energy bundle")
    if state.energy_bundle_id != bundle.bundle_id:
        raise ValueError("ego and energy bundle are incompatible")
    mechanics, energy = advance(state.mechanics, state.energy, request)
    if mechanics.time_s <= state.mechanics.time_s:
        raise ValueError("shared physics must advance time")
    return EgoState(state.identity, mechanics, energy, state.energy_bundle_id)
