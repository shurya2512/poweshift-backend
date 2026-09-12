"""Read-only inventory for FastF1 parser caches."""

from hashlib import sha256
from pathlib import Path


def cache_inventory(cache_dir: Path) -> dict[str, str]:
    """Return SHA-256 hashes without deserializing cache entries."""
    return {
        str(path.relative_to(cache_dir)): sha256(path.read_bytes()).hexdigest()
        for path in sorted(cache_dir.rglob("*.ff1pkl"))
    }
