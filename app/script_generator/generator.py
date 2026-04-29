"""Script generation with an Ollama → Gemini → static fallback chain,
plus an AI self-review loop before the script is accepted.
"""

import json
import logging
import random
import re
from typing import Dict, List, Optional, Tuple

import requests

from app.config.settings import (
    CYBER_KEYWORDS,
    FALLBACK_SEARCH_TERMS,
    GEMINI_API_KEY,
    MIN_SCRIPT_SCORE,
    OLLAMA_HOST,
    OLLAMA_MODEL,
    SCRIPT_RETRY_ATTEMPTS,
)

log = logging.getLogger("CyberBot.script")

_SCRIPT_PROMPT = (
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


# ── Raw script generation ──────────────────────────────────────────────────────

def _ollama_script(title: str, context: str) -> Optional[str]:
    log.info("Generating script with Ollama (%s)...", OLLAMA_MODEL)
    try:
        r = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": _SCRIPT_PROMPT.format(title=title, context=context[:400]),
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
    except Exception as exc:
        log.warning("Ollama script error: %s", exc)
    return None


def _gemini_script(title: str, context: str) -> Optional[str]:
    if not GEMINI_API_KEY:
        return None
    log.info("Generating script with Gemini (fallback)...")
    try:
        r = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
            json={
                "contents": [{
                    "parts": [{"text": _SCRIPT_PROMPT.format(title=title, context=context[:400])}]
                }]
            },
            timeout=30,
        )
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        log.info("Script from Gemini")
        return text[:400]
    except Exception as exc:
        log.warning("Gemini script error: %s", exc)
    return None


def _static_script(title: str) -> str:
    log.warning("Using static fallback script")
    return (
        f"BREAKING: {title[:120]}. "
        "Cybersecurity researchers are raising the alarm. "
        "Patch your systems immediately. "
        "Follow for daily cyber updates."
    )


def generate_script(title: str, context: str) -> str:
    """Ollama → Gemini → static fallback chain."""
    return _ollama_script(title, context) or _gemini_script(title, context) or _static_script(title)


# ── Script normalisation ───────────────────────────────────────────────────────

def normalize_script(text: str) -> str:
    """Enforce channel rules: hook prefix and CTA suffix."""
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


# ── Script quality review ──────────────────────────────────────────────────────

def heuristic_script_review(script: str, title: str, _context: str) -> Dict:
    """Score a script locally without needing a model."""
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
        issues.append("does not match title")
    if any(w in script.lower() for w in ["guaranteed", "confirmed hacked everyone"]):
        score -= 3
        issues.append("overclaims")
    return {
        "score": max(1, min(10, score)),
        "approved": score >= MIN_SCRIPT_SCORE,
        "reason": ", ".join(issues) if issues else "heuristic checks passed",
    }


def ai_review_script(script: str, title: str, context: str) -> Dict:
    """Ask the LLM to critique the script; fall back to heuristics on failure."""
    prompt = (
        "You are a strict cybersecurity Shorts editor.\n"
        "Review this script for factual caution, hook strength, clarity, length, and fit.\n"
        "Return ONLY compact JSON: {score (1-10), approved (true/false), reason}.\n\n"
        f"Title: {title}\nContext: {context[:700]}\nScript: {script}"
    )
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
    except Exception as exc:
        log.warning("AI script review failed: %s", exc)
        return heuristic_script_review(script, title, context)


def generate_script_with_review(title: str, context: str) -> Tuple[str, Dict]:
    """Generate, self-critique, and if necessary revise before accepting a script."""
    best_script = ""
    best_review: Dict = {"score": 0, "approved": False, "reason": "not generated"}
    revision_context = context

    for attempt in range(1, SCRIPT_RETRY_ATTEMPTS + 2):
        script = normalize_script(generate_script(title, revision_context))
        review = ai_review_script(script, title, context)
        log.info(
            "Script review attempt %d: score=%d approved=%s reason=%s",
            attempt, review["score"], review["approved"], review["reason"],
        )
        if review["score"] > best_review["score"]:
            best_script, best_review = script, review
        if review["approved"] and review["score"] >= MIN_SCRIPT_SCORE:
            return script, review
        revision_context = (
            f"{context[:400]}\n\nPrevious script rejected: {review['reason']}.\n"
            "Rewrite: fewer claims, stronger hook, exact CTA."
        )

    best_review["approved"] = best_review["score"] >= max(5, MIN_SCRIPT_SCORE - 2)
    return best_script or normalize_script(_static_script(title)), best_review


# ── AI-generated video search terms ───────────────────────────────────────────

def ai_generate_search_terms(title: str, context: str = "") -> List[str]:
    """Use the LLM to generate 2-3 faceless stock-video search queries."""
    prompt = (
        "Given this cybersecurity news headline, generate 2-3 short search queries "
        "(max 4 words each) for finding FACELESS stock videos (no people, no faces). "
        "Focus on visual concepts: code, servers, locks, shields, data streams.\n\n"
        f"Headline: {title}\nContext: {context[:200]}\n\n"
        "Return ONLY the queries, one per line, no extra text.\n"
        "Example:\ndigital lock encryption\nserver rack blinking\nbinary code matrix"
    )
    try:
        r = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=60,
        )
        r.raise_for_status()
        response = r.json().get("response", "").strip()
        terms = [line.strip() for line in response.split("\n") if line.strip()]
        if terms:
            log.info("AI search terms: %s", terms)
            return terms[:3]
    except Exception as exc:
        log.warning("AI term generation failed: %s", exc)

    keywords = [kw for kw in CYBER_KEYWORDS if kw in title.lower()]
    if keywords:
        fallback = [f"{random.choice(keywords)} abstract", f"digital {random.choice(keywords)}"]
        log.info("Using keyword fallback terms: %s", fallback)
        return fallback[:2]
    return FALLBACK_SEARCH_TERMS.copy()
