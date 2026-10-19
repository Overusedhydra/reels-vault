---
name: reels-vault
description: >-
  Save, transcribe, classify, and search Instagram reels in Obsidian, Notion, or
  both. Use when the user shares an Instagram reel/post URL (instagram.com/reel/,
  /reels/, or /p/) and wants to save, extract, transcribe, or analyze it — or
  when they ask what's in their vault ("what do creators say about hooks",
  "show my reels on copywriting", "which creators have I saved"). Runs locally
  via the reels-vault CLI; no cloud classification APIs.
compatibility: "Requires Python 3.10+, ffmpeg, yt-dlp, openai-whisper, shazamio, Playwright, and PyYAML."
---

# Reels Vault

Download a public Instagram reel, transcribe it with Whisper, identify music
with Shazam, extract optional frames, and save a tagged note to Obsidian,
Notion, or both. Classification is **agent-in-the-loop**: you label the reel
after saving it. The repo has no keyword tables or classification API.

## Step 1 — Locate the install (every time)

```bash
DIR=$(python3 -c "import json,os;p=os.path.expanduser('~/.config/reels-vault/config.json');print(json.load(open(p)).get('install_dir','') if os.path.exists(p) else '')" 2>/dev/null)
[ -z "$DIR" ] && DIR="${REELS_VAULT_DIR:-$HOME/reels-vault}"
echo "$DIR"
```

If `$DIR` has no `.venv`, run its setup once:

```bash
cd "$DIR" && ./setup.sh
```

If storage is not configured yet, run `"$DIR/.venv/bin/reels-vault-connect"`
and let the user choose Obsidian, Notion, or both. Check with:

```bash
"$DIR/.venv/bin/reels-vault-mcp" --check
```

## Step 2 — Save and classify a reel

Save the reel first. Use `--json` when you need the full result, but the note is
saved either way:

```bash
"$DIR/.venv/bin/reels-vault" "<reel-url>" --topic "<topic>"
```

- Pick a short, lowercase, hyphenated `--topic` from the content (e.g.
  `hooks`, `copywriting`, `content-creation`, `ai-tools`). If the user named a
  topic, use theirs verbatim.
- Useful flags: `--whisper-model small`, `--no-music`, `--cookies-from chrome`,
  `--frame-max-width 1280`, `--no-frames`.
- `--storage obsidian|notion|both` overrides the configured backend for one run.

Then classify the new note using your own reading of the transcript, caption,
and visuals. Do not ask another API and do not guess from the creator name:

```bash
"$DIR/.venv/bin/reels-vault-classify" --source "<reel-url>" \
  --metadata-json '{"niche":"business","category":"marketing","industry":"education","tags":["ads","hooks"]}'
```

- Labels are freeform unless the user configured `taxonomy.json`; if validation
  rejects a value, read the allowed list in the error and retry.
- Use `--list-unclassified` to find reels saved earlier without labels.
- Use `--note "<ref>"` instead of `--source` when you already have a ref.

## Step 2b — Bulk import many reels

Bulk mode downloads everything through one shared browser into a local cache,
then runs extraction offline:

```bash
"$DIR/.venv/bin/python" -m reels_vault.bulk_import urls.txt --topic "<topic>"
```

- `urls.txt` = one reel URL per line; duplicates and already-saved reels are skipped.
- `--download-only` / `--process-only` resume a half-finished run.
- `--delay 3` seconds if Instagram starts rate-limiting.
- After the run, classify new notes with `--list-unclassified` and your own labels.

## Step 2c — Import recent reels from a creator

```bash
"$DIR/.venv/bin/python" -m reels_vault.import_creator "<creator>" --limit 25 --topic "<topic>" --import
```

- `<creator>` can be `username`, `@username`, or a profile URL.
- Omit `--import` to only write the URL list.
- Default topic is the creator username.
- Use `--download-only` / `--process-only` to resume through the bulk runner.

## Step 3 — Search / browse

Search through the MCP tools when available (`search_reels`, `list_topics`,
`list_creators`, `read_note`). Otherwise:

- **Obsidian:** read `vault_path` from `~/.config/reels-vault/config.json`,
  then search `Reels/**/*.md` or browse `index/` and `Creators/`.
- **Notion:** use the MCP search tools, or open the Reel Vault database views.
- **Read a note:** open the matching ref and summarize the transcript.

## What Gets Extracted

- Creator name and handle
- Metrics (views, likes, comments)
- Music (song, artist, album, genre, Shazam link)
- Caption and hashtags
- Transcript with timestamps and language
- Optional key frames as WebP, capped by `--frame-max-width` (default 1280).
  Obsidian only; JPEG is used if ffmpeg lacks libwebp.

## Output

Each note starts with valid YAML frontmatter (`creator`, `handle`, `topic`,
`niche`, `category`, `industry`, `classification: pending`, `tags`, `source`,
`source_id`, `extracted`). After classification, `classification` changes to
`classified` and the labels are written to the note or Notion page.

Cite the creator and source URL when quoting. Never invent transcript content.
