import json

import pytest

from poweshift_backend.representation.weekend_run import run_weekend_smoke


def test_runner_persists_missing_artifact_refusal(tmp_path) -> None:
    with pytest.raises(ValueError, match="verified batch"):
        run_weekend_smoke(tmp_path / "missing.pt", tmp_path / "binding.json", None, tmp_path / "out", mode="preflight")

    report = json.loads((tmp_path / "out" / "preflight.json").read_text())
    assert report["status"] == "failed"
    assert report["steps"] == 0
