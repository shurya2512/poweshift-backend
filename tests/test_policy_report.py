import pytest

from poweshift_backend.contracts.powertrain import EnergyBundleCompatibility
from poweshift_backend.policy.report import PolicyCompatibility, build_policy_report


def test_policy_report_refuses_admission_when_any_compatibility_is_missing() -> None:
    compatibility = PolicyCompatibility(
        model_id="model-a",
        schema_id="schema-a",
        physics_id=None,
        rules_id="rules-a",
        pit_manifest_id="pit-a",
        scenario_id="scenario-a",
        energy_bundle_id="bundle-a",
        continuous_profile_id="profile-a",
    )

    report = build_policy_report(compatibility, requested_admission=True)

    assert report.admitted is False
    assert report.unsupported == ("physics",)
    with pytest.raises(ValueError, match="unsupported claim"):
        build_policy_report(compatibility, requested_admission=True, claim="two-corner policy validated")


def test_policy_compatibility_derives_phase_identities_from_energy_bundle() -> None:
    bundle = EnergyBundleCompatibility(
        "bundle-a", True, "physics-a", "rules-a", "response-a", "accounting-a", "profile-a"
    )

    compatibility = PolicyCompatibility.from_energy_bundle(
        model_id="model-a",
        schema_id="schema-a",
        energy_bundle=bundle,
        pit_manifest_id="pit-a",
        scenario_id="scenario-a",
    )
    report = build_policy_report(compatibility, requested_admission=True)

    assert report.admitted is True
    assert compatibility.physics_id == "physics-a"
    assert compatibility.rules_id == "rules-a"
    assert compatibility.continuous_profile_id == "profile-a"


def test_policy_compatibility_refuses_an_unadmitted_bundle() -> None:
    bundle = EnergyBundleCompatibility(
        "bundle-a", False, "physics-a", "rules-a", "response-a", "accounting-a", "profile-a"
    )

    with pytest.raises(ValueError, match="admitted"):
        PolicyCompatibility.from_energy_bundle(
            model_id="model-a",
            schema_id="schema-a",
            energy_bundle=bundle,
            pit_manifest_id="pit-a",
            scenario_id="scenario-a",
        )
