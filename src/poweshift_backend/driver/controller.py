"""Deterministic demands for recorded replay and autonomous forecasts."""

from dataclasses import dataclass
from enum import Enum

import numpy as np


class DriverMode(str, Enum):
    """States whether a demand uses recorded controls or a declared prefix."""

    KNOWN_INPUT = "known_input"
    FORECAST = "forecast"


@dataclass(frozen=True)
class DriverDemand:
    """Signed pedal demand and front share for one mechanics evaluation."""

    throttle: float
    brake: float
    front_brake_share: float
    mode: DriverMode

    def __post_init__(self) -> None:
        if not 0.0 <= self.throttle <= 1.0:
            raise ValueError("throttle must be between zero and one")
        if not 0.0 <= self.brake <= 1.0:
            raise ValueError("brake must be between zero and one")
        if not 0.0 <= self.front_brake_share <= 1.0:
            raise ValueError("front_brake_share must be between zero and one")


@dataclass(frozen=True)
class KnownInputController:
    """Reads recorded controls only for a labelled known-input interval."""

    time_s: np.ndarray
    throttle: np.ndarray
    brake: np.ndarray
    front_brake_share: np.ndarray

    def __post_init__(self) -> None:
        time_s = np.asarray(self.time_s, dtype=np.float64)
        throttle = np.asarray(self.throttle, dtype=np.float64)
        brake = np.asarray(self.brake, dtype=np.float64)
        if time_s.ndim != 1 or len(time_s) == 0 or np.any(np.diff(time_s) <= 0.0):
            raise ValueError("known-input times must strictly increase")
        if len(throttle) != len(time_s) or len(brake) != len(time_s):
            raise ValueError("known-input controls must align with times")
        if not np.isfinite(time_s).all() or not np.isfinite(throttle).all() or not np.isfinite(brake).all():
            raise ValueError("known-input controls must be finite")
        if np.any((throttle < 0.0) | (throttle > 1.0)) or np.any((brake < 0.0) | (brake > 1.0)):
            raise ValueError("known-input pedals must be between zero and one")
        share = np.asarray(self.front_brake_share, dtype=np.float64)
        if len(share) != len(time_s) or not np.isfinite(share).all() or np.any((share < 0.0) | (share > 1.0)):
            raise ValueError("known-input brake shares must align and be between zero and one")
        for values in (time_s, throttle, brake, share):
            values.setflags(write=False)
        object.__setattr__(self, "time_s", time_s)
        object.__setattr__(self, "throttle", throttle)
        object.__setattr__(self, "brake", brake)
        object.__setattr__(self, "front_brake_share", share)

    def demand(self, time_s: float) -> DriverDemand:
        """Interpolate the recorded demand inside its scored interval."""
        if time_s < self.time_s[0] or time_s > self.time_s[-1]:
            raise ValueError("known-input time is outside recorded controls")
        return DriverDemand(
            throttle=float(np.interp(time_s, self.time_s, self.throttle)),
            brake=float(np.interp(time_s, self.time_s, self.brake)),
            front_brake_share=float(np.interp(time_s, self.time_s, self.front_brake_share)),
            mode=DriverMode.KNOWN_INPUT,
        )


@dataclass(frozen=True)
class ForecastController:
    """Holds the last declared prefix demand without future telemetry."""

    prefix_demand: DriverDemand

    def __post_init__(self) -> None:
        if self.prefix_demand.mode is not DriverMode.FORECAST:
            object.__setattr__(
                self,
                "prefix_demand",
                DriverDemand(
                    throttle=self.prefix_demand.throttle,
                    brake=self.prefix_demand.brake,
                    front_brake_share=self.prefix_demand.front_brake_share,
                    mode=DriverMode.FORECAST,
                ),
            )

    def demand(self, _: float) -> DriverDemand:
        """Return the declared prefix demand at every forecast step."""
        return self.prefix_demand
