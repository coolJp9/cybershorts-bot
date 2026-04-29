"""Aggregate news from all fetcher sources into a single deduplicated list."""

import logging
import re
from typing import Dict, List, Optional

import requests

from app.config.settings import CYBER_KEYWORDS
from app.fetchers.hackernews import fetch_algolia_hackernews, fetch_hackernews_top
from app.fetchers.rss import fetch_rss_news

log = logging.getLogger("CyberBot.aggregator")


def fetch_all_news() -> List[Dict]:
    """Return the combined raw story list from every configured source."""
    stories: List[Dict] = []
    stories.extend(fetch_rss_news())
    stories.extend(fetch_hackernews_top())
    stories.extend(fetch_algolia_hackernews())
    log.info("Total raw stories fetched: %d", len(stories))
    return stories


def fetch_article_text(url: str) -> str:
    """Best-effort plain-text extraction from an article URL (max 1 500 chars)."""
    if not url:
        return ""
    try:
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; CyberShortsBot/7.0)"},
            timeout=10,
        )
        text = re.sub(r"<[^>]+>", " ", r.text)
        text = re.sub(r"\s+", " ", text).strip()
        log.info("Article fetched (%d chars)", len(text))
        return text[:1500]
    except Exception as exc:
        log.warning("Article fetch failed: %s", exc)
        return ""
