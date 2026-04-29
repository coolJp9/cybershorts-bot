"""Title-based story deduplication to avoid re-processing seen stories."""

import hashlib
import json
import logging
import re
from typing import Set

from app.config.settings import USED_FILE

log = logging.getLogger("CyberBot.dedup")


def story_hash(title: str) -> str:
    """Normalize a title and return a short MD5 fingerprint."""
    normalized = re.sub(r'\b(the|a|an|to|for|of|in|on|at)\b', '', title.lower())
    normalized = re.sub(r'[^\w\s]', '', normalized)[:80]
    return hashlib.md5(normalized.encode()).hexdigest()[:12]


def load_used_titles() -> Set[str]:
    if USED_FILE.exists():
        try:
            data = set(json.loads(USED_FILE.read_text()))
            log.info("Loaded %d used story hashes", len(data))
            return data
        except Exception as exc:
            log.warning("Could not read %s: %s", USED_FILE, exc)
    return set()


def mark_used_title(title: str) -> None:
    h = story_hash(title)
    used = load_used_titles()
    used.add(h)
    used_list = list(used)[-500:]
    try:
        USED_FILE.write_text(json.dumps(used_list))
        log.info("Marked story as used (hash=%s, total=%d)", h, len(used_list))
    except Exception as exc:
        log.error("Could not write %s: %s", USED_FILE, exc)


def completed_story_hashes() -> Set[str]:
    """Return hashes of stories that already produced a video or upload."""
    from app.utils.models import load_job_memory
    hashes: Set[str] = set()
    for job in load_job_memory():
        story = job.get("story") or {}
        title = story.get("title", "")
        if title and job.get("status") in {"created", "uploaded", "upload_skipped"}:
            hashes.add(story_hash(title))
    return hashes
