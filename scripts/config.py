#!/usr/bin/env python3
"""Reels Vault configuration.

The config lives outside the repository so tokens and local paths never get
committed:

    ~/.config/reels-vault/config.json

Storage backends
----------------
``storage`` is one of ``obsidian``, ``notion``, or ``both``.  Obsidian uses a
normal folder inside the user's vault.  Notion uses a database created by
``scripts/connect.py`` (or an existing database the user points us at).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(os.path.expanduser("~/.config/reels-vault"))
CONFIG_FILE = CONFIG_DIR / "config.json"
SESSION_DIR = CONFIG_DIR / "session"
PLAYWRIGHT_SESSION = SESSION_DIR / "instagram-playwright.json"
INSTALOADER_SESSION = SESSION_DIR / "instagram-instaloader.session"
DEFAULT_TAXONOMY = CONFIG_DIR / "taxonomy.json"

STORAGE_CHOICES = ("obsidian", "notion", "both")


def _expand(value: str | os.PathLike[str] | None) -> str:
    if not value:
        return ""
    return str(Path(value).expanduser())


def load_config() -> dict[str, Any]:
    """Load the stored config, returning an empty dict if unavailable."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        with CONFIG_FILE.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(config: dict[str, Any]) -> None:
    """Persist config, keeping credentials readable only by the user."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, CONFIG_FILE)
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except OSError:
        pass


def config_path() -> str:
    """Where the config file lives (shown to the user)."""
    return str(CONFIG_FILE)


def storage_backend(config: dict[str, Any] | None = None) -> str:
    """Return the configured backend, inferring it for older configs."""
    cfg = config if config is not None else load_config()
    env = os.environ.get("REELS_STORAGE", "").strip().lower()
    if env in STORAGE_CHOICES:
        return env

    configured = str(cfg.get("storage", "")).strip().lower()
    if configured in STORAGE_CHOICES:
        return configured

    notion = cfg.get("notion") or {}
    if notion.get("database_id") and not cfg.get("vault_path"):
        return "notion"
    return "obsidian"


def vault_path(config: dict[str, Any] | None = None) -> str:
    """Resolve the Obsidian ``Reel Vault`` folder, if configured."""
    cfg = config if config is not None else load_config()
    env = os.environ.get("REELS_VAULT_PATH", "").strip()
    if env:
        return _expand(env)
    return _expand(cfg.get("vault_path", ""))


def notion_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve Notion settings, allowing environment overrides."""
    cfg = config if config is not None else load_config()
    raw = cfg.get("notion") or {}
    token = os.environ.get("NOTION_TOKEN", "").strip() or str(raw.get("token", "")).strip()
    database_id = (
        os.environ.get("REELS_NOTION_DATABASE_ID", "").strip()
        or str(raw.get("database_id", "")).strip()
    )
    parent_page_id = (
        os.environ.get("REELS_NOTION_PARENT_PAGE_ID", "").strip()
        or str(raw.get("parent_page_id", "")).strip()
    )
    return {
        "token": token,
        "database_id": database_id,
        "parent_page_id": parent_page_id,
        "version": str(raw.get("version", "2022-06-28")),
    }


def session_paths(config: dict[str, Any] | None = None) -> dict[str, str]:
    """Resolve Playwright and instaloader session paths."""
    cfg = config if config is not None else load_config()
    sessions = cfg.get("sessions") or {}
    pw = sessions.get("playwright") or str(PLAYWRIGHT_SESSION)
    il = sessions.get("instaloader") or str(INSTALOADER_SESSION)
    return {
        "playwright": _expand(pw),
        "instaloader": _expand(il),
    }


def taxonomy_path(config: dict[str, Any] | None = None) -> str:
    cfg = config if config is not None else load_config()
    return _expand(cfg.get("taxonomy_path") or str(DEFAULT_TAXONOMY))


def install_dir() -> str:
    """Repository/install directory containing ``scripts/``."""
    return str(Path(__file__).resolve().parent.parent)
