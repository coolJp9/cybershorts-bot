# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and the project uses [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- Modular project structure under `app/` with clean separation of concerns
- `app/subtitles/generator.py` — SRT caption generation from script text
- `app/utils/retry.py` — generic configurable retry helper
- `app/utils/models.py` — `VideoJob` dataclass with full lifecycle management
- `app/config/settings.py` — single source of truth for all configuration
- `tests/` — pytest suite covering utilities, script generator, and fetchers
- `Dockerfile` and `docker-compose.yml` for containerised deployment
- `Makefile` for developer convenience
- GitHub Actions CI workflow for lint and test
- `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`
- `.env.example` with documented placeholders
- Architecture diagram in `docs/architecture.svg`

### Changed
- Refactored monolithic `cyber_shorts_bot.py` into focused modules
- `main.py` is now a thin orchestration entry point
- All logging uses module-level loggers (`CyberBot.<module>`)
- `normalize_script` and `heuristic_script_review` moved to `script_generator/generator.py`

### Removed
- Direct environment variable reads scattered throughout `cyber_shorts_bot.py` — all reads are now in `settings.py`

---

## [7.0.0] — 2024-01-01

### Added
- Agentic multi-video pipeline with persistent `VideoJob` state
- `ai_plan_story_batch` — LLM-curated diversity across categories
- `generate_script_with_review` — critic loop with configurable retries
- `check_quota_cooldown` / `set_quota_cooldown` — 24-hour upload throttle
- `get_youtube_credentials` — robust token refresh with `invalid_grant` recovery
- `--plan-only`, `--create-only`, `--upload-only` CLI flags
- `--check-token`, `--refresh-token`, `--check-quota`, `--clear-quota` diagnostics
- 19-source RSS/Atom feed aggregation
- `heuristic_story_score` — recency, source trust, keyword density, severity

### Changed
- Story deduplication upgraded from ID-based to title-hash-based
- Voiceover now regenerated automatically if audio duration exceeds 55 seconds

### Fixed
- Token refresh fails gracefully when refresh token is revoked
- FFmpeg assembly retries with solid background on corrupted stock footage

---

## [6.0.0] — 2023-09-01

### Added
- Initial multi-source news fetching (HackerNews, Algolia)
- edge-tts voiceover with pyttsx3 fallback
- Pexels stock footage with faceless filtering
- FFmpeg video assembly
- YouTube Data API v3 upload with scheduled publishing
