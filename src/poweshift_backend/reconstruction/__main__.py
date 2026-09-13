"""Run the admitted effective-profile baseline and held-out replay."""

import argparse
from pathlib import Path

from poweshift_backend.contracts.reconstruction import EvidenceReport
from poweshift_backend.driver.controller import DriverMode
from poweshift_backend.reconstruction.baseline import build_fit_report, fit_effective_profile
from poweshift_backend.reconstruction.evidence import build_evidence
from poweshift_backend.reconstruction.inputs import load_admitted_inputs
from poweshift_backend.reconstruction.replay import replay_final_evaluation
from poweshift_backend.reconstruction.report import write_evidence, write_fit_report, write_settings


def main() -> None:
    """Fit on training telemetry and emit final-evaluation motion evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=Path("data/preparation_verified_698aaed/phase2_evidence_manifest.json"))
    parser.add_argument("--admission", type=Path, default=Path("data/reconstruction_phase3/phase3_admission.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/reconstruction_phase3/baseline_run"))
    parser.add_argument("--sample-budget", type=int, default=24)
    parser.add_argument("--heldout-chunk-budget", type=int, default=4)
    parser.add_argument("--entry")
    args = parser.parse_args()
    inputs = load_admitted_inputs(args.evidence, args.admission)
    entries = sorted({chunk.entry for chunk in inputs.chunks})
    if args.entry is not None:
        entries = [args.entry] if args.entry in entries else []
    if not entries:
        raise ValueError("requested entry is absent from admitted evidence")
    for entry in entries:
        entry_inputs = type(inputs)(
            inputs.manifest,
            tuple(chunk for chunk in inputs.chunks if chunk.entry == entry),
            tuple(item for item in inputs.continuations if item[1] == entry),
            inputs.alignment_support,
        )
        baseline = fit_effective_profile(entry_inputs, args.sample_budget, entry)
        output_dir = args.output_dir / f"entry_{entry}"
        settings_pin = write_settings(baseline.settings, output_dir)
        fit_pin = write_fit_report(build_fit_report(entry_inputs, baseline, settings_pin), output_dir)
        summary = build_evidence(
            replay_final_evaluation(entry_inputs, baseline, DriverMode.KNOWN_INPUT, args.heldout_chunk_budget), baseline
        )
        evidence = EvidenceReport(fit_report=fit_pin, input_manifest=entry_inputs.manifest, **summary)
        print(write_evidence(evidence, output_dir))


if __name__ == "__main__":
    main()
