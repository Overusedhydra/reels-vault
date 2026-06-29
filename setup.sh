#!/bin/bash
#
# Reels Vault — Setup
# Installs everything needed to run the reel extraction pipeline.
# Works on macOS (Homebrew) and Linux (apt). For Windows, see README.
#
set -e

echo "🎬 Reels Vault — Setup"
echo "======================"
echo ""

# ----------------------------------------------------------------------------
# 1. Python 3.10+ (actually enforced this time)
# ----------------------------------------------------------------------------
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required."
    echo "   macOS:  brew install python"
    echo "   Ubuntu: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

PY_OK=$(python3 -c 'import sys; print(1 if sys.version_info >= (3,10) else 0)')
if [ "$PY_OK" != "1" ]; then
    echo "❌ Python 3.10+ required. You have $(python3 --version)."
    exit 1
fi
echo "✓ Python $(python3 --version)"

# ----------------------------------------------------------------------------
# 2. ffmpeg (system dependency, can't pip install reliably)
# ----------------------------------------------------------------------------
install_ffmpeg() {
    if command -v brew &> /dev/null; then
        brew install ffmpeg
    elif command -v apt-get &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y ffmpeg
    else
        echo "❌ No Homebrew or apt found. Install ffmpeg manually:"
        echo "   https://ffmpeg.org/download.html"
        exit 1
    fi
}
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  ffmpeg not found — installing..."
    install_ffmpeg
fi
echo "✓ ffmpeg found"

# ----------------------------------------------------------------------------
# 3. Virtual environment + Python packages
# ----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo ""
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

echo ""
echo "Installing Python packages (yt-dlp, whisper, shazamio, playwright)..."
"$VENV_DIR/bin/pip" install --upgrade pip >/dev/null
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

echo ""
echo "Installing Playwright Chromium browser..."
"$VENV_DIR/bin/playwright" install chromium

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Connect your Obsidian vault (one time):"
echo "       $VENV_DIR/bin/python3 scripts/connect.py"
echo ""
echo "  2. Extract a reel:"
echo '       $VENV_DIR/bin/python3 scripts/extract_reel.py "<instagram-reel-url>" --topic content-creation'
echo ""
echo "Options:"
echo "  --topic <name>          File reel under a topic (groups reels in Obsidian)"
echo "  --whisper-model small   Better transcription (slower)"
echo "  --no-music              Skip Shazam music identification"
echo "  --json                  Output raw JSON instead of markdown"
