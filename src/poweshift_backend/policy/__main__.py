"""Command line entry point for source-bound policy training."""

import argparse
from pathlib import Path

from poweshift_backend.policy.run import run_policy_training


def main() -> None:
    """Run one frozen policy training artifact."""
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "smoke"))
    parser.add_argument("artifact", type=Path)
    parser.add_argument("source_binding", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = run_policy_training(args.artifact, args.source_binding, args.output, mode=args.mode)
    raise SystemExit(0 if report.status == "passed" else 1)


if __name__ == "__main__":
    main()
