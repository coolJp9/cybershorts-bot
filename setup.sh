#!/usr/bin/env bash
# Quick-start setup script for CyberShorts Bot

set -euo pipefail

echo "==> CyberShorts Bot Setup"
echo ""

# Check Python version
python3 --version || { echo "ERROR: Python 3.10+ is required"; exit 1; }

# Check FFmpeg
ffmpeg -version > /dev/null 2>&1 || {
  echo "WARNING: ffmpeg not found in PATH"
  echo "  Ubuntu/Debian: sudo apt install ffmpeg"
  echo "  macOS:         brew install ffmpeg"
  echo "  Windows:       https://ffmpeg.org/download.html"
}

# Create virtual environment
if [ ! -d "venv" ]; then
  echo "==> Creating virtual environment..."
  python3 -m venv venv
fi

# Activate
source venv/bin/activate

# Install dependencies
echo "==> Installing Python dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# Copy .env.example if .env doesn't exist
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "==> Created .env from .env.example"
  echo "    Edit .env and fill in your API keys before running the bot."
fi

# Create required directories
mkdir -p output logs assets/audio assets/videos assets/temp assets/subtitles

echo ""
echo "==> Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your API keys"
echo "  2. Start Ollama: ollama serve && ollama pull llama3.2"
echo "  3. Place credentials.json in the project root (YouTube OAuth)"
echo "  4. Run: python main.py --plan-only   (test news fetching)"
echo "  5. Run: python main.py --create-only (test video creation)"
echo "  6. Run: python main.py               (full run with upload)"
