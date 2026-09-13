import pytest

from poweshift_backend.tyres.condition import DryTyreCondition, UnsupportedTyreCondition


def test_non_dry_condition_is_not_silently_supported() -> None:
    with pytest.raises(UnsupportedTyreCondition):
        DryTyreCondition(1.5, 1.5, surface="wet")
