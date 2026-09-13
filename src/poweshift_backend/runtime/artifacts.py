"""Server-owned registry for immutable runtime artifacts."""

from hashlib import sha256
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from poweshift_backend.contracts.acquisition import StrictModel


class RegisteredArtifact(StrictModel):
    """One relative, hashed artifact known to the local server."""

    kind: Literal["policy_checkpoint", "weekend_source", "protected_target", "run_manifest", "news_prior"]
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def require_relative_path(cls, value: str) -> str:
        """Keep every artifact inside the registry root."""
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("registered artifact path must stay inside the registry root")
        return value


class ArtifactRegistry:
    """Resolve registered IDs without accepting client paths."""

    def __init__(self, root: Path, artifacts: dict[str, RegisteredArtifact]) -> None:
        self.root = root.resolve()
        self.artifacts = artifacts

    @classmethod
    def load(cls, path: Path) -> "ArtifactRegistry":
        """Load a strict server-owned registry file."""
        payload = json.loads(path.read_text())
        raw = payload.get("artifacts")
        if not isinstance(raw, dict) or not raw:
            raise ValueError("artifact registry is empty")
        artifacts = {name: RegisteredArtifact.model_validate(value) for name, value in raw.items()}
        return cls(path.parent, artifacts)

    def reference(self, artifact_id: str, kind: str) -> RegisteredArtifact:
        """Return metadata without opening the registered artifact."""
        try:
            artifact = self.artifacts[artifact_id]
        except KeyError as error:
            raise KeyError(f"artifact is not registered: {artifact_id}") from error
        if artifact.kind != kind:
            raise ValueError(f"artifact {artifact_id} is not registered as {kind}")
        return artifact

    def resolve(self, artifact_id: str, kind: str) -> Path:
        """Resolve and verify one registered artifact."""
        artifact = self.reference(artifact_id, kind)
        relative = Path(artifact.path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("registered artifact path must stay inside the registry root")
        path = (self.root / relative).resolve()
        if path.parent != self.root and self.root not in path.parents:
            raise ValueError("registered artifact path escapes the registry root")
        if not path.is_file():
            raise FileNotFoundError(f"registered artifact is missing: {artifact_id}")
        if sha256(path.read_bytes()).hexdigest() != artifact.sha256:
            raise ValueError(f"registered artifact hash differs: {artifact_id}")
        return path
