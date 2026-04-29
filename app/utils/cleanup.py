"""File cleanup utilities for intermediate and final video artefacts."""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

from app.config.settings import OUTPUT_DIR

log = logging.getLogger("CyberBot.cleanup")


def cleanup_video_files(video_files: List[str]) -> None:
    """Delete specific files produced during a single video job."""
    for f in video_files:
        path = Path(f)
        if path.exists():
            try:
                path.unlink()
                log.info("Deleted: %s", path.name)
            except Exception as exc:
                log.warning("Could not delete %s: %s", f, exc)


def cleanup_output_dir(keep_final: int = 0, keep_days: int = 1) -> None:
    """Purge old files from the output directory.

    Args:
        keep_final: Number of most-recent final videos to retain (0 = delete all).
        keep_days:  Keep files newer than this many days.
    """
    cutoff = datetime.now() - timedelta(days=keep_days)
    all_files = list(OUTPUT_DIR.glob("*"))

    final_videos = sorted(
        [f for f in all_files if f.name.startswith("cyber_short_")],
        key=os.path.getctime,
        reverse=True,
    )
    intermediate_files = [f for f in all_files if not f.name.startswith("cyber_short_")]

    for f in intermediate_files:
        try:
            f.unlink()
            log.info("Deleted intermediate: %s", f.name)
        except Exception as exc:
            log.warning("Could not delete %s: %s", f.name, exc)

    if keep_final > 0:
        for f in final_videos[keep_final:]:
            try:
                f.unlink()
                log.info("Deleted old video: %s", f.name)
            except Exception as exc:
                log.warning("Could not delete %s: %s", f.name, exc)
    else:
        for f in final_videos:
            try:
                file_time = datetime.fromtimestamp(os.path.getctime(f))
                if file_time < cutoff:
                    f.unlink()
                    log.info("Deleted aged video: %s", f.name)
            except Exception as exc:
                log.warning("Could not delete %s: %s", f.name, exc)


def cleanup_legacy(keep: int = 20) -> None:
    """Keep only the *keep* most-recent files in the output directory."""
    files = sorted(OUTPUT_DIR.glob("*"), key=os.path.getctime)
    for f in files[:-keep]:
        try:
            f.unlink()
            log.info("Deleted old file: %s", f.name)
        except Exception as exc:
            log.warning("Could not delete %s: %s", f.name, exc)
