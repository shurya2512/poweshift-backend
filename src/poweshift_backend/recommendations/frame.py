"""Projection from guarded policy results to recommendation frames."""

from poweshift_backend.contracts.runtime import InferenceResult, RecommendationFrame


def build_recommendation(result: InferenceResult, *, expires_after_ns: int) -> RecommendationFrame:
    """Build an expiring retrospective recommendation."""
    if expires_after_ns < 1:
        raise ValueError("recommendation expiry must be positive")
    return RecommendationFrame(
        run_id=result.run_id,
        request_id=result.request_id,
        sequence=result.sequence,
        intent=result.action.manoeuvre.value,
        deployment_fraction=result.action.deployment_fraction,
        requested_power_w=None,
        reachable_power_w=None,
        evidence_status="retrospective_inference" if result.status == "accepted" else "unsupported_fallback",
        binding_reasons=result.binding_reasons,
        created_monotonic_ns=result.completed_monotonic_ns,
        expires_monotonic_ns=result.completed_monotonic_ns + expires_after_ns,
        memory_version=result.memory_version,
        policy_id=result.policy_id,
        energy_bundle_id=result.energy_bundle_id,
        continuous_profile_id=result.continuous_profile_id,
        physics_id=result.physics_id,
        rules_id=result.rules_id,
        pit_manifest_id=result.pit_manifest_id,
        route_id=result.route_id,
        scenario_id=result.scenario_id,
        news_prior_ids=result.news_prior_ids,
    )
