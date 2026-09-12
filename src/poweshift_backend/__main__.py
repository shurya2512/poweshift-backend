"""Run the Phase 1 acquisition job."""

import argparse
from pathlib import Path

from poweshift_backend.data.acquisition import acquire_all


def main() -> None:
    """Acquire all permitted Bahrain test days."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, default=Path("data/phase1_fastf1_cache"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/acquisition"))
    args = parser.parse_args()
    print(acquire_all(args.cache_dir, args.output_dir))


if __name__ == "__main__":
    main()
