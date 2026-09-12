import sys
from pathlib import Path

from poweshift_backend.representation import __main__ as cli


class _Audit:
    def model_dump_json(self) -> str:
        return '{"status":"blocked"}'


def test_weekend_audit_command_does_not_start_the_historical_training_path(monkeypatch, capsys, tmp_path: Path) -> None:
    captured: dict[str, Path | None] = {}

    def audit(cache_root: Path, destination: Path, race_manifests: tuple[Path, ...]) -> _Audit:
        captured.update(cache_root=cache_root, destination=destination, race_manifests=race_manifests)
        return _Audit()

    monkeypatch.setattr(cli, "audit_weekend_cache", audit)
    monkeypatch.setattr(sys, "argv", ["poweshift", "--weekend-audit", "--weekend-cache", str(tmp_path / "cache"), "--audit-output", str(tmp_path / "audit.json")])

    cli.main()

    assert captured["cache_root"] == tmp_path / "cache"
    assert captured["destination"] == tmp_path / "audit.json"
    assert len(captured["race_manifests"]) == 10
    assert capsys.readouterr().out == '{"status":"blocked"}\n'
