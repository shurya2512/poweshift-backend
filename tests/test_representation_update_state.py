import numpy as np
import pytest

from poweshift_backend.representation.update import UpdateQuality, UpdateState, apply_quality_aware_update, assess_update_quality, session_reset_reason


def test_quality_aware_update_withholds_missing_or_low_quality_prefixes() -> None:
    state = UpdateState("model-a", "transform-a", np.zeros(4, dtype=np.float32))

    missing = apply_quality_aware_update(state, np.ones(4, dtype=np.float32), UpdateQuality("missing", 0.0), "model-a", "transform-a")
    low = apply_quality_aware_update(state, np.ones(4, dtype=np.float32), UpdateQuality("low", 0.2), "model-a", "transform-a")

    assert missing.withheld_reason == "missing"
    assert low.withheld_reason == "low_quality"
    assert missing.state == state


def test_update_refuses_incompatible_model_or_transform_reset() -> None:
    state = UpdateState("model-a", "transform-a", np.zeros(4, dtype=np.float32))

    with pytest.raises(ValueError, match="incompatible"):
        apply_quality_aware_update(state, np.ones(4, dtype=np.float32), UpdateQuality("accepted", 1.0), "model-b", "transform-a")


def test_quality_aware_reset_keeps_evidence_and_requires_accepted_quality() -> None:
    state = UpdateState("model-a", "transform-a", np.ones(4, dtype=np.float32), update_count=3)
    result = apply_quality_aware_update(state, np.zeros(4, dtype=np.float32), UpdateQuality("accepted", 1.0, reset_reason="completed_run_reset"), "model-a", "transform-a")

    assert result.state.reset_count == 1
    assert result.state.update_count == 1
    assert result.reset_reason == "completed_run_reset"


def test_quality_assessment_uses_only_telemetry_masks_and_session_boundaries() -> None:
    quality = assess_update_quality(np.array([[True, False], [True, True]], dtype=np.bool_), np.array([False, False], dtype=np.bool_), 0.8)

    assert quality.status == "low"
    assert session_reset_reason("session-a", "session-b") == "session_change"
