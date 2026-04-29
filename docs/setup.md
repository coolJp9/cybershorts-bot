# Detailed Setup Guide

## 1. System Dependencies

### FFmpeg

FFmpeg must be installed and available on your system `PATH`.

**Ubuntu / Debian:**
```bash
sudo apt update && sudo apt install -y ffmpeg
ffmpeg -version   # verify
```

**macOS (Homebrew):**
```bash
brew install ffmpeg
```

**Windows:**
Download from [ffmpeg.org/download.html](https://ffmpeg.org/download.html), extract, and add the `bin/` folder to your `PATH` environment variable.

---

### Ollama

```bash
# Linux / macOS
curl -fsSL https://ollama.ai/install.sh | sh
ollama serve
ollama pull llama3.2
```

**Windows:** Download the installer from [ollama.ai](https://ollama.ai/).

Verify Ollama is running:
```bash
curl http://localhost:11434/api/tags
```

---

## 2. Python Environment

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## 3. Pexels API Key

1. Create a free account at [pexels.com](https://www.pexels.com/)
2. Go to [pexels.com/api](https://www.pexels.com/api/) → "Your API Key"
3. Copy the key into your `.env`:
   ```
   PEXELS_API_KEY=your_key_here
   ```

---

## 4. Google Cloud / YouTube Setup

### Create a project

1. Go to [console.cloud.google.com](https://console.cloud.google.com/)
2. Create a new project (e.g. `CyberShorts Bot`)

### Enable the API

1. In the left menu, go to **APIs & Services → Library**
2. Search for **YouTube Data API v3** and enable it

### Create OAuth credentials

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth client ID**
3. Application type: **Desktop app**
4. Download the JSON and save it as `credentials.json` in the project root

### First-time authentication

```bash
python main.py --refresh-token
```

A browser window will open. Authorise the application. A `token.json` file will be created and reused automatically.

---

## 5. Google Gemini (Optional)

1. Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Create an API key
3. Add to `.env`:
   ```
   GEMINI_API_KEY=your_key_here
   ```

Gemini is only used as a fallback when Ollama is unavailable.

---

## 6. Verify Everything

```bash
python main.py --check-token    # token status
python main.py --check-quota    # quota status
python main.py --plan-only      # test news fetching and story selection
```

---

## 7. First Real Run

```bash
python main.py --create-only    # create 10 videos locally; no upload
```

Inspect the `output/` folder to verify video quality before enabling uploads.

```bash
python main.py --verify output/cyber_short_YYYYMMDD_HHMMSS_1.mp4
```

When satisfied:

```bash
python main.py --upload-only    # upload the locally saved videos
```

Or for a full run that creates and uploads in one step:

```bash
python main.py
```
