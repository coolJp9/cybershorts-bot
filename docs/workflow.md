# Pipeline Workflow

This document explains the step-by-step execution flow of a standard run (`python main.py`).

---

## Sequence Diagram (text)

```
main.py
  │
  ├─► plan_video_jobs(10)
  │     │
  │     ├─► fetch_all_news()
  │     │     ├─ fetch_rss_news()        → 19 RSS/Atom sources
  │     │     ├─ fetch_hackernews_top()  → HN Firebase API
  │     │     └─ fetch_algolia_hn()      → Algolia search
  │     │
  │     ├─► dedupe_stories()             → title-hash deduplication
  │     ├─► heuristic_story_score()      → recency + source trust + severity
  │     ├─► ai_plan_story_batch()        → Ollama LLM (heuristic fallback)
  │     └─► [VideoJob × 10] persisted to agent_jobs.json
  │
  └─► for each job:
        │
        ├─► fetch_article_text(url)       → plain-text context (1 500 chars)
        │
        ├─► generate_script_with_review()
        │     ├─ _ollama_script()         → local LLM
        │     ├─ _gemini_script()         → Google Gemini (fallback)
        │     ├─ _static_script()         → template (fallback)
        │     ├─ normalize_script()       → enforce hook + CTA
        │     └─ ai_review_script()       → critic loop (up to 3 attempts)
        │
        ├─► generate_voiceover_sync()
        │     ├─ _tts_edge()              → edge-tts (online)
        │     └─ _tts_pyttsx3()          → pyttsx3 (offline fallback)
        │
        ├─► ai_generate_search_terms()    → Ollama → keyword fallback
        │
        ├─► get_stock_video()             → Pexels API (faceless filter)
        ├─► download_file()               → stream download
        │
        ├─► assemble_video()
        │     ├─ reencode_video()         → clean H.264
        │     ├─ FFmpeg scale + crop      → 1080 × 1920
        │     └─ FFmpeg audio merge       → AAC 192k
        │
        ├─► mark_used_title()             → write to used_stories.json
        │
        └─► upload_youtube_scheduled()
              ├─ check_quota_cooldown()   → 24h gate if quota exceeded
              ├─ get_youtube_credentials() → OAuth2 + token refresh
              └─ YouTube Data API v3      → private + publishAt (IST slots)
```

---

## State Machine — VideoJob.status

```
planned
  │
  ├─► fetching_context
  │
  ├─► scripting
  │     └─ [rejected] → failed
  │
  ├─► voiceover
  │     └─ [failed] → failed
  │
  ├─► footage
  │
  ├─► assembling
  │     └─ [failed] → failed
  │
  ├─► created
  │     ├─► uploaded       (upload succeeded → file deleted)
  │     └─► upload_skipped (quota / create-only → file kept)
  │
  └─► failed
```

---

## Fallback Chains

| Stage              | Primary          | Fallback 1        | Fallback 2        |
|--------------------|------------------|-------------------|-------------------|
| Script generation  | Ollama           | Gemini            | Static template   |
| Script review      | Ollama critic    | Heuristic checker | —                 |
| TTS                | edge-tts         | pyttsx3           | —                 |
| Video background   | Pexels footage   | Solid colour fill | —                 |
| Story selection    | Ollama LLM       | Heuristic scoring | —                 |
| Video search terms | Ollama LLM       | Keyword combos    | Hardcoded list    |

---

## Quota Handling

YouTube limits new/unverified channels to approximately 15 uploads per day. When the API returns `uploadLimitExceeded` or `quotaExceeded`:

1. The bot sets a 24-hour cooldown in `youtube_quota_state.json`.
2. Remaining videos in the batch are assembled locally but not uploaded.
3. Their job status is set to `upload_skipped`.
4. After cooldown expires, run `python main.py --upload-only` to complete the uploads.
