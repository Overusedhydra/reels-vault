#!/bin/bash
#
# Reels Vault — Setup
# Auto-detects Python 3.10+, uses uv if available.
#
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
echo "Python: $PYTHON ($($PYTHON --version 2>&1))"

# ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "Installing ffmpeg..."
    if command -v brew &> /dev/null; then
        brew install ffmpeg
    elif command -v apt-get &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y ffmpeg
    else
        echo "Install ffmpeg manually: https://ffmpeg.org/download.html"
        exit 1
    fi
fi
echo "ffmpeg: OK"

# Venv — prefer uv for speed
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    if command -v uv &> /dev/null; then
        echo "Creating venv with uv..."
        uv venv "$VENV_DIR" --python "$PYTHON"
    else
        echo "Creating venv..."
        "$PYTHON" -m venv "$VENV_DIR"
    fi
fi

echo "Installing packages..."
if command -v uv &> /dev/null; then
    uv pip install --python "$VENV_DIR/bin/python" -r "$SCRIPT_DIR/requirements.txt"
else
    "$VENV_DIR/bin/pip" install --upgrade pip >/dev/null
    "$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
fi

echo ""
echo "Setup complete!"
echo "  Connect vault:  $VENV_DIR/bin/reels-vault-connect"
echo "  Extract a reel: $VENV_DIR/bin/reels-vault <url> --topic <topic>"
