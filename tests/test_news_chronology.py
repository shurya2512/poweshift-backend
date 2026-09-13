from datetime import datetime, timezone
from hashlib import sha256

import pytest
from pydantic import ValidationError

from poweshift_backend.contracts.news import ArticleSource, NewsReview
from poweshift_backend.learning.chronology import build_profile_update, decide_news_promotion
from poweshift_backend.news.capture import capture_article
from poweshift_backend.news.review import build_news_prior


UTC = timezone.utc


def test_article_capture_binds_visible_text_to_registered_source() -> None:
    html = b"<html><body><p>Revised rear suspension fitted in Bahrain.</p></body></html>"
    source = ArticleSource(
        source_id="source-a",
        url="https://example.test/article",
        published_at=datetime(2026, 2, 10, 8, tzinfo=UTC),
        first_known_at=datetime(2026, 2, 10, 9, tzinfo=UTC),
    )

    article = capture_article(source, lambda _url: html, maximum_bytes=1024)

    assert article.source_sha256 == sha256(html).hexdigest()
    assert article.visible_text == "Revised rear suspension fitted in Bahrain."
    assert article.article_id == sha256(
        f"source-a:{source.first_known_at.isoformat()}:{article.source_sha256}".encode()
    ).hexdigest()


def test_article_source_refuses_timezone_free_availability() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        ArticleSource(
            source_id="source-a",
            url="https://example.test/article",
            published_at=datetime(2026, 2, 10, 8),
            first_known_at=datetime(2026, 2, 10, 9),
        )


def test_news_review_refuses_timezone_free_review_time() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        NewsReview(
            entry_id="12",
            component="floor",
            claim_type="fitment",
            source_span="New floor package fitted to car 12.",
            fitment_status="confirmed",
            reviewed_by="reviewer-a",
            reviewed_at=datetime(2026, 2, 10, 9, 5),
        )


def test_news_prior_refuses_text_that_was_not_available_by_the_stint_cutoff() -> None:
    html = b"<p>New floor package fitted to car 12.</p>"
    source = ArticleSource(
        source_id="source-a",
        url="https://example.test/article",
        published_at=datetime(2026, 2, 10, 8, tzinfo=UTC),
        first_known_at=datetime(2026, 2, 10, 12, tzinfo=UTC),
    )
    article = capture_article(source, lambda _url: html, maximum_bytes=1024)
    review = NewsReview(
        entry_id="12",
        component="floor",
        claim_type="fitment",
        source_span="New floor package fitted to car 12.",
        fitment_status="confirmed",
        reviewed_by="reviewer-a",
        reviewed_at=datetime(2026, 2, 10, 12, 5, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="not available"):
        build_news_prior(article, review, datetime(2026, 2, 10, 11, tzinfo=UTC))

    with pytest.raises(ValueError, match="timezone"):
        build_news_prior(article, review, datetime(2026, 2, 10, 13))


def test_news_prior_defaults_to_zero_numerical_influence() -> None:
    html = b"<p>New floor package fitted to car 12.</p>"
    source = ArticleSource(
        source_id="source-a",
        url="https://example.test/article",
        published_at=datetime(2026, 2, 10, 8, tzinfo=UTC),
        first_known_at=datetime(2026, 2, 10, 9, tzinfo=UTC),
    )
    article = capture_article(source, lambda _url: html, maximum_bytes=1024)
    prior = build_news_prior(
        article,
        NewsReview(
            entry_id="12",
            component="floor",
            claim_type="fitment",
            source_span="New floor package fitted to car 12.",
            fitment_status="confirmed",
            reviewed_by="reviewer-a",
            reviewed_at=datetime(2026, 2, 10, 9, 5, tzinfo=UTC),
        ),
        datetime(2026, 2, 10, 10, tzinfo=UTC),
    )

    assert prior.numerical_influence == 0.0
    assert prior.influence_status == "unmeasured"


def test_profile_update_accepts_training_and_refuses_protected_partitions() -> None:
    update = build_profile_update(
        entry_id="12",
        parent_profile_id="profile-a",
        model_id="model-a",
        transform_id="transform-a",
        source_run_id="run-a",
        source_sha256="a" * 64,
        source_partition="training",
        completed_cutoff=datetime(2026, 2, 10, 10, tzinfo=UTC),
        news_prior_ids=(),
    )
    assert update.source_partition == "training"
    assert len(update.update_id) == 64

    with pytest.raises(ValidationError, match="training"):
        build_profile_update(
            entry_id="12",
            parent_profile_id="profile-a",
            model_id="model-a",
            transform_id="transform-a",
            source_run_id="run-b",
            source_sha256="b" * 64,
            source_partition="final_evaluation",
            completed_cutoff=datetime(2026, 2, 20, 10, tzinfo=UTC),
            news_prior_ids=(),
        )


def test_news_promotion_requires_matched_improvement() -> None:
    retained = decide_news_promotion(
        candidate_profile_id="profile-b",
        telemetry_only_metric=1.0,
        news_metric=1.1,
        metric_name="signed_gap_mae_s",
        comparison_id="comparison-a",
    )
    promoted = decide_news_promotion(
        candidate_profile_id="profile-c",
        telemetry_only_metric=1.0,
        news_metric=0.8,
        metric_name="signed_gap_mae_s",
        comparison_id="comparison-b",
    )

    assert retained.decision == "retained"
    assert retained.news_numerical_influence is False
    assert promoted.decision == "promoted"
    assert promoted.news_numerical_influence is True
