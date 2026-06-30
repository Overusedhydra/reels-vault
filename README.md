# 🎬 Reels Vault

**Paste a reel URL. Get a transcript. Ask your AI about it.

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
- **No cloud, no paid APIs** — runs entirely on your machine (Instagram cookies may be needed for downloads; see Limitations)

---

## Quick Start

### The easy way — use Claude (no terminal needed)

**Step 1:** Install Reels Vault (paste this in your terminal — one time only):

```bash
curl -fsSL https://raw.githubusercontent.com/Overusedhydra/reels-vault/main/install.sh | bash
```

**Step 2:** Open Claude Desktop → **Settings → Developer → Edit Config**. Paste this:

```json
{
  "mcpServers": {
    "reels-vault": {
      "command": "/Users/you/reels-vault/.venv/bin/python3",
      "args": ["/Users/you/reels-vault/mcp_server/server.py"]
    }
  }
}
```

> Replace `/Users/you/reels-vault` with the actual path. Run `pwd` in the
> `reels-vault` folder to find it.

**Step 3:** Quit and reopen Claude Desktop.

**Step 4:** Paste any reel link and tell Claude to save it:

> *"Save this reel: https://www.instagram.com/reels/ABC123/"*

That's it. Claude downloads it, transcribes it, finds the music, and files it
into your Obsidian vault. No commands. No copy-pasting.

Want to search what you've saved? Just ask:

> *"What do creators say about hooks?"*

---

<details>
<summary><strong>Prefer the terminal? (click to expand)</strong></summary>

```bash
# Install
curl -fsSL https://raw.githubusercontent.com/Overusedhydra/reels-vault/main/install.sh | bash
cd ~/reels-vault

# Save a reel
.venv/bin/reels-vault "https://www.instagram.com/reels/ABC123/" --topic hooks

# Better transcription (slower)
.venv/bin/reels-vault "URL" --topic marketing --whisper-model small

# Skip music ID (faster)
.venv/bin/reels-vault "URL" --topic ai --no-music

# If Instagram blocks the download
.venv/bin/reels-vault "URL" --cookies-from chrome
```

</details>

---

## How It Works

### 1. Install (one time)

```bash
curl -fsSL https://raw.githubusercontent.com/Overusedhydra/reels-vault/main/install.sh | bash
```

This clones the repo, installs all dependencies, and asks where your Obsidian
vault is. Takes about 2 minutes the first time.

### 2. Connect Claude Desktop

Paste the MCP config into Claude Desktop's settings (see Quick Start above).
Now Claude can use Reels Vault — paste a reel link and it saves everything.

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

### 4. Let Claude do it for you (recommended — no terminal!)

This is the easiest way to use Reels Vault. After a one-time setup, you just
**talk to Claude** — paste a reel link and it does everything:

> *"Save this reel to my vault: https://www.instagram.com/reel/ABC123/"*

Claude downloads it, transcribes it, finds the music, and files it away. No
commands, no copy-pasting transcripts. It can also search everything you've
saved (*"What do creators say about hooks?"*).

**One-time setup (about 2 minutes):**

1. Open Claude Desktop → **Settings → Developer → Edit Config**. (This opens a
   file called `claude_desktop_config.json`.)
2. Paste in the block below.
3. Replace the **3 paths** with your real ones (see the tip under the block).
4. Save the file and fully quit + reopen Claude Desktop.

```jsonc
{
  "mcpServers": {
    "reels-vault": {
      "command": "/path/to/reels-vault/.venv/bin/python3",
      "args": ["/path/to/reels-vault/mcp_server/server.py"],
      "env": { "REELS_VAULT_PATH": "/path/to/your-vault/Reel Vault" }
    }
  }
}
```

> **Tip — getting the paths right:** in the `reels-vault` folder, run `pwd` in
> your terminal to print its full path. Swap that in for `/path/to/reels-vault`
> (both times). For the last line, use the `Reel Vault` folder that
> `connect.py` created inside your Obsidian vault.

Once it's connected, Claude can `extract_reel` (save a new reel), `search_reels`,
`list_topics`, `list_creators`, `read_note`, and `vault_status` — all by itself.

> Prefer doing it by hand? The `extract_reel.py` command in step 2 above always
> works without any of this.

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
- **yt-dlp**, **Whisper**, **shazamio**, **Playwright** — all pip-installed by `setup.sh`
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
