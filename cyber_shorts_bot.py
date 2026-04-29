#!/usr/bin/env python3
"""
FACELESS Cybersecurity YouTube Shorts Bot v7 (Agentic)
======================================================
- Multi-source news: HackerNews, IndieHackers, Algolia HN
- AI picks the "spiciest" story using Ollama (llama3.2)
- AI generates dynamic video search terms (no hardcoded lists)
- Title-based deduplication (stores title hashes, not IDs)
- TTS: edge-tts (online) → pyttsx3 (offline)
- Video: stock clip looped to exact audio length
- Upload: YouTube Data API v3 with scheduled publishing
- Logging & cleanup
- v7: Better quota handling, token refresh, auto-cleanup
"""

import os
import re
import json
import asyncio
import random
import logging
import subprocess
import hashlib
import requests
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional, Dict, List, Tuple, Set

from dotenv import load_dotenv
load_dotenv()

# ─────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
log_file = LOG_DIR / f"bot_{datetime.now().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("CyberBot")

# ─────────────────────────────────────────────────────────────
# CONFIG — from .env only
# ─────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
OLLAMA_HOST    = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL   = os.getenv("OLLAMA_MODEL", "llama3.2")

VIDEO_WIDTH  = 1080
VIDEO_HEIGHT = 1920
OUTPUT_DIR   = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)
USED_FILE    = Path("used_stories.json")      # stores title hashes
JOB_MEMORY_FILE = Path("agent_jobs.json")
TOKEN_FILE   = Path("token.json")
CREDENTIALS_FILE = Path("credentials.json")

# Multi-video config
VIDEOS_PER_RUN = 10
SCHEDULE_TIMES = ["06:30","08:30","09:00","11:30","12:00","14:30","15:00","17:30","18:00","21:30"]  # IST
SCRIPT_RETRY_ATTEMPTS = int(os.getenv("SCRIPT_RETRY_ATTEMPTS", "2"))
MIN_SCRIPT_SCORE = int(os.getenv("MIN_SCRIPT_SCORE", "7"))
NETWORK_RETRIES = int(os.getenv("NETWORK_RETRIES", "2"))
RSS_STORIES_PER_SOURCE = int(os.getenv("RSS_STORIES_PER_SOURCE", "12"))

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────
CYBER_KEYWORDS = [
    "security", "hack", "breach", "vulnerability", "cyber",
    "ransomware", "zero-day", "exploit", "malware", "phishing",
    "data leak", "cybersecurity", "cve", "patch", "attack",
    "trojan", "botnet", "ddos", "spyware", "backdoor",
    "password", "encryption", "firewall", "surveillance", "privacy",
]

# Only used as fallback if AI term generation fails
FALLBACK_TERMS = [
    "digital lock encryption",
    "server rack data center",
    "binary code matrix",
]

FACE_WORDS = {
    "person", "face", "woman", "man", "people",
    "human", "girl", "boy", "portrait", "model",
}

RSS_NEWS_SOURCES = [
    {"name": "BleepingComputer",    "url": "https://www.bleepingcomputer.com/feed/",                       "score": 90},
    {"name": "TheHackerNews",       "url": "https://feeds.feedburner.com/TheHackersNews",                  "score": 85},
    {"name": "KrebsOnSecurity",     "url": "https://krebsonsecurity.com/feed/",                            "score": 84},
    {"name": "SecurityWeek",        "url": "https://www.securityweek.com/feed/",                           "score": 82},
    {"name": "TheRecord",           "url": "https://therecord.media/feed",                                 "score": 80},
    {"name": "ISCHandler",          "url": "https://isc.sans.edu/rssfeed_full.xml",                        "score": 79},
    {"name": "CybersecurityDive",   "url": "https://www.cybersecuritydive.com/feeds/news/",                "score": 78},
    {"name": "CyberScoop",          "url": "https://cyberscoop.com/feed/",                                 "score": 76},
    {"name": "SecureList",          "url": "https://securelist.com/feed/",                                 "score": 76},
    {"name": "Hackread",            "url": "https://hackread.com/feed/",                                   "score": 75},
    {"name": "ThreatPost",          "url": "https://threatpost.com/feed/",                                 "score": 75},
    {"name": "HelpNetSecurity",     "url": "https://www.helpnetsecurity.com/feed/",                        "score": 74},
    {"name": "TroyHunt",            "url": "https://feeds.feedburner.com/TroyHunt",                        "score": 74},
    {"name": "InfosecurityMagazine","url": "https://www.infosecurity-magazine.com/rss/news/",              "score": 73},
    {"name": "WiredSecurity",       "url": "https://www.wired.com/feed/category/security/latest/rss",      "score": 70},
    {"name": "GrahamCluley",        "url": "https://grahamcluley.com/feed/",                               "score": 69},
    {"name": "TechCrunchSecurity",  "url": "https://techcrunch.com/category/security/feed/",               "score": 68},
    {"name": "UnsupervisedLearning","url": "https://danielmiessler.com/feed/",                             "score": 68},
    {"name": "Schneier",            "url": "https://www.schneier.com/feed/atom/",                          "score": 66},
]

TTS_VOICES: List[Tuple[str, str]] = [
    ("en-US-JennyNeural",       "+0%"),
    ("en-US-GuyNeural",         "+3%"),
    ("en-US-AriaNeural",        "-3%"),
    ("en-US-ChristopherNeural", "+0%"),
    ("en-US-MichelleNeural",    "+3%"),
    ("en-US-EricNeural",        "-3%"),
    ("en-US-SteffanNeural",     "+0%"),
    ("en-GB-SoniaNeural",       "+3%"),
    ("en-GB-RyanNeural",        "-3%"),
    ("en-AU-NatashaNeural",     "+0%"),
]

# ─────────────────────────────────────────────────────────────
# YOUTUBE QUOTA TRACKING
# ─────────────────────────────────────────────────────────────
class YouTubeQuotaExceeded(Exception):
    """Raised when YouTube upload quota is exceeded."""
    pass

@dataclass
class VideoJob:
    """Persistent state for one autonomous video task."""
    job_id: str
    story: Dict[str, Any]
    status: str = "planned"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    reason: str = ""
    category: str = "general"
    score: int = 0
    context_chars: int = 0
    script: str = ""
    script_score: int = 0
    script_review: str = ""
    search_terms: List[str] = field(default_factory=list)
    voice_path: str = ""
    raw_video_path: str = ""
    final_video_path: str = ""
    scheduled_for: str = ""
    uploaded: bool = False
    upload_skipped: bool = False
    errors: List[str] = field(default_factory=list)

    def touch(self, status: Optional[str] = None):
        if status:
            self.status = status
        self.updated_at = datetime.now().isoformat(timespec="seconds")

    def fail(self, message: str):
        self.errors.append(message)
        self.touch("failed")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VideoJob":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})

QUOTA_STATE_FILE = Path("youtube_quota_state.json")

def check_quota_cooldown() -> Tuple[bool, Optional[datetime]]:
    """Check if we're in a quota cooldown period.
    Returns (can_upload, cooldown_ends_at)
    """
    if not QUOTA_STATE_FILE.exists():
        return True, None
    
    try:
        state = json.loads(QUOTA_STATE_FILE.read_text())
        cooldown_until = datetime.fromisoformat(state.get("cooldown_until", ""))
        if datetime.now() < cooldown_until:
            return False, cooldown_until
        # Cooldown expired, clear the file
        QUOTA_STATE_FILE.unlink(missing_ok=True)
        return True, None
    except Exception as e:
        log.warning(f"Could not read quota state: {e}")
        return True, None

def set_quota_cooldown(hours: int = 24):
    """Set a cooldown period after hitting quota limit."""
    cooldown_until = datetime.now() + timedelta(hours=hours)
    state = {
        "cooldown_until": cooldown_until.isoformat(),
        "reason": "uploadLimitExceeded",
        "set_at": datetime.now().isoformat(),
    }
    try:
        QUOTA_STATE_FILE.write_text(json.dumps(state, indent=2))
        log.info(f"Set YouTube quota cooldown until {cooldown_until.strftime('%Y-%m-%d %H:%M')}")
    except Exception as e:
        log.error(f"Could not write quota state: {e}")

# ─────────────────────────────────────────────────────────────
# DEDUPLICATION (title-based hashing)
# ─────────────────────────────────────────────────────────────
def story_hash(title: str) -> str:
    """Create a hash of the story title for deduplication."""
    normalized = re.sub(r'\b(the|a|an|to|for|of|in|on|at)\b', '', title.lower())
    normalized = re.sub(r'[^\w\s]', '', normalized)[:80]
    return hashlib.md5(normalized.encode()).hexdigest()[:12]

def load_used_titles() -> Set[str]:
    """Load previously used story hashes."""
    if USED_FILE.exists():
        try:
            data = set(json.loads(USED_FILE.read_text()))
            log.info(f"Loaded {len(data)} used story hashes")
            return data
        except Exception as e:
            log.warning(f"Could not read {USED_FILE}: {e}")
    return set()

def mark_used_title(title: str):
    """Mark a story title as used (by its hash)."""
    h = story_hash(title)
    used = load_used_titles()
    used.add(h)
    used_list = list(used)[-500:]
    try:
        USED_FILE.write_text(json.dumps(used_list))
        log.info(f"Marked story as used (hash={h}, total={len(used_list)})")
    except Exception as e:
        log.error(f"Could not write {USED_FILE}: {e}")

# ─────────────────────────────────────────────────────────────
# MULTI-SOURCE NEWS FETCHING
# ─────────────────────────────────────────────────────────────
def load_job_memory() -> List[Dict[str, Any]]:
    """Load persistent agent job memory."""
    if not JOB_MEMORY_FILE.exists():
        return []
    try:
        data = json.loads(JOB_MEMORY_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception as e:
        log.warning(f"Could not read {JOB_MEMORY_FILE}: {e}")
    return []

def save_job_memory(jobs: List[Dict[str, Any]]):
    """Write persistent agent job memory, keeping recent history compact."""
    try:
        JOB_MEMORY_FILE.write_text(
            json.dumps(jobs[-300:], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        log.error(f"Could not write {JOB_MEMORY_FILE}: {e}")

def upsert_job(job: VideoJob):
    """Insert or update a job in persistent memory."""
    jobs = load_job_memory()
    job_data = asdict(job)
    for idx, existing in enumerate(jobs):
        if existing.get("job_id") == job.job_id:
            jobs[idx] = job_data
            save_job_memory(jobs)
            return
    jobs.append(job_data)
    save_job_memory(jobs)

def completed_story_hashes() -> Set[str]:
    """Stories that already produced a successful local video or upload."""
    hashes = set()
    for job in load_job_memory():
        story = job.get("story") or {}
        title = story.get("title", "")
        if title and job.get("status") in {"created", "uploaded", "upload_skipped"}:
            hashes.add(story_hash(title))
    return hashes

def retry_call(name: str, fn: Callable[[], Any], attempts: int = NETWORK_RETRIES, delay: float = 2.0) -> Any:
    """Retry transient operations without hiding the final failure."""
    last_error = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return fn()
        except Exception as e:
            last_error = e
            if attempt < attempts:
                wait = delay * attempt
                log.warning(f"{name} failed on attempt {attempt}/{attempts}: {e}. Retrying in {wait:.1f}s")
                time.sleep(wait)
            else:
                log.warning(f"{name} failed after {attempts} attempts: {e}")
    if last_error:
        raise last_error
    return None

def fetch_hackernews_top() -> List[Dict]:
    """Fetch top cybersecurity stories from Hacker News."""
    stories = []
    try:
        ids = requests.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json",
            timeout=10,
        ).json()[:100]
        for sid in ids:
            try:
                s = requests.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                    timeout=5,
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
    except Exception as e:
        log.error(f"HackerNews fetch failed: {e}")
    return stories

def fetch_indiehackers() -> List[Dict]:
    """Fetch recent posts from IndieHackers (RSS)."""
    stories = []
    try:
        r = requests.get("https://www.indiehackers.com", timeout=10)
        root = ET.fromstring(r.content)
        for item in root.findall(".//item")[:20]:
            title = item.find("title").text if item.find("title") is not None else ""
            link = item.find("link").text if item.find("link") is not None else ""
            if any(kw in title.lower() for kw in CYBER_KEYWORDS):
                stories.append({
                    "source": "IndieHackers",
                    "title": title,
                    "url": link,
                    "score": 50,
                    "time": 0,
                })
    except Exception as e:
        log.warning(f"IndieHackers fetch failed: {e}")
    return stories

def fetch_algolia_hackernews(query: str = "cybersecurity") -> List[Dict]:
    """Search Hacker News via Algolia API for recent cyber news."""
    stories = []
    try:
        url = f"https://hn.algolia.com/api/v1/search?query={query}&tags=story&hitsPerPage=20"
        r = requests.get(url, timeout=10)
        data = r.json()
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
    except Exception as e:
        log.warning(f"Algolia fetch failed: {e}")
    return stories

def _xml_text(node: Optional[ET.Element], tag_names: List[str]) -> str:
    """Return stripped text for the first matching tag, namespace-agnostic."""
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
    """Extract a usable link from RSS or Atom entries."""
    for child in list(node):
        local_name = child.tag.split("}")[-1]
        if local_name != "link":
            continue
        href = (child.attrib.get("href") or "").strip()
        if href:
            return href
        text = "".join(child.itertext()).strip()
        if text:
            return text
    return ""

def _parse_feed_time(raw_value: str) -> int:
    """Convert feed timestamps into Unix seconds when possible."""
    if not raw_value:
        return 0
    raw_value = raw_value.strip()
    try:
        return int(parsedate_to_datetime(raw_value).timestamp())
    except Exception:
        pass
    try:
        cleaned = raw_value.replace("Z", "+00:00")
        return int(datetime.fromisoformat(cleaned).timestamp())
    except Exception:
        return 0

def fetch_rss_news() -> List[Dict]:
    """Fetch cybersecurity headlines from curated RSS/Atom sources."""
    stories = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }
    for source in RSS_NEWS_SOURCES:
        try:
            response = requests.get(source["url"], headers=headers, timeout=12)
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

                stories.append({
                    "source": source["name"],
                    "title": title,
                    "url": link,
                    "score": source["score"],
                    "time": _parse_feed_time(published),
                })
                picked += 1
                if picked >= RSS_STORIES_PER_SOURCE:
                    break
        except Exception as e:
            log.warning(f"{source['name']} RSS fetch failed: {e}")
    return stories

def fetch_all_news() -> List[Dict]:
    """Aggregate news from all sources."""
    all_stories = []
    all_stories.extend(fetch_rss_news())
    all_stories.extend(fetch_hackernews_top())
    # all_stories.extend(fetch_indiehackers())
    all_stories.extend(fetch_algolia_hackernews())
    log.info(f"Total raw stories fetched: {len(all_stories)}")
    return all_stories

# ─────────────────────────────────────────────────────────────
# AI-POWERED STORY SELECTION
# ─────────────────────────────────────────────────────────────
def story_category(title: str) -> str:
    """Lightweight category for batch diversity."""
    t = title.lower()
    buckets = [
        ("ransomware", ["ransomware", "extortion"]),
        ("breach", ["breach", "leak", "stolen", "exposed", "data"]),
        ("vulnerability", ["cve", "vulnerability", "zero-day", "exploit", "patch"]),
        ("malware", ["malware", "trojan", "botnet", "spyware", "backdoor"]),
        ("privacy", ["privacy", "surveillance", "whatsapp", "meta", "google"]),
        ("ai_security", ["ai", "llm", "model", "prompt"]),
        ("defense", ["security", "cybersecurity", "firewall", "encryption"]),
    ]
    for category, needles in buckets:
        if any(needle in t for needle in needles):
            return category
    return "general"

def heuristic_story_score(story: Dict) -> int:
    """Deterministic fallback score when the model is unavailable."""
    title = story.get("title", "")
    lower = title.lower()
    keyword_hits = sum(1 for kw in CYBER_KEYWORDS if kw in lower)
    source_bonus = {
        "BleepingComputer": 20,
        "TheHackerNews": 18,
        "KrebsOnSecurity": 18,
        "SecurityWeek": 16,
        "TheRecord": 16,
        "DarkReading": 15,
        "CybersecurityDive": 15,
        "CyberScoop": 14,
        "Hackread": 14,
        "HelpNetSecurity": 13,
        "CyberWire": 13,
        "CISA": 13,
        "InfosecurityMagazine": 12,
        "Cybernews": 11,
        "WiredSecurity": 10,
        "UnsupervisedLearning": 10,
        "Schneier": 10,
        "HackerNews": 8,
        "AlgoliaHN": 5,
        "IndieHackers": 2,
    }.get(story.get("source"), 0)
    hn_score = min(int(story.get("score") or 0), 300) // 10
    recency_bonus = 0
    story_time = int(story.get("time") or 0)
    if story_time:
        age_hours = max(0, (datetime.now().timestamp() - story_time) / 3600)
        recency_bonus = max(0, 24 - int(age_hours // 2))
    severity_bonus = 10 if any(w in lower for w in ["breach", "zero-day", "ransomware", "critical", "exploit"]) else 0
    return keyword_hits * 5 + source_bonus + hn_score + recency_bonus + severity_bonus

def dedupe_stories(stories: List[Dict]) -> List[Dict]:
    """Keep the strongest copy of each title hash."""
    best_by_hash: Dict[str, Dict] = {}
    for story in stories:
        title = story.get("title", "").strip()
        if not title:
            continue
        h = story_hash(title)
        story = dict(story)
        story["agent_score"] = heuristic_story_score(story)
        story["category"] = story_category(title)
        if h not in best_by_hash or story["agent_score"] > best_by_hash[h].get("agent_score", 0):
            best_by_hash[h] = story
    return list(best_by_hash.values())

def ai_plan_story_batch(stories: List[Dict], count: int) -> List[Dict]:
    """Ask the local model to pick a diverse batch; fall back to heuristic diversity."""
    if not stories:
        return []

    candidates = sorted(stories, key=lambda s: s.get("agent_score", 0), reverse=True)[:40]
    candidate_lines = []
    for idx, s in enumerate(candidates, 1):
        candidate_lines.append(
            f"{idx}. [{s.get('source')}] ({s.get('category')}, score={s.get('agent_score')}) {s.get('title')}"
        )

    prompt = f"""You are the planning agent for a faceless cybersecurity Shorts channel.
Pick {count} stories from this list for one publishing batch.
Goals: high impact, fresh, varied topics, clear viewer hook, avoid duplicates.
Return ONLY the story numbers in best publishing order, comma separated.

Stories:
{chr(10).join(candidate_lines)}
"""
    try:
        r = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=75,
        )
        r.raise_for_status()
        response = r.json().get("response", "")
        picked = []
        seen = set()
        for raw in re.findall(r"\d+", response):
            idx = int(raw) - 1
            if 0 <= idx < len(candidates) and idx not in seen:
                seen.add(idx)
                picked.append(candidates[idx])
            if len(picked) >= count:
                break
        if picked:
            log.info(f"AI batch planner selected {len(picked)} stories")
            return picked
    except Exception as e:
        log.warning(f"AI batch planning failed: {e}")

    selected = []
    used_categories: Dict[str, int] = {}
    for story in candidates:
        cat = story.get("category", "general")
        if used_categories.get(cat, 0) >= 2 and len(selected) < count - 2:
            continue
        selected.append(story)
        used_categories[cat] = used_categories.get(cat, 0) + 1
        if len(selected) >= count:
            break
    if len(selected) < count:
        selected_hashes = {story_hash(s["title"]) for s in selected}
        for story in candidates:
            if story_hash(story["title"]) not in selected_hashes:
                selected.append(story)
            if len(selected) >= count:
                break
    log.info(f"Heuristic batch planner selected {len(selected)} stories")
    return selected[:count]

def plan_video_jobs(count: int) -> List[VideoJob]:
    """Fetch once, filter memory, and create a planned batch."""
    log.info("Agent planner: fetching candidate stories once for the full batch...")
    used_hashes = load_used_titles() | completed_story_hashes()
    stories = dedupe_stories(fetch_all_news())
    fresh = [s for s in stories if story_hash(s["title"]) not in used_hashes]

    if not fresh:
        log.warning("No fresh stories found. Keeping job memory, clearing title hash cache, and retrying candidates.")
        USED_FILE.unlink(missing_ok=True)
        used_hashes = completed_story_hashes()
        fresh = [s for s in stories if story_hash(s["title"]) not in used_hashes]

    planned_stories = ai_plan_story_batch(fresh, count)
    jobs = []
    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    for idx, story in enumerate(planned_stories, 1):
        title = story["title"]
        job = VideoJob(
            job_id=f"{batch_id}_{idx}_{story_hash(title)}",
            story=story,
            reason=f"planned as {story.get('category', 'general')} story with score {story.get('agent_score', 0)}",
            category=story.get("category", "general"),
            score=int(story.get("agent_score", 0)),
        )
        upsert_job(job)
        jobs.append(job)
    log.info(f"Agent planner created {len(jobs)} jobs")
    return jobs

def ai_pick_best_story(stories: List[Dict]) -> Optional[Dict]:
    """Use Ollama to pick the most 'spicy' and eye-catching story."""
    if not stories:
        return None

    candidates = stories[:15]
    candidates_text = ""
    for idx, s in enumerate(candidates):
        candidates_text += f"{idx+1}. [{s['source']}] {s['title']} (score: {s['score']})\n"

    prompt = f"""You are a cybersecurity news editor. Pick the SINGLE most "spicy", eye-catching, and important cybersecurity story from the list below. 
Consider: recency, severity, impact, novelty.
Return ONLY the number (1-{len(candidates)}) of your choice, nothing else.

Stories:
{candidates_text}
"""

    try:
        r = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=60,
        )
        r.raise_for_status()
        response = r.json().get("response", "").strip()
        match = re.search(r'\d+', response)
        if match:
            idx = int(match.group()) - 1
            if 0 <= idx < len(candidates):
                chosen = candidates[idx]
                log.info(f"AI chose story {idx+1}: {chosen['title'][:80]}...")
                return chosen
    except Exception as e:
        log.warning(f"AI story selection failed: {e}")

    log.info("Falling back to highest score selection")
    return max(stories, key=lambda x: x.get('score', 0))

def fetch_story() -> Optional[Dict]:
    """Fetch and AI-pick the best unused cybersecurity story."""
    log.info("Fetching news from all sources...")
    used_hashes = load_used_titles()

    all_stories = fetch_all_news()
    new_stories = [s for s in all_stories if story_hash(s['title']) not in used_hashes]

    if not new_stories:
        log.warning("No unused stories found — clearing history and retrying")
        USED_FILE.unlink(missing_ok=True)
        return fetch_story()

    log.info(f"Found {len(new_stories)} new stories")
    story = ai_pick_best_story(new_stories)

    if not story:
        log.error("No story selected")
        return None

    mark_used_title(story['title'])
    return story

def fetch_article_text(url: str) -> str:
    """Best-effort plain-text extraction from article URL."""
    if not url:
        return ""
    try:
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; CyberShortsBot/6.0)"},
            timeout=10,
        )
        text = re.sub(r"<[^>]+>", " ", r.text)
        text = re.sub(r"\s+", " ", text).strip()
        log.info(f"Article fetched ({len(text)} chars)")
        return text[:1500]
    except Exception as e:
        log.warning(f"Article fetch failed: {e}")
        return ""

# ─────────────────────────────────────────────────────────────
# AI-GENERATED VIDEO SEARCH TERMS
# ─────────────────────────────────────────────────────────────
def ai_generate_search_terms(title: str, context: str = "") -> List[str]:
    """Use Ollama to generate 2-3 relevant, faceless video search terms."""
    prompt = f"""Given this cybersecurity news headline, generate 2-3 short search queries (max 4 words each) for finding FACELESS stock videos (no people, no faces). 
Focus on visual concepts: code, servers, locks, shields, data streams, encryption.

Headline: {title}
Context: {context[:200]}

Return ONLY the queries, one per line, no extra text.
Example outputs:
digital lock encryption
server rack blinking
binary code matrix
"""

    try:
        r = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=60,
        )
        r.raise_for_status()
        response = r.json().get("response", "").strip()
        terms = [line.strip() for line in response.split('\n') if line.strip()]
        if terms:
            log.info(f"AI generated search terms: {terms}")
            return terms[:3]
    except Exception as e:
        log.warning(f"AI term generation failed: {e}")

    keywords = [kw for kw in CYBER_KEYWORDS if kw in title.lower()]
    if keywords:
        fallback = [f"{random.choice(keywords)} abstract", f"digital {random.choice(keywords)}"]
        log.info(f"Using fallback terms: {fallback}")
        return fallback[:2]
    return FALLBACK_TERMS.copy()

# ─────────────────────────────────────────────────────────────
# SCRIPT GENERATION (Ollama → Gemini → static)
# ─────────────────────────────────────────────────────────────
_PROMPT = (
    "Write a punchy 45-second YouTube Shorts script about this cybersecurity news:\n\n"
    "Title: {title}\n"
    "Context: {context}\n\n"
    "Rules:\n"
    "- Start with BREAKING: or ALERT: or WARNING:\n"
    "- Maximum 380 characters total\n"
    "- Plain simple language, no jargon\n"
    "- End with exactly: Follow for daily cyber updates\n"
    "- Output ONLY the script text, no quotes, no labels"
)

def _ollama_script(title: str, context: str) -> Optional[str]:
    log.info(f"Generating script with Ollama ({OLLAMA_MODEL})...")
    try:
        r = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model":  OLLAMA_MODEL,
                "prompt": _PROMPT.format(title=title, context=context[:400]),
                "stream": False,
            },
            timeout=90,
        )
        r.raise_for_status()
        text = r.json().get("response", "").strip()
        if text:
            log.info("Script from Ollama")
            return text[:400]
        log.warning("Ollama returned empty response")
    except Exception as e:
        log.warning(f"Ollama script error: {e}")
    return None

def _gemini_script(title: str, context: str) -> Optional[str]:
    if not GEMINI_API_KEY:
        return None
    log.info("Generating script with Gemini (fallback)...")
    try:
        r = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
            json={"contents": [{"parts": [{"text": _PROMPT.format(title=title, context=context[:400])}]}]},
            timeout=30,
        )
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        log.info("Script from Gemini")
        return text[:400]
    except Exception as e:
        log.warning(f"Gemini script error: {e}")
    return None

def _static_script(title: str) -> str:
    log.warning("Using static fallback script")
    return (f"BREAKING: {title[:120]}. "
            "Cybersecurity researchers are raising the alarm. "
            "Patch your systems immediately. "
            "Follow for daily cyber updates.")

def generate_script(title: str, context: str) -> str:
    """Ollama → Gemini → static fallback."""
    return _ollama_script(title, context) or _gemini_script(title, context) or _static_script(title)

# ─────────────────────────────────────────────────────────────
# VOICEOVER (edge-tts → pyttsx3)
# ─────────────────────────────────────────────────────────────
def normalize_script(text: str) -> str:
    """Make model output fit the channel rules before review."""
    text = re.sub(r"^\s*(script|voiceover|caption)\s*:\s*", "", text.strip(), flags=re.I)
    text = text.strip().strip('"').strip("'")
    text = re.sub(r"\s+", " ", text)
    if not re.match(r"^(BREAKING|ALERT|WARNING):", text, flags=re.I):
        text = f"BREAKING: {text}"
    cta = "Follow for daily cyber updates"
    if cta.lower() not in text.lower():
        text = re.sub(r"\s*follow for .*?$", "", text, flags=re.I).strip()
        text = f"{text} {cta}"
    return text[:430]

def heuristic_script_review(script: str, title: str, context: str) -> Dict[str, Any]:
    """Score a script without a model, so the pipeline still self-checks offline."""
    score = 10
    issues = []
    if len(script) > 400:
        score -= 2
        issues.append("too long")
    if not re.match(r"^(BREAKING|ALERT|WARNING):", script, flags=re.I):
        score -= 2
        issues.append("weak hook")
    if "Follow for daily cyber updates" not in script:
        score -= 2
        issues.append("missing CTA")
    title_terms = {w for w in re.findall(r"[a-zA-Z]{5,}", title.lower())}
    script_terms = set(re.findall(r"[a-zA-Z]{5,}", script.lower()))
    if title_terms and not (title_terms & script_terms):
        score -= 2
        issues.append("does not clearly match title")
    if any(word in script.lower() for word in ["guaranteed", "confirmed hacked everyone", "all users are hacked"]):
        score -= 3
        issues.append("overclaims")
    return {
        "score": max(1, min(10, score)),
        "approved": score >= MIN_SCRIPT_SCORE,
        "reason": ", ".join(issues) if issues else "heuristic checks passed",
    }

def ai_review_script(script: str, title: str, context: str) -> Dict[str, Any]:
    """Model critic: approve/reject a script before video generation."""
    prompt = f"""You are a strict cybersecurity Shorts editor.
Review this script for factual caution, hook strength, clarity, length, and fit to the source.
Return ONLY compact JSON with keys: score (1-10), approved (true/false), reason.

Title: {title}
Context: {context[:700]}
Script: {script}
"""
    try:
        r = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=60,
        )
        r.raise_for_status()
        response = r.json().get("response", "").strip()
        match = re.search(r"\{.*\}", response, flags=re.S)
        data = json.loads(match.group(0) if match else response)
        score = int(data.get("score", 0))
        return {
            "score": max(1, min(10, score)),
            "approved": bool(data.get("approved", score >= MIN_SCRIPT_SCORE)),
            "reason": str(data.get("reason", ""))[:240],
        }
    except Exception as e:
        log.warning(f"AI script review failed: {e}")
        return heuristic_script_review(script, title, context)

def generate_script_with_review(title: str, context: str) -> Tuple[str, Dict[str, Any]]:
    """Generate, critique, and revise a script before committing to TTS."""
    best_script = ""
    best_review = {"score": 0, "approved": False, "reason": "not generated"}
    revision_context = context

    for attempt in range(1, SCRIPT_RETRY_ATTEMPTS + 2):
        script = normalize_script(generate_script(title, revision_context))
        review = ai_review_script(script, title, context)
        log.info(f"Script review attempt {attempt}: score={review['score']} approved={review['approved']} reason={review['reason']}")
        if review["score"] > best_review["score"]:
            best_script, best_review = script, review
        if review["approved"] and review["score"] >= MIN_SCRIPT_SCORE:
            return script, review
        revision_context = (
            f"{context[:400]}\n\nPrevious script was rejected because: {review['reason']}.\n"
            "Rewrite with fewer claims, stronger hook, and exact CTA."
        )

    best_review["approved"] = best_review["score"] >= max(5, MIN_SCRIPT_SCORE - 2)
    return best_script or normalize_script(_static_script(title)), best_review

async def _tts_edge(text: str, path: str) -> bool:
    try:
        import edge_tts
    except ImportError:
        subprocess.run(["pip", "install", "edge-tts"], capture_output=True)
        import edge_tts

    voice, rate = random.choice(TTS_VOICES)
    log.info(f"edge-tts: {voice} @ {rate}")
    try:
        await edge_tts.Communicate(text, voice, rate=rate).save(path)
        log.info(f"Voiceover saved → {path}")
        return True
    except Exception as e:
        log.warning(f"edge-tts failed: {e}")
        return False

def _tts_pyttsx3(text: str, path: str) -> bool:
    log.info("Trying pyttsx3 (offline fallback)...")
    try:
        import pyttsx3
    except ImportError:
        subprocess.run(["pip", "install", "pyttsx3"], capture_output=True)
        try:
            import pyttsx3
        except Exception:
            log.error("pyttsx3 install failed")
            return False
    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", 165)
        voices = engine.getProperty("voices")
        if voices:
            engine.setProperty("voice", random.choice(voices[:4]).id)
        engine.save_to_file(text, path)
        engine.runAndWait()
        log.info(f"Voiceover (pyttsx3) saved → {path}")
        return True
    except Exception as e:
        log.error(f"pyttsx3 failed: {e}")
        return False

async def generate_voiceover(text: str, path: str) -> bool:
    if await _tts_edge(text, path):
        return True
    return _tts_pyttsx3(text, path)

# ─────────────────────────────────────────────────────────────
# STOCK FOOTAGE (with AI-generated terms)
# ─────────────────────────────────────────────────────────────
def get_stock_video(search_terms: List[str]) -> Optional[str]:
    """Fetch faceless stock video using AI-generated search terms."""
    if not PEXELS_API_KEY:
        log.warning("PEXELS_API_KEY not set — no footage")
        return None

    log.info(f"Searching Pexels with terms: {search_terms}")
    for query in search_terms:
        try:
            r = requests.get(
                "https://api.pexels.com/videos/search"
                f"?query={query}&per_page=15&orientation=portrait&min_width=1080&min_height=1920",
                headers={"Authorization": PEXELS_API_KEY},
                timeout=10,
            )
            r.raise_for_status()
            videos = r.json().get("videos", [])
            random.shuffle(videos)

            for v in videos:
                if any(w in v.get("url", "").lower() for w in FACE_WORDS):
                    continue
                for vf in v.get("video_files", []):
                    if vf.get("height", 0) >= 720 and vf.get("file_type") == "video/mp4":
                        log.info(f"Found video for query '{query}'")
                        return vf["link"]
        except Exception as e:
            log.warning(f"Pexels search failed for '{query}': {e}")

    log.warning("No stock footage found — will use solid colour background")
    return None

def download_file(url: str, dest: str) -> bool:
    try:
        r = requests.get(url, stream=True, timeout=60)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        log.info(f"Downloaded → {dest}")
        return True
    except Exception as e:
        log.error(f"Download failed: {e}")
        return False

# ─────────────────────────────────────────────────────────────
# AUDIO DURATION
# ─────────────────────────────────────────────────────────────
def get_audio_duration(audio_path: str) -> float:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ],
            capture_output=True, text=True, timeout=15,
        )
        dur = float(result.stdout.strip())
        log.info(f"Audio duration: {dur:.2f}s")
        return dur
    except Exception as e:
        log.warning(f"ffprobe failed: {e} — defaulting to 60s")
        return 60.0

# ─────────────────────────────────────────────────────────────
# VIDEO ASSEMBLY (single clip looped)
# ─────────────────────────────────────────────────────────────
def is_valid_video(file_path: str) -> bool:
    """Check if video file is readable and has video stream."""
    if not os.path.exists(file_path):
        return False
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1:nokey=1",
                file_path,
            ],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0 and "video" in result.stdout.lower()
    except Exception:
        return False

def assemble_video(video_path: Optional[str], audio_path: str, output_path: str) -> bool:
    """Merge stock footage + voiceover with better error handling."""
    log.info("Assembling video with FFmpeg...")
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except FileNotFoundError:
        log.error("FFmpeg not installed")
        return False

    audio_dur = get_audio_duration(audio_path)
    valid_video = False

    if video_path and is_valid_video(video_path):
        valid_video = True
        try:
            res = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path],
                capture_output=True, text=True, timeout=10,
            )
            vid_dur = float(res.stdout.strip()) if res.stdout else 0
            if vid_dur < 0.5:
                log.warning(f"Video duration too short ({vid_dur}s), using fallback")
                valid_video = False
        except Exception:
            pass

    if valid_video:
        reencoded = str(Path(video_path).parent / f"reencoded_{Path(video_path).name}")
        if reencode_video(video_path, reencoded):
            video_path = reencoded
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-vf", f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,crop={VIDEO_WIDTH}:{VIDEO_HEIGHT}",
            "-t", str(audio_dur),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-ac", "2",
            "-r", "30",
            "-movflags", "+faststart",
            output_path,
        ]
    else:
        log.warning("No valid footage — using solid colour background")
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x0a0a0a:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:d={int(audio_dur)+2}",
            "-i", audio_path,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-t", str(audio_dur),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-ac", "2",
            "-r", "30",
            "-movflags", "+faststart",
            output_path,
        ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        if res.returncode == 0:
            mb = os.path.getsize(output_path) / 1e6
            log.info(f"Video assembled → {output_path} ({mb:.1f} MB, {audio_dur:.1f}s)")
            _verify_audio_stream(output_path)
            return True
        else:
            log.error(f"FFmpeg failed (code {res.returncode}):\n{res.stderr[-800:]}")
            if valid_video:
                log.info("Retrying with solid colour background...")
                return assemble_video(None, audio_path, output_path)
            return False
    except subprocess.TimeoutExpired:
        log.error(f"FFmpeg timed out after 90 seconds")
        if valid_video:
            log.info("Timeout likely due to corrupted video. Retrying with solid background...")
            return assemble_video(None, audio_path, output_path)
        return False
    except Exception as e:
        log.error(f"FFmpeg exception: {e}")
        return False

def reencode_video(input_path: str, output_path: str) -> bool:
    """Re-encode video to a clean format (avoids looping/timeout issues)."""
    try:
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-vf", "fps=30", "-an",
            output_path
        ]
        subprocess.run(cmd, check=True, timeout=60)
        log.info(f"Re-encoded video: {output_path}")
        return True
    except Exception as e:
        log.warning(f"Re-encode failed: {e}")
        return False

def _verify_audio_stream(video_path: str):
    try:
        res = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_name",
                "-of", "default=noprint_wrappers=1",
                video_path,
            ],
            capture_output=True, text=True, timeout=15,
        )
        if res.stdout.strip():
            log.info("Audio stream verified in output")
        else:
            log.error("NO AUDIO STREAM found in assembled video!")
    except Exception as e:
        log.warning(f"Audio verification failed: {e}")

# ─────────────────────────────────────────────────────────────
# YOUTUBE AUTHENTICATION (with robust token refresh)
# ─────────────────────────────────────────────────────────────
def get_youtube_credentials():
    """Get valid YouTube credentials, handling token refresh and expiry.
    
    Returns credentials or None if authentication fails.
    Automatically handles:
    - Expired access tokens (refreshes using refresh_token)
    - Expired refresh tokens (prompts for re-authentication)
    - Missing tokens (prompts for authentication)
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
    
    creds = None
    
    # Try to load existing credentials
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
            log.info("Loaded existing credentials from token.json")
        except Exception as e:
            log.warning(f"Could not load token.json: {e}")
            creds = None
    
    # Check if credentials are valid
    if creds and creds.valid:
        log.info("Credentials are valid")
        return creds
    
    # Try to refresh expired credentials
    if creds and creds.expired and creds.refresh_token:
        log.info("Access token expired, attempting refresh...")
        try:
            creds.refresh(Request())
            # Save refreshed credentials
            TOKEN_FILE.write_text(creds.to_json())
            log.info("✅ Token refreshed successfully")
            return creds
        except Exception as e:
            error_str = str(e).lower()
            if "token has been expired or revoked" in error_str or "invalid_grant" in error_str:
                log.warning("⚠️ Refresh token expired or revoked. Need to re-authenticate.")
                # Delete the old token file
                TOKEN_FILE.unlink(missing_ok=True)
                creds = None
            else:
                log.error(f"Token refresh failed: {e}")
                return None
    
    # Need to authenticate from scratch
    if not creds:
        if not CREDENTIALS_FILE.exists():
            log.error("credentials.json not found — cannot authenticate")
            return None
        
        log.info("🔐 Starting OAuth flow for YouTube authentication...")
        log.info("A browser window will open. Please authorize the application.")
        
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), 
                SCOPES,
                redirect_uri='urn:ietf:wg:oauth:2.0:oob'  # For headless environments
            )
            
            # Try local server first, fall back to console if needed
            try:
                creds = flow.run_local_server(
                    port=0, 
                    authorization_prompt_message='Please visit this URL: {url}',
                    success_message='Authorization complete! You may close this window.',
                    open_browser=True
                )
            except Exception:
                # Fallback for headless environments
                log.info("Local server failed, using console flow...")
                creds = flow.run_console()
            
            # Save the new credentials
            TOKEN_FILE.write_text(creds.to_json())
            log.info("✅ New credentials saved to token.json")
            return creds
            
        except Exception as e:
            log.error(f"OAuth flow failed: {e}")
            return None
    
    return creds

def check_token_expiry() -> Dict:
    """Check token status and return info about expiry."""
    info = {
        "exists": TOKEN_FILE.exists(),
        "valid": False,
        "expires_at": None,
        "refresh_token_present": False,
        "needs_reauth": False,
    }
    
    if not TOKEN_FILE.exists():
        info["needs_reauth"] = True
        return info
    
    try:
        token_data = json.loads(TOKEN_FILE.read_text())
        info["refresh_token_present"] = bool(token_data.get("refresh_token"))
        
        # Check expiry
        expiry = token_data.get("expiry")
        if expiry:
            expiry_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            info["expires_at"] = expiry_dt.isoformat()
            info["valid"] = datetime.now(expiry_dt.tzinfo) < expiry_dt
        
        # If no refresh token, will need reauth when access token expires
        if not info["refresh_token_present"] and not info["valid"]:
            info["needs_reauth"] = True
            
    except Exception as e:
        log.warning(f"Could not parse token.json: {e}")
        info["needs_reauth"] = True
    
    return info

# ─────────────────────────────────────────────────────────────
# YOUTUBE UPLOAD (with scheduling and quota handling)
# ─────────────────────────────────────────────────────────────
def upload_youtube_scheduled(video_path: str, title: str, description: str, publish_time: datetime) -> Tuple[bool, bool]:
    """Upload to YouTube with scheduled publish time.
    
    Returns: (success, quota_exceeded)
    - (True, False) = Upload successful
    - (False, True) = Quota exceeded, should stop trying
    - (False, False) = Other error, can retry
    """
    log.info(f"Uploading to YouTube (scheduled for {publish_time.strftime('%H:%M IST')})...")

    # Check quota cooldown
    can_upload, cooldown_until = check_quota_cooldown()
    if not can_upload:
        log.warning(f"⚠️ YouTube quota cooldown active until {cooldown_until.strftime('%Y-%m-%d %H:%M')}")
        return False, True

    if not CREDENTIALS_FILE.exists():
        log.warning("credentials.json not found — skipping upload")
        return False, False

    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from googleapiclient.errors import HttpError

        # Get credentials using robust handler
        creds = get_youtube_credentials()
        if not creds:
            log.error("Could not obtain valid YouTube credentials")
            return False, False

        yt = build("youtube", "v3", credentials=creds)

        # Convert IST to UTC (IST = UTC+5:30)
        publish_utc = publish_time - timedelta(hours=5, minutes=30)
        publish_rfc = publish_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        body = {
            "snippet": {
                "title": f"🔒 {title[:90]}",
                "description": f"{description}\n\n#cybersecurity #shorts #hackernews #infosec",
                "categoryId": "28",
                "tags": ["cybersecurity", "hacking", "shorts", "infosec"],
            },
            "status": {
                "privacyStatus": "private",
                "publishAt": publish_rfc,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(video_path, mimetype="video/mp4", chunksize=4*1024*1024, resumable=True)
        request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                log.info(f"Upload progress: {int(status.progress()*100)}%")

        vid_id = response.get("id", "unknown")
        log.info(f"✅ Scheduled → https://youtu.be/{vid_id} will go live at {publish_time.strftime('%Y-%m-%d %H:%M IST')}")
        return True, False

    except HttpError as e:
        error_reason = ""
        try:
            error_details = json.loads(e.content.decode())
            error_reason = error_details.get("error", {}).get("errors", [{}])[0].get("reason", "")
        except:
            error_reason = str(e)
        
        if "uploadLimitExceeded" in str(e) or error_reason == "uploadLimitExceeded":
            log.error("🚫 YouTube upload quota exceeded!")
            log.info("YouTube limits new/unverified channels to ~15 videos per day.")
            log.info("Setting 24-hour cooldown...")
            set_quota_cooldown(hours=24)
            return False, True
        
        elif "quotaExceeded" in str(e) or error_reason == "quotaExceeded":
            log.error("🚫 YouTube API quota exceeded!")
            log.info("Daily API quota limit reached. Resets at midnight Pacific Time.")
            set_quota_cooldown(hours=24)
            return False, True
        
        elif "forbidden" in str(e).lower() or error_reason in ["forbidden", "accessNotConfigured"]:
            log.error(f"🚫 YouTube API access forbidden: {e}")
            log.info("Check that YouTube Data API is enabled in Google Cloud Console.")
            return False, False
        
        else:
            log.error(f"YouTube HTTP error: {e}")
            return False, False

    except Exception as e:
        log.error(f"YouTube upload failed: {e}")
        return False, False

# ─────────────────────────────────────────────────────────────
# CLEANUP (improved)
# ─────────────────────────────────────────────────────────────
def cleanup_video_files(video_files: List[str]):
    """Delete specific video-related files after successful upload."""
    for f in video_files:
        try:
            path = Path(f)
            if path.exists():
                path.unlink()
                log.info(f"🗑️ Deleted: {path.name}")
        except Exception as e:
            log.warning(f"Could not delete {f}: {e}")

def cleanup_output_dir(keep_final: int = 0, keep_days: int = 1):
    """Clean up output directory.
    
    Args:
        keep_final: Number of final videos to keep (0 = delete all)
        keep_days: Keep files newer than this many days
    """
    now = datetime.now()
    cutoff = now - timedelta(days=keep_days)
    
    all_files = list(OUTPUT_DIR.glob("*"))
    
    # Separate final videos from intermediate files
    final_videos = sorted(
        [f for f in all_files if f.name.startswith("cyber_short_")],
        key=os.path.getctime,
        reverse=True
    )
    intermediate_files = [f for f in all_files if not f.name.startswith("cyber_short_")]
    
    # Delete all intermediate files (raw_, voice_, reencoded_)
    for f in intermediate_files:
        try:
            f.unlink()
            log.info(f"🗑️ Deleted intermediate: {f.name}")
        except Exception as e:
            log.warning(f"Could not delete {f.name}: {e}")
    
    # Keep only the specified number of final videos
    if keep_final > 0:
        for f in final_videos[keep_final:]:
            try:
                f.unlink()
                log.info(f"🗑️ Deleted old video: {f.name}")
            except Exception as e:
                log.warning(f"Could not delete {f.name}: {e}")
    else:
        # Delete all final videos too
        for f in final_videos:
            try:
                # Only delete if older than cutoff
                file_time = datetime.fromtimestamp(os.path.getctime(f))
                if file_time < cutoff:
                    f.unlink()
                    log.info(f"🗑️ Deleted old video: {f.name}")
            except Exception as e:
                log.warning(f"Could not delete {f.name}: {e}")

def cleanup(keep: int = 20):
    """Legacy cleanup function for backwards compatibility."""
    files = sorted(OUTPUT_DIR.glob("*"), key=os.path.getctime)
    for f in files[:-keep]:
        try:
            f.unlink()
            log.info(f"Deleted old file: {f.name}")
        except Exception as e:
            log.warning(f"Could not delete {f.name}: {e}")

# ─────────────────────────────────────────────────────────────
# MAIN PIPELINE (multi-video with quota handling)
# ─────────────────────────────────────────────────────────────
def run_legacy() -> bool:
    """Create VIDEOS_PER_RUN videos in one go, schedule each at different times."""
    log.info("=" * 60)
    log.info(f"CYBER SHORTS BOT v7 — creating {VIDEOS_PER_RUN} videos")
    log.info(f"Ollama : {OLLAMA_MODEL} @ {OLLAMA_HOST}")
    log.info(f"Gemini : {'SET' if GEMINI_API_KEY else 'not set'}")
    log.info(f"Pexels : {'SET' if PEXELS_API_KEY else 'not set'}")
    log.info("=" * 60)

    # Check quota status before starting
    can_upload, cooldown_until = check_quota_cooldown()
    if not can_upload:
        log.warning(f"⚠️ YouTube quota cooldown active until {cooldown_until.strftime('%Y-%m-%d %H:%M')}")
        log.info("Will create videos but skip uploads until cooldown expires.")

    # Check token status
    token_info = check_token_expiry()
    if token_info["needs_reauth"]:
        log.warning("⚠️ YouTube token needs re-authentication")
        log.info("Will attempt to authenticate during first upload...")

    base_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    now_ist = datetime.now()
    today = now_ist.date()

    # Build schedule datetimes
    schedule_datetimes = []
    for time_str in SCHEDULE_TIMES:
        hour, minute = map(int, time_str.split(':'))
        scheduled = datetime(today.year, today.month, today.day, hour, minute)
        if scheduled <= now_ist:
            scheduled += timedelta(days=1)
        schedule_datetimes.append(scheduled)

    success_count = 0
    upload_count = 0
    quota_exceeded = False
    
    for i in range(VIDEOS_PER_RUN):
        log.info("")
        log.info(f"{'='*40}")
        log.info(f"📹 CREATING VIDEO {i+1} OF {VIDEOS_PER_RUN}")
        log.info(f"{'='*40}")

        ts = f"{base_ts}_{i+1}"
        video_files_to_cleanup = []  # Track files for this video

        # 1. Fetch story
        story = fetch_story()
        if not story:
            log.error(f"Video {i+1}: No story found — skipping")
            continue

        # 2. Article context
        context = fetch_article_text(story["url"])

        # 3. Generate script
        script = generate_script(story["title"], context)
        log.info(f"Script preview: {script[:120]}...")

        # 4. Voiceover
        voice_path = str(OUTPUT_DIR / f"voice_{ts}.mp3")
        video_files_to_cleanup.append(voice_path)
        
        if not asyncio.run(generate_voiceover(script, voice_path)):
            log.error(f"Video {i+1}: Voiceover failed")
            continue
        if not os.path.exists(voice_path):
            log.error(f"Video {i+1}: Voice file missing")
            continue

        # 5. AI generates video search terms
        search_terms = ai_generate_search_terms(story["title"], context)
        if not search_terms:
            search_terms = FALLBACK_TERMS

        # 6. Fetch stock footage
        video_url = get_stock_video(search_terms)
        raw_video = str(OUTPUT_DIR / f"raw_{ts}.mp4")
        video_files_to_cleanup.append(raw_video)
        
        if video_url:
            download_file(video_url, raw_video)
        
        # Also track re-encoded video if created
        reencoded_video = str(OUTPUT_DIR / f"reencoded_raw_{ts}.mp4")
        video_files_to_cleanup.append(reencoded_video)

        # 7. Assemble video
        final_path = str(OUTPUT_DIR / f"cyber_short_{ts}.mp4")
        if not assemble_video(
            raw_video if os.path.exists(raw_video) else None,
            voice_path,
            final_path,
        ):
            log.error(f"Video {i+1}: Assembly failed")
            cleanup_video_files(video_files_to_cleanup)
            continue

        success_count += 1

        # 8. Upload (if not in quota cooldown)
        if not quota_exceeded:
            upload_success, quota_hit = upload_youtube_scheduled(
                final_path, story["title"], script, schedule_datetimes[i]
            )
            
            if upload_success:
                upload_count += 1
                # Delete all files for this video after successful upload
                video_files_to_cleanup.append(final_path)
                cleanup_video_files(video_files_to_cleanup)
                log.info(f"✅ Video {i+1} uploaded and files cleaned up")
            elif quota_hit:
                quota_exceeded = True
                log.warning(f"⚠️ Quota exceeded — skipping remaining uploads")
                # Keep the final video since it wasn't uploaded
                cleanup_video_files([f for f in video_files_to_cleanup if f != final_path])
            else:
                # Other upload error — keep final video, clean intermediate files
                cleanup_video_files([f for f in video_files_to_cleanup if f != final_path])
        else:
            log.info(f"⏭️ Skipping upload (quota exceeded) — video saved: {final_path}")
            # Clean intermediate files only
            cleanup_video_files([f for f in video_files_to_cleanup if f != final_path])

        # Short delay between videos
        if i < VIDEOS_PER_RUN - 1:
            log.info("⏳ Waiting 10 seconds before next video...")
            import time
            time.sleep(10)

    log.info("")
    log.info("=" * 60)
    log.info(f"✅ Run complete!")
    log.info(f"   Videos created: {success_count}/{VIDEOS_PER_RUN}")
    log.info(f"   Videos uploaded: {upload_count}/{success_count}")
    if quota_exceeded:
        log.info(f"   ⚠️ YouTube quota exceeded — remaining videos saved locally")
    log.info("=" * 60)
    
    return success_count > 0

# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────
def build_schedule_datetimes(count: int) -> List[datetime]:
    """Build publish slots in IST for the current batch."""
    now_ist = datetime.now()
    today = now_ist.date()
    schedule_datetimes = []
    for time_str in SCHEDULE_TIMES:
        hour, minute = map(int, time_str.split(':'))
        scheduled = datetime(today.year, today.month, today.day, hour, minute)
        if scheduled <= now_ist:
            scheduled += timedelta(days=1)
        schedule_datetimes.append(scheduled)

    while len(schedule_datetimes) < count and schedule_datetimes:
        schedule_datetimes.append(schedule_datetimes[-len(SCHEDULE_TIMES)] + timedelta(days=1))
    return schedule_datetimes[:count]

def process_video_job(job: VideoJob, index: int, total: int, ts: str) -> Tuple[bool, List[str]]:
    """Run autonomous create stages for one planned job."""
    story = job.story
    title = story["title"]
    video_files_to_cleanup: List[str] = []

    log.info("")
    log.info(f"{'='*40}")
    log.info(f"CREATING VIDEO {index} OF {total}")
    log.info(f"Story: {title[:110]}")
    log.info(f"Agent reason: {job.reason}")
    log.info(f"{'='*40}")

    try:
        job.touch("fetching_context")
        upsert_job(job)
        context = retry_call("article fetch", lambda: fetch_article_text(story.get("url", "")), attempts=NETWORK_RETRIES)
        job.context_chars = len(context or "")

        job.touch("scripting")
        upsert_job(job)
        script, review = generate_script_with_review(title, context or "")
        job.script = script
        job.script_score = int(review.get("score", 0))
        job.script_review = review.get("reason", "")
        if not review.get("approved", False):
            job.fail(f"Script rejected: score={job.script_score} reason={job.script_review}")
            upsert_job(job)
            return False, video_files_to_cleanup
        log.info(f"Script preview: {script[:120]}...")

        job.touch("voiceover")
        upsert_job(job)
        voice_path = str(OUTPUT_DIR / f"voice_{ts}.mp3")
        job.voice_path = voice_path
        video_files_to_cleanup.append(voice_path)
        if not asyncio.run(generate_voiceover(script, voice_path)):
            job.fail("Voiceover failed")
            upsert_job(job)
            return False, video_files_to_cleanup
        if not os.path.exists(voice_path):
            job.fail("Voice file missing")
            upsert_job(job)
            return False, video_files_to_cleanup

        audio_duration = get_audio_duration(voice_path)
        if audio_duration > 55 and SCRIPT_RETRY_ATTEMPTS > 0:
            log.warning(f"Voiceover is long ({audio_duration:.1f}s). Regenerating shorter script once.")
            shorter_context = f"{context[:400]}\n\nMake the script shorter. Target 30 seconds."
            script, review = generate_script_with_review(title, shorter_context)
            job.script = script
            job.script_score = int(review.get("score", 0))
            job.script_review = f"shortened after long audio: {review.get('reason', '')}"
            upsert_job(job)
            if asyncio.run(generate_voiceover(script, voice_path)):
                get_audio_duration(voice_path)

        job.touch("footage")
        upsert_job(job)
        search_terms = ai_generate_search_terms(title, context or "")
        job.search_terms = search_terms or FALLBACK_TERMS.copy()
        raw_video = str(OUTPUT_DIR / f"raw_{ts}.mp4")
        job.raw_video_path = raw_video
        video_files_to_cleanup.append(raw_video)

        video_url = get_stock_video(job.search_terms)
        if video_url:
            ok = False
            for attempt in range(1, NETWORK_RETRIES + 1):
                ok = download_file(video_url, raw_video)
                if ok:
                    break
                if attempt < NETWORK_RETRIES:
                    time.sleep(2 * attempt)
            if not ok:
                log.warning("Stock video download failed. Continuing with generated background.")

        reencoded_video = str(OUTPUT_DIR / f"reencoded_raw_{ts}.mp4")
        video_files_to_cleanup.append(reencoded_video)

        job.touch("assembling")
        upsert_job(job)
        final_path = str(OUTPUT_DIR / f"cyber_short_{ts}.mp4")
        job.final_video_path = final_path
        if not assemble_video(raw_video if os.path.exists(raw_video) else None, voice_path, final_path):
            job.fail("Assembly failed")
            upsert_job(job)
            return False, video_files_to_cleanup

        job.touch("created")
        upsert_job(job)
        mark_used_title(title)
        return True, video_files_to_cleanup

    except Exception as e:
        job.fail(f"Unhandled job error: {e}")
        upsert_job(job)
        log.error(f"Video {index}: unhandled job error: {e}")
        return False, video_files_to_cleanup

def run_upload_only() -> bool:
    """Upload all locally created videos that were skipped (upload_skipped status)."""
    log.info("=" * 60)
    log.info("UPLOAD-ONLY MODE — scanning job memory for pending uploads")
    log.info("=" * 60)

    can_upload, cooldown_until = check_quota_cooldown()
    if not can_upload:
        log.error(f"Quota cooldown active until {cooldown_until.strftime('%Y-%m-%d %H:%M')} — aborting")
        return False

    jobs = load_job_memory()
    pending = [
        VideoJob.from_dict(j) for j in jobs
        if j.get("status") == "upload_skipped"
        and j.get("final_video_path")
        and Path(j["final_video_path"]).exists()
    ]

    if not pending:
        log.info("No pending videos found (status=upload_skipped with existing file).")
        return False

    log.info(f"Found {len(pending)} video(s) to upload.")
    schedule_datetimes = build_schedule_datetimes(len(pending))
    upload_count = 0
    quota_exceeded = False

    for i, job in enumerate(pending):
        if quota_exceeded:
            log.warning(f"Quota exceeded — skipping remaining {len(pending) - i} video(s)")
            break

        log.info(f"[{i+1}/{len(pending)}] Uploading: {job.story.get('title')}")
        upload_success, quota_hit = upload_youtube_scheduled(
            job.final_video_path, job.story["title"], job.script, schedule_datetimes[i]
        )
        if upload_success:
            upload_count += 1
            job.uploaded = True
            job.upload_skipped = False
            job.touch("uploaded")
            upsert_job(job)
            Path(job.final_video_path).unlink(missing_ok=True)
            log.info(f"Uploaded and cleaned up: {job.final_video_path}")
        elif quota_hit:
            quota_exceeded = True
            log.warning("YouTube quota exceeded — stopping uploads")
        else:
            log.error(f"Upload failed for: {job.story.get('title')} — file kept locally")

    log.info("=" * 60)
    log.info(f"Upload-only run complete: {upload_count}/{len(pending)} uploaded")
    log.info("=" * 60)
    return upload_count > 0


def run(plan_only: bool = False, create_only: bool = False) -> bool:
    """Create a planned batch of videos, with persistent agent state."""
    log.info("=" * 60)
    log.info(f"CYBER SHORTS BOT v7 Agentic - planning {VIDEOS_PER_RUN} videos")
    log.info(f"Ollama : {OLLAMA_MODEL} @ {OLLAMA_HOST}")
    log.info(f"Gemini : {'SET' if GEMINI_API_KEY else 'not set'}")
    log.info(f"Pexels : {'SET' if PEXELS_API_KEY else 'not set'}")
    log.info("=" * 60)

    can_upload, cooldown_until = check_quota_cooldown()
    if not can_upload:
        log.warning(f"Quota cooldown active until {cooldown_until.strftime('%Y-%m-%d %H:%M')}")
        log.info("Will create videos but skip uploads until cooldown expires.")

    token_info = check_token_expiry()
    if token_info["needs_reauth"] and not create_only and not plan_only:
        log.warning("YouTube token needs re-authentication")
        log.info("Will attempt to authenticate during first upload...")

    jobs = plan_video_jobs(VIDEOS_PER_RUN)
    if plan_only:
        for idx, job in enumerate(jobs, 1):
            log.info(f"PLAN {idx}: [{job.category}] score={job.score} {job.story.get('title')}")
        return bool(jobs)
    if not jobs:
        log.error("No jobs planned")
        return False

    base_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    schedule_datetimes = build_schedule_datetimes(len(jobs))
    success_count = 0
    upload_count = 0
    quota_exceeded = False

    for i, job in enumerate(jobs):
        ts = f"{base_ts}_{i+1}"
        created, video_files_to_cleanup = process_video_job(job, i + 1, len(jobs), ts)
        if not created:
            cleanup_video_files(video_files_to_cleanup)
            continue

        success_count += 1
        job.scheduled_for = schedule_datetimes[i].isoformat(timespec="seconds")
        upsert_job(job)

        if create_only:
            job.upload_skipped = True
            job.touch("upload_skipped")
            upsert_job(job)
            cleanup_video_files([f for f in video_files_to_cleanup if f != job.final_video_path])
            log.info(f"Create-only mode - video saved: {job.final_video_path}")
        elif not quota_exceeded:
            upload_success, quota_hit = upload_youtube_scheduled(
                job.final_video_path, job.story["title"], job.script, schedule_datetimes[i]
            )
            if upload_success:
                upload_count += 1
                job.uploaded = True
                job.touch("uploaded")
                upsert_job(job)
                video_files_to_cleanup.append(job.final_video_path)
                cleanup_video_files(video_files_to_cleanup)
                log.info(f"Video {i+1} uploaded and files cleaned up")
            elif quota_hit:
                quota_exceeded = True
                job.upload_skipped = True
                job.touch("upload_skipped")
                upsert_job(job)
                log.warning("Quota exceeded - skipping remaining uploads")
                cleanup_video_files([f for f in video_files_to_cleanup if f != job.final_video_path])
            else:
                job.errors.append("Upload failed; final video kept locally")
                job.touch("created")
                upsert_job(job)
                cleanup_video_files([f for f in video_files_to_cleanup if f != job.final_video_path])
        else:
            job.upload_skipped = True
            job.touch("upload_skipped")
            upsert_job(job)
            log.info(f"Skipping upload - video saved: {job.final_video_path}")
            cleanup_video_files([f for f in video_files_to_cleanup if f != job.final_video_path])

        if i < len(jobs) - 1:
            log.info("Waiting 10 seconds before next video...")
            time.sleep(10)

    log.info("")
    log.info("=" * 60)
    log.info("Run complete")
    log.info(f"   Videos created: {success_count}/{len(jobs)}")
    log.info(f"   Videos uploaded: {upload_count}/{success_count}")
    if quota_exceeded:
        log.info("   YouTube quota exceeded - remaining videos saved locally")
    log.info("=" * 60)
    return success_count > 0

if __name__ == "__main__":
    import argparse
    import time

    p = argparse.ArgumentParser(description="Cyber Shorts Bot v7 (Agentic)")
    p.add_argument("--mode", choices=["once", "loop"], default="once",
                   help="once = single run | loop = run every 24h")
    p.add_argument("--setup", action="store_true", help="Install dependencies")
    p.add_argument("--verify", metavar="VIDEO", help="Check audio stream in video")
    p.add_argument("--check-token", action="store_true", help="Check YouTube token status")
    p.add_argument("--refresh-token", action="store_true", help="Force re-authentication")
    p.add_argument("--check-quota", action="store_true", help="Check YouTube quota status")
    p.add_argument("--clear-quota", action="store_true", help="Clear quota cooldown (use with caution)")
    p.add_argument("--cleanup", action="store_true", help="Clean up output directory")
    p.add_argument("--plan-only", action="store_true", help="Only plan and score stories; do not create videos")
    p.add_argument("--create-only", action="store_true", help="Create videos and keep them locally; skip uploads")
    p.add_argument("--upload-only", action="store_true", help="Upload all locally saved videos that were previously skipped")
    p.add_argument("--legacy-run", action="store_true", help="Run the old one-story-at-a-time pipeline")
    args = p.parse_args()

    if args.setup:
        log.info("Installing dependencies...")
        subprocess.run([
            "pip", "install",
            "requests", "edge-tts", "python-dotenv", "pyttsx3",
            "google-api-python-client", "google-auth-oauthlib",
        ])
        log.info("Done! Create a .env file with:")
        log.info("  OLLAMA_MODEL=llama3.2")
        log.info("  OLLAMA_HOST=http://localhost:11434")
        log.info("  PEXELS_API_KEY=your_key")
        log.info("  GEMINI_API_KEY=your_key   # optional fallback")
        log.info("")
        log.info("Start Ollama: ollama serve && ollama pull llama3.2")

    elif args.verify:
        _verify_audio_stream(args.verify)

    elif args.check_token:
        info = check_token_expiry()
        log.info("YouTube Token Status:")
        log.info(f"  Exists: {info['exists']}")
        log.info(f"  Valid: {info['valid']}")
        log.info(f"  Expires at: {info['expires_at']}")
        log.info(f"  Refresh token present: {info['refresh_token_present']}")
        log.info(f"  Needs re-auth: {info['needs_reauth']}")

    elif args.refresh_token:
        log.info("Forcing re-authentication...")
        TOKEN_FILE.unlink(missing_ok=True)
        creds = get_youtube_credentials()
        if creds:
            log.info("✅ Re-authentication successful!")
        else:
            log.error("❌ Re-authentication failed")

    elif args.check_quota:
        can_upload, cooldown_until = check_quota_cooldown()
        if can_upload:
            log.info("✅ No quota cooldown active — uploads allowed")
        else:
            log.info(f"⚠️ Quota cooldown active until {cooldown_until.strftime('%Y-%m-%d %H:%M')}")

    elif args.clear_quota:
        QUOTA_STATE_FILE.unlink(missing_ok=True)
        log.info("Quota cooldown cleared")

    elif args.cleanup:
        log.info("Cleaning up output directory...")
        cleanup_output_dir(keep_final=5, keep_days=1)
        log.info("Done!")

    elif args.plan_only:
        run(plan_only=True)

    elif args.create_only:
        run(create_only=True)

    elif args.upload_only:
        run_upload_only()

    elif args.legacy_run:
        run_legacy()

    elif args.mode == "loop":
        log.info("Loop mode — runs every 24 hours")
        while True:
            run()
            log.info("Sleeping 24h until next run...")
            time.sleep(86400)

    else:
        run()
