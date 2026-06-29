#!/usr/bin/env python3
"""
Reels Vault — config storage.

Stores a tiny JSON config at ~/.config/reels-vault/config.json so that once
you've "connected" your Obsidian vault, you never have to type its path again:

    python3 scripts/extract_reel.py "<reel-url>"

just drops the reel into your vault under the right topic folder.
"""

import os
import json

CONFIG_DIR = os.path.expanduser("~/.config/reels-vault")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def load_config() -> dict:
    """Load the stored config, or an empty dict if not set up yet."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_config(config: dict) -> None:
    """Persist the config to disk."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def config_path() -> str:
    """Where the config file lives (handy to show the user)."""
    return CONFIG_FILE
