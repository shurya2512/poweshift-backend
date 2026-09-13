"""Strict contracts for source-attributed news and chronological learning."""

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from poweshift_backend.contracts.acquisition import StrictModel


class ArticleSource(StrictModel):
    """Registered source identity and earliest known availability."""

    source_id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    published_at: datetime
    first_known_at: datetime

    @field_validator("published_at", "first_known_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """Require an absolute publication timeline."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("article timestamps require a timezone")
        return value

    @field_validator("url")
    @classmethod
    def require_https(cls, value: str) -> str:
        """Allow only registered HTTPS article sources."""
        if not value.startswith("https://"):
            raise ValueError("article source must use HTTPS")
        return value

    @model_validator(mode="after")
    def require_chronology(self) -> "ArticleSource":
        """Reject availability earlier than publication."""
        if self.first_known_at < self.published_at:
            raise ValueError("article availability precedes publication")
        return self


class ArticleSnapshot(StrictModel):
    """Immutable visible article text and source hash."""

    article_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    source: ArticleSource
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    visible_text: str = Field(min_length=1)


class NewsReview(StrictModel):
    """Human-reviewed fitment and source span."""

    entry_id: str = Field(min_length=1)
    component: str = Field(min_length=1)
    claim_type: str = Field(min_length=1)
    source_span: str = Field(min_length=1)
    fitment_status: Literal["confirmed", "uncertain", "not_fitted"]
    reviewed_by: str = Field(min_length=1)
    reviewed_at: datetime

    @field_validator("reviewed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """Require an absolute review time."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("news review timestamps require a timezone")
        return value


class NewsPrior(StrictModel):
    """Reviewed context that starts with no numerical effect."""

    prior_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    article_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    entry_id: str
    component: str
    claim_type: str
    source_span: str
    fitment_status: Literal["confirmed", "uncertain", "not_fitted"]
    available_at: datetime
    completed_cutoff: datetime
    reviewed_by: str
    reviewed_at: datetime
    numerical_influence: Literal[0.0] = 0.0
    influence_status: Literal["unmeasured"] = "unmeasured"

    @field_validator("available_at", "completed_cutoff", "reviewed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """Require an absolute prior timeline."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("news prior timestamps require a timezone")
        return value


class ProfileUpdateManifest(StrictModel):
    """Training-only completed-stint update boundary."""

    update_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    entry_id: str = Field(min_length=1)
    parent_profile_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    transform_id: str = Field(min_length=1)
    source_run_id: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_partition: Literal["training"]
    completed_cutoff: datetime
    news_prior_ids: tuple[str, ...]

    @field_validator("completed_cutoff")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """Require an absolute evidence cutoff."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("profile update timestamps require a timezone")
        return value


class ModelPromotionReport(StrictModel):
    """Matched comparison decision for one candidate profile."""

    promotion_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_profile_id: str
    metric_name: str
    telemetry_only_metric: float = Field(ge=0.0)
    news_metric: float = Field(ge=0.0)
    comparison_id: str
    decision: Literal["promoted", "retained"]
    news_numerical_influence: bool
