"""Run or score one registered protected weekend."""

import argparse
from pathlib import Path

from poweshift_backend.contracts.runtime import WeekendRunManifest
from poweshift_backend.evaluation.weekend import score_weekend_inference
from poweshift_backend.runtime.artifacts import ArtifactRegistry
from poweshift_backend.runtime.weekend import run_weekend_inference


def main() -> None:
    """Execute inference or separate descriptive scoring."""
    parser = argparse.ArgumentParser()
    parser.add_argument("registry", type=Path)
    parser.add_argument("run_id")
    subparsers = parser.add_subparsers(dest="command", required=True)
    infer = subparsers.add_parser("infer")
    infer.add_argument("output", type=Path)
    score = subparsers.add_parser("score")
    score.add_argument("run_output", type=Path)
    score.add_argument("output", type=Path)
    args = parser.parse_args()
    registry = ArtifactRegistry.load(args.registry)
    manifest = WeekendRunManifest.model_validate_json(registry.resolve(args.run_id, "run_manifest").read_text())
    if args.command == "infer":
        print(run_weekend_inference(manifest, registry, args.output).model_dump_json())
    else:
        print(score_weekend_inference(manifest, registry, args.run_output, args.output).model_dump_json())


if __name__ == "__main__":
    main()
