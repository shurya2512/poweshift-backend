"""Read only approved Phase 2 inputs and restore their physical timelines."""

import json
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path

import numpy as np
import pandas as pd

from poweshift_backend.contracts.preparation import CoverageDisposition, PreprocessingSpec
from poweshift_backend.contracts.reconstruction import EvidencePin, Phase3Admission, ReconstructionInputManifest, SupportState

_SERIALIZED_FLOAT_TOLERANCE = 1e-9


@dataclass(frozen=True)
class TelemetryChunk:
    """One physical-time telemetry chunk with native speed values."""

    session_key: str
    entry: str
    run_id: str
    chunk_index: int
    split: str
    time_s: np.ndarray
    speed_ms: np.ndarray
    controls: dict[str, np.ndarray]
    valid: dict[str, np.ndarray]
    tyre: dict[str, object]
    source_rows: tuple[str, ...]


@dataclass(frozen=True)
class Phase3Inputs:
    """Approved chunks and verified continuations for a later fit or replay."""

    manifest: ReconstructionInputManifest
    chunks: tuple[TelemetryChunk, ...]
    continuations: tuple[tuple[str, str, str, int, int], ...]
    alignment_support: SupportState


def load_admitted_inputs(
    evidence_manifest_path: Path, admission_path: Path, session_keys: set[str] | None = None
) -> Phase3Inputs:
    """Load selected sessions only after every required approval and hash agrees."""
    evidence = _read_json(evidence_manifest_path)
    admission = Phase3Admission.model_validate(_read_json(admission_path))
    _validate_admission(evidence_manifest_path, evidence, admission)
    manifest = _build_manifest(evidence_manifest_path, evidence, admission)

    chunks = []
    sessions = evidence.get("sessions")
    if not isinstance(sessions, list):
        raise ValueError("phase 2 evidence has no sessions")
    for session in sessions:
        session_key = _require_string(session, "session_key")
        if session_keys is not None and session_key not in session_keys:
            continue
        chunks.extend(_read_session_chunks(evidence_manifest_path, session, evidence["split_manifest"], evidence))
    if session_keys is not None and {chunk.session_key for chunk in chunks} != session_keys:
        raise ValueError("requested session is absent from approved evidence")
    ordered = tuple(sorted(chunks, key=lambda chunk: (chunk.session_key, chunk.entry, chunk.run_id, chunk.chunk_index)))
    return Phase3Inputs(
        manifest=manifest,
        chunks=ordered,
        continuations=_verified_continuations(ordered, _approved_gap_limit(evidence_manifest_path, evidence)),
        alignment_support=SupportState.MISSING,
    )


def _validate_admission(evidence_path: Path, evidence: dict, admission: Phase3Admission) -> None:
    if _sha256(evidence_path) != admission.phase2_evidence_manifest_sha256:
        raise ValueError("phase 2 evidence does not match the approval")
    coverage = evidence.get("coverage_disposition", {})
    preprocessing = evidence.get("preprocessing_spec", {})
    if coverage.get("sha256") != admission.coverage_disposition_sha256:
        raise ValueError("coverage disposition does not match the approval")
    if preprocessing.get("sha256") != admission.preprocessing_spec_sha256:
        raise ValueError("preprocessing specification does not match the approval")
    if evidence.get("split_manifest") != admission.split_manifest:
        raise ValueError("split manifest does not match the approval")
    if _effective_manifest_sha256(admission) != admission.effective_manifest_sha256:
        raise ValueError("effective manifest does not match the approval")
    _validate_phase2_decisions(evidence_path, evidence, admission)


def _validate_phase2_decisions(evidence_path: Path, evidence: dict, admission: Phase3Admission) -> None:
    coverage_path = _resolve(evidence_path, evidence["coverage_disposition"]["path"])
    coverage = CoverageDisposition.model_validate_json(coverage_path.read_text())
    if coverage.bundle_sha256 != _sha256(_resolve(evidence_path, _require_string(evidence, "bundle_path"))):
        raise ValueError("coverage disposition is not bound to the acquisition bundle")
    preprocessing_path = _resolve(evidence_path, evidence["preprocessing_spec"]["path"])
    preprocessing = PreprocessingSpec.model_validate_json(preprocessing_path.read_text())
    approved = admission.approved_defaults
    if not all(
        np.isclose(actual, expected, rtol=0.0, atol=_SERIALIZED_FLOAT_TOLERANCE)
        for actual, expected in (
            (preprocessing.gap_limit_s, approved.gap_limit_s),
            (preprocessing.smoothing_limit_s, approved.smoothing_limit_s),
            (preprocessing.window_limit_s, approved.window_limit_s),
        )
    ):
        raise ValueError("preprocessing limits do not match the approved defaults")


def _build_manifest(evidence_path: Path, evidence: dict, admission: Phase3Admission) -> ReconstructionInputManifest:
    coverage = evidence["coverage_disposition"]
    preprocessing = evidence["preprocessing_spec"]
    profile = evidence["track_profile"]
    evidence_pin = EvidencePin(path=str(evidence_path), sha256=_sha256(evidence_path))
    coverage_pin = _verified_pin(evidence_path, _manifest_pin(coverage))
    preprocessing_pin = _verified_pin(evidence_path, _manifest_pin(preprocessing))
    profile_pin = _verified_pin(evidence_path, _manifest_pin(profile))
    _verify_profile_table(evidence_path, profile_pin.path)
    return ReconstructionInputManifest(
        phase2_evidence=evidence_pin,
        coverage_disposition=coverage_pin,
        preprocessing_spec=preprocessing_pin,
        track_profile=profile_pin,
        split_manifest=admission.split_manifest,
        effective_manifest_sha256=admission.effective_manifest_sha256,
    )


def _read_session_chunks(evidence_path: Path, session: dict, split_manifest: dict, evidence: dict) -> list[TelemetryChunk]:
    session_key = _require_string(session, "session_key")
    if session.get("identity", {}).get("date") != session_key:
        raise ValueError("session identity does not match its session key")
    coverage = _read_json(_resolve(evidence_path, evidence["coverage_disposition"]["path"]))
    if coverage.get("admitted_entries", {}).get(session_key) != session.get("admitted_entries"):
        raise ValueError("session entries do not match the coverage disposition")
    package_pin = _verified_pin(evidence_path, _manifest_pin(session["stint_packages"]))
    package_manifest = _read_json(_resolve(evidence_path, package_pin.path))
    if package_manifest.get("session_key") != session_key:
        raise ValueError("stint package manifest names a different session")
    table_path = _resolve(evidence_path, _require_string(package_manifest, "table_path"))
    if _sha256(table_path) != _require_string(package_manifest, "table_sha256"):
        raise ValueError("stint package table does not match its manifest")
    table = pd.read_parquet(table_path)
    packages = package_manifest.get("packages")
    if not isinstance(packages, list):
        raise ValueError("stint package manifest has no packages")
    rows_by_package = {package_id: rows.sort_values("row_index") for package_id, rows in table.groupby("package_id")}
    offsets: dict[tuple[str, str], int] = {}
    chunks = []
    for package in sorted(packages, key=lambda item: (item["entry"], item["run_id"], item["chunk_index"])):
        source_date = _require_string(package.get("provenance", {}).get("source_identity", {}), "date")
        if source_date != session_key:
            raise ValueError("package source date does not match its session")
        expected_split = _split_for_source_date(source_date, split_manifest)
        if package.get("split") != expected_split:
            raise ValueError("package split disagrees with its source date")
        if package.get("entry") not in session["admitted_entries"]:
            raise ValueError("package entry is not admitted")
        package_id = _require_string(package, "package_id")
        if package_id not in rows_by_package:
            raise ValueError("package table has no declared package rows")
        key = (_require_string(package, "entry"), _require_string(package, "run_id"))
        source_rows = tuple(str(value) for value in package.get("provenance", {}).get("source_rows", ()))
        row_count = int((~rows_by_package[package_id]["padding"]).sum())
        offset = offsets.get(key, 0)
        chunk_source_rows = source_rows[offset : offset + row_count] if source_rows else ()
        if source_rows and len(chunk_source_rows) != row_count:
            raise ValueError("package source rows cannot support this chunk")
        offsets[key] = offset + row_count
        chunks.append(_chunk_from_package(rows_by_package[package_id], package, session_key, chunk_source_rows))
    return chunks


def _chunk_from_package(rows: pd.DataFrame, package: dict, session_key: str, source_rows: tuple[str, ...]) -> TelemetryChunk:
    required_features = {"speed_ms", "throttle_pct", "brake", "n_gear"}
    if not required_features.issubset(package.get("feature_names", [])):
        raise ValueError("package does not declare physical speed and controls")
    required = {"dt_s", "padding"} | {f"X__{feature}" for feature in required_features} | {
        f"valid__{feature}" for feature in required_features
    }
    if not required.issubset(rows.columns):
        raise ValueError("package table is missing physical speed columns")
    rows = rows.loc[~rows["padding"]]
    if rows.empty or not rows["valid__speed_ms"].all():
        raise ValueError("physical speed_ms is unavailable")
    dt_s = rows["dt_s"].to_numpy(dtype=np.float64)
    if dt_s[0] != 0.0 or np.any(dt_s[1:] <= 0.0):
        raise ValueError("chunk intervals are not physical")
    time_s = float(package["start_time_s"]) + np.cumsum(dt_s)
    if not np.isclose(time_s[-1], float(package["end_time_s"])):
        raise ValueError("chunk anchor and intervals disagree with its end time")
    speed_ms = rows["X__speed_ms"].to_numpy(dtype=np.float64)
    if not np.isfinite(speed_ms).all():
        raise ValueError("physical speed_ms must be finite")
    controls = {feature: rows[f"X__{feature}"].to_numpy(dtype=np.float64) for feature in ("throttle_pct", "brake", "n_gear")}
    valid = {feature: rows[f"valid__{feature}"].to_numpy(dtype=np.bool_) for feature in required_features}
    time_s.setflags(write=False)
    speed_ms.setflags(write=False)
    for values in (*controls.values(), *valid.values()):
        values.setflags(write=False)
    return TelemetryChunk(
        session_key=session_key,
        entry=_require_string(package, "entry"),
        run_id=_require_string(package, "run_id"),
        chunk_index=int(package["chunk_index"]),
        split=_require_string(package, "split"),
        time_s=time_s,
        speed_ms=speed_ms,
        controls=controls,
        valid=valid,
        tyre=dict(package.get("tyre", {})),
        source_rows=source_rows,
    )


def _verified_continuations(
    chunks: tuple[TelemetryChunk, ...], gap_limit_s: float
) -> tuple[tuple[str, str, str, int, int], ...]:
    continuations = []
    for earlier, later in zip(chunks, chunks[1:]):
        same_run = (earlier.session_key, earlier.entry, earlier.run_id) == (later.session_key, later.entry, later.run_id)
        gap_s = later.time_s[0] - earlier.time_s[-1]
        if same_run and later.chunk_index == earlier.chunk_index + 1 and 0.0 < gap_s <= gap_limit_s:
            continuations.append((earlier.session_key, earlier.entry, earlier.run_id, earlier.chunk_index, later.chunk_index))
    return tuple(continuations)


def _split_for_source_date(source_date: str, split_manifest: dict) -> str:
    value = date.fromisoformat(source_date)
    if value in (date(2026, 2, 11), date(2026, 2, 12), date(2026, 2, 13)):
        return "training"
    if source_date == split_manifest.get("selection"):
        return "selection"
    if source_date in split_manifest.get("final_evaluation", []):
        return "final_evaluation"
    raise ValueError("source date is outside the approved split")


def _effective_manifest_sha256(admission: Phase3Admission) -> str:
    value = {
        "coverage_disposition_sha256": admission.coverage_disposition_sha256,
        "preprocessing_spec_sha256": admission.preprocessing_spec_sha256,
        "phase2_evidence_manifest_sha256": admission.phase2_evidence_manifest_sha256,
        "split_manifest": admission.split_manifest,
    }
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _approved_gap_limit(evidence_path: Path, evidence: dict) -> float:
    path = _resolve(evidence_path, evidence["preprocessing_spec"]["path"])
    return PreprocessingSpec.model_validate_json(path.read_text()).gap_limit_s


def _manifest_pin(record: dict) -> dict:
    return {"path": record.get("manifest_path", record.get("path")), "sha256": record.get("manifest_sha256", record.get("sha256"))}


def _verified_pin(evidence_path: Path, record: dict) -> EvidencePin:
    pin = EvidencePin.model_validate(record)
    if _sha256(_resolve(evidence_path, pin.path)) != pin.sha256:
        raise ValueError("pinned artifact does not match its manifest")
    return pin


def _verify_profile_table(evidence_path: Path, profile_manifest_path: str) -> None:
    profile = _read_json(_resolve(evidence_path, profile_manifest_path))
    table_path = _resolve(evidence_path, _require_string(profile, "table_path"))
    if _sha256(table_path) != _require_string(profile, "table_sha256"):
        raise ValueError("track profile table does not match its manifest")


def _resolve(evidence_path: Path, path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    for parent in (evidence_path.parent, *evidence_path.parents):
        resolved = parent / candidate
        if resolved.exists():
            return resolved
    return evidence_path.parent / candidate


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("manifest must be a JSON object")
    return value


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _require_string(record: dict, key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str):
        raise ValueError(f"manifest is missing {key}")
    return value
