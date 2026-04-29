"""
Centralised configuration — all values come from environment variables.
Import this module everywhere instead of reading os.getenv directly.
"""

import os
import logging
from pathlib import Path
from typing import List, Tuple

from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).resolve().parents[2]
OUTPUT_DIR      = BASE_DIR / "output"
ASSETS_DIR      = BASE_DIR / "assets"
LOG_DIR         = BASE_DIR / "logs"
USED_FILE       = BASE_DIR / "used_stories.json"
JOB_MEMORY_FILE = BASE_DIR / "agent_jobs.json"
TOKEN_FILE      = BASE_DIR / "token.json"
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
QUOTA_STATE_FILE = BASE_DIR / "youtube_quota_state.json"

for _d in (OUTPUT_DIR, LOG_DIR, ASSETS_DIR / "audio", ASSETS_DIR / "videos",
           ASSETS_DIR / "subtitles", ASSETS_DIR / "temp"):
    _d.mkdir(parents=True, exist_ok=True)

# ── AI / API keys ──────────────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
PEXELS_API_KEY: str = os.getenv("PEXELS_API_KEY", "")
OLLAMA_HOST: str    = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL: str   = os.getenv("OLLAMA_MODEL", "llama3.2")

# ── Video dimensions ───────────────────────────────────────────────────────────
VIDEO_WIDTH:  int = 1080
VIDEO_HEIGHT: int = 1920

# ── Pipeline tuning ────────────────────────────────────────────────────────────
VIDEOS_PER_RUN: int       = int(os.getenv("VIDEOS_PER_RUN", "10"))
SCRIPT_RETRY_ATTEMPTS: int = int(os.getenv("SCRIPT_RETRY_ATTEMPTS", "2"))
MIN_SCRIPT_SCORE: int      = int(os.getenv("MIN_SCRIPT_SCORE", "7"))
NETWORK_RETRIES: int       = int(os.getenv("NETWORK_RETRIES", "2"))
RSS_STORIES_PER_SOURCE: int = int(os.getenv("RSS_STORIES_PER_SOURCE", "12"))

# IST publish slots (HH:MM)
SCHEDULE_TIMES: List[str] = [
    "06:30", "08:30", "09:00", "11:30", "12:00",
    "14:30", "15:00", "17:30", "18:00", "21:30",
]

# ── Cybersecurity keyword lists ────────────────────────────────────────────────
CYBER_KEYWORDS: List[str] = [
    "security", "hack", "breach", "vulnerability", "cyber",
    "ransomware", "zero-day", "exploit", "malware", "phishing",
    "data leak", "cybersecurity", "cve", "patch", "attack",
    "trojan", "botnet", "ddos", "spyware", "backdoor",
    "password", "encryption", "firewall", "surveillance", "privacy",
]

FALLBACK_SEARCH_TERMS: List[str] = [
    "digital lock encryption",
    "server rack data center",
    "binary code matrix",
]

FACE_WORDS = {
    "person", "face", "woman", "man", "people",
    "human", "girl", "boy", "portrait", "model",
}

# ── RSS sources ────────────────────────────────────────────────────────────────
RSS_NEWS_SOURCES = [
    {"name": "BleepingComputer",     "url": "https://www.bleepingcomputer.com/feed/",                       "score": 90},
    {"name": "TheHackerNews",        "url": "https://feeds.feedburner.com/TheHackersNews",                  "score": 85},
    {"name": "KrebsOnSecurity",      "url": "https://krebsonsecurity.com/feed/",                            "score": 84},
    {"name": "SecurityWeek",         "url": "https://www.securityweek.com/feed/",                           "score": 82},
    {"name": "TheRecord",            "url": "https://therecord.media/feed",                                 "score": 80},
    {"name": "ISCHandler",           "url": "https://isc.sans.edu/rssfeed_full.xml",                        "score": 79},
    {"name": "CybersecurityDive",    "url": "https://www.cybersecuritydive.com/feeds/news/",                "score": 78},
    {"name": "CyberScoop",           "url": "https://cyberscoop.com/feed/",                                 "score": 76},
    {"name": "SecureList",           "url": "https://securelist.com/feed/",                                 "score": 76},
    {"name": "Hackread",             "url": "https://hackread.com/feed/",                                   "score": 75},
    {"name": "ThreatPost",           "url": "https://threatpost.com/feed/",                                 "score": 75},
    {"name": "HelpNetSecurity",      "url": "https://www.helpnetsecurity.com/feed/",                        "score": 74},
    {"name": "TroyHunt",             "url": "https://feeds.feedburner.com/TroyHunt",                        "score": 74},
    {"name": "InfosecurityMagazine", "url": "https://www.infosecurity-magazine.com/rss/news/",              "score": 73},
    {"name": "WiredSecurity",        "url": "https://www.wired.com/feed/category/security/latest/rss",      "score": 70},
    {"name": "GrahamCluley",         "url": "https://grahamcluley.com/feed/",                               "score": 69},
    {"name": "TechCrunchSecurity",   "url": "https://techcrunch.com/category/security/feed/",               "score": 68},
    {"name": "UnsupervisedLearning", "url": "https://danielmiessler.com/feed/",                             "score": 68},
    {"name": "Schneier",             "url": "https://www.schneier.com/feed/atom/",                          "score": 66},
]

# ── TTS voices ─────────────────────────────────────────────────────────────────
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

# ── Logging ────────────────────────────────────────────────────────────────────
def configure_logging(name: str = "CyberBot") -> logging.Logger:
    from datetime import datetime
    log_file = LOG_DIR / f"bot_{datetime.now().strftime('%Y%m%d')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger(name)
