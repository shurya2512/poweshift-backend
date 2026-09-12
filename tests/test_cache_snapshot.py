from pathlib import Path

import pytest

from poweshift_backend.sources.cache_audit import snapshot_session


def test_snapshot_refuses_added_source_without_mutating_sealed_files(tmp_path: Path) -> None:
    source = tmp_path / "cache" / "2026" / "event" / "2026-02-11_Day_1"
    source.mkdir(parents=True)
    (source / "a.ff1pkl").write_bytes(b"a")
    sealed = tmp_path / "sealed"
    snapshot_session(tmp_path / "cache", "2026-02-11", 1, sealed)
    (source / "b.ff1pkl").write_bytes(b"b")

    with pytest.raises(FileExistsError):
        snapshot_session(tmp_path / "cache", "2026-02-11", 1, sealed)

    assert [path.name for path in sealed.iterdir()] == ["a.ff1pkl"]


def test_snapshot_rejects_missing_or_ambiguous_session_directories(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        snapshot_session(tmp_path, "2026-02-11", 1, tmp_path / "sealed")
