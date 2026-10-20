#!/usr/bin/env bash
set -euo pipefail

INSTALL=0
WITH_MODEL=0
MODEL="${REELS_VAULT_LITE_MODEL:-nemotron-3.5}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${REELS_VAULT_LITE_BIN:-$HOME/.local/bin}"
mkdir -p "$BIN_DIR"

for arg in "$@"; do
  case "$arg" in
    --install) INSTALL=1 ;;
    --with-model) WITH_MODEL=1 ;;
    --model) ;;
    --help|-h)
      echo "Usage: setup.sh [--install] [--with-model] [--model NAME]"
      exit 0
      ;;
    *)
      if [ "${previous:-}" = "--model" ]; then
        MODEL="$arg"
      else
        echo "Unknown option: $arg" >&2
        exit 2
      fi
      ;;
  esac
  previous="$arg"
done

if { [ "$INSTALL" -eq 1 ] || [ "$WITH_MODEL" -eq 1 ]; } && ! command -v curl >/dev/null 2>&1; then
  echo "curl is required to download tools and models."
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.9+ is required. Install it from https://www.python.org/downloads/"
  exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "Python 3.9+ is required; found $(python3 --version 2>&1)."
  exit 1
fi

find_tool() {
  command -v "$1" 2>/dev/null || true
}

YTDLP="$(find_tool yt-dlp)"
FFMPEG="$(find_tool ffmpeg)"
NEMO="$(find_tool nemo-speech)"

if [ -z "$FFMPEG" ] && [ -x "$BIN_DIR/ffmpeg" ]; then
  FFMPEG="$BIN_DIR/ffmpeg"
fi
if [ -z "$NEMO" ] && [ -x "$HOME/.local/bin/nemo-speech" ]; then
  NEMO="$HOME/.local/bin/nemo-speech"
fi

if [ -z "$FFMPEG" ]; then
  echo "ffmpeg is required."
  echo "  macOS:   brew install ffmpeg"
  echo "  Ubuntu:  sudo apt install ffmpeg"
  exit 1
fi

if [ -z "$YTDLP" ]; then
  if [ "$INSTALL" -eq 1 ]; then
    case "$(uname -s):$(uname -m)" in
      Darwin:*) YTDLP_URL="https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos" ;;
      Linux:x86_64|Linux:amd64) YTDLP_URL="https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux" ;;
      Linux:aarch64|Linux:arm64) YTDLP_URL="https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux_aarch64" ;;
      *)
        echo "No prebuilt yt-dlp for $(uname -s) $(uname -m). Install it with pipx or your package manager." >&2
        exit 1
        ;;
    esac
    echo "Installing yt-dlp to $BIN_DIR/yt-dlp"
    curl -fL --proto '=https' --tlsv1.2 --retry 3 -o "$BIN_DIR/yt-dlp" "$YTDLP_URL"
    chmod +x "$BIN_DIR/yt-dlp"
    YTDLP="$BIN_DIR/yt-dlp"
    if [ ! -x "$YTDLP" ]; then
      echo "yt-dlp install did not produce an executable at $YTDLP" >&2
      exit 1
    fi
  else
    echo "yt-dlp is required. Re-run with --install or install it with pipx/brew."
    MISSING=1
  fi
fi

if [ -z "$NEMO" ]; then
  if [ "$INSTALL" -eq 1 ]; then
    echo "Installing NVIDIA nemo-speech"
    INSTALLER="$(mktemp "${TMPDIR:-/tmp}/nemo-speech-install.XXXXXX")"
    trap 'rm -f "$INSTALLER"' EXIT
    curl -fsSL --proto '=https' --tlsv1.2 --retry 3 \
      -o "$INSTALLER" https://github.com/NVIDIA/NeMo-Speech.cpp/raw/main/scripts/install.sh
    sh "$INSTALLER" --binary-only
    NEMO="$HOME/.local/bin/nemo-speech"
    if [ ! -x "$NEMO" ]; then
      echo "nemo-speech install did not produce an executable at $NEMO" >&2
      exit 1
    fi
  else
    echo "nemo-speech is required. Re-run with --install."
    MISSING=1
  fi
fi

if [ "${MISSING:-0}" -eq 1 ]; then
  exit 1
fi

if [ "$WITH_MODEL" -eq 1 ]; then
  echo "Downloading NVIDIA $MODEL (about 708 MB for the default Q8 model)"
  "$NEMO" pull "$MODEL"
fi

export PATH="$BIN_DIR:$HOME/.local/bin:$PATH"
python3 "$SCRIPT_DIR/scripts/reels_vault_lite.py" status
