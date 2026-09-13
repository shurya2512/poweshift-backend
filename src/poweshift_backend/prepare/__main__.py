"""Run the Phase 2 preparation job over the immutable Phase 1 bundle."""

import argparse
from datetime import date
from pathlib import Path

from poweshift_backend.data.prepare_run import run_preparation


def main() -> None:
    """Record the admitted-entries coverage disposition and prepare all Phase 2 evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-path", type=Path, default=Path("data/acquisition_verified_d22e9c4/acquisition_bundle.json"))
    parser.add_argument("--evidence-dir", type=Path, default=Path("data/preparation_verified"))
    parser.add_argument("--reviewer", type=str, default="coverage-reviewer")
    parser.add_argument("--recorded-on", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    print(run_preparation(args.bundle_path, args.evidence_dir, args.reviewer, args.recorded_on))


if __name__ == "__main__":
    main()
