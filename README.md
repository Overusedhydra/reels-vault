# 🎬 Reels Vault

**Paste a URL. Build a knowledge base. Plug into AI.**

A local-first pipeline that extracts transcripts, music, and metadata from any
Instagram reel, then organizes them into your Obsidian vault — tagged by
**topic** and **creator** so you can search across hundreds of reels from
hundreds of creators.

The idea: instead of saving scattered bookmarks, you build a real library.
*"What do 50 creators say about hooks?"* → one search.

```
Instagram Reel → Download → Transcribe → Identify Music → File by Topic → AI-Ready
```

- **Extract** video, transcript, metadata, and music from any public reel
- **Organize** in your own Obsidian vault — grouped by topic, not dumped in a pile
- **Connect** to Claude/Cursor via MCP so your AI can search your reels
- **No API keys, no cloud** — runs 100% on your machine

---

## Quick Start

```bash
# 1. Clone & set up
git clone https://github.com/yourusername/reels-vault.git   # ← TODO: your username
cd reels-vault
chmod +x setup.sh
./setup.sh

# 2. Connect your Obsidian vault (one time)
.venv/bin/python3 scripts/connect.py

# 3. Extract a reel
.venv/bin/python3 scripts/extract_reel.py "https://www.instagram.com/reels/ABC123/" --topic content-creation
```

That's it. The reel lands in your vault at `Reel Vault/content-creation/`,
tagged with creator, topic, and hashtags. Do it 200 times and you've got a
searchable library — organized automatically.

---

## How It Works

### 1. Connect your vault (one time)

```bash
python3 scripts/connect.py
```

Points the pipeline at your Obsidian vault and drops in a `Reel Vault/` folder
with topic notes, creator profiles, and a recipe book. The path is remembered,
so you never type it again.

### 2. Extract reels

```bash
# Basic — files under a topic
.venv/bin/python3 scripts/extract_reel.py "URL" --topic content-creation

# Better transcription (slower)
.venv/bin/python3 scripts/extract_reel.py "URL" --topic marketing --whisper-model small

# Skip Shazam music ID (faster)
.venv/bin/python3 scripts/extract_reel.py "URL" --topic ai --no-music

# If Instagram blocks the download, authenticate via your browser
.venv/bin/python3 scripts/extract_reel.py "URL" --cookies-from chrome

# Raw JSON for custom pipelines
.venv/bin/python3 scripts/extract_reel.py "URL" --json
```

### 3. Your vault organizes itself

Every extracted reel gets a frontmatter label at the top:

```yaml
---
creator: "Alex Hormozi"
handle: hormozi
topic: content-creation
tags: [ads, hooks]
source: https://www.instagram.com/reels/ABC123/
extracted: 2026-06-29
---
```

…so Obsidian can group and filter them automatically. Your vault structure:

```
Your Vault/
  Reel Vault/
    content-creation/      ← reels grouped by topic
      hormozi-reel-2026-06-29.md
      ali-abdaal-reel-2026-06-29.md
    marketing/
      garyvee-reel-2026-06-29.md
    topics/                ← cross-creator notes (Hooks, Scripting, ...)
    creators/              ← per-creator profiles
    recipes/               ← copy-paste formulas
```

Install the [Dataview](https://github.com/blacksmithgu/obsidian-dataview)
plugin in Obsidian and the built-in index/queries light up automatically.

### 4. Plug into AI (optional)

Add the MCP server to Claude Desktop, Cursor, or any MCP client:

```jsonc
// Claude Desktop: ~/Library/Application Support/Claude/claude_desktop_config.json
{
  "mcpServers": {
    "reels-vault": {
      "command": "/path/to/reels-vault/.venv/bin/python3",
      "args": ["/path/to/reels-vault/mcp/server.py"],
      "env": { "REELS_VAULT_PATH": "/path/to/your-vault/Reel Vault" }
    }
  }
}
```

Now your AI can `search_reels`, `list_topics`, `list_creators`, `read_note`,
and `vault_status` — it reads your reel library without you pasting anything.

---

## Output Example

```markdown
---
creator: "Alex Hormozi"
handle: hormozi
topic: content-creation
tags: [ads, hooks]
source: https://www.instagram.com/reels/ABC123/
extracted: 2026-06-29
---

## Transcript
*Language detected: en*

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

---

## Requirements

- **Python** 3.10+ (enforced by `setup.sh`)
- **ffmpeg** (auto-installed on macOS/Linux via Homebrew/apt)
- **yt-dlp**, **Whisper**, **shazamio**, **mcp** — all pip-installed by `setup.sh`
- ~1 GB disk for the Whisper `base` model

**macOS / Linux:** run `./setup.sh`.
**Windows:** install [Python](https://python.org), [ffmpeg](https://ffmpeg.org/download.html),
then `pip install -r requirements.txt` inside a venv.

## Limitations

- Instagram rate-limits and changes often. If a download fails, retry with
  `--cookies-from chrome` (or firefox/safari) to authenticate.
- Whisper `base` is fast but not perfect — use `small`/`medium` for accuracy.
- Shazam works on the audio mix; speech-heavy reels may not ID a track.
- Respect creators' content and Instagram's Terms of Service. For personal
  research/learning.

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Issues and PRs welcome.

## Acknowledgments

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — video downloading
- [openai-whisper](https://github.com/openai/whisper) — transcription
- [shazamio](https://github.com/dotenv-io/shazamio) — music identification
- [MCP](https://github.com/modelcontextprotocol) — AI tool integration
