"""Run the bounded real-data readiness gate."""

import argparse
import json
from pathlib import Path

from poweshift_backend.reconstruction.inputs import load_admitted_inputs
from poweshift_backend.representation.experiment import run_comparison
from poweshift_backend.representation.run import run_full_training, run_phase4_gate, run_smoke
from poweshift_backend.sources.cache_audit import audit_weekend_cache


def main() -> None:
    """Load only admitted evidence and print its readiness report."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=Path("data/preparation_verified_698aaed/phase2_evidence_manifest.json"))
    parser.add_argument("--admission", type=Path, default=Path("data/reconstruction_phase3/phase3_admission.json"))
    parser.add_argument("--entry", default="1")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("data/representation_phase4/full_training_entry_1"))
    parser.add_argument("--evaluate", type=Path)
    parser.add_argument("--weekend-audit", action="store_true")
    parser.add_argument("--weekend-cache", type=Path, default=Path("data/fastf1data/2026"))
    parser.add_argument("--race-manifest", type=Path, action="append")
    parser.add_argument("--audit-output", type=Path, default=Path("data/representation_phase4/weekend_source_audit_v4.json"))
    args = parser.parse_args()
    if args.weekend_audit:
        manifests = tuple(args.race_manifest or sorted(Path("data/phase4_weekend_acquisition").glob("*/*/export_v2/acquisition_bundle.json")))
        print(audit_weekend_cache(args.weekend_cache, args.audit_output, manifests).model_dump_json())
        return
    inputs = load_admitted_inputs(args.evidence, args.admission)
    outcome = run_phase4_gate(inputs, args.entry)
    print(outcome.json())
    if args.smoke and outcome.status == "ready":
        print(json.dumps(run_smoke(inputs, args.entry, outcome.policy, outcome.policy_id), sort_keys=True))
    if args.full and outcome.status == "ready":
        print(json.dumps(run_full_training(inputs, args.entry, outcome.policy, outcome.policy_id, args.output), sort_keys=True))
    if args.evaluate and outcome.status == "ready":
        print(json.dumps(run_comparison(inputs, args.entry, args.evaluate, args.evaluate / "comparison_report_v4.json"), sort_keys=True))


if __name__ == "__main__":
    main()
