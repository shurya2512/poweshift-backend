"""Read-only inventory for FastF1 parser caches."""

from hashlib import sha256
from pathlib import Path
import shutil


def cache_inventory(cache_dir: Path) -> dict[str, str]:
    """Return SHA-256 hashes without deserializing cache entries."""
    return {
        str(path.relative_to(cache_dir)): sha256(path.read_bytes()).hexdigest()
        for path in sorted(cache_dir.rglob("*.ff1pkl"))
    }


def snapshot_session(cache_dir: Path, session_date: str, day_number: int, destination: Path) -> dict[str, str]:
    """Seal the parser-cache records used for one testing day."""
    directories = list(cache_dir.glob(f"**/{session_date}_Day_{day_number}"))
    if len(directories) != 1:
        raise ValueError("expected exactly one parser-cache session directory")
    sources = sorted(directories[0].glob("*.ff1pkl"))
    if not sources:
        raise ValueError("parser-cache session directory is empty")
    result = {source.name: sha256(source.read_bytes()).hexdigest() for source in sources}
    if destination.exists():
        existing = {path.name: sha256(path.read_bytes()).hexdigest() for path in destination.glob("*.ff1pkl")}
        if existing != result:
            raise FileExistsError(f"immutable source snapshot differs: {destination}")
        return result
    destination.mkdir(parents=True)
    for source in sources:
        shutil.copyfile(source, destination / source.name)
    return result
