"""Text-to-speech generation: edge-tts (online) → pyttsx3 (offline fallback)."""

import asyncio
import logging
import random
import subprocess

from app.config.settings import TTS_VOICES

log = logging.getLogger("CyberBot.tts")


async def _tts_edge(text: str, path: str) -> bool:
    try:
        import edge_tts
    except ImportError:
        subprocess.run(["pip", "install", "edge-tts"], capture_output=True, check=False)
        import edge_tts  # type: ignore[import]

    voice, rate = random.choice(TTS_VOICES)
    log.info("edge-tts: %s @ %s", voice, rate)
    try:
        await edge_tts.Communicate(text, voice, rate=rate).save(path)
        log.info("Voiceover saved → %s", path)
        return True
    except Exception as exc:
        log.warning("edge-tts failed: %s", exc)
        return False


def _tts_pyttsx3(text: str, path: str) -> bool:
    log.info("Trying pyttsx3 (offline fallback)...")
    try:
        import pyttsx3
    except ImportError:
        subprocess.run(["pip", "install", "pyttsx3"], capture_output=True, check=False)
        try:
            import pyttsx3  # type: ignore[import]
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
        log.info("Voiceover (pyttsx3) saved → %s", path)
        return True
    except Exception as exc:
        log.error("pyttsx3 failed: %s", exc)
        return False


async def generate_voiceover(text: str, path: str) -> bool:
    """Attempt edge-tts; fall back to pyttsx3 if it fails."""
    if await _tts_edge(text, path):
        return True
    return _tts_pyttsx3(text, path)


def generate_voiceover_sync(text: str, path: str) -> bool:
    """Synchronous wrapper around the async TTS generator."""
    return asyncio.run(generate_voiceover(text, path))
