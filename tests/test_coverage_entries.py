import pandas as pd

from poweshift_backend.data.coverage import entry_exclusions


def test_excludes_roster_entries_without_observed_or_accurate_laps() -> None:
    laps = pd.DataFrame(
        {
            "DriverNumber": ["1", "2"],
            "IsAccurate": [True, False],
        }
    )

    assert entry_exclusions(laps, ["1", "2", "3"]) == {
        "2": "no_accurate_lap_records",
        "3": "no_lap_records",
    }
