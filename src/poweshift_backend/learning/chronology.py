"""Chronology and evidence gates for later profile updates."""

from datetime import datetime
from hashlib import sha256
import json
from math import isfinite

from poweshift_backend.contracts.news import ModelPromotionReport, ProfileUpdateManifest


def build_profile_update(
    *,
    entry_id: str,
    parent_profile_id: str,
    model_id: str,
    transform_id: str,
    source_run_id: str,
    source_sha256: str,
    source_partition: str,
    completed_cutoff: datetime,
    news_prior_ids: tuple[str, ...],
) -> ProfileUpdateManifest:
    """Freeze one training-only completed-stint update."""
    payload = {
        "entry_id": entry_id,
        "parent_profile_id": parent_profile_id,
        "model_id": model_id,
        "transform_id": transform_id,
        "source_run_id": source_run_id,
        "source_sha256": source_sha256,
        "source_partition": source_partition,
        "completed_cutoff": completed_cutoff,
        "news_prior_ids": news_prior_ids,
    }
    canonical = {**payload, "completed_cutoff": completed_cutoff.isoformat()}
    update_id = sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return ProfileUpdateManifest(update_id=update_id, **payload)


def decide_news_promotion(
    *,
    candidate_profile_id: str,
    telemetry_only_metric: float,
    news_metric: float,
    metric_name: str,
    comparison_id: str,
) -> ModelPromotionReport:
    """Promote only a strictly better matched news candidate."""
    if not all(isfinite(value) and value >= 0.0 for value in (telemetry_only_metric, news_metric)):
        raise ValueError("promotion metrics must be finite and nonnegative")
    promoted = news_metric < telemetry_only_metric
    payload = {
        "candidate_profile_id": candidate_profile_id,
        "metric_name": metric_name,
        "telemetry_only_metric": telemetry_only_metric,
        "news_metric": news_metric,
        "comparison_id": comparison_id,
        "decision": "promoted" if promoted else "retained",
        "news_numerical_influence": promoted,
    }
    promotion_id = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return ModelPromotionReport(promotion_id=promotion_id, **payload)
