"""Acquire the 2026 Madring qualifying session as protected test data."""

from datetime import date
from pathlib import Path

from poweshift_backend.data.qualifying_test_export import acquire_qualifying_test


ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    manifest = acquire_qualifying_test(
        year=2026,
        event_name="Spanish Grand Prix",
        event_date=date(2026, 9, 13),
        session_date=date(2026, 9, 12),
        cache_root=ROOT / "data/fastf1data",
        output_dir=ROOT / "data/representation_phase4/qualifying_madring_test_v1",
    )
    print(manifest)


if __name__ == "__main__":
    main()
