# CyberShorts Bot

An autonomous, AI-powered pipeline that fetches the day's most important cybersecurity news, turns it into a narrated YouTube Short, and schedules the upload — with zero human intervention.

---

## Features

- **Multi-source news aggregation** — RSS/Atom feeds (BleepingComputer, KrebsOnSecurity, TheHackerNews, and 15 more), Hacker News top stories, and Algolia HN search
- **AI story selection** — Ollama (local LLM) picks a diverse, high-impact batch; falls back to a scored heuristic if the model is unavailable
- **Script generation** — Ollama → Google Gemini → static template fallback chain, with a built-in critic/review loop
- **Neural TTS** — edge-tts with 10 different neural voices; pyttsx3 offline fallback
- **Faceless stock footage** — AI-generated Pexels search queries; automatically avoids human faces
- **Video assembly** — FFmpeg-based, portrait 9:16 1080×1920 output; solid-colour background fallback
- **Automatic YouTube upload** — OAuth2 with token refresh; scheduled publishing (up to 10 videos/day); quota-aware cooldown
- **Persistent agent state** — every job is tracked in `agent_jobs.json`; interrupted runs can resume
- **Title-hash deduplication** — stories are never repeated across runs

---

## Architecture

```
News Sources (RSS, HN, Algolia)
        │
        ▼
   app/fetchers/
  (rss, hackernews, aggregator)
        │
        ▼
 app/summarizer/story_selector
  (score, dedup, AI batch plan)
        │
        ▼
 app/script_generator/generator
  (Ollama → Gemini → static)
        │
        ▼
      app/tts/engine
  (edge-tts → pyttsx3)
        │
        ▼
 app/video_engine/assembler
  (Pexels footage + FFmpeg)
        │
        ▼
   app/subtitles/generator
  (SRT caption file)
        │
        ▼
   app/uploader/youtube
  (OAuth2 scheduled upload)
```

---

## Requirements

| Requirement    | Notes                                           |
|----------------|-------------------------------------------------|
| Python 3.10+   |                                                 |
| FFmpeg         | Must be in `PATH`                               |
| Ollama         | `ollama serve` + `ollama pull llama3.2`         |
| Pexels API key | Free key at [pexels.com/api](https://www.pexels.com/api/) |
| YouTube OAuth  | Google Cloud project with YouTube Data API v3 enabled |
| Gemini API     | Optional — fallback script generator            |

---

## Quick Start (Recommended)

### Windows — double-click or run in terminal

```bat
setup.bat
```

What it does automatically:
- Checks Python, FFmpeg, and Ollama are installed
- Creates a `venv\` virtual environment
- Installs all dependencies from `requirements.txt`
- Copies `.env.example` → `.env` on first run
- Creates all required folders (`output\`, `logs\`, `assets\*`)
- Prints the next steps

### Linux / macOS

```bash
chmod +x setup.sh
./setup.sh
```

Same steps as `setup.bat` but for Unix systems.

---

## Manual Installation

If you prefer to set up manually:

```bash
git clone https://github.com/your-username/cybershorts-bot.git
cd cybershorts-bot

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate          # Linux / macOS
venv\Scripts\activate.bat         # Windows CMD
venv\Scripts\Activate.ps1         # Windows PowerShell

# Install dependencies
pip install -r requirements.txt
```

---

## Setup

### 1. Environment variables

```bash
# Copy the example and fill in your keys
cp .env.example .env          # Linux / macOS
copy .env.example .env        # Windows
notepad .env                  # Windows — edit with Notepad
```

`.env` contents:

```env
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2
PEXELS_API_KEY=your_pexels_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here   # optional
```

---

### 2. YouTube — credentials.json

> The bot needs a Google OAuth2 Desktop App credential to upload videos.

**Step-by-step:**

1. Go to [console.cloud.google.com](https://console.cloud.google.com/)
2. Create a new project (e.g. `CyberShorts`)
3. Go to **APIs & Services → Library** → search **YouTube Data API v3** → **Enable**
4. Go to **APIs & Services → Credentials** → **Create Credentials → OAuth client ID**
5. Application type: **Desktop app** → give it any name → **Create**
6. Click **Download JSON** → rename the file to **`credentials.json`**
7. Move `credentials.json` into the project root folder

The file should look like this (see `credentials.json.example`):

```json
{
  "installed": {
    "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
    "project_id": "your-google-cloud-project-id",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "YOUR_CLIENT_SECRET_HERE",
    "redirect_uris": ["http://localhost"]
  }
}
```

> **Never commit `credentials.json` to Git.** It is already listed in `.gitignore`.

---

### 3. YouTube — token.json (auto-generated)

`token.json` is created **automatically** the first time you authenticate. You do not need to create it manually.

Run this to trigger the one-time browser login:

```bash
# Linux / macOS
python main.py --refresh-token

# Windows
venv\Scripts\python.exe main.py --refresh-token
```

A browser window opens → log in with your Google account → click **Allow**.  
The file `token.json` is saved automatically and reused on every future run.

The file will look like this (see `token.json.example`):

```json
{
  "token": "ya29.YOUR_ACCESS_TOKEN",
  "refresh_token": "1//YOUR_REFRESH_TOKEN",
  "token_uri": "https://oauth2.googleapis.com/token",
  "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
  "client_secret": "YOUR_CLIENT_SECRET_HERE",
  "scopes": ["https://www.googleapis.com/auth/youtube.upload"],
  "expiry": "2024-01-01T00:00:00.000000Z"
}
```

> **Never commit `token.json` to Git.** It is already listed in `.gitignore`.

---

### 4. Ollama

```bash
ollama serve
ollama pull llama3.2
```

---

### 5. Verify everything is ready

```bash
python main.py --check-token    # YouTube token status
python main.py --check-quota    # Upload quota status
python main.py --plan-only      # Test news fetching (no video created)
```

---

## Usage

```bash
# Full run: plan + create + upload 10 videos
python main.py

# Plan only (score stories, no video creation)
python main.py --plan-only

# Create videos locally, skip upload
python main.py --create-only

# Upload videos that were previously saved locally
python main.py --upload-only

# Run every 24 hours automatically
python main.py --mode loop

# Diagnostics
python main.py --check-token     # Show token status
python main.py --refresh-token   # Re-authenticate with Google
python main.py --check-quota     # Show quota cooldown status
python main.py --clear-quota     # Clear quota cooldown flag
python main.py --cleanup         # Delete old output files
python main.py --verify output/cyber_short_xyz.mp4   # Check audio stream
```

**Windows users** — prefix all commands with `venv\Scripts\python.exe`:

```bat
venv\Scripts\python.exe main.py --plan-only
venv\Scripts\python.exe main.py --create-only
venv\Scripts\python.exe main.py
```

---

## Push to GitHub

### First time setup

```bash
# 1. Initialize git (skip if already done)
git init
git checkout -b main

# 2. Stage all files
git add .

# 3. Commit
git commit -m "feat: initial commit — CyberShorts Bot"

# 4. Create a repo on github.com (do this in your browser first), then:
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git

# 5. Push
git push -u origin main
```

### Subsequent pushes

```bash
git add .
git commit -m "your commit message"
git push
```

> **Important:** Make sure `credentials.json`, `token.json`, and `.env` are listed in `.gitignore` (they already are) and never pushed to GitHub.

---

## Project Structure

```
cybershorts-bot/
├── app/
│   ├── config/settings.py         # All configuration & constants
│   ├── fetchers/
│   │   ├── rss.py                 # RSS/Atom feed scraper
│   │   ├── hackernews.py          # HN Firebase + Algolia API
│   │   └── aggregator.py          # Combines all sources
│   ├── summarizer/
│   │   └── story_selector.py      # Scoring, dedup, AI batch planning
│   ├── script_generator/
│   │   └── generator.py           # Ollama/Gemini script + review loop
│   ├── tts/
│   │   └── engine.py              # edge-tts / pyttsx3
│   ├── video_engine/
│   │   └── assembler.py           # Pexels + FFmpeg assembly
│   ├── subtitles/
│   │   └── generator.py           # SRT caption generator
│   ├── uploader/
│   │   └── youtube.py             # OAuth2 upload + quota management
│   └── utils/
│       ├── models.py              # VideoJob dataclass + persistence
│       ├── deduplication.py       # Title-hash dedup
│       ├── retry.py               # Generic retry helper
│       └── cleanup.py             # File cleanup utilities
├── assets/                        # Generated media (gitignored)
├── docs/                          # Architecture diagrams & docs
├── tests/                         # pytest test suite
├── .github/workflows/ci.yml       # Lint + test CI
├── main.py                        # Entry point & CLI
├── setup.bat                      # Windows one-click setup
├── setup.sh                       # Linux / macOS one-click setup
├── credentials.json.example       # Credentials file template
├── token.json.example             # Token file template
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── requirements.txt
├── requirements-dev.txt
└── .env.example
```

---

## Environment Variables

| Variable                | Required | Default                   | Description                      |
|-------------------------|----------|---------------------------|----------------------------------|
| `OLLAMA_HOST`           | No       | `http://localhost:11434`  | Ollama API base URL              |
| `OLLAMA_MODEL`          | No       | `llama3.2`                | Model name for Ollama            |
| `GEMINI_API_KEY`        | No       | —                         | Fallback script generation       |
| `PEXELS_API_KEY`        | Yes      | —                         | Stock footage API key            |
| `VIDEOS_PER_RUN`        | No       | `10`                      | Videos to create per run         |
| `SCRIPT_RETRY_ATTEMPTS` | No       | `2`                       | Max script revision attempts     |
| `MIN_SCRIPT_SCORE`      | No       | `7`                       | Minimum AI review score (1–10)   |
| `NETWORK_RETRIES`       | No       | `2`                       | HTTP retry count                 |
| `RSS_STORIES_PER_SOURCE`| No       | `12`                      | Articles fetched per RSS source  |

---

## Running with Docker

```bash
docker-compose up --build
```

For scheduled daily runs:

```bash
docker-compose run --rm cyberbot python main.py --mode loop
```

---

## Development

```bash
pip install -r requirements-dev.txt
pre-commit install

make lint    # ruff + black check
make format  # auto-fix code style
make test    # pytest with coverage
make clean   # remove generated artefacts
```

---

## Troubleshooting

**`credentials.json not found`** — Download your OAuth client JSON from Google Cloud Console, rename it `credentials.json`, and place it in the project root.

**`Token has been expired or revoked`** — Run `python main.py --refresh-token` to re-authenticate.

**`uploadLimitExceeded`** — YouTube limits unverified channels to ~15 uploads/day. The bot sets a 24-hour cooldown automatically. Check with `python main.py --check-quota`.

**`FFmpeg not installed`** — Install FFmpeg and add it to PATH. See [ffmpeg.org/download.html](https://ffmpeg.org/download.html).

**`Ollama connection refused`** — Start the daemon: `ollama serve`, then pull: `ollama pull llama3.2`.

**No stock footage in video** — The bot falls back to a dark background. Verify `PEXELS_API_KEY` is set correctly in `.env`.

---

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

---

## Security

Please report security vulnerabilities privately via the process described in [SECURITY.md](SECURITY.md).

---

## Disclaimer

This tool is for **educational and content-creation purposes only**. Always comply with the terms of service of all APIs used (YouTube, Pexels, Ollama, Gemini). Ensure content adheres to YouTube's community guidelines. The authors are not responsible for misuse of this software.

---

## License

[MIT](LICENSE) © 2026 CyberShorts Bot Contributors
