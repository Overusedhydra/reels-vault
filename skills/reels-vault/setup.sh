#!/bin/bash
# Setup script for Reels Vault
# Auto-detects Python, uses uv for fast venv setup

set -e

echo "Reels Vault — Setup"
echo "==================="

# Auto-detect Python 3.10+
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v "$candidate" &> /dev/null; then
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "Python 3.10+ required but not found."
    echo "  macOS:  brew install python@3.12"
    echo "  Ubuntu: sudo apt install python3 python3-venv"
    exit 1
fi
echo "Using: $PYTHON ($($PYTHON --version 2>&1))"

# Check for uv (fast venv creator), fall back to regular venv
if command -v uv &> /dev/null; then
    echo "Using uv for fast setup"
    uv venv .venv --python "$PYTHON"
    uv pip install -r requirements.txt
else
    echo "uv not found, using standard venv (install uv for faster setup: pip install uv)"
    "$PYTHON" -m venv .venv
    .venv/bin/pip install --upgrade pip >/dev/null
    .venv/bin/pip install -r requirements.txt
fi

# ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "ffmpeg not found — install it:"
    echo "  macOS:  brew install ffmpeg"
    echo "  Ubuntu: sudo apt install ffmpeg"
    exit 1
fi
echo "ffmpeg: OK"

echo ""
echo "Setup complete!"
echo "  Connect vault:  reels-vault-connect"
echo "  Extract a reel: reels-vault <url> --topic <topic>"
