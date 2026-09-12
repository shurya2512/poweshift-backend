import pytest
import torch

from poweshift_backend.powertrain.residual import BoundedResponseResidual


def test_residual_is_bounded_and_requires_one_named_mechanism() -> None:
    residual = BoundedResponseResidual(input_width=3, hidden_width=4, maximum_correction_w=2_000.0, mechanism="turbo_lag")
    values = residual(torch.ones((5, 3)))

    assert values.shape == (5,)
    assert torch.all(torch.abs(values) <= 2_000.0)
    with pytest.raises(ValueError, match="mechanism"):
        BoundedResponseResidual(3, 4, 2_000.0, "")
