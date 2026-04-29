"""Story scoring, deduplication, category tagging, and AI batch planning."""

import logging
import re
from datetime import datetime
from typing import Dict, List, Optional

import requests

from app.config.settings import (
    CYBER_KEYWORDS,
    OLLAMA_HOST,
    OLLAMA_MODEL,
    USED_FILE,
    VIDEOS_PER_RUN,
)
from app.utils.deduplication import (
    completed_story_hashes,
    load_used_titles,
    mark_used_title,
    story_hash,
)
from app.fetchers.aggregator import fetch_all_news, fetch_article_text
from app.utils.models import VideoJob, upsert_job

log = logging.getLogger("CyberBot.selector")


# ── Category tagging ───────────────────────────────────────────────────────────

_CATEGORY_BUCKETS = [
    ("ransomware",    ["ransomware", "extortion"]),
    ("breach",        ["breach", "leak", "stolen", "exposed", "data"]),
    ("vulnerability", ["cve", "vulnerability", "zero-day", "exploit", "patch"]),
    ("malware",       ["malware", "trojan", "botnet", "spyware", "backdoor"]),
    ("privacy",       ["privacy", "surveillance", "whatsapp", "meta", "google"]),
    ("ai_security",   ["ai", "llm", "model", "prompt"]),
    ("defense",       ["security", "cybersecurity", "firewall", "encryption"]),
]


def story_category(title: str) -> str:
    t = title.lower()
    for category, needles in _CATEGORY_BUCKETS:
        if any(needle in t for needle in needles):
            return category
    return "general"


# ── Heuristic scoring ──────────────────────────────────────────────────────────

_SOURCE_BONUS: Dict[str, int] = {
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
}

_SEVERITY_WORDS = {"breach", "zero-day", "ransomware", "critical", "exploit"}


def heuristic_story_score(story: Dict) -> int:
    title = story.get("title", "")
    lower = title.lower()
    keyword_hits = sum(1 for kw in CYBER_KEYWORDS if kw in lower)
    source_bonus = _SOURCE_BONUS.get(story.get("source", ""), 0)
    hn_score = min(int(story.get("score") or 0), 300) // 10
    recency_bonus = 0
    story_time = int(story.get("time") or 0)
    if story_time:
        age_hours = max(0, (datetime.now().timestamp() - story_time) / 3600)
        recency_bonus = max(0, 24 - int(age_hours // 2))
    severity_bonus = 10 if any(w in lower for w in _SEVERITY_WORDS) else 0
    return keyword_hits * 5 + source_bonus + hn_score + recency_bonus + severity_bonus


def dedupe_stories(stories: List[Dict]) -> List[Dict]:
    """Return one entry per title hash, keeping the highest-scored copy."""
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


# ── AI batch planning ──────────────────────────────────────────────────────────

def ai_plan_story_batch(stories: List[Dict], count: int) -> List[Dict]:
    """Ask the local LLM to curate a diverse batch; fall back to heuristics."""
    if not stories:
        return []

    candidates = sorted(stories, key=lambda s: s.get("agent_score", 0), reverse=True)[:40]
    candidate_lines = [
        f"{i}. [{s['source']}] ({s['category']}, score={s['agent_score']}) {s['title']}"
        for i, s in enumerate(candidates, 1)
    ]

    prompt = (
        f"You are the planning agent for a faceless cybersecurity Shorts channel.\n"
        f"Pick {count} stories from this list for one publishing batch.\n"
        "Goals: high impact, fresh, varied topics, clear viewer hook, avoid duplicates.\n"
        "Return ONLY the story numbers in best publishing order, comma separated.\n\n"
        "Stories:\n" + "\n".join(candidate_lines)
    )

    try:
        r = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=75,
        )
        r.raise_for_status()
        response = r.json().get("response", "")
        picked: List[Dict] = []
        seen = set()
        for raw in re.findall(r"\d+", response):
            idx = int(raw) - 1
            if 0 <= idx < len(candidates) and idx not in seen:
                seen.add(idx)
                picked.append(candidates[idx])
            if len(picked) >= count:
                break
        if picked:
            log.info("AI batch planner selected %d stories", len(picked))
            return picked
    except Exception as exc:
        log.warning("AI batch planning failed: %s", exc)

    # Heuristic fallback: at most 2 stories per category
    selected: List[Dict] = []
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

    log.info("Heuristic batch planner selected %d stories", len(selected))
    return selected[:count]


def ai_pick_best_story(stories: List[Dict]) -> Optional[Dict]:
    """Ask the LLM to pick the single most impactful story."""
    if not stories:
        return None
    candidates = stories[:15]
    candidates_text = "\n".join(
        f"{i+1}. [{s['source']}] {s['title']} (score: {s['score']})"
        for i, s in enumerate(candidates)
    )
    prompt = (
        "You are a cybersecurity news editor. Pick the SINGLE most eye-catching "
        f"story from the list below.\nReturn ONLY the number (1-{len(candidates)}).\n\n"
        f"Stories:\n{candidates_text}"
    )
    try:
        r = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=60,
        )
        r.raise_for_status()
        response = r.json().get("response", "").strip()
        match = re.search(r"\d+", response)
        if match:
            idx = int(match.group()) - 1
            if 0 <= idx < len(candidates):
                log.info("AI chose story %d: %s", idx + 1, candidates[idx]["title"][:80])
                return candidates[idx]
    except Exception as exc:
        log.warning("AI story selection failed: %s", exc)

    log.info("Falling back to highest-score selection")
    return max(stories, key=lambda x: x.get("score", 0))


# ── Top-level entry points ─────────────────────────────────────────────────────

def fetch_story() -> Optional[Dict]:
    """Fetch all news and return the best unused story."""
    log.info("Fetching news from all sources...")
    used_hashes = load_used_titles()
    all_stories = fetch_all_news()
    new_stories = [s for s in all_stories if story_hash(s["title"]) not in used_hashes]

    if not new_stories:
        log.warning("No unused stories — clearing history and retrying")
        USED_FILE.unlink(missing_ok=True)
        return fetch_story()

    log.info("Found %d new stories", len(new_stories))
    story = ai_pick_best_story(new_stories)
    if not story:
        log.error("No story selected")
        return None

    mark_used_title(story["title"])
    return story


def plan_video_jobs(count: int) -> List[VideoJob]:
    """Fetch once, filter already-seen stories, and create a planned batch of jobs."""
    log.info("Agent planner: fetching candidate stories for batch of %d...", count)
    used_hashes = load_used_titles() | completed_story_hashes()
    stories = dedupe_stories(fetch_all_news())
    fresh = [s for s in stories if story_hash(s["title"]) not in used_hashes]

    if not fresh:
        log.warning("No fresh stories — clearing title hash cache and retrying")
        USED_FILE.unlink(missing_ok=True)
        used_hashes = completed_story_hashes()
        fresh = [s for s in stories if story_hash(s["title"]) not in used_hashes]

    planned = ai_plan_story_batch(fresh, count)
    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    jobs: List[VideoJob] = []
    for idx, story in enumerate(planned, 1):
        title = story["title"]
        job = VideoJob(
            job_id=f"{batch_id}_{idx}_{story_hash(title)}",
            story=story,
            reason=f"planned as {story.get('category', 'general')} (score {story.get('agent_score', 0)})",
            category=story.get("category", "general"),
            score=int(story.get("agent_score", 0)),
        )
        upsert_job(job)
        jobs.append(job)

    log.info("Agent planner created %d jobs", len(jobs))
    return jobs
