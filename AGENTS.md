# Reels Vault

Local-first Instagram reel extraction for Obsidian, Notion, or both. The AI
agent that saves a reel also classifies it; there are no built-in keyword rules
or classification API keys.

## Architecture

- `reels_vault/extract.py` — yt-dlp/Playwright download, Whisper transcript, Shazam, frames, note formatting, and the CLI.
- `reels_vault/storage.py` — `ObsidianStore`, `NotionStore`, and `StorageManager` for `obsidian`, `notion`, and `both`.
- `reels_vault/notes.py` — safe YAML frontmatter, slugs, stable note names, metadata updates.
- `reels_vault/classify.py` — agent classification CLI (`--note`/`--source`, `--list-unclassified`, `--reindex`).
- `reels_vault/config.py` — config at `~/.config/reels-vault/config.json` (`0600`), sessions, taxonomy, env overrides.
- `reels_vault/connect.py` — one-time Obsidian/Notion setup, including Notion database creation.
- `reels_vault/bulk_import.py`, `reels_vault/import_creator.py` — cached bulk downloads and creator discovery.
- `reels_vault/server.py` — FastMCP tools: extract, search, list, read, classify, reindex, status.
- `skills/reels-vault/` — full Claude skill. It delegates to the installed package; there are no duplicate script copies.
- `skills/reels-vault-lite/` — low-space Obsidian-only skill using `yt-dlp`, `ffmpeg`, and NVIDIA `nemo-speech`; no pip package, MCP, Playwright, Notion, or Shazam.
- `tests/test_output.py` — formatting, YAML, Obsidian save/search/classify, path-safety tests.
- `tests/test_lite_skill.py` — frontmatter, metadata, and fake-tool save/classify/search tests for the lite helper.

## Commands

```bash
./setup.sh
./.venv/bin/reels-vault-connect /path/to/ObsidianVault   # or --storage notion/both
./.venv/bin/reels-vault "https://www.instagram.com/reel/ID/" --topic hooks
./.venv/bin/reels-vault-classify --list-unclassified
./.venv/bin/reels-vault-mcp --check
./.venv/bin/python -m pip install -e ".[dev]"   # once, for tests
./.venv/bin/python -m pytest -q
./skills/reels-vault-lite/setup.sh --install --with-model   # lite path (macOS/Linux)
```

## Status

- Extraction: working (yt-dlp, Playwright fallback, Whisper, Shazam).
- Storage: Obsidian, Notion, both implemented; Notion requires a live token/database to verify.
- Classification: pending by default; agent fills it via `reels-vault-classify` or MCP `classify_reel`.
- Frames: Obsidian only; WebP, capped by `--frame-max-width` (default 1280).
- Indexes: auto-built for Obsidian; Notion uses database views.
- Install: `setup.sh` uses uv/pip, installs the MCP extra, and downloads Playwright Chromium. The lite path uses `nemo-speech` and a ~708 MB Q8 model instead of PyTorch/Playwright.

## Decisions

- Classification is agent-in-the-loop; no keyword matching, no provider integration.
- `taxonomy.json` is optional and empty by default; values are freeform unless configured.
- Re-saving the same source reuses the note/page (stable `source_id`), not a `-2` duplicate.
- Secrets and local sessions live outside the repo; config is written `0600`.
- All extraction is local; Notion stores the resulting notes when selected.
