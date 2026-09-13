"""Serve the local recommendation API."""

import argparse
from pathlib import Path

import uvicorn

from poweshift_backend.api.app import create_app
from poweshift_backend.runtime.supervisor import RunSupervisor


def main() -> None:
    """Run the API on a local interface by default."""
    parser = argparse.ArgumentParser()
    parser.add_argument("registry", type=Path)
    parser.add_argument("outputs", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--diagnostic-reports", type=Path)
    args = parser.parse_args()
    app = create_app(
        RunSupervisor(args.registry, args.outputs),
        diagnostic_report_root=args.diagnostic_reports,
    )
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
