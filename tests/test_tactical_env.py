import pytest

from poweshift_backend.policy.reward import tactical_reward
from poweshift_backend.simulation.tactical_env import TacticalAdmission, require_tactical_ready


def test_tactical_entry_refuses_missing_world_or_continuation() -> None:
    with pytest.raises(ValueError, match="interaction world"):
        require_tactical_ready(TacticalAdmission(True, False, True, True, True))
    with pytest.raises(ValueError, match="continuation"):
        tactical_reward(1.0, 2.0, has_supported_continuation=False)


def test_tactical_reward_keeps_local_and_tail_components_separate() -> None:
    reward = tactical_reward(1.0, 2.0, has_supported_continuation=True)

    assert reward.local == 1.0
    assert reward.tail == 2.0
    assert reward.total == 3.0
