"""Coverage and entry-exclusion decisions for acquired records."""

import pandas as pd


def entry_exclusions(laps: pd.DataFrame, roster: list[str]) -> dict[str, str]:
    """Exclude entries without an accurate observed lap."""
    exclusions: dict[str, str] = {}
    for driver in roster:
        driver_laps = laps[laps["DriverNumber"].astype(str) == driver]
        if driver_laps.empty:
            exclusions[driver] = "no_lap_records"
        elif not driver_laps["IsAccurate"].fillna(False).astype(bool).any():
            exclusions[driver] = "no_accurate_lap_records"
    return exclusions


def parser_quality(laps: pd.DataFrame) -> dict[str, int]:
    """Count parser-derived and inaccurate lap records."""
    return {
        "parser_generated_laps": int(laps["FastF1Generated"].fillna(False).astype(bool).sum()),
        "inaccurate_laps": int((~laps["IsAccurate"].fillna(False).astype(bool)).sum()),
    }
