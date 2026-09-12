"""Coverage and entry-exclusion decisions for acquired records."""

import pandas as pd


def entry_exclusions(
    laps: pd.DataFrame | None,
    roster: list[str],
    car: pd.DataFrame | None,
    position: pd.DataFrame | None,
    tyres: pd.DataFrame | None,
) -> dict[str, str]:
    """Exclude entries without an accurate observed lap."""
    exclusions: dict[str, str] = {}
    for driver in roster:
        if not _has_driver(car, driver):
            exclusions[driver] = "missing_car_data"
            continue
        if not _has_driver(position, driver):
            exclusions[driver] = "missing_position_data"
            continue
        if not _has_driver(tyres, driver):
            exclusions[driver] = "missing_tyre_context"
            continue
        if laps is None:
            exclusions[driver] = "missing_lap_records"
            continue
        driver_laps = laps[laps["DriverNumber"].astype(str) == driver]
        if driver_laps.empty:
            exclusions[driver] = "no_lap_records"
        elif not driver_laps["IsAccurate"].fillna(False).astype(bool).any():
            exclusions[driver] = "no_accurate_lap_records"
    return exclusions


def _has_driver(records: pd.DataFrame | None, driver: str) -> bool:
    return records is not None and "DriverNumber" in records and driver in set(records["DriverNumber"].dropna().astype(str))


def parser_quality(laps: pd.DataFrame) -> dict[str, int]:
    """Count parser-derived and inaccurate lap records."""
    return {
        "parser_generated_laps": int(laps["FastF1Generated"].fillna(False).astype(bool).sum()),
        "inaccurate_laps": int((~laps["IsAccurate"].fillna(False).astype(bool)).sum()),
    }
