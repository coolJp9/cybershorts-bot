"""Subtitle / caption generation utilities.

Generates SRT files from a script string by splitting text into timed segments
that match the voiceover duration. Designed for future integration with the
FFmpeg video assembly step (burn-in captions or sidecar .srt files).
"""

import logging
import math
import re
from pathlib import Path
from typing import List, Tuple

log = logging.getLogger("CyberBot.subtitles")

# Characters-per-second estimate for edge-tts at default rate
_CHARS_PER_SECOND: float = 14.0
_MAX_LINE_CHARS: int = 42


def _chunk_text(text: str, max_chars: int = _MAX_LINE_CHARS) -> List[str]:
    """Split *text* into short segments suitable for subtitle lines."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: List[str] = []
    current = ""
    for sentence in sentences:
        words = sentence.split()
        for word in words:
            candidate = f"{current} {word}".strip() if current else word
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = word
    if current:
        chunks.append(current)
    return chunks


def _format_srt_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt(script: str, audio_duration: float) -> str:
    """Return a well-formed SRT string for *script* timed to *audio_duration* seconds."""
    chunks = _chunk_text(script)
    if not chunks:
        return ""

    time_per_char = audio_duration / max(sum(len(c) for c in chunks), 1)
    srt_lines: List[str] = []
    index = 1
    elapsed = 0.0

    for chunk in chunks:
        duration = len(chunk) * time_per_char
        start = elapsed
        end = min(elapsed + duration, audio_duration)
        srt_lines.append(
            f"{index}\n"
            f"{_format_srt_time(start)} --> {_format_srt_time(end)}\n"
            f"{chunk}\n"
        )
        elapsed = end
        index += 1

    return "\n".join(srt_lines)


def save_srt(script: str, audio_duration: float, output_path: str) -> bool:
    """Write an SRT file to *output_path*. Returns True on success."""
    try:
        srt_content = generate_srt(script, audio_duration)
        Path(output_path).write_text(srt_content, encoding="utf-8")
        log.info("SRT saved → %s", output_path)
        return True
    except Exception as exc:
        log.error("Could not write SRT: %s", exc)
        return False
