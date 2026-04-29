"""Fetch cybersecurity headlines from curated RSS/Atom feeds."""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import requests

from app.config.settings import CYBER_KEYWORDS, RSS_NEWS_SOURCES, RSS_STORIES_PER_SOURCE

log = logging.getLogger("CyberBot.rss")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}


def _xml_text(node: ET.Element | None, tag_names: list[str]) -> str:
    """Return the first non-empty text found among *tag_names*, namespace-agnostic."""
    if node is None:
        return ""
    for child in list(node):
        local_name = child.tag.split("}")[-1]
        if local_name in tag_names:
            text = "".join(child.itertext()).strip()
            if text:
                return text
    return ""


def _entry_link(node: ET.Element) -> str:
    """Extract a usable URL from an RSS item or Atom entry."""
    for child in list(node):
        if child.tag.split("}")[-1] != "link":
            continue
        href = (child.attrib.get("href") or "").strip()
        if href:
            return href
        text = "".join(child.itertext()).strip()
        if text:
            return text
    return ""


def _parse_feed_time(raw_value: str) -> int:
    """Convert a feed timestamp to Unix seconds, returning 0 on failure."""
    if not raw_value:
        return 0
    raw_value = raw_value.strip()
    try:
        return int(parsedate_to_datetime(raw_value).timestamp())
    except Exception:
        pass
    try:
        return int(datetime.fromisoformat(raw_value.replace("Z", "+00:00")).timestamp())
    except Exception:
        return 0


def fetch_rss_news() -> list[dict]:
    """Return cybersecurity stories scraped from all configured RSS/Atom sources."""
    stories: list[dict] = []
    for source in RSS_NEWS_SOURCES:
        try:
            response = requests.get(source["url"], headers=_HEADERS, timeout=12)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            entries = root.findall(".//item") or root.findall(".//{*}entry")
            picked = 0
            for entry in entries:
                title = _xml_text(entry, ["title"])
                link = _entry_link(entry)
                summary = _xml_text(entry, ["description", "summary", "content"])
                published = _xml_text(entry, ["pubDate", "published", "updated"])
                if not title or not link:
                    continue
                haystack = f"{title} {summary}".lower()
                if not any(kw in haystack for kw in CYBER_KEYWORDS):
                    continue
                stories.append(
                    {
                        "source": source["name"],
                        "title": title,
                        "url": link,
                        "score": source["score"],
                        "time": _parse_feed_time(published),
                    }
                )
                picked += 1
                if picked >= RSS_STORIES_PER_SOURCE:
                    break
        except Exception as exc:
            log.warning("%s RSS fetch failed: %s", source["name"], exc)
    log.info("RSS fetcher returned %d stories", len(stories))
    return stories
