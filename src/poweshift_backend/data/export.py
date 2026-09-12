"""Immutable table and manifest exports."""

import json
from hashlib import sha256
from pathlib import Path

import pandas as pd


def write_table(records: pd.DataFrame, path: Path) -> str:
    """Write a stable parquet table and return its SHA-256 hash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate = path.with_suffix(path.suffix + ".candidate")
    records.to_parquet(candidate, engine="pyarrow", compression="zstd", index=False)
    digest = sha256(candidate.read_bytes()).hexdigest()
    if path.exists() and sha256(path.read_bytes()).hexdigest() != digest:
        candidate.unlink()
        raise FileExistsError(f"immutable export differs: {path}")
    candidate.replace(path)
    return digest


def write_manifest(payload: dict, path: Path) -> str:
    """Write canonical JSON and return its SHA-256 hash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    digest = sha256(content.encode()).hexdigest()
    if path.exists() and sha256(path.read_bytes()).hexdigest() != digest:
        raise FileExistsError(f"immutable manifest differs: {path}")
    path.write_text(content)
    return digest
