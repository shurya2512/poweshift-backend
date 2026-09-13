"""Review gates for bounded technical-news context."""

from datetime import datetime
from hashlib import sha256
import json

from poweshift_backend.contracts.news import ArticleSnapshot, NewsPrior, NewsReview


def build_news_prior(article: ArticleSnapshot, review: NewsReview, completed_cutoff: datetime) -> NewsPrior:
    """Create zero-influence context available by a completed cutoff."""
    if completed_cutoff.tzinfo is None or completed_cutoff.utcoffset() is None:
        raise ValueError("completed-stint cutoff requires a timezone")
    if article.source.first_known_at > completed_cutoff:
        raise ValueError("article was not available by the completed-stint cutoff")
    if review.reviewed_at > completed_cutoff:
        raise ValueError("news review was not available by the completed-stint cutoff")
    if review.source_span not in article.visible_text:
        raise ValueError("reviewed source span is absent from the captured article")
    payload = {
        "article_id": article.article_id,
        "entry_id": review.entry_id,
        "component": review.component,
        "claim_type": review.claim_type,
        "source_span": review.source_span,
        "fitment_status": review.fitment_status,
        "available_at": article.source.first_known_at,
        "completed_cutoff": completed_cutoff,
        "reviewed_by": review.reviewed_by,
        "reviewed_at": review.reviewed_at,
    }
    canonical = {
        **payload,
        "available_at": article.source.first_known_at.isoformat(),
        "completed_cutoff": completed_cutoff.isoformat(),
        "reviewed_at": review.reviewed_at.isoformat(),
    }
    prior_id = sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return NewsPrior(prior_id=prior_id, **payload)
