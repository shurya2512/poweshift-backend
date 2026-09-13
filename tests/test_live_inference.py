from hashlib import sha256
import json

import pytest

from poweshift_backend.contracts.runtime import ObservationFrame
from poweshift_backend.runtime.artifacts import ArtifactRegistry
from poweshift_backend.runtime.live import LivePolicySession
from test_weekend_inference import _write_inputs


def _registered(tmp_path):
    _registry, manifest, root = _write_inputs(tmp_path)
    manifest_path = root / "selection-run.json"
    manifest_path.write_text(manifest.model_dump_json())
    registry_path = root / "registry.json"
    payload = json.loads(registry_path.read_text())
    payload["artifacts"][manifest.run_id] = {
        "kind": "run_manifest",
        "path": manifest_path.name,
        "sha256": sha256(manifest_path.read_bytes()).hexdigest(),
    }
    registry_path.write_text(json.dumps(payload, sort_keys=True))
    return ArtifactRegistry.load(registry_path)


def _frame(sequence: int, observed_at_s: float) -> ObservationFrame:
    return ObservationFrame(
        sequence=sequence,
        observed_at_s=observed_at_s,
        values=(20.0, 4_000_000.0),
        feature_mask=(True, True),
        action_mask=(True, True, True, True),
        deployment_available=True,
    )


def test_live_policy_holds_four_hz_input_for_five_hz_decisions(tmp_path) -> None:
    session = LivePolicySession.from_registered_run(_registered(tmp_path), "selection-run")
    session.ingest(_frame(0, 0.0))

    first = session.decide()
    second = session.decide()
    session.ingest(_frame(1, 0.25))
    third = session.decide()

    assert (first.decision_sequence, second.decision_sequence, third.decision_sequence) == (0, 1, 2)
    assert (first.source_sequence, second.source_sequence, third.source_sequence) == (0, 0, 1)
    assert first.held_source_frame is False
    assert second.held_source_frame is True
    assert third.held_source_frame is False
    assert first.input_hz == 4.0
    assert first.decision_hz == 5.0
    assert first.partition == "selection"


def test_live_policy_rejects_non_four_hz_or_out_of_order_input(tmp_path) -> None:
    session = LivePolicySession.from_registered_run(_registered(tmp_path), "selection-run")
    session.ingest(_frame(0, 0.0))
    with pytest.raises(ValueError, match="4 Hz"):
        session.ingest(_frame(1, 0.2))
    with pytest.raises(ValueError, match="next sequence"):
        session.ingest(_frame(2, 0.5))
