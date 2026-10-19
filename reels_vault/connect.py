#!/usr/bin/env python3
"""Connect Reels Vault to Obsidian, Notion, or both.

Examples:
    reels-vault-connect /path/to/ObsidianVault
    reels-vault-connect --storage notion --token "$NOTION_TOKEN" --parent PAGE_URL
    reels-vault-connect --storage both /path/to/ObsidianVault --parent PAGE_URL
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .config import config_path, load_config, save_config
from .storage import NotionStore, StorageError

VAULT_FOLDER_NAME = "Reel Vault"
INDEX_TEMPLATE = """---
tags: [vault-index]
---

# Reel Vault

Every saved reel is a Markdown note under `Reels/<topic>/`. Classification is
filled in by the AI agent after extraction.

## All Reels

```dataview
TABLE creator AS "Creator", topic AS "Topic", niche AS "Niche", extracted AS "Date"
FROM "Reels"
WHERE source
SORT extracted DESC
```
"""


def _create_reel_vault(vault_path: str) -> str:
    """Create the ``Reel Vault`` folder inside an Obsidian vault."""
    base = Path(vault_path).expanduser().resolve()
    reel_vault = base if base.name == VAULT_FOLDER_NAME else base / VAULT_FOLDER_NAME
    reel_vault.mkdir(parents=True, exist_ok=True)
    index = reel_vault / "Index.md"
    if not index.exists():
        index.write_text(INDEX_TEMPLATE, encoding="utf-8")
    (reel_vault / "Reels").mkdir(exist_ok=True)
    (reel_vault / "index").mkdir(exist_ok=True)
    (reel_vault / "Creators").mkdir(exist_ok=True)
    return str(reel_vault)


def _connect_obsidian(vault_path: str | None, current: str = "") -> str:
    if not vault_path:
        hint = f" [current: {current}]" if current else ""
        raw = input(f"Path to your Obsidian vault{hint}:\n> ").strip().strip('"').strip("'")
        if not raw:
            raise StorageError("No Obsidian path entered.")
        vault_path = raw
    vault = Path(vault_path).expanduser().resolve()
    if not vault.is_dir():
        raise StorageError(f"Folder doesn't exist: {vault}")
    if not (vault / ".obsidian").is_dir():
        print(f"Note: no .obsidian folder at {vault}; creating the Reel Vault folder anyway.")
    return _create_reel_vault(str(vault))


def _connect_notion(token: str, database_id: str, parent_page_id: str) -> dict:
    if not token:
        token = os.environ.get("NOTION_TOKEN", "").strip()
    if not token and sys.stdin.isatty():
        token = input("Notion integration token (starts with ntn_):\n> ").strip()
    if not token:
        raise StorageError("A Notion integration token is required. Set NOTION_TOKEN.")
    if not database_id and not parent_page_id and sys.stdin.isatty():
        parent_page_id = input(
            "Notion parent page URL/ID (share it with your integration):\n> "
        ).strip()
    if not database_id and not parent_page_id:
        raise StorageError("Provide --database-id or --parent-page-id.")

    store = NotionStore({
        "token": token,
        "database_id": database_id,
        "parent_page_id": parent_page_id,
    })
    store.ensure()
    created = not database_id
    return {
        "token": token,
        "database_id": store.database_id,
        "parent_page_id": parent_page_id,
        "url": f"https://www.notion.so/{store.database_id.replace('-', '')}",
        "created": created,
    }


def connect(vault_path: str | None = None, storage: str | None = None,
            token: str = "", database_id: str = "", parent_page_id: str = "",
            interactive: bool = True) -> dict:
    """Connect one or both backends and persist the config."""
    cfg = load_config()
    existing_vault = cfg.get("vault_path", "")
    notion_cfg = cfg.get("notion") or {}

    if not storage:
        storage = cfg.get("storage", "")
    if storage not in ("obsidian", "notion", "both"):
        if interactive and sys.stdin.isatty():
            print("Where should your reels live?")
            print("  1) Obsidian")
            print("  2) Notion")
            print("  3) Both")
            choice = input("> ").strip() or "1"
            storage = {"1": "obsidian", "2": "notion", "3": "both"}.get(choice, "obsidian")
        else:
            storage = "obsidian"

    result: dict = {"storage": storage}
    if storage in ("obsidian", "both"):
        result["vault_path"] = _connect_obsidian(vault_path, existing_vault)
    if storage in ("notion", "both"):
        notion = _connect_notion(
            token or notion_cfg.get("token", ""),
            database_id or notion_cfg.get("database_id", ""),
            parent_page_id or notion_cfg.get("parent_page_id", ""),
        )
        result["notion"] = notion

    cfg.update(result)
    cfg["install_dir"] = str(Path(__file__).resolve().parent.parent)
    cfg.setdefault("sessions", {
        "playwright": str((Path.home() / ".config/reels-vault/session/instagram-playwright.json")),
        "instaloader": str((Path.home() / ".config/reels-vault/session/instagram-instaloader.session")),
    })
    save_config(cfg)

    print()
    if result.get("vault_path"):
        print(f"Obsidian: {result['vault_path']}")
    if result.get("notion"):
        notion = result["notion"]
        print(f"Notion:   {notion['url']} ({'created' if notion.get('created') else 'connected'})")
    print(f"Storage:  {storage}")
    print(f"Config:   {config_path()}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Connect Reels Vault to Obsidian and/or Notion.")
    parser.add_argument("vault", nargs="?", default=None, help="Obsidian vault path")
    parser.add_argument("--storage", choices=["obsidian", "notion", "both"], default=None)
    parser.add_argument("--token", default="", help="Notion integration token")
    parser.add_argument("--database-id", default="", help="Existing Notion database ID/URL")
    parser.add_argument("--parent-page-id", default="", help="Notion parent page ID/URL")
    parser.add_argument("--no-input", action="store_true", help="Never prompt (for scripts)")
    args = parser.parse_args()
    try:
        connect(
            vault_path=args.vault,
            storage=args.storage,
            token=args.token,
            database_id=args.database_id,
            parent_page_id=args.parent_page_id,
            interactive=not args.no_input,
        )
    except StorageError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
