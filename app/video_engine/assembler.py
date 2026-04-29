"""Stock-footage fetching, downloading, and FFmpeg video assembly."""

import logging
import os
import random
import subprocess
from pathlib import Path
from typing import List, Optional

import requests

from app.config.settings import FACE_WORDS, PEXELS_API_KEY, VIDEO_HEIGHT, VIDEO_WIDTH

log = logging.getLogger("CyberBot.video")


# ── Stock footage ──────────────────────────────────────────────────────────────

def get_stock_video(search_terms: List[str]) -> Optional[str]:
    """Return a direct MP4 download URL from Pexels, or None if nothing matches."""
    if not PEXELS_API_KEY:
        log.warning("PEXELS_API_KEY not set — no footage")
        return None

    log.info("Searching Pexels with terms: %s", search_terms)
    for query in search_terms:
        try:
            r = requests.get(
                "https://api.pexels.com/videos/search"
                f"?query={query}&per_page=15&orientation=portrait"
                f"&min_width=1080&min_height=1920",
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
                        log.info("Found video for query '%s'", query)
                        return vf["link"]
        except Exception as exc:
            log.warning("Pexels search failed for '%s': %s", query, exc)

    log.warning("No stock footage found — will use solid colour background")
    return None


def download_file(url: str, dest: str) -> bool:
    """Stream-download *url* to *dest*, returning True on success."""
    try:
        r = requests.get(url, stream=True, timeout=60)
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(8192):
                fh.write(chunk)
        log.info("Downloaded → %s", dest)
        return True
    except Exception as exc:
        log.error("Download failed: %s", exc)
        return False


# ── FFmpeg helpers ─────────────────────────────────────────────────────────────

def get_audio_duration(audio_path: str) -> float:
    """Return audio duration in seconds via ffprobe, defaulting to 60.0."""
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
        log.info("Audio duration: %.2fs", dur)
        return dur
    except Exception as exc:
        log.warning("ffprobe failed: %s — defaulting to 60s", exc)
        return 60.0


def is_valid_video(file_path: str) -> bool:
    """Return True if the file exists and ffprobe can detect a video stream."""
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


def reencode_video(input_path: str, output_path: str) -> bool:
    """Re-encode to clean H.264 to avoid corruption/loop artefacts."""
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", input_path,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-vf", "fps=30", "-an",
                output_path,
            ],
            check=True, timeout=60, capture_output=True,
        )
        log.info("Re-encoded video: %s", output_path)
        return True
    except Exception as exc:
        log.warning("Re-encode failed: %s", exc)
        return False


def _verify_audio_stream(video_path: str) -> None:
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
            log.error("NO AUDIO STREAM in assembled video!")
    except Exception as exc:
        log.warning("Audio verification failed: %s", exc)


def _build_stock_cmd(
    video_path: str, audio_path: str, audio_dur: float, output_path: str
) -> list:
    return [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-vf", f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,crop={VIDEO_WIDTH}:{VIDEO_HEIGHT}",
        "-t", str(audio_dur),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-r", "30", "-movflags", "+faststart",
        output_path,
    ]


def _build_fallback_cmd(audio_path: str, audio_dur: float, output_path: str) -> list:
    return [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c=0x0a0a0a:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:d={int(audio_dur)+2}",
        "-i", audio_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-t", str(audio_dur),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-r", "30", "-movflags", "+faststart",
        output_path,
    ]


def assemble_video(
    video_path: Optional[str], audio_path: str, output_path: str
) -> bool:
    """Combine stock footage (or colour fill) with TTS audio into a final MP4."""
    log.info("Assembling video with FFmpeg...")
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except FileNotFoundError:
        log.error("FFmpeg not installed")
        return False

    audio_dur = get_audio_duration(audio_path)
    valid_video = False

    if video_path and is_valid_video(video_path):
        try:
            res = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", video_path],
                capture_output=True, text=True, timeout=10,
            )
            vid_dur = float(res.stdout.strip()) if res.stdout.strip() else 0
            valid_video = vid_dur >= 0.5
        except Exception:
            valid_video = False

    if valid_video and video_path:
        reencoded = str(Path(video_path).parent / f"reencoded_{Path(video_path).name}")
        if reencode_video(video_path, reencoded):
            video_path = reencoded
        cmd = _build_stock_cmd(video_path, audio_path, audio_dur, output_path)
    else:
        log.warning("No valid footage — using solid colour background")
        cmd = _build_fallback_cmd(audio_path, audio_dur, output_path)

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        if res.returncode == 0:
            mb = os.path.getsize(output_path) / 1e6
            log.info("Video assembled → %s (%.1f MB, %.1fs)", output_path, mb, audio_dur)
            _verify_audio_stream(output_path)
            return True
        log.error("FFmpeg failed (code %d):\n%s", res.returncode, res.stderr[-800:])
        if valid_video:
            log.info("Retrying with solid colour background...")
            return assemble_video(None, audio_path, output_path)
        return False
    except subprocess.TimeoutExpired:
        log.error("FFmpeg timed out after 90 seconds")
        if valid_video:
            log.info("Timeout — retrying with solid background...")
            return assemble_video(None, audio_path, output_path)
        return False
    except Exception as exc:
        log.error("FFmpeg exception: %s", exc)
        return False
