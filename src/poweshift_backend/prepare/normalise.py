"""Convert supported measurements to SI units, keeping native elapsed time explicit."""

from dataclasses import dataclass

import pandas as pd

_KMH_TO_MS = 1.0 / 3.6


@dataclass(frozen=True)
class SIConversion:
    """One converted value with its source unit and value kept for provenance."""

    si_value: float
    si_unit: str
    source_unit: str
    source_value: float


def convert_speed_kmh(value: float) -> SIConversion:
    """Convert one km/h speed reading to m/s, retaining the source value."""
    return SIConversion(si_value=value * _KMH_TO_MS, si_unit="m/s", source_unit="km/h", source_value=value)


def speed_series_kmh_to_si(speeds: pd.Series) -> pd.Series:
    """Convert a km/h speed series to m/s for bulk feature construction."""
    return speeds.astype(float) * _KMH_TO_MS


def elapsed_seconds(times: pd.Series, origin: pd.Timestamp) -> pd.Series:
    """Native elapsed seconds from an explicit absolute time origin, never an inferred one."""
    return (times - origin).dt.total_seconds()


def native_elapsed_seconds(times: pd.Series) -> pd.Series:
    """Elapsed seconds for a stream already relative to session start; not a resampled grid."""
    return times.dt.total_seconds()
