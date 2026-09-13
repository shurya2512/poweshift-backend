"""Policy compatibility report with unsupported-claim refusal."""

from dataclasses import dataclass

from poweshift_backend.contracts.powertrain import EnergyBundleCompatibility


@dataclass(frozen=True)
class PolicyCompatibility:
    """Artifact identities needed for policy admission."""

    model_id: str | None
    schema_id: str | None
    physics_id: str | None
    rules_id: str | None
    pit_manifest_id: str | None
    scenario_id: str | None
    energy_bundle_id: str | None
    continuous_profile_id: str | None

    @classmethod
    def from_energy_bundle(
        cls,
        *,
        model_id: str | None,
        schema_id: str | None,
        energy_bundle: EnergyBundleCompatibility,
        pit_manifest_id: str | None,
        scenario_id: str | None,
    ) -> "PolicyCompatibility":
        """Derive policy physics, rules and profile identities from one bundle."""
        if not energy_bundle.admitted:
            raise ValueError("policy compatibility requires an admitted energy bundle")
        return cls(
            model_id,
            schema_id,
            energy_bundle.physics_id,
            energy_bundle.rules_id,
            pit_manifest_id,
            scenario_id,
            energy_bundle.bundle_id,
            energy_bundle.continuous_profile_id,
        )


@dataclass(frozen=True)
class PolicyReport:
    """Admission result and exact missing compatibility fields."""

    admitted: bool
    compatibility: PolicyCompatibility
    unsupported: tuple[str, ...]
    claim: str | None


def build_policy_report(
    compatibility: PolicyCompatibility,
    *,
    requested_admission: bool,
    claim: str | None = None,
) -> PolicyReport:
    """Admit only a complete compatible artifact set."""
    fields = {
        "model": compatibility.model_id,
        "schema": compatibility.schema_id,
        "physics": compatibility.physics_id,
        "rules": compatibility.rules_id,
        "fixed_pits": compatibility.pit_manifest_id,
        "scenario": compatibility.scenario_id,
        "energy_bundle": compatibility.energy_bundle_id,
        "continuous_profile": compatibility.continuous_profile_id,
    }
    unsupported = tuple(name for name, value in fields.items() if not value)
    if claim and unsupported:
        raise ValueError("unsupported claim cannot accompany an incompatible policy")
    return PolicyReport(requested_admission and not unsupported, compatibility, unsupported, claim)
