"""Fetch cybersecurity stories from Hacker News (Firebase API + Algolia search)."""

import logging
import xml.etree.ElementTree as ET
from typing import Dict, List

import requests

from app.config.settings import CYBER_KEYWORDS

log = logging.getLogger("CyberBot.hackernews")


def fetch_hackernews_top() -> List[Dict]:
    """Return cybersecurity-relevant stories from the HN top-stories list."""
    stories: List[Dict] = []
    try:
        ids = requests.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json", timeout=10
        ).json()[:100]
        for sid in ids:
            try:
                s = requests.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=5
                ).json()
                if not s or s.get("deleted") or s.get("dead"):
                    continue
                title = s.get("title", "")
                if any(kw in title.lower() for kw in CYBER_KEYWORDS):
                    stories.append({
                        "source": "HackerNews",
                        "title": title,
                        "url": s.get("url", ""),
                        "score": s.get("score", 0),
                        "time": s.get("time", 0),
                    })
            except Exception:
                continue
    except Exception as exc:
        log.error("HackerNews fetch failed: %s", exc)
    log.info("HackerNews returned %d stories", len(stories))
    return stories


def fetch_algolia_hackernews(query: str = "cybersecurity") -> List[Dict]:
    """Search HN via the Algolia API for recent cyber news."""
    stories: List[Dict] = []
    try:
        url = (
            f"https://hn.algolia.com/api/v1/search"
            f"?query={query}&tags=story&hitsPerPage=20"
        )
        data = requests.get(url, timeout=10).json()
        for hit in data.get("hits", []):
            title = hit.get("title", "")
            if not title:
                continue
            stories.append({
                "source": "AlgoliaHN",
                "title": title,
                "url": hit.get("url", ""),
                "score": hit.get("points", 20),
                "time": hit.get("created_at_i", 0),
            })
    except Exception as exc:
        log.warning("Algolia fetch failed: %s", exc)
    log.info("Algolia returned %d stories", len(stories))
    return stories
