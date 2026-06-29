#!/bin/bash
# Reels Vault — Setup Script
# Installs all dependencies for the reel extraction pipeline

set -e

echo "🎬 Reels Vault — Setup"
echo "======================"
echo ""

# Check for Python 3.10+
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required. Install via: brew install python"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✓ Python $PYTHON_VERSION found"

# Check for ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  ffmpeg not found. Installing via Homebrew..."
    if command -v brew &> /dev/null; then
        brew install ffmpeg
    else
        echo "❌ Homebrew not found. Install ffmpeg manually: https://ffmpeg.org/download.html"
        exit 1
    fi
fi
echo "✓ ffmpeg found"

# Check for yt-dlp
if ! command -v yt-dlp &> /dev/null; then
    echo "⚠️  yt-dlp not found. Installing via Homebrew..."
    if command -v brew &> /dev/null; then
        brew install yt-dlp
    else
        echo "❌ Homebrew not found. Install yt-dlp manually: https://github.com/yt-dlp/yt-dlp"
        exit 1
    fi
fi
echo "✓ yt-dlp found"

# Create virtual environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo ""
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate and install Python packages
echo ""
echo "Installing Python packages..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

# Install Playwright browser
echo ""
echo "Installing Playwright Chromium..."
"$VENV_DIR/bin/playwright" install chromium

echo ""
echo "✅ Setup complete!"
echo ""
echo "Usage:"
echo "  $VENV_DIR/bin/python3 scripts/extract_reel.py <instagram-reel-url>"
echo ""
echo "Options:"
echo "  --save-dir ./extractions    Save extraction to a directory"
echo "  --whisper-model small       Use a better transcription model"
echo "  --no-frames                 Skip frame extraction"
echo "  --json                      Output raw JSON"
