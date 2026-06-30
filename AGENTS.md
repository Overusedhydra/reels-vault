# Reels Vault

Local marketing intelligence pipeline. Extract transcripts, music, and smart metadata from Instagram reels. Organize into an Obsidian knowledge base that grows as you save.

## What's Built

- `scripts/extract_reel.py` — Core extraction (yt-dlp + Whisper + Shazam + smart metadata detection)
- `scripts/connect.py` — One-time Obsidian vault connection (creates minimal `Reel Vault/` folder)
- `scripts/config.py` — Stores the connected vault path at `~/.config/reels-vault/config.json`
- `vault-template/` — Minimal vault foundation (grows as reels are saved, no pre-filled templates)
- `mcp_server/server.py` — Real MCP server (FastMCP) for Claude/Cursor integration
- `prompts/` — AI prompt templates for analysis
- `skills/reels-vault/` — Claude skill for reel extraction

## Stack

Python 3.10+ (auto-detected), yt-dlp, Whisper, shazamio, ffmpeg, uv (optional, for fast venv setup)

## Status

- Reel extraction: ✅ Working end-to-end (yt-dlp + Whisper + Shazam)
- Smart metadata: ✅ Auto-detects niche, category, industry from content
- Vault connection: ✅ Minimal foundation, no templates
- Index building: ✅ Auto-grows as reels are saved (by niche, category, industry, creator)
- Claude skill: ✅ Renamed to `reels-vault` (was `instagram-reel-extractor`)
- MCP server: ✅ FastMCP server (extract_reel + search/list/read tools)

## Key Decisions

- Smart metadata (niche, category, industry) detected from transcript + caption via keyword matching — no API keys
- Reels tagged with rich frontmatter (creator, topic, niche, category, industry, tags, source)
- Vault grows organically — topic folders created on save, indexes auto-built
- No pre-filled templates — clean foundation that gets smarter as you add reels
- Setup auto-detects Python version, uses uv if available for faster venv creation
- Whisper `base` model default (good balance of speed/accuracy)
- 100% local — no cloud APIs required
