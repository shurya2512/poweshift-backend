"""Finite ICE response inside a declared source map."""

from dataclasses import dataclass
from math import isfinite

from poweshift_backend.powertrain.maps import SourcePowerMap


@dataclass(frozen=True)
class ResponseConfig:
    """Power slew limits and supported minimum shaft speed."""

    rise_rate_w_s: float
    fall_rate_w_s: float
    minimum_shaft_speed_rpm: float
    evidence_id: str

    def __post_init__(self) -> None:
        values = (self.rise_rate_w_s, self.fall_rate_w_s, self.minimum_shaft_speed_rpm)
        if not all(isfinite(value) and value > 0.0 for value in values) or not self.evidence_id:
            raise ValueError("response configuration is incomplete")


@dataclass(frozen=True)
class ResponseState:
    """Previous delivered ICE shaft power."""

    delivered_power_w: float

    def __post_init__(self) -> None:
        if not isfinite(self.delivered_power_w) or self.delivered_power_w < 0.0:
            raise ValueError("response state power must be finite and non-negative")


def resolve_ice_response(
    state: ResponseState,
    requested_power_w: float,
    shaft_speed_rpm: float,
    step_s: float,
    power_map: SourcePowerMap,
    config: ResponseConfig,
    *,
    shift_active: bool = False,
) -> ResponseState:
    """Advance delivered power within map and finite response support."""
    if shift_active:
        raise ValueError("shift response is unsupported")
    if shaft_speed_rpm < config.minimum_shaft_speed_rpm:
        raise ValueError("low-speed response is unsupported")
    if not isfinite(requested_power_w) or requested_power_w < 0.0 or not isfinite(step_s) or step_s <= 0.0:
        raise ValueError("response request and step must be finite and supported")
    target = min(requested_power_w, power_map.maximum_power_w(shaft_speed_rpm))
    delta = target - state.delivered_power_w
    limit = config.rise_rate_w_s * step_s if delta >= 0.0 else config.fall_rate_w_s * step_s
    return ResponseState(state.delivered_power_w + max(-limit, min(limit, delta)))
