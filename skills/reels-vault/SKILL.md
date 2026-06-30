---
name: reels-vault
description: >-
  Save, transcribe, and search Instagram reels in a local Obsidian "Reel Vault".
  Use when the user shares an Instagram reel/post URL (instagram.com/reel/,
  /reels/, or /p/) and wants to save, extract, transcribe, or analyze it — or
  when they ask what's in their vault ("what do creators say about hooks",
  "show my reels on copywriting", "which creators have I saved"). Runs entirely
  on the user's machine via the reels-vault CLI; no cloud, no paid APIs.
compatibility: "Requires Python 3.10+, ffmpeg, yt-dlp, openai-whisper, and shazamio. Uses uv for fast venv setup."
---

# Reels Vault

A local pipeline that downloads any public Instagram reel, transcribes it with
Whisper, identifies the background music with Shazam, extracts smart metadata
(niche, category, industry), and files it into the user's Obsidian vault —
tagged and indexed so it stays searchable.

## Step 1 — Locate the install (do this first, every time)

```bash
DIR=$(python3 -c "import json,os;p=os.path.expanduser('~/.config/reels-vault/config.json');print(json.load(open(p)).get('install_dir','') if os.path.exists(p) else '')" 2>/dev/null)
[ -z "$DIR" ] && DIR="${REELS_VAULT_DIR:-$HOME/reels-vault}"
echo "$DIR"
```

If `$DIR` doesn't exist or has no `.venv`, install first:

```bash
cd "$DIR" && uv venv && uv pip install -r requirements.txt
```

## Step 2 — Save a reel

When the user shares a reel URL and wants it saved:

```bash
"$DIR/.venv/bin/python3" "$DIR/scripts/extract_reel.py" "<reel-url>" --topic "<topic>"
```

- Pick a short, lowercase, hyphenated `--topic` from the content (e.g.
  `hooks`, `copywriting`, `content-creation`, `ai-tools`). If the user named a
  topic, use theirs verbatim.
- Useful flags:
  - `--whisper-model small` — slower but more accurate transcription
  - `--no-music` — skip Shazam music identification (faster)
  - `--cookies-from chrome` — when download fails with auth errors

The script auto-detects niche, category, and industry from the transcript and
caption, and builds indexes in the vault as reels are added.

## Step 3 — Search / browse the vault

For "what do creators say about X" etc., read the vault directly. The vault
path is `vault_path` in `~/.config/reels-vault/config.json`.

- **Search**: grep `.md` files for keywords
- **Browse indexes**: read `vault/index/` for niche, category, industry breakdowns
- **Read a note**: open the matching `.md` and summarize the transcript

## What Gets Extracted

- **Creator** — username and handle
- **Smart metadata** — niche, category, industry (auto-detected from content)
- **Metrics** — likes, comments, views
- **Music** — song, artist, album, genre, Shazam link
- **Caption + hashtags**
- **Transcript** — full spoken text with timestamps
- **Language** — auto-detected

## Output

Each saved reel is a markdown note with frontmatter (`creator`, `handle`,
`topic`, `niche`, `category`, `industry`, `tags`, `source`, `extracted`).
Indexes grow automatically in `vault/index/` as reels are added.

Cite the creator and source URL when quoting. Never invent transcript content.
