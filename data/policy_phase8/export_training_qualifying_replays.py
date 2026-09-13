"""Seal every training-weekend qualifying source for runtime reports."""

import json
from pathlib import Path

from poweshift_backend.data.qualifying_export import export_qualifying, qualifying_session_name


ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "data/representation_phase4/weekend_source_audit_v9.json"
ISOLATED = Path("/tmp/trackshift-qualifying-runtime-cache-v1")
OUTPUT = ROOT / "data/representation_phase4"


def main() -> None:
    audit = json.loads(AUDIT.read_text())
    manifests = []
    for record in audit["sessions"]:
        if record["partition"] != "training":
            continue
        session = qualifying_session_name(record["session_names"])
        if session is None:
            continue
        slug = "_".join(
            word.lower() for word in record["weekend"][11:].split("_")
            if word.lower() not in {"grand", "prix"}
        )
        output = OUTPUT / f"qualifying_{slug}_v1"
        manifest = output / "qualifying_export.json"
        if not manifest.exists():
            manifest = export_qualifying(
                Path(audit["cache_root"]) / record["weekend"] / session,
                audit_path=AUDIT,
                isolated_cache_root=ISOLATED,
                output_dir=output,
            )
        manifests.append(str(manifest))
        print(manifest, flush=True)
    summary = ROOT / "data/policy_phase8/training_qualifying_replay_exports_v1.json"
    summary.write_text(json.dumps({"manifests": manifests}, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()
