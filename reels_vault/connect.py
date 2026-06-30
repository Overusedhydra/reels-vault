#!/usr/bin/env python3
"""
Reels Vault — Connect your Obsidian vault (one-time setup).

Creates a `Reel Vault/` folder inside your Obsidian vault and remembers
the path. After this, reels auto-file there.

Usage:
    reels-vault-connect                          # interactive
    reels-vault-connect /path/to/my-vault        # non-interactive
"""

import os
import sys

from reels_vault.config import load_config, save_config, config_path

VAULT_FOLDER_NAME = "Reel Vault"


def _create_reel_vault(vault_path: str) -> str:
    """Create the `Reel Vault` folder inside the given vault."""
    reel_vault_path = os.path.join(vault_path, VAULT_FOLDER_NAME)
    os.makedirs(reel_vault_path, exist_ok=True)

    # Write a minimal Index.md if it doesn't exist
    index_path = os.path.join(reel_vault_path, "Index.md")
    if not os.path.exists(index_path):
        with open(index_path, "w") as f:
            f.write("""---
tags: [vault-index]
---

# Reel Vault

Your extracted reels live in topic folders. Each reel is auto-tagged with creator, niche, and category.

## All Reels

```dataview
TABLE creator AS "Creator", topic AS "Topic", extracted AS "Date"
FROM ""
WHERE source
SORT extracted DESC
```
""")

    return reel_vault_path


def connect(vault_path: str = None) -> str:
    """Connect a vault. Returns the path to the Reel Vault folder."""
    if vault_path is None:
        existing = load_config().get("vault_path", "")
        hint = f" [current: {existing}]" if existing else ""
        print("Reels Vault — Connect your Obsidian vault")
        print("-" * 40)
        raw = input(f"Path to your Obsidian vault{hint}:\n> ").strip().strip('"').strip("'")
        if not raw:
            print("No path entered. Exiting.")
            sys.exit(0)
        vault_path = os.path.expanduser(raw)

    vault_path = os.path.abspath(os.path.expanduser(vault_path))

    if not os.path.isdir(vault_path):
        print(f"Folder doesn't exist: {vault_path}")
        sys.exit(1)

    if not os.path.isdir(os.path.join(vault_path, ".obsidian")):
        print(f"No .obsidian folder at {vault_path} — may not be an Obsidian vault.")

    reel_vault_path = _create_reel_vault(vault_path)

    install_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = load_config()
    cfg.update({"vault_path": reel_vault_path, "install_dir": install_dir})
    save_config(cfg)

    print()
    print(f"Connected: {reel_vault_path}")
    print(f"Config:    {config_path()}")

    return reel_vault_path


def main():
    vault_arg = sys.argv[1] if len(sys.argv) > 1 else None
    connect(vault_arg)


if __name__ == "__main__":
    main()
