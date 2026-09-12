"""Immutable table and manifest exports."""

import json
from hashlib import sha256
from pathlib import Path

import pandas as pd


def write_table(records: pd.DataFrame, path: Path) -> str:
    """Write a stable parquet table and return its SHA-256 hash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    records.to_parquet(path, engine="pyarrow", compression="zstd", index=False)
    return sha256(path.read_bytes()).hexdigest()


def write_manifest(payload: dict, path: Path) -> str:
    """Write canonical JSON and return its SHA-256 hash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n")
    return sha256(path.read_bytes()).hexdigest()
