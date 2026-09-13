"""Promote direct race profiles under an explicit provisional evidence policy."""

from hashlib import sha256
import json
from math import isfinite
from pathlib import Path


DEFAULT_LIMIT = 0.06


def promote_provisional_race_profiles(
    report_path: Path,
    profiles_path: Path,
    retention_paths: tuple[Path, ...],
    output_path: Path,
    *,
    progress_limit: float = DEFAULT_LIMIT,
    crossing_limit: float = DEFAULT_LIMIT,
) -> dict[str, object]:
    """Activate profiles that meet the declared relaxed motion policy."""
    report = _read_object(report_path)
    source_profiles = _read_object(profiles_path)
    if report.get("status") != "passed":
        raise ValueError("race training report did not pass")
    if not 0.0 < progress_limit <= DEFAULT_LIMIT or not 0.0 < crossing_limit <= DEFAULT_LIMIT:
        raise ValueError("provisional motion limits cannot exceed six percent")
    _check_checkpoint_binding(report, source_profiles)
    metrics = report.get("error_metrics")
    if not isinstance(metrics, dict):
        raise ValueError("race training report lacks error metrics")
    progress_error = _finite_metric(metrics, "progress_normalized_rmse")
    crossing_error = _finite_metric(metrics, "crossing_normalized_rmse")
    if progress_error > progress_limit:
        raise ValueError("profile exceeds the provisional progress motion limit")
    if crossing_error > crossing_limit:
        raise ValueError("profile exceeds the provisional crossing motion limit")
    profiles = source_profiles.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("profile artifact has no car profiles")

    checkpoint_sha256 = str(report["checkpoint_sha256"])
    policy = {
        "progress_normalized_rmse_limit": progress_limit,
        "crossing_normalized_rmse_limit": crossing_limit,
        "speed_gate_waived": True,
        "reason": "speed error remains coupled to zero-curvature and estimated brake priors",
    }
    evidence = {
        "training_report": _bound_file(report_path),
        "source_profiles": _bound_file(profiles_path),
        "retention_reports": [_bound_file(path) for path in retention_paths],
    }
    limitations = [
        "race windows restart from observed state and do not prove continuous full-race motion",
        "route curvature is zero in the diagnostic adapter",
        "Boolean brake-on is estimated as 0.2 demand and throttle is clamped",
        "speed motion error is recorded but waived by this provisional policy",
        "protected validation and test races remain unevaluated",
    ]
    active_profiles = {
        str(entry): {
            "active": True,
            "version": 1,
            "profile_id": _identifier(
                {"checkpoint_sha256": checkpoint_sha256, "entry": str(entry), "profile": profile}
            ),
            "checkpoint_sha256": checkpoint_sha256,
            "profile": profile,
        }
        for entry, profile in sorted(profiles.items(), key=lambda item: int(item[0]))
    }
    admission_seed = {
        "active_profile_ids": {entry: value["profile_id"] for entry, value in active_profiles.items()},
        "evidence": evidence,
        "policy": policy,
        "limitations": limitations,
    }
    registry = {
        "artifact_kind": "provisional_phase4_profile_registry_v1",
        "status": "promoted_provisional",
        "compatible_with_downstream_contract": True,
        "physics_admission": False,
        "profile_admission_id": _identifier(admission_seed),
        "checkpoint": report["checkpoint"],
        "checkpoint_sha256": checkpoint_sha256,
        "policy": policy,
        "accepted_metrics": {
            "progress_normalized_rmse": progress_error,
            "crossing_normalized_rmse": crossing_error,
            "speed_normalized_rmse": _finite_metric(metrics, "speed_normalized_rmse"),
            "progress_rank_accuracy": _finite_metric(metrics, "progress_rank_accuracy"),
            "signed_gap_mae_s": _finite_metric(metrics, "signed_gap_mae_s"),
        },
        "limitations": limitations,
        "evidence": evidence,
        "active_profiles": active_profiles,
    }
    _write_immutable(output_path, registry)
    return registry


def _check_checkpoint_binding(report: dict[str, object], profiles: dict[str, object]) -> None:
    checkpoint_path = Path(str(report.get("checkpoint", "")))
    expected = str(report.get("checkpoint_sha256", ""))
    if not checkpoint_path.is_file() or sha256(checkpoint_path.read_bytes()).hexdigest() != expected:
        raise ValueError("race report checkpoint binding is invalid")
    if profiles.get("checkpoint") != str(checkpoint_path) or profiles.get("checkpoint_sha256") != expected:
        raise ValueError("profile checkpoint binding differs from the race report")


def _finite_metric(metrics: dict[str, object], name: str) -> float:
    value = metrics.get(name)
    if not isinstance(value, (int, float)) or not isfinite(float(value)) or float(value) < 0.0:
        raise ValueError(f"promotion metric {name} must be finite and nonnegative")
    return float(value)


def _read_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"artifact must contain an object: {path}")
    return value


def _bound_file(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}


def _identifier(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode()).hexdigest()


def _write_immutable(path: Path, value: dict[str, object]) -> None:
    content = json.dumps(value, sort_keys=True, indent=2) + "\n"
    if path.exists() and path.read_text() != content:
        raise FileExistsError(f"immutable promotion differs: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
