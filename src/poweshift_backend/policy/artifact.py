"""Immutable source-bound policy training artifacts."""

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Literal

from poweshift_backend.contracts.policy_training import PolicyTrainingManifest, PpoRunConfig


@dataclass(frozen=True)
class TrainingScenarioCandidate:
    """A source-supported episode candidate without outcome metrics."""

    scenario_id: str
    starts_at_utc: str
    source_partition: Literal["training"]
    source_sha256: str
    compatible: bool


@dataclass(frozen=True)
class PolicyTrainingArtifact:
    """Canonical training manifest and selected scenario."""

    artifact_sha256: str
    manifest: PolicyTrainingManifest
    scenario_id: str


def manifest_from_dict(payload: dict[str, object]) -> PolicyTrainingManifest:
    """Restore a manifest from primitive JSON values."""
    values = dict(payload)
    values["config"] = PpoRunConfig(**values["config"])
    return PolicyTrainingManifest(**values)


def artifact_payload(manifest: PolicyTrainingManifest, scenario_id: str) -> dict[str, object]:
    """Return the canonical artifact payload before its hash."""
    return {"manifest": asdict(manifest), "scenario_id": scenario_id}


def artifact_sha256(manifest: PolicyTrainingManifest, scenario_id: str) -> str:
    """Hash every frozen manifest field and scenario identity."""
    encoded = json.dumps(artifact_payload(manifest, scenario_id), sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def load_policy_training_artifact(path: Path) -> PolicyTrainingArtifact:
    """Load and verify a primitive JSON artifact."""
    payload = json.loads(path.read_text())
    manifest = manifest_from_dict(payload["manifest"])
    artifact = PolicyTrainingArtifact(payload["artifact_sha256"], manifest, payload["scenario_id"])
    if artifact.artifact_sha256 != artifact_sha256(manifest, artifact.scenario_id):
        raise ValueError("policy training artifact hash is invalid")
    return artifact

def build_policy_training_artifact(
    candidates: tuple[TrainingScenarioCandidate, ...],
    manifest: PolicyTrainingManifest,
    output: Path,
) -> PolicyTrainingArtifact:
    """Select the earliest unique compatible training episode."""
    if output.exists():
        raise FileExistsError(f"policy training artifact already exists: {output}")
    compatible = tuple(
        candidate for candidate in candidates
        if candidate.compatible and candidate.source_partition == "training" and candidate.source_sha256 == manifest.training_source_sha256
    )
    if not compatible:
        raise ValueError("no compatible training scenario candidate")
    ordered = sorted(compatible, key=lambda candidate: datetime.fromisoformat(candidate.starts_at_utc))
    first_time = datetime.fromisoformat(ordered[0].starts_at_utc)
    if sum(datetime.fromisoformat(candidate.starts_at_utc) == first_time for candidate in ordered) != 1:
        raise ValueError("earliest compatible training scenario is ambiguous")
    selected = ordered[0]
    if selected.scenario_id != manifest.scenario_id:
        raise ValueError("selected scenario does not match the training manifest")
    digest = artifact_sha256(manifest, selected.scenario_id)
    artifact = PolicyTrainingArtifact(digest, manifest, selected.scenario_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"artifact_sha256": digest, **artifact_payload(manifest, selected.scenario_id)}, sort_keys=True, separators=(",", ":")))
    return artifact
