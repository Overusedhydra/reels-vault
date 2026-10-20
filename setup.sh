#!/usr/bin/env bash
#
# Reels Vault — setup
# Auto-detects Python 3.10+, uses uv when available.
#
set -euo pipefail

SCRIPT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "Reels Vault — Setup"
echo "==================="

PYTHON=""
for candidate in python3.12 python3.11 python3.10 python3.13 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
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

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "Installing ffmpeg..."
    if command -v brew >/dev/null 2>&1; then
        brew install ffmpeg
    elif command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update && sudo apt-get install -y ffmpeg
    else
        echo "Install ffmpeg manually: https://ffmpeg.org/download.html"
        exit 1
    fi
fi
echo "ffmpeg: OK"

if [ ! -d "$VENV_DIR" ]; then
    if command -v uv >/dev/null 2>&1; then
        echo "Creating venv with uv..."
        uv venv "$VENV_DIR" --python "$PYTHON"
    else
        echo "Creating venv..."
        "$PYTHON" -m venv "$VENV_DIR"
    fi
fi

echo "Installing Reels Vault and dependencies..."
if command -v uv >/dev/null 2>&1; then
    uv pip install --python "$VENV_DIR/bin/python" -e "${SCRIPT_DIR}[mcp]"
else
    "$VENV_DIR/bin/python" -m pip install --upgrade pip >/dev/null
    "$VENV_DIR/bin/python" -m pip install -e "${SCRIPT_DIR}[mcp]"
fi

if [ "${REELS_VAULT_SKIP_BROWSER:-0}" != "1" ]; then
    echo "Installing Playwright Chromium (set REELS_VAULT_SKIP_BROWSER=1 to skip)..."
    "$VENV_DIR/bin/python" -m playwright install chromium || {
        echo "Warning: Chromium install failed; bulk import needs it."
    }
fi

mkdir -p "$HOME/.config/reels-vault/session"
chmod 700 "$HOME/.config/reels-vault/session" 2>/dev/null || true

echo ""
echo "Setup complete!"
echo "  Connect storage: $VENV_DIR/bin/reels-vault-connect"
echo "  Save a reel:     $VENV_DIR/bin/reels-vault <url> --topic <topic>"
echo "  MCP server:      $VENV_DIR/bin/reels-vault-mcp --check"
