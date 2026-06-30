---
name: reels-vault
description: >-
  Save, transcribe, and search Instagram reels in a local Obsidian "Reel Vault".
  Use when the user shares an Instagram reel/post URL (instagram.com/reel/,
  /reels/, or /p/) and wants to save, extract, transcribe, or analyze it — or
  when they ask what's in their vault ("what do creators say about hooks",
  "show my reels on copywriting", "which creators have I saved"). Runs entirely
  on the user's machine via the reels-vault CLI; no cloud, no paid APIs.
---

# Reels Vault

A local pipeline that downloads any public Instagram reel, transcribes it with
Whisper, identifies the background music with Shazam, and files it into the
user's Obsidian vault — tagged by topic and creator so it stays searchable.

This skill drives the already-installed `reels-vault` CLI. It does **not**
reimplement extraction; it shells out to the bundled scripts.

## Step 1 — Locate the install (do this first, every time)

The repo and its virtualenv live wherever the user installed Reels Vault. Find
it from the config that `connect.py` wrote, with sensible fallbacks:

```bash
DIR=$(python3 -c "import json,os;p=os.path.expanduser('~/.config/reels-vault/config.json');print(json.load(open(p)).get('install_dir','') if os.path.exists(p) else '')" 2>/dev/null)
[ -z "$DIR" ] && DIR="${REELS_VAULT_DIR:-$HOME/reels-vault}"
echo "$DIR"
```

- `$DIR/.venv/bin/reels-vault` is the CLI.
- `$DIR/.venv/bin/python3 $DIR/scripts/connect.py` connects an Obsidian vault.

If `$DIR` doesn't exist or has no `.venv`, Reels Vault isn't installed yet —
tell the user to run the one-line installer from the README
(`curl -fsSL https://raw.githubusercontent.com/Overusedhydra/reels-vault/main/install.sh | bash`)
and, if needed, connect a vault with
`"$DIR/.venv/bin/python3" "$DIR/scripts/connect.py" "<path-to-obsidian-vault>"`.

## Step 2 — Save a reel

When the user shares a reel URL and wants it saved, run:

```bash
"$DIR/.venv/bin/reels-vault" "<reel-url>" --topic "<topic>"
```

- Pick a short, lowercase, hyphenated `--topic` from the content (e.g.
  `hooks`, `copywriting`, `content-creation`, `ai-tools`). If the user named a
  topic, use theirs verbatim. If unsure, ask once or default to a sensible
  guess and tell them what you chose.
- Useful flags:
  - `--whisper-model small` — slower but more accurate transcription
    (default is `base`). Offer this if the user complains about transcript
    quality.
  - `--no-music` — skip Shazam music identification (faster).
  - `--cookies-from chrome` (or `firefox`/`safari`) — use when a download
    fails with a login/rate-limit error; Instagram often requires auth.
- Extraction downloads + transcribes, so it can take a minute or more. Don't
  re-run on a timeout; report progress and let it finish.
- On failure, read the CLI's error. The most common fix is retrying with
  `--cookies-from chrome`.

Relay the saved file path and a one-line summary of what the reel was about.

## Step 3 — Search / browse the vault

For "what do creators say about X", "show my reels on Y", "which creators have
I saved", etc., use the bundled MCP tools if the client has the `reels-vault`
MCP server connected. Otherwise read the vault directly — the vault path is the
`vault_path` field in `~/.config/reels-vault/config.json`:

- **Search**: grep the vault's `.md` files for the keyword and show the
  matching reels (creator + path + snippet).
- **List topics**: list the topic folders at the vault root (everything except
  `topics/`, `creators/`, `recipes/`, `extracts/`).
- **List creators**: read `creators/` notes.
- **Read a note**: open the matching `.md` and summarize the transcript.

Each saved reel is a markdown note with frontmatter (`creator`, `handle`,
`topic`, `tags`, `source`, `extracted`) followed by a transcript and a
timestamped transcript. Cite the creator and source URL when you quote one.

## Guardrails

- Only act on Instagram reel/post URLs the user provides. Don't fetch or save
  anything they didn't ask for.
- This is for the user's personal research. Respect creators' content and
  Instagram's Terms of Service; don't republish transcripts externally.
- Never invent transcript content — if a reel isn't in the vault, say so and
  offer to extract it.
