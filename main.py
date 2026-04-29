#!/usr/bin/env python3
"""
CyberShorts Bot — entry point.

Usage examples
--------------
    python main.py                     # plan + create + upload 10 videos
    python main.py --plan-only         # score stories; no video creation
    python main.py --create-only       # create videos; skip YouTube upload
    python main.py --upload-only       # upload videos previously saved locally
    python main.py --legacy-run        # run old single-story pipeline
    python main.py --mode loop         # repeat every 24 hours
    python main.py --check-token       # inspect YouTube token status
    python main.py --refresh-token     # force re-authentication
    python main.py --check-quota       # check upload quota cooldown
    python main.py --clear-quota       # clear quota cooldown flag
    python main.py --cleanup           # purge old output files
    python main.py --verify <file.mp4> # verify audio stream in a video
    python main.py --setup             # install runtime dependencies
"""

import argparse
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from app.config.settings import (
    GEMINI_API_KEY,
    OLLAMA_HOST,
    OLLAMA_MODEL,
    OUTPUT_DIR,
    PEXELS_API_KEY,
    QUOTA_STATE_FILE,
    SCHEDULE_TIMES,
    SCRIPT_RETRY_ATTEMPTS,
    TOKEN_FILE,
    VIDEOS_PER_RUN,
    configure_logging,
)
from app.fetchers.aggregator import fetch_article_text
from app.script_generator.generator import (
    ai_generate_search_terms,
    generate_script,
    generate_script_with_review,
)
from app.summarizer.story_selector import fetch_story, plan_video_jobs
from app.tts.engine import generate_voiceover_sync
from app.uploader.youtube import (
    check_quota_cooldown,
    check_token_expiry,
    get_youtube_credentials,
    upload_youtube_scheduled,
)
from app.utils.cleanup import cleanup_output_dir, cleanup_video_files
from app.utils.deduplication import mark_used_title
from app.utils.models import VideoJob, upsert_job
from app.video_engine.assembler import (
    assemble_video,
    download_file,
    get_audio_duration,
    get_stock_video,
)

log = configure_logging("CyberBot")

FALLBACK_TERMS = ["digital lock encryption", "server rack data center", "binary code matrix"]


# ── Schedule helpers ───────────────────────────────────────────────────────────


def build_schedule_datetimes(count: int) -> list[datetime]:
    """Return a list of future IST datetimes for publishing the batch."""
    now_ist = datetime.now()
    today = now_ist.date()
    slots: list[datetime] = []
    for time_str in SCHEDULE_TIMES:
        hour, minute = map(int, time_str.split(":"))
        scheduled = datetime(today.year, today.month, today.day, hour, minute)
        if scheduled <= now_ist:
            scheduled += timedelta(days=1)
        slots.append(scheduled)

    # If we need more slots than one day provides, roll over to subsequent days
    while len(slots) < count and slots:
        slots.append(slots[-len(SCHEDULE_TIMES)] + timedelta(days=1))
    return slots[:count]


# ── Single-job processor ───────────────────────────────────────────────────────


def process_video_job(job: VideoJob, index: int, total: int, ts: str) -> tuple[bool, list[str]]:
    """Execute all creation stages for one planned job.

    Returns (success, list_of_intermediate_files_to_clean).
    """
    story = job.story
    title = story["title"]
    cleanup_files: list[str] = []

    log.info("")
    log.info("=" * 40)
    log.info("CREATING VIDEO %d OF %d", index, total)
    log.info("Story: %s", title[:110])
    log.info("Reason: %s", job.reason)
    log.info("=" * 40)

    try:
        # 1. Fetch article context
        job.touch("fetching_context")
        upsert_job(job)
        context = fetch_article_text(story.get("url", "")) or ""
        job.context_chars = len(context)

        # 2. Generate & review script
        job.touch("scripting")
        upsert_job(job)
        script, review = generate_script_with_review(title, context)
        job.script = script
        job.script_score = int(review.get("score", 0))
        job.script_review = review.get("reason", "")
        if not review.get("approved", False):
            job.fail(f"Script rejected: score={job.script_score} reason={job.script_review}")
            upsert_job(job)
            return False, cleanup_files
        log.info("Script preview: %s...", script[:120])

        # 3. Voiceover
        job.touch("voiceover")
        upsert_job(job)
        voice_path = str(OUTPUT_DIR / f"voice_{ts}.mp3")
        job.voice_path = voice_path
        cleanup_files.append(voice_path)
        if not generate_voiceover_sync(script, voice_path):
            job.fail("Voiceover generation failed")
            upsert_job(job)
            return False, cleanup_files
        if not Path(voice_path).exists():
            job.fail("Voice file missing after generation")
            upsert_job(job)
            return False, cleanup_files

        # Regenerate if audio is too long
        audio_dur = get_audio_duration(voice_path)
        if audio_dur > 55 and SCRIPT_RETRY_ATTEMPTS > 0:
            log.warning("Voiceover too long (%.1fs) — regenerating shorter script", audio_dur)
            shorter_context = f"{context[:400]}\n\nMake the script shorter. Target 30 seconds."
            script, review = generate_script_with_review(title, shorter_context)
            job.script = script
            job.script_score = int(review.get("score", 0))
            job.script_review = f"shortened: {review.get('reason', '')}"
            upsert_job(job)
            generate_voiceover_sync(script, voice_path)
            get_audio_duration(voice_path)

        # 4. Stock footage
        job.touch("footage")
        upsert_job(job)
        search_terms = ai_generate_search_terms(title, context) or FALLBACK_TERMS.copy()
        job.search_terms = search_terms
        raw_video = str(OUTPUT_DIR / f"raw_{ts}.mp4")
        job.raw_video_path = raw_video
        cleanup_files.append(raw_video)
        cleanup_files.append(str(OUTPUT_DIR / f"reencoded_raw_{ts}.mp4"))

        video_url = get_stock_video(search_terms)
        if video_url:
            for attempt in range(1, 3):
                if download_file(video_url, raw_video):
                    break
                time.sleep(2 * attempt)

        # 5. Assemble
        job.touch("assembling")
        upsert_job(job)
        final_path = str(OUTPUT_DIR / f"cyber_short_{ts}.mp4")
        job.final_video_path = final_path
        raw_exists = Path(raw_video).exists()
        if not assemble_video(raw_video if raw_exists else None, voice_path, final_path):
            job.fail("Video assembly failed")
            upsert_job(job)
            return False, cleanup_files

        job.touch("created")
        upsert_job(job)
        mark_used_title(title)
        return True, cleanup_files

    except Exception as exc:
        job.fail(f"Unhandled error: {exc}")
        upsert_job(job)
        log.error("Video %d: unhandled error: %s", index, exc)
        return False, cleanup_files


# ── Main pipeline ──────────────────────────────────────────────────────────────


def run(plan_only: bool = False, create_only: bool = False) -> bool:
    """Plan a batch of videos, create them, and optionally upload."""
    log.info("=" * 60)
    log.info("CYBER SHORTS BOT v7 Agentic — batch of %d", VIDEOS_PER_RUN)
    log.info("Ollama : %s @ %s", OLLAMA_MODEL, OLLAMA_HOST)
    log.info("Gemini : %s", "SET" if GEMINI_API_KEY else "not set")
    log.info("Pexels : %s", "SET" if PEXELS_API_KEY else "not set")
    log.info("=" * 60)

    can_upload, cooldown_until = check_quota_cooldown()
    if not can_upload:
        log.warning("Quota cooldown active until %s", cooldown_until.strftime("%Y-%m-%d %H:%M"))

    token_info = check_token_expiry()
    if token_info["needs_reauth"] and not create_only and not plan_only:
        log.warning("YouTube token needs re-authentication (will prompt on first upload)")

    jobs = plan_video_jobs(VIDEOS_PER_RUN)
    if plan_only:
        for idx, job in enumerate(jobs, 1):
            log.info(
                "PLAN %d: [%s] score=%d %s", idx, job.category, job.score, job.story.get("title")
            )
        return bool(jobs)

    if not jobs:
        log.error("No jobs planned — aborting")
        return False

    base_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    schedule_slots = build_schedule_datetimes(len(jobs))
    success_count = upload_count = 0
    quota_exceeded = False

    for i, job in enumerate(jobs):
        ts = f"{base_ts}_{i + 1}"
        created, cleanup_files = process_video_job(job, i + 1, len(jobs), ts)
        if not created:
            cleanup_video_files(cleanup_files)
            continue

        success_count += 1
        job.scheduled_for = schedule_slots[i].isoformat(timespec="seconds")
        upsert_job(job)

        if create_only:
            job.upload_skipped = True
            job.touch("upload_skipped")
            upsert_job(job)
            cleanup_video_files([f for f in cleanup_files if f != job.final_video_path])
            log.info("Create-only: video saved → %s", job.final_video_path)
        elif not quota_exceeded:
            ok, quota_hit = upload_youtube_scheduled(
                job.final_video_path, job.story["title"], job.script, schedule_slots[i]
            )
            if ok:
                upload_count += 1
                job.uploaded = True
                job.touch("uploaded")
                upsert_job(job)
                cleanup_files.append(job.final_video_path)
                cleanup_video_files(cleanup_files)
                log.info("Video %d uploaded and cleaned up", i + 1)
            elif quota_hit:
                quota_exceeded = True
                job.upload_skipped = True
                job.touch("upload_skipped")
                upsert_job(job)
                cleanup_video_files([f for f in cleanup_files if f != job.final_video_path])
                log.warning("Quota exceeded — remaining videos will be saved locally")
            else:
                job.errors.append("Upload failed; video kept locally")
                job.touch("created")
                upsert_job(job)
                cleanup_video_files([f for f in cleanup_files if f != job.final_video_path])
        else:
            job.upload_skipped = True
            job.touch("upload_skipped")
            upsert_job(job)
            cleanup_video_files([f for f in cleanup_files if f != job.final_video_path])
            log.info("Quota exceeded — video saved locally: %s", job.final_video_path)

        if i < len(jobs) - 1:
            log.info("Waiting 10 seconds before next video...")
            time.sleep(10)

    log.info("=" * 60)
    log.info("Run complete")
    log.info("  Videos created : %d/%d", success_count, len(jobs))
    log.info("  Videos uploaded: %d/%d", upload_count, success_count)
    if quota_exceeded:
        log.info("  YouTube quota exceeded — remaining videos saved locally")
    log.info("=" * 60)
    return success_count > 0


def run_upload_only() -> bool:
    """Upload all locally saved videos with status=upload_skipped."""
    log.info("=" * 60)
    log.info("UPLOAD-ONLY MODE — scanning job memory for pending uploads")
    log.info("=" * 60)

    can_upload, cooldown_until = check_quota_cooldown()
    if not can_upload:
        log.error(
            "Quota cooldown active until %s — aborting", cooldown_until.strftime("%Y-%m-%d %H:%M")
        )
        return False

    from app.utils.models import load_job_memory

    jobs_raw = load_job_memory()
    pending = [
        VideoJob.from_dict(j)
        for j in jobs_raw
        if j.get("status") == "upload_skipped"
        and j.get("final_video_path")
        and Path(j["final_video_path"]).exists()
    ]

    if not pending:
        log.info("No pending videos found")
        return False

    log.info("Found %d video(s) to upload", len(pending))
    slots = build_schedule_datetimes(len(pending))
    upload_count = 0
    quota_exceeded = False

    for i, job in enumerate(pending):
        if quota_exceeded:
            log.warning("Quota exceeded — skipping remaining %d video(s)", len(pending) - i)
            break
        log.info("[%d/%d] Uploading: %s", i + 1, len(pending), job.story.get("title"))
        ok, quota_hit = upload_youtube_scheduled(
            job.final_video_path, job.story["title"], job.script, slots[i]
        )
        if ok:
            upload_count += 1
            job.uploaded = True
            job.upload_skipped = False
            job.touch("uploaded")
            upsert_job(job)
            Path(job.final_video_path).unlink(missing_ok=True)
            log.info("Uploaded and cleaned up: %s", job.final_video_path)
        elif quota_hit:
            quota_exceeded = True
            log.warning("YouTube quota exceeded — stopping uploads")
        else:
            log.error("Upload failed for: %s — file kept locally", job.story.get("title"))

    log.info("=" * 60)
    log.info("Upload-only complete: %d/%d uploaded", upload_count, len(pending))
    log.info("=" * 60)
    return upload_count > 0


def run_legacy() -> bool:
    """Single-story-at-a-time legacy pipeline (no persistent job state)."""
    log.info("=" * 60)
    log.info("LEGACY RUN — creating %d videos", VIDEOS_PER_RUN)
    log.info("=" * 60)

    can_upload, cooldown_until = check_quota_cooldown()
    if not can_upload:
        log.warning(
            "Quota cooldown until %s — uploads will be skipped",
            cooldown_until.strftime("%Y-%m-%d %H:%M"),
        )

    base_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    now_ist = datetime.now()
    now_ist.date()
    schedule_slots = build_schedule_datetimes(VIDEOS_PER_RUN)
    success_count = upload_count = 0
    quota_exceeded = False

    for i in range(VIDEOS_PER_RUN):
        log.info("\n%s\nLEGACY VIDEO %d OF %d\n%s", "=" * 40, i + 1, VIDEOS_PER_RUN, "=" * 40)
        ts = f"{base_ts}_{i + 1}"
        cleanup_files: list[str] = []

        story = fetch_story()
        if not story:
            log.error("Video %d: no story found — skipping", i + 1)
            continue

        context = fetch_article_text(story["url"])
        script = generate_script(story["title"], context)
        log.info("Script: %s...", script[:120])

        voice_path = str(OUTPUT_DIR / f"voice_{ts}.mp3")
        cleanup_files.append(voice_path)
        if not generate_voiceover_sync(script, voice_path):
            log.error("Video %d: voiceover failed", i + 1)
            continue
        if not Path(voice_path).exists():
            log.error("Video %d: voice file missing", i + 1)
            continue

        search_terms = ai_generate_search_terms(story["title"], context) or FALLBACK_TERMS
        video_url = get_stock_video(search_terms)
        raw_video = str(OUTPUT_DIR / f"raw_{ts}.mp4")
        cleanup_files.extend([raw_video, str(OUTPUT_DIR / f"reencoded_raw_{ts}.mp4")])
        if video_url:
            download_file(video_url, raw_video)

        final_path = str(OUTPUT_DIR / f"cyber_short_{ts}.mp4")
        if not assemble_video(
            raw_video if Path(raw_video).exists() else None, voice_path, final_path
        ):
            log.error("Video %d: assembly failed", i + 1)
            cleanup_video_files(cleanup_files)
            continue

        success_count += 1
        if not quota_exceeded:
            ok, quota_hit = upload_youtube_scheduled(
                final_path, story["title"], script, schedule_slots[i]
            )
            if ok:
                upload_count += 1
                cleanup_files.append(final_path)
                cleanup_video_files(cleanup_files)
            elif quota_hit:
                quota_exceeded = True
                cleanup_video_files([f for f in cleanup_files if f != final_path])
            else:
                cleanup_video_files([f for f in cleanup_files if f != final_path])
        else:
            log.info("Skipping upload — saved: %s", final_path)
            cleanup_video_files([f for f in cleanup_files if f != final_path])

        if i < VIDEOS_PER_RUN - 1:
            time.sleep(10)

    log.info(
        "Legacy run complete — created %d/%d, uploaded %d",
        success_count,
        VIDEOS_PER_RUN,
        upload_count,
    )
    return success_count > 0


# ── CLI ────────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="CyberShorts Bot v7 — autonomous cybersecurity Shorts creator"
    )
    p.add_argument(
        "--mode",
        choices=["once", "loop"],
        default="once",
        help="once = single run | loop = run every 24 hours",
    )
    p.add_argument("--setup", action="store_true", help="Install runtime dependencies")
    p.add_argument("--verify", metavar="VIDEO", help="Check audio stream in a video file")
    p.add_argument("--check-token", action="store_true", help="Show YouTube token status")
    p.add_argument("--refresh-token", action="store_true", help="Force re-authentication")
    p.add_argument("--check-quota", action="store_true", help="Show YouTube quota cooldown status")
    p.add_argument(
        "--clear-quota", action="store_true", help="Clear quota cooldown (use carefully)"
    )
    p.add_argument("--cleanup", action="store_true", help="Purge old output files")
    p.add_argument(
        "--plan-only", action="store_true", help="Score stories only; do not create videos"
    )
    p.add_argument("--create-only", action="store_true", help="Create videos; skip YouTube upload")
    p.add_argument("--upload-only", action="store_true", help="Upload locally saved videos")
    p.add_argument("--legacy-run", action="store_true", help="Run the old single-story pipeline")
    return p


def main() -> None:
    args = _build_parser().parse_args()

    if args.setup:
        log.info("Installing runtime dependencies...")
        subprocess.run(
            [
                "pip",
                "install",
                "requests",
                "edge-tts",
                "python-dotenv",
                "pyttsx3",
                "google-api-python-client",
                "google-auth-oauthlib",
            ],
            check=False,
        )
        log.info(
            "Dependencies installed. Create a .env file with your API keys (see .env.example)."
        )

    elif args.verify:
        from app.video_engine.assembler import _verify_audio_stream

        _verify_audio_stream(args.verify)

    elif args.check_token:
        info = check_token_expiry()
        log.info("YouTube Token Status:")
        for k, v in info.items():
            log.info("  %-30s %s", k + ":", v)

    elif args.refresh_token:
        TOKEN_FILE.unlink(missing_ok=True)
        creds = get_youtube_credentials()
        log.info("Re-authentication %s", "successful" if creds else "failed")

    elif args.check_quota:
        can_upload, cooldown_until = check_quota_cooldown()
        if can_upload:
            log.info("No quota cooldown active — uploads allowed")
        else:
            log.info("Quota cooldown active until %s", cooldown_until.strftime("%Y-%m-%d %H:%M"))

    elif args.clear_quota:
        QUOTA_STATE_FILE.unlink(missing_ok=True)
        log.info("Quota cooldown cleared")

    elif args.cleanup:
        cleanup_output_dir(keep_final=5, keep_days=1)
        log.info("Cleanup complete")

    elif args.plan_only:
        run(plan_only=True)

    elif args.create_only:
        run(create_only=True)

    elif args.upload_only:
        run_upload_only()

    elif args.legacy_run:
        run_legacy()

    elif args.mode == "loop":
        log.info("Loop mode — will repeat every 24 hours")
        while True:
            run()
            log.info("Sleeping 24 hours...")
            time.sleep(86400)

    else:
        run()


if __name__ == "__main__":
    main()
