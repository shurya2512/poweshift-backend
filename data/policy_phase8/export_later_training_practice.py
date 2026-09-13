"""Export audited later-weekend free-practice energy controls."""

import json
from pathlib import Path

from poweshift_backend.data.practice_export import export_practice


ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "data/representation_phase4/weekend_source_audit_v9.json"
ISOLATED = Path("/tmp/trackshift-practice-cache-v1")
OUTPUT = ROOT / "data/representation_phase4"
EVENTS = {
    "2026-05-03_Miami_Grand_Prix",
    "2026-05-24_Canadian_Grand_Prix",
    "2026-06-07_Monaco_Grand_Prix",
    "2026-06-14_Barcelona_Grand_Prix",
    "2026-06-28_Austrian_Grand_Prix",
    "2026-07-05_British_Grand_Prix",
}


def main() -> None:
    audit = json.loads(AUDIT.read_text())
    manifests = []
    for record in audit["sessions"]:
        weekend = record["weekend"]
        if weekend not in EVENTS:
            continue
        for session in record["session_names"]:
            if "_Practice_" not in session:
                continue
            ordinal = session.rsplit("_", 1)[-1]
            slug = "_".join(
                word.lower() for word in weekend[11:].split("_")
                if word.lower() not in {"grand", "prix"}
            )
            output = OUTPUT / f"practice_{slug}_fp{ordinal}_v1"
            manifest = export_practice(
                Path(audit["cache_root"]) / weekend / session,
                audit_path=AUDIT,
                isolated_cache_root=ISOLATED,
                output_dir=output,
            )
            manifests.append(str(manifest))
            print(manifest, flush=True)
    summary = ROOT / "data/policy_phase8/later_training_practice_exports_v1.json"
    summary.write_text(json.dumps({"manifests": manifests}, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()
