---
name: reels-vault-lite
description: >-
  Low-space, Obsidian-only Instagram reel saver. Downloads a public reel with
  yt-dlp, transcribes locally with NVIDIA Nemotron 3.5 ASR through the official
  nemo-speech runtime, and writes a tagged Markdown note. Use when the user
  wants a lightweight install without the pip package, MCP server, Notion,
  music ID, or browser automation — especially on low-disk or Windows machines.
compatibility: "Requires Python 3.9+, yt-dlp, ffmpeg, and nemo-speech. No PyTorch or Playwright."
---

# Reels Vault Lite

Save a public Instagram reel to Obsidian with a local transcript. This path
trades Notion, Shazam music ID, Playwright, and the pip package for a
~700 MB model plus small native binaries. Classification stays
**agent-in-the-loop**: the note starts as `classification: pending`.

## Step 1 — Locate the skill

```bash
SKILL_DIR=$(python3 -c 'import os,sys; print(os.path.dirname(os.path.realpath(sys.argv[1])))' "$HOME/.claude/skills/reels-vault-lite")
test -f "$SKILL_DIR/SKILL.md" || SKILL_DIR="$HOME/reels-vault/skills/reels-vault-lite"
```

## Step 2 — One-time setup

macOS/Linux:

```bash
"$SKILL_DIR/setup.sh" --install --with-model
```

Windows PowerShell:

```powershell
$SkillDir = "$HOME\reels-vault\skills\reels-vault-lite"
powershell -ExecutionPolicy Bypass -File "$SkillDir\setup.ps1" -Install -WithModel
```

> On Windows, use `py "$SkillDir\scripts\reels_vault_lite.py" ...` for the
> commands below instead of `python3`.

- Installs `nemo-speech` (official NVIDIA CPU/Metal/CUDA/Vulkan runtime) and
  `yt-dlp` into user-local paths.
- Downloads the default `nemotron-3.5` Q8 model (~708 MB) only with
  `--with-model` / `-WithModel`.
- `ffmpeg` must already be installed. Use `brew install ffmpeg` on macOS,
  `sudo apt install ffmpeg` on Debian/Ubuntu, or
  `winget install Gyan.FFmpeg` on Windows.
- No pip packages, PyTorch, Playwright, or browser download.

Configure the Obsidian vault once (skip if the full Reels Vault config already
has `vault_path`). Pass the Obsidian vault root; notes go under its `Reel Vault`
subfolder, matching the full installer:

```bash
python3 "$SKILL_DIR/scripts/reels_vault_lite.py" configure --vault "/path/to/ObsidianVault"
```

Check dependencies, vault, and model cache:

```bash
python3 "$SKILL_DIR/scripts/reels_vault_lite.py" status
```

## Step 3 — Save a reel

Pick a short lowercase topic from the content (for example `hooks`,
`copywriting`, `ai-tools`). If the user named a topic, use theirs verbatim.

```bash
python3 "$SKILL_DIR/scripts/reels_vault_lite.py" save "<reel-url>" --topic "<topic>"
```

The command prints the saved note path. Add `--json` for a machine-readable
result. Useful flags:

- `--cookies-from chrome` (or `safari`, `firefox`, `edge`) when Instagram
  blocks the download; `--cookies /path/cookies.txt` also works.
- `--frames 3` to download video and save up to three WebP key frames
  (off by default; costs bandwidth, not dependencies).
- `--frame-max-width 1280` to cap frame width.
- `--model nemotron-en` for English-only, or `--model parakeet-tdt` for 25
  European languages. The default `nemotron-3.5` is multilingual.

Notes are written to `Reels/<topic>/<handle>-reel-<date>-<shortcode>.md`.
Re-saving the same source reuses the existing note. `index/`, `Creators/`, and
`Index.md` are maintained automatically.

## Step 4 — Classify the new note

Read the transcript, caption, and any frames. Label the reel with your own
judgment; do not guess from the creator name:

```bash
python3 "$SKILL_DIR/scripts/reels_vault_lite.py" classify "<note-ref-or-path>" \
  --niche "business" --category "marketing" --industry "education" \
  --tags "ads,hooks"
```

Omit labels you are not confident about. `classify` sets
`classification: classified` and updates the note body and indexes.

## Step 5 — Search and read

```bash
python3 "$SKILL_DIR/scripts/reels_vault_lite.py" search "hooks" --limit 10
python3 "$SKILL_DIR/scripts/reels_vault_lite.py" search --creator "hormozi" --json
```

Or read `Reels/**/*.md` directly. Cite the creator and source URL when quoting.
Never invent transcript content.

## What this path omits

- Notion, MCP server, and the pip/Whisper package.
- Shazam music identification.
- Playwright browser automation and Instagram login sessions.
- Automatic frame extraction unless `--frames` is passed.

If the user needs Notion, music ID, bulk import, creator discovery, or MCP
search, use the full `reels-vault` skill instead.
