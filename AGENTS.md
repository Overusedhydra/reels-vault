# Reels Vault

Open-source marketing intelligence pipeline. Extract transcripts, music, and insights from Instagram reels. Organize into an AI-ready knowledge base.

## What's Built

- `scripts/extract_reel.py` — Core extraction (yt-dlp + Whisper transcription + Shazam music ID)
- `scripts/connect.py` — One-time Obsidian vault connection (creates `Reel Vault/` folder)
- `scripts/config.py` — Stores the connected vault path at `~/.config/reels-vault/config.json`
- `vault-template/` — Obsidian knowledge base template (topics, creators, recipes, extracts)
- `mcp/server.py` — Real MCP server (FastMCP) for Claude/Cursor integration
- `prompts/` — AI prompt templates for analysis

## Stack

Python 3.10+, yt-dlp, Whisper, shazamio, ffmpeg, MCP SDK

## Status

- Reel extraction: ✅ Working end-to-end (yt-dlp + Whisper + Shazam)
- Vault connection: ✅ `connect.py` wires pipeline to Obsidian vault
- Vault template: ✅ Built with Hormozi example, Dataview paths fixed
- MCP server: ✅ Real FastMCP server (search/list/read tools)
- GitHub repo: ⏳ Ready to push

## Key Decisions

- Reels are tagged with frontmatter (creator/topic/tags) and filed under `<topic>/` folders
- yt-dlp handles IG auth via `--cookies-from-browser`; no brittle scraper fallback
- Whisper `base` model default (good balance of speed/accuracy)
- Vault organized by topic (cross-creator), not by creator
- No API keys required — runs 100% locally
