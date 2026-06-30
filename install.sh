#!/usr/bin/env bash
#
# Reels Vault — one-line installer.
#
# Paste this one line into your terminal and it does everything: downloads the
# code, installs what it needs, and connects your Obsidian vault.
#
#   curl -fsSL https://raw.githubusercontent.com/Overusedhydra/reels-vault/main/install.sh | bash
#
# Install somewhere else? Set REELS_VAULT_DIR first:
#   REELS_VAULT_DIR=~/tools/reels-vault  curl -fsSL .../install.sh | bash
#
set -e

REPO_URL="https://github.com/Overusedhydra/reels-vault.git"
TARGET_DIR="${REELS_VAULT_DIR:-$HOME/reels-vault}"

echo "🎬 Reels Vault — one-line installer"
echo "==================================="
echo ""

# ---------------------------------------------------------------------------
# 1. Make sure git + python3 exist (everything else, setup.sh installs)
# ---------------------------------------------------------------------------
for tool in git python3; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "❌ '$tool' is required but not installed."
        case "$tool" in
            git)     echo "   macOS:  xcode-select --install"
                     echo "   Ubuntu: sudo apt install git" ;;
            python3) echo "   macOS:  brew install python"
                     echo "   Ubuntu: sudo apt install python3 python3-venv python3-pip" ;;
        esac
        exit 1
    fi
done

# ---------------------------------------------------------------------------
# 2. Download the code (or update it if it's already there)
# ---------------------------------------------------------------------------
if [ -d "$TARGET_DIR/.git" ]; then
    echo "📂 Found an existing copy at $TARGET_DIR — updating it..."
    git -C "$TARGET_DIR" pull --ff-only
else
    echo "📂 Downloading into $TARGET_DIR ..."
    git clone "$REPO_URL" "$TARGET_DIR"
fi

cd "$TARGET_DIR"

# ---------------------------------------------------------------------------
# 3. Install everything (ffmpeg, a private workspace, the Python packages)
# ---------------------------------------------------------------------------
echo ""
echo "⚙️  Installing (this can take a few minutes the first time)..."
chmod +x setup.sh
./setup.sh

# Enable the short `reels-vault` command inside the workspace.
# setup.sh makes the venv with uv when available (uv venvs have no pip), so
# match that here instead of assuming `.venv/bin/pip` exists.
if command -v uv >/dev/null 2>&1; then
    uv pip install --python .venv/bin/python -e . -q
else
    .venv/bin/pip install -e . -q
fi

# ---------------------------------------------------------------------------
# 4. Connect the Obsidian vault.
#    When run as `curl ... | bash`, this script *is* stdin, so a normal prompt
#    can't read the keyboard — we read from /dev/tty (the real terminal).
# ---------------------------------------------------------------------------
echo ""
if [ -r /dev/tty ]; then
    echo "🔗 Last step — connect your Obsidian vault."
    printf "   Path to your Obsidian vault (or press Enter to skip): "
    read -r VAULT_PATH < /dev/tty || VAULT_PATH=""
    if [ -n "$VAULT_PATH" ]; then
        .venv/bin/reels-vault-connect "$VAULT_PATH"
    else
        echo "   ⏭️  Skipped. Connect later with:"
        echo "        cd \"$TARGET_DIR\" && .venv/bin/reels-vault-connect"
    fi
else
    echo "⏭️  Can't ask for your vault path here. Connect it later with:"
    echo "     cd \"$TARGET_DIR\" && .venv/bin/reels-vault-connect"
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "✅ All set! Reels Vault is installed at: $TARGET_DIR"
echo ""
echo "Try saving your first reel:"
echo "   cd \"$TARGET_DIR\""
echo '   .venv/bin/reels-vault "<instagram-reel-url>" --topic hooks'
echo ""
echo "Want Claude to do it for you (no terminal)? See the 'Let Claude do it"
echo "for you' section in the README."
