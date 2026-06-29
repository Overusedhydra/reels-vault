# Reels Vault

Open-source marketing intelligence pipeline. Extract transcripts, music, and insights from Instagram reels. Organize into an AI-ready knowledge base.

## What's Built

- `scripts/extract_reel.py` — Core extraction (yt-dlp + Playwright fallback, Whisper transcription, Shazam music ID)
- `vault-template/` — Obsidian knowledge base template (topics, creators, recipes, extracts)
- `mcp/server.py` — MCP server for Claude/Cursor integration
- `prompts/` — AI prompt templates for analysis

## Stack

Python 3.10+, yt-dlp, Whisper, shazamio, Playwright, ffmpeg

## Status

- Reel extraction: ✅ Working end-to-end
- Obsidian vault template: ✅ Built with Hormozi example
- MCP server: ✅ Basic implementation
- GitHub repo: ⏳ Ready to push

## Key Decisions

- Playwright fallback handles Instagram without Chrome keychain permissions
- Whisper `base` model default (good balance of speed/accuracy)
- Vault organized by topic (cross-creator), not by creator
- No API keys required — runs 100% locally
