"""Run the frozen physical-policy preflight or smoke artifact."""

import sys
from pathlib import Path

from poweshift_backend.policy.run import run_policy_training


def main() -> None:
    """Use fixed artifact locations for the requested mode."""
    if len(sys.argv) != 2 or sys.argv[1] not in {"preflight", "smoke"}:
        raise SystemExit("usage: run_first_real_ppo.py {preflight|smoke}")
    mode = sys.argv[1]
    root = Path(__file__).resolve().parent
    report = run_policy_training(root / f"{mode}_artifact.json", root / "training_source_binding.json", root / "runs" / mode, mode=mode)
    raise SystemExit(0 if report.status == "passed" else 1)


if __name__ == "__main__":
    main()
