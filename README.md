# 🎬 Reels Vault

**Extract. Understand. Organize. Plug into AI.**

An open-source marketing intelligence pipeline that extracts transcripts, music, and insights from any Instagram reel — then organizes them into an AI-ready knowledge base.

## What It Does

```
Instagram Reel → Download → Transcribe → Identify Music → Organize → AI-Ready
```

- **Extract** any public Instagram reel (video, transcript, metadata)
- **Understand** content with Whisper transcription + Shazam music ID
- **Organize** into an Obsidian knowledge base (topics, creators, recipes)
- **Connect** to AI agents via MCP server or JSON exports

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/yourusername/reels-vault.git
cd reels-vault

# 2. Run setup (installs everything)
chmod +x setup.sh
./setup.sh

# 3. Extract a reel
.venv/bin/python3 scripts/extract_reel.py "https://www.instagram.com/reels/ABC123/"
```

## Features

### Extraction Pipeline
- **yt-dlp** for fast downloads (when available)
- **Playwright** fallback (no Chrome keychain needed)
- **Whisper** transcription (multiple model sizes)
- **Shazam** music identification
- **Frame extraction** for visual analysis

### Knowledge Base Template
Pre-built Obsidian vault structure with:
- **Topic notes** — Cross-referenced by creator (Hooks, Scripting, Editing, etc.)
- **Creator profiles** — Per-creator frameworks and systems
- **Recipe book** — Copy-paste formulas from top creators
- **Extracts** — Raw transcripts with metadata

### AI Integration
- **MCP server** — Query your vault from Claude, Cursor, or any MCP tool
- **JSON export** — Structured data for any AI workflow
- **Prompt templates** — Analyze reels, extract frameworks, generate recipes

## Usage

### Extract a Reel

```bash
# Basic extraction
.venv/bin/python3 scripts/extract_reel.py "https://www.instagram.com/reels/ABC123/"

# Save to a directory
.venv/bin/python3 scripts/extract_reel.py "URL" --save-dir ./extractions

# Better transcription (slower)
.venv/bin/python3 scripts/extract_reel.py "URL" --whisper-model small

# JSON output for AI processing
.venv/bin/python3 scripts/extract_reel.py "URL" --json

# Skip frame extraction
.venv/bin/python3 scripts/extract_reel.py "URL" --no-frames
```

### Set Up the Knowledge Base

```bash
# Copy the vault template to your Obsidian vault
cp -r vault-template/ ~/path/to/your/obsidian-vault/content-recipes/
```

### Use the MCP Server

```python
# Add to your MCP config
{
  "mcpServers": {
    "reels-vault": {
      "command": "python3",
      "args": ["path/to/reels-vault/mcp/server.py"]
    }
  }
}
```

## Output Example

```markdown
# Instagram Reel Extraction

**Source:** https://www.instagram.com/reels/ABC123/
**Extracted:** 2026-06-29 12:00 UTC

## Metadata
- **Creator:** Alex Hormozi (@hormozi)
- **Views:** 44,000
- **Likes:** 44,000

## Transcript
Here's how to take a company's ads from this to this...

## Timestamped Transcript
[00:00] Here's how to take a company's ads from this to this.
[00:02] So ads are made up of three parts.
[00:03] Hook, meat, CTA.
```

## Whisper Models

| Model  | Speed    | Accuracy | Memory  |
|--------|----------|----------|---------|
| tiny   | Fastest  | Lower    | ~1 GB   |
| base   | Fast     | Good     | ~1 GB   |
| small  | Moderate | Better   | ~2 GB   |
| medium | Slow     | Great    | ~5 GB   |
| large  | Slowest  | Best     | ~10 GB  |

## Requirements

- Python 3.10+
- ffmpeg
- yt-dlp
- ~1 GB disk for Whisper base model

## License

MIT License — see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Open an issue or submit a PR.

## Acknowledgments

- [openai-whisper](https://github.com/openai/whisper) for transcription
- [shazamio](https://github.com/dotenv-io/shazamio) for music identification
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) for video downloading
- [Playwright](https://playwright.dev/) for browser automation
