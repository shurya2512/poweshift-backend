"""Guard that targets and pit-source records never mix into reconstruction inputs."""

from pathlib import Path

_TARGET_MARKER = "target"
_PIT_MARKER = "pit_"


def check_protected_directories(reconstruction_inputs_dir: Path, targets_dir: Path, pit_dir: Path) -> None:
    """Fail if a target or pit artifact is under reconstruction inputs, or a pit artifact is under targets."""
    _forbid(reconstruction_inputs_dir, (_TARGET_MARKER, _PIT_MARKER), "reconstruction-input root")
    _forbid(targets_dir, (_PIT_MARKER,), "targets root")


def _forbid(root: Path, markers: tuple[str, ...], context: str) -> None:
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        name = path.name.lower()
        for marker in markers:
            if marker in name:
                raise ValueError(f"{context} must not contain a {marker.strip('_')} artifact: {path}")
