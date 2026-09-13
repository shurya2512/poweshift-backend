"""Bounded capture of registered technical-news sources."""

from collections.abc import Callable
from hashlib import sha256

import httpx
from bs4 import BeautifulSoup

from poweshift_backend.contracts.news import ArticleSnapshot, ArticleSource


Fetcher = Callable[[str], bytes]


def fetch_https(url: str, *, timeout_s: float, maximum_bytes: int) -> bytes:
    """Fetch one registered HTTPS document with explicit bounds."""
    if timeout_s <= 0.0 or maximum_bytes < 1:
        raise ValueError("article fetch bounds must be positive")
    with httpx.Client(timeout=httpx.Timeout(timeout_s), follow_redirects=False) as client:
        with client.stream("GET", url, headers={"User-Agent": "poweshift-news-capture/1"}) as response:
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > maximum_bytes:
                    raise ValueError("article response exceeds the configured byte limit")
    return bytes(content)


def capture_article(source: ArticleSource, fetch: Fetcher, *, maximum_bytes: int) -> ArticleSnapshot:
    """Bind visible text to the registered source and availability."""
    if maximum_bytes < 1:
        raise ValueError("article byte limit must be positive")
    content = fetch(source.url)
    if len(content) > maximum_bytes:
        raise ValueError("article response exceeds the configured byte limit")
    digest = sha256(content).hexdigest()
    visible_text = BeautifulSoup(content, "html.parser").get_text(" ", strip=True)
    article_id = sha256(f"{source.source_id}:{source.first_known_at.isoformat()}:{digest}".encode()).hexdigest()
    return ArticleSnapshot(
        article_id=article_id,
        source=source,
        source_sha256=digest,
        visible_text=visible_text,
    )
