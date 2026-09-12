import pytest

from poweshift_backend.contracts.pits import FixedPitManifest, PitEvent
from poweshift_backend.pits.manifest import require_no_pit_window


def test_fixed_manifest_is_context_not_an_optimiser() -> None:
    manifest = FixedPitManifest("pit-a", "source-a", "a" * 64, (PitEvent(100.0, "entry", "pit_entry"),))

    assert require_no_pit_window(manifest, 0.0, 90.0) is manifest
    with pytest.raises(ValueError, match="pit event"):
        require_no_pit_window(manifest, 90.0, 110.0)
