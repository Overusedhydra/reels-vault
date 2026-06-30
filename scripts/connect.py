#!/usr/bin/env python3
"""
Reels Vault — Connect your Obsidian vault (one-time setup).

This is the "connect Obsidian" step. You run it ONCE. It asks where your
Obsidian vault is, creates a `Reel Vault` folder inside it (with topic,
creator, and extracts sub-folders from the template), and remembers the path.

After this, you never think about paths again:

    python3 scripts/extract_reel.py "<reel-url>" --topic content-creation

…just lands the reel inside your Obsidian vault automatically.

Usage:
    python3 scripts/connect.py                          # interactive
    python3 scripts/connect.py /path/to/my-vault        # non-interactive
"""

import os
import sys
import shutil

# Allow running both as `python3 scripts/connect.py` and from inside scripts/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import load_config, save_config, config_path  # noqa: E402

VAULT_FOLDER_NAME = "Reel Vault"

# The template that ships with this repo lives one level up in vault-template/
TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "vault-template",
)


def _create_reel_vault(vault_path: str) -> str:
    """Create the `Reel Vault` folder inside the given vault, from template."""
    reel_vault_path = os.path.join(vault_path, VAULT_FOLDER_NAME)
    os.makedirs(reel_vault_path, exist_ok=True)

    # Copy the template structure in (creators/, topics/, recipes/, extracts/)
    for item in os.listdir(TEMPLATE_DIR):
        src = os.path.join(TEMPLATE_DIR, item)
        dst = os.path.join(reel_vault_path, item)
        if os.path.isdir(src):
            if not os.path.exists(dst):
                shutil.copytree(src, dst)
        else:
            if not os.path.exists(dst):
                shutil.copy2(src, dst)

    return reel_vault_path


def connect(vault_path: str = None) -> str:
    """Connect a vault. Returns the path to the Reel Vault folder.

    If vault_path is None, runs interactively (prompts the user).
    """
    # Interactive: ask the user where their vault is
    if vault_path is None:
        existing = load_config().get("vault_path", "")
        hint = f" [current: {existing}]" if existing else ""
        print("🎬 Reels Vault — Connect your Obsidian vault")
        print("-" * 48)
        raw = input(f"Path to your Obsidian vault{hint}:\n> ").strip().strip('"').strip("'")
        if not raw:
            print("No path entered. Exiting (nothing changed).")
            sys.exit(0)
        vault_path = os.path.expanduser(raw)

    vault_path = os.path.abspath(os.path.expanduser(vault_path))

    # Validate the vault exists
    if not os.path.isdir(vault_path):
        print(f"❌ That folder doesn't exist: {vault_path}")
        sys.exit(1)

    # Friendly check: does this look like an Obsidian vault? (.obsidian folder)
    if not os.path.isdir(os.path.join(vault_path, ".obsidian")):
        print(f"⚠️  Heads up: no `.obsidian` folder found at {vault_path}")
        print("   That's okay if it's just a notes folder, but a real Obsidian")
        print("   vault usually has a `.obsidian` folder inside it.")

    reel_vault_path = _create_reel_vault(vault_path)

    # Remember the vault path *and* where this repo lives, so the optional
    # Claude skill (skills/reels-vault/) can locate the venv + scripts without
    # the user wiring up any paths by hand.
    install_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = load_config()
    cfg.update({"vault_path": reel_vault_path, "install_dir": install_dir})
    save_config(cfg)

    print()
    print(f"✅ Connected!")
    print(f"   Reel Vault folder: {reel_vault_path}")
    print(f"   Config saved at:   {config_path()}")
    print()
    print("Now you can extract reels without thinking about paths:")
    print('   python3 scripts/extract_reel.py "<reel-url>" --topic content-creation')

    return reel_vault_path


if __name__ == "__main__":
    vault_arg = sys.argv[1] if len(sys.argv) > 1 else None
    connect(vault_arg)
