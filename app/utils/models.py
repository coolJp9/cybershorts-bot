"""Persistent data models for the video pipeline."""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from app.config.settings import JOB_MEMORY_FILE

log = logging.getLogger("CyberBot.models")


@dataclass
class VideoJob:
    """Represents one video creation task with full lifecycle state."""

    job_id: str
    story: dict[str, Any]
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
    search_terms: list[str] = field(default_factory=list)
    voice_path: str = ""
    raw_video_path: str = ""
    final_video_path: str = ""
    scheduled_for: str = ""
    uploaded: bool = False
    upload_skipped: bool = False
    errors: list[str] = field(default_factory=list)

    def touch(self, status: str | None = None) -> None:
        if status:
            self.status = status
        self.updated_at = datetime.now().isoformat(timespec="seconds")

    def fail(self, message: str) -> None:
        self.errors.append(message)
        self.touch("failed")
        log.warning("Job %s failed: %s", self.job_id, message)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VideoJob":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


# ── Job memory persistence ─────────────────────────────────────────────────────


def load_job_memory() -> list[dict[str, Any]]:
    if not JOB_MEMORY_FILE.exists():
        return []
    try:
        data = json.loads(JOB_MEMORY_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception as exc:
        log.warning("Could not read %s: %s", JOB_MEMORY_FILE, exc)
    return []


def save_job_memory(jobs: list[dict[str, Any]]) -> None:
    try:
        JOB_MEMORY_FILE.write_text(
            json.dumps(jobs[-300:], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        log.error("Could not write %s: %s", JOB_MEMORY_FILE, exc)


def upsert_job(job: VideoJob) -> None:
    jobs = load_job_memory()
    job_data = asdict(job)
    for idx, existing in enumerate(jobs):
        if existing.get("job_id") == job.job_id:
            jobs[idx] = job_data
            save_job_memory(jobs)
            return
    jobs.append(job_data)
    save_job_memory(jobs)
