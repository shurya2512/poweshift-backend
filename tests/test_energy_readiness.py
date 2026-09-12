import pytest

from poweshift_backend.reconstruction.evidence import admit_energy_bundle, build_energy_readiness


def test_runtime_stays_disabled_without_every_admission_result() -> None:
    readiness = build_energy_readiness(
        interface_stable=True,
        phase4_training_artifact_id="training-a",
        continuous_profile_id="profile-a",
        continuous_profile_admission_id="profile-admission-a",
        physics_id="physics-a",
        response_evidence_id="response-a",
        accounting_evidence_id=None,
        rules_snapshot_id="rules-a",
        numerical_compatible=True,
        differentiable_compatible=True,
    )

    assert readiness["runtime_enabled"] is False
    assert readiness["missing"] == ("accounting_evidence",)


def test_phase4_training_opens_offline_work_but_not_runtime() -> None:
    readiness = build_energy_readiness(
        interface_stable=True,
        phase4_training_artifact_id="training-a",
        continuous_profile_id=None,
        continuous_profile_admission_id=None,
        physics_id="physics-a",
        response_evidence_id=None,
        accounting_evidence_id=None,
        rules_snapshot_id=None,
        numerical_compatible=True,
        differentiable_compatible=True,
    )

    assert readiness["offline_experiments_enabled"] is True
    assert readiness["runtime_enabled"] is False
    assert readiness["missing"] == (
        "continuous_profile",
        "continuous_profile_admission",
        "response_evidence",
        "accounting_evidence",
        "rules_snapshot",
    )


def test_energy_bundle_is_derived_only_from_complete_readiness() -> None:
    blocked = build_energy_readiness(
        interface_stable=True,
        phase4_training_artifact_id="training-a",
        continuous_profile_id=None,
        continuous_profile_admission_id=None,
        physics_id="physics-a",
        response_evidence_id="response-a",
        accounting_evidence_id="accounting-a",
        rules_snapshot_id="rules-a",
        numerical_compatible=True,
        differentiable_compatible=True,
    )
    with pytest.raises(ValueError, match="readiness"):
        admit_energy_bundle(blocked, bundle_id="bundle-a")

    ready = build_energy_readiness(
        interface_stable=True,
        phase4_training_artifact_id="training-a",
        continuous_profile_id="profile-a",
        continuous_profile_admission_id="profile-admission-a",
        physics_id="physics-a",
        response_evidence_id="response-a",
        accounting_evidence_id="accounting-a",
        rules_snapshot_id="rules-a",
        numerical_compatible=True,
        differentiable_compatible=True,
    )

    bundle = admit_energy_bundle(ready, bundle_id="bundle-a")

    assert bundle.admitted is True
    assert bundle.continuous_profile_id == "profile-a"
