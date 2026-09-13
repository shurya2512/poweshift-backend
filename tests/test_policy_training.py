import pytest
import torch

from poweshift_backend.contracts.action import Manoeuvre
from poweshift_backend.contracts.powertrain import EnergyBundleCompatibility
from poweshift_backend.policy.model import RecurrentActorCritic, structural_forward_backward_diagnostic
from poweshift_backend.policy.schema import PolicySchema
from poweshift_backend.policy.train import PhysicalTrainingGate, require_physical_training_ready


def _schema() -> PolicySchema:
    return PolicySchema("schema-a", ("speed", "energy"), tuple(Manoeuvre), 4, "beta-v1")


def test_recurrent_model_applies_action_and_feature_masks_with_finite_backward() -> None:
    model = RecurrentActorCritic(_schema())
    features = torch.tensor([[[20.0, 500.0], [21.0, 490.0]]], dtype=torch.float32)
    feature_mask = torch.tensor([[[True, True], [True, False]]])
    action_mask = torch.tensor([[True, False, True, True]])

    result = structural_forward_backward_diagnostic(model, features, feature_mask, action_mask)

    assert result.finite is True
    assert result.masked_probability == 0.0
    assert result.gradient_norm > 0.0


def test_physical_training_refuses_an_unadmitted_energy_bundle() -> None:
    bundle = EnergyBundleCompatibility("bundle-a", False, "physics-a", "rules-a", "response-a", "accounting-a", "profile-a")
    gate = PhysicalTrainingGate(bundle, "profile-a", "measure-a", "criteria-a")

    with pytest.raises(ValueError, match="energy bundle"):
        require_physical_training_ready(gate)


def test_physical_training_requires_the_bundle_profile() -> None:
    bundle = EnergyBundleCompatibility("bundle-a", True, "physics-a", "rules-a", "response-a", "accounting-a", "profile-a")
    gate = PhysicalTrainingGate(bundle, "profile-b", "measure-a", "criteria-a")

    with pytest.raises(ValueError, match="profile"):
        require_physical_training_ready(gate)
