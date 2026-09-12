import numpy as np

from poweshift_backend.reconstruction.losses import masked_residuals


def test_masked_residuals_excludes_invalid_observations() -> None:
    residuals = masked_residuals(
        predicted=np.array([10.0, 12.0, 14.0]),
        observed=np.array([9.0, 10.0, 12.0]),
        mask=np.array([True, False, True]),
    )

    assert residuals.tolist() == [1.0, 2.0]
