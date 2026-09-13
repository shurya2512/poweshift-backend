"""Prepare later training races as source-bound 4 Hz artifacts."""

import json
from pathlib import Path

from poweshift_backend.representation.training_event_prep import prepare_training_event


ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "data/representation_phase4/weekend_source_audit_v9.json"
OUTPUT = ROOT / "data/representation_phase4"
EVENTS = (
    "2026-05-03_Miami_Grand_Prix",
    "2026-05-24_Canadian_Grand_Prix",
    "2026-06-07_Monaco_Grand_Prix",
    "2026-06-14_Barcelona_Grand_Prix",
    "2026-06-28_Austrian_Grand_Prix",
    "2026-07-05_British_Grand_Prix",
)


def main() -> None:
    reports = []
    for weekend in EVENTS:
        date = weekend[:10]
        acquisition = (
            ROOT / "data/phase4_weekend_acquisition" / weekend
            / f"{date}_Race/export_v2/acquisition_bundle.json"
        )
        report = prepare_training_event(acquisition, AUDIT, OUTPUT)
        reports.append(report)
        print(json.dumps(report, sort_keys=True))
    summary = ROOT / "data/policy_phase8/later_training_race_preparation_v1.json"
    summary.write_text(json.dumps({"events": reports}, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()
