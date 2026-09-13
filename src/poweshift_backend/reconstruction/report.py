"""Write immutable reconstruction artifacts with source and settings hashes."""

import json
from hashlib import sha256
from pathlib import Path

from poweshift_backend.contracts.reconstruction import EvidencePin, EvidenceReport, FitReport


def write_fit_report(report: FitReport, output_dir: Path) -> EvidencePin:
    """Write a fit report once and return its immutable evidence pin."""
    path = output_dir / "fit_report.json"
    _write_once(path, report.model_dump(mode="json"))
    return EvidencePin(path=str(path), sha256=_sha256(path))


def write_settings(settings: dict[str, object], output_dir: Path) -> EvidencePin:
    """Write frozen numerical settings before they are referenced by a fit."""
    path = output_dir / "settings.json"
    _write_once(path, settings)
    return EvidencePin(path=str(path), sha256=_sha256(path))


def write_evidence(report: EvidenceReport, output_dir: Path) -> Path:
    """Write the final held-out report once outside the source evidence tree."""
    path = output_dir / "heldout_evidence.json"
    _write_once(path, report.model_dump(mode="json"))
    return path


def _write_once(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"immutable artifact already exists: {path}")
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()
