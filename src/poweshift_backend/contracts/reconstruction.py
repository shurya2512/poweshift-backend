"""Contracts for admitted reconstruction inputs and frozen numerical artifacts."""

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import Field

from poweshift_backend.contracts.acquisition import StrictModel


class SupportState(str, Enum):
    SUPPORTED = "supported"
    MISSING = "missing"
    ASSUMED = "assumed"


class Phase3Admission(StrictModel):
    """The approved hashes and chronology required before reconstruction reads evidence."""

    phase2_evidence_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    coverage_disposition_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    preprocessing_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    split_manifest: dict[str, object]
    effective_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_by: str
    approved_defaults: "Phase3Defaults"


class Phase3Defaults(StrictModel):
    """The approved preparation values carried into reconstruction."""

    gap_limit_s: float
    smoothing_limit_s: float
    window_limit_s: float
    staleness_policy: Literal["recorded_not_used"]


class EvidencePin(StrictModel):
    """One immutable source artifact and its digest."""

    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReconstructionInputManifest(StrictModel):
    """Pins the evidence and decisions consumed by one reconstruction run."""

    phase2_evidence: EvidencePin
    coverage_disposition: EvidencePin
    preprocessing_spec: EvidencePin
    track_profile: EvidencePin
    split_manifest: dict[str, object]
    effective_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DeclaredAssumption(StrictModel):
    """A measured or assumed quantity with its label and unit."""

    value: float
    unit: str
    support: SupportState
    source: str


class MechanicsAssumptions(StrictModel):
    """Frozen mechanical inputs required by later fitting and replay."""

    reference_mass_kg: DeclaredAssumption
    fuel_load_kg: DeclaredAssumption
    front_axle_distance_m: DeclaredAssumption
    rear_axle_distance_m: DeclaredAssumption


class EffectiveComponent(StrictModel):
    """One bounded effective term with its evidence label."""

    name: Literal["propulsion", "resistance", "braking", "grip"]
    value: float
    unit: str
    support: SupportState


class EffectiveProfile(StrictModel):
    """A frozen set of effective components, not factory vehicle maps."""

    components: tuple[EffectiveComponent, ...]
    assumptions: MechanicsAssumptions


class FitReport(StrictModel):
    """Frozen fitting settings, evidence, profile and unsupported components."""

    created_on: date
    input_manifest: ReconstructionInputManifest
    profile: EffectiveProfile
    settings_evidence: tuple[EvidencePin, ...]
    missing_components: tuple[str, ...]
    settings: dict[str, object]
    diagnostics: dict[str, object]


class EvidenceReport(StrictModel):
    """Held-out motion evidence with its numerical and support limits."""

    fit_report: EvidencePin
    input_manifest: ReconstructionInputManifest
    counts_by_entry_regime: dict[str, int]
    metrics_by_entry_regime: dict[str, dict[str, float]]
    exclusions: tuple[str, ...]
    numerical_diagnostics: dict[str, float]
    unsupported_components: tuple[str, ...]
