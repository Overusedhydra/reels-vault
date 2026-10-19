#!/usr/bin/env bash
#
# Reels Vault — one-line installer.
#
#   curl -fsSL https://raw.githubusercontent.com/Overusedhydra/reels-vault/main/install.sh | bash
#
set -euo pipefail

REPO_URL="https://github.com/Overusedhydra/reels-vault.git"
TARGET_DIR="${REELS_VAULT_DIR:-$HOME/reels-vault}"

echo "🎬 Reels Vault — one-line installer"
echo "==================================="
echo ""

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

if [ -d "$TARGET_DIR/.git" ]; then
    echo "📂 Found an existing copy at $TARGET_DIR — updating it..."
    git -C "$TARGET_DIR" pull --ff-only
else
    echo "📂 Downloading into $TARGET_DIR ..."
    git clone "$REPO_URL" "$TARGET_DIR"
fi

cd "$TARGET_DIR"
echo ""
echo "⚙️  Installing (this can take a few minutes the first time)..."
chmod +x setup.sh
./setup.sh

echo ""
echo "🔗 Connect storage (Obsidian, Notion, or both)."
if [ -r /dev/tty ]; then
    .venv/bin/reels-vault-connect < /dev/tty || {
        echo "   Connection skipped. Run later:"
        echo "     cd \"$TARGET_DIR\" && .venv/bin/reels-vault-connect"
    }
else
    echo "   No terminal available. Connect later:"
    echo "     cd \"$TARGET_DIR\" && .venv/bin/reels-vault-connect"
fi

echo ""
echo "✅ All set! Reels Vault is installed at: $TARGET_DIR"
echo ""
echo "Try saving your first reel:"
echo "   cd \"$TARGET_DIR\""
echo '   .venv/bin/reels-vault "<instagram-reel-url>" --topic hooks'
