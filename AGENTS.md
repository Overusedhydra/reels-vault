# Reels Vault

Local-first Instagram reel extraction for Obsidian, Notion, or both. The AI
agent that saves a reel also classifies it; there are no built-in keyword rules
or classification API keys.

## Architecture

- `scripts/extract_reel.py` — yt-dlp/Playwright download, Whisper transcript, Shazam, frames, note formatting, and the CLI.
- `scripts/storage.py` — `ObsidianStore`, `NotionStore`, and `StorageManager` for `obsidian`, `notion`, and `both`.
- `scripts/notes.py` — safe YAML frontmatter, slugs, stable note names, metadata updates.
- `scripts/classify.py` — agent classification CLI (`--note`/`--source`, `--list-unclassified`, `--reindex`).
- `scripts/config.py` — config at `~/.config/reels-vault/config.json` (`0600`), sessions, taxonomy, env overrides.
- `scripts/connect.py` — one-time Obsidian/Notion setup, including Notion database creation.
- `scripts/bulk_import.py`, `scripts/import_creator.py` — cached bulk downloads and creator discovery.
- `mcp_server/server.py` — FastMCP tools: extract, search, list, read, classify, reindex, status.
- `skills/reels-vault/` — Claude skill. It delegates to the repo scripts; there are no duplicate script copies.
- `tests/test_output.py` — formatting, YAML, Obsidian save/search/classify, path-safety tests.

## Commands

```bash
./setup.sh
./.venv/bin/python scripts/connect.py /path/to/ObsidianVault   # or --storage notion/both
./.venv/bin/reels-vault "https://www.instagram.com/reel/ID/" --topic hooks
./.venv/bin/python scripts/classify.py --list-unclassified
./.venv/bin/python mcp_server/server.py --check
./.venv/bin/python -m pip install -e ".[dev]"   # once, for tests
./.venv/bin/python -m pytest -q
```

## Status

- Extraction: working (yt-dlp, Playwright fallback, Whisper, Shazam).
- Storage: Obsidian, Notion, both implemented; Notion requires a live token/database to verify.
- Classification: pending by default; agent fills it via `classify.py` or MCP `classify_reel`.
- Frames: Obsidian only; WebP, capped by `--frame-max-width` (default 1280).
- Indexes: auto-built for Obsidian; Notion uses database views.
- Install: `setup.sh` uses uv/pip, installs the MCP extra, and downloads Playwright Chromium.

## Decisions

- Classification is agent-in-the-loop; no keyword matching, no provider integration.
- `taxonomy.json` is optional and empty by default; values are freeform unless configured.
- Re-saving the same source reuses the note/page (stable `source_id`), not a `-2` duplicate.
- Secrets and local sessions live outside the repo; config is written `0600`.
- All extraction is local; Notion stores the resulting notes when selected.
