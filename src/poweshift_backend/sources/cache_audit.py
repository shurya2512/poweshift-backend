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
    files = sorted(cache_dir.glob(f"**/{session_date}_Day_{day_number}/*.ff1pkl"))
    destination.mkdir(parents=True, exist_ok=True)
    result = {}
    for source in files:
        target = destination / source.name
        digest = sha256(source.read_bytes()).hexdigest()
        if target.exists() and sha256(target.read_bytes()).hexdigest() != digest:
            raise FileExistsError(f"immutable source snapshot differs: {target}")
        if not target.exists():
            shutil.copyfile(source, target)
        result[source.name] = digest
    return result
