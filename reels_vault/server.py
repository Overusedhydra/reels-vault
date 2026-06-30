#!/usr/bin/env python3
"""
Reels Vault MCP Server

Expose your Reels Vault knowledge base to any MCP-compatible AI tool
(Claude Desktop, Cursor, Continue, etc.) so the AI can search your reels,
browse creators, and read transcripts without you pasting them by hand.

Usage — add to your client's MCP config:

    {
      "mcpServers": {
        "reels-vault": {
          "command": "/path/to/reels-vault/.venv/bin/reels-vault-mcp",
          "env": { "REELS_VAULT_PATH": "/path/to/your-vault/Reel Vault" }
        }
      }
    }

REELS_VAULT_PATH defaults to the vault you connected via `reels-vault-connect`.
Run it standalone (`reels-vault-mcp --check`) for a quick smoke test.
"""

import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from reels_vault.config import load_config


def _vault_path() -> Path:
    """Resolve the vault path from env var, else the connected vault."""
    env = os.environ.get("REELS_VAULT_PATH", "")
    if env:
        return Path(env).expanduser()
    connected = load_config().get("vault_path", "")
    if connected:
        return Path(connected)
    # Last-resort fallback: a `vault/` folder next to this repo
    return Path(__file__).resolve().parent.parent / "vault"


VAULT = _vault_path()

mcp = FastMCP("reels-vault")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _iter_notes(subdir: str):
    """Yield every .md note under <vault>/<subdir>/ (recursive). Topic folders
    like 'content-creation/' live at the vault root, so we scan the whole vault
    for the topic-grouped reels, and named subdirs for the template content."""
    base = VAULT / subdir
    if base.is_dir():
        yield from base.rglob("*.md")
    # Also scan topic folders at the vault root (where reels actually land)
    if subdir == "extracts":
        for child in VAULT.iterdir():
            if child.is_dir() and child.name not in ("topics", "creators", "recipes", "extracts"):
                yield from child.rglob("*.md")


@mcp.tool()
def search_reels(query: str, creator: str = "", topic: str = "") -> str:
    """Search your extracted reels by keyword. Optional filters: creator name, topic.

    Returns matching notes (path + first 500 chars) so the AI can decide which
    to read in full via read_note().
    """
    q = query.lower()
    c = creator.lower()
    t = topic.lower()
    hits = []

    for f in _iter_notes("extracts"):
        if not f.is_file():
            continue
        text = _read(f)
        if q and q not in text.lower():
            continue
        if c and c not in text.lower():
            continue
        if t and t != f.parent.name.lower():
            continue
        hits.append(f"- {f.relative_to(VAULT)}\n  {text[:500].strip()}")

    if not hits:
        return f"No reels found for query='{query}'" + (f" topic='{topic}'" if topic else "")
    return f"{len(hits)} reel(s) found:\n\n" + "\n".join(hits)


@mcp.tool()
def list_topics() -> str:
    """List every topic folder (and the built-in topic notes) in the vault."""
    out = []
    # User-created topic folders (where reels get filed)
    builtin = {"topics", "creators", "recipes", "extracts"}
    for child in sorted(VAULT.iterdir()):
        if child.is_dir() and child.name not in builtin:
            count = sum(1 for _ in child.rglob("*.md"))
            out.append(f"- {child.name} ({count} reel(s))")
    # Built-in topic notes from the template
    topics_dir = VAULT / "topics"
    if topics_dir.is_dir():
        notes = [f.stem for f in topics_dir.glob("*.md")]
        if notes:
            out.append("\nBuilt-in topic notes:")
            out += [f"  - {n}" for n in sorted(notes)]
    return "\n".join(out) or "Vault is empty. Extract some reels first."


@mcp.tool()
def list_creators() -> str:
    """List creator profiles in the vault."""
    creators_dir = VAULT / "creators"
    if not creators_dir.is_dir():
        return "No creators folder found."
    skip = {"Creator Profiles.md", "Creator Template.md"}
    names = sorted(f.stem for f in creators_dir.glob("*.md") if f.name not in skip)
    return "\n".join(f"- {n}" for n in names) or "No creators yet."


@mcp.tool()
def read_note(relative_path: str) -> str:
    """Read a note by its path relative to the vault root (e.g.
    'content-creation/hormozi-reel-2026-06-29.md'). Returns the full text."""
    # Block path traversal — only allow paths under the vault
    target = (VAULT / relative_path).resolve()
    try:
        target.relative_to(VAULT.resolve())
    except ValueError:
        return "Error: path must stay inside the vault."
    if not target.is_file():
        return f"Not found: {relative_path}"
    return _read(target)


@mcp.tool()
def vault_status() -> str:
    """Show where the vault is and a quick inventory (reel count, topics)."""
    if not VAULT.exists():
        return (f"Vault not found at: {VAULT}\n"
                f"Set REELS_VAULT_PATH or run reels-vault-connect.")
    reels = sum(1 for _ in _iter_notes("extracts"))
    return (f"Vault: {VAULT}\n"
            f"Reels: {reels}\n"
            f"Path: {VAULT}")


@mcp.tool()
def extract_reel(url: str, topic: str = "", whisper_model: str = "base",
                 skip_music: bool = False) -> str:
    """Extract an Instagram reel and save it into the vault — no terminal needed.

    Give it a reel URL and (optionally) a topic to file it under. This downloads
    the reel, transcribes the speech, identifies the music, and writes a tagged
    Markdown note into your connected vault. Use this when the user pastes an
    Instagram reel/post link and wants it saved.

    Args:
        url: The Instagram reel or post URL.
        topic: Optional topic folder to file under (e.g. "hooks", "marketing").
        whisper_model: Transcription model — tiny/base/small/medium/large.
        skip_music: Set True to skip Shazam music identification (faster).

    Returns a short summary of what was saved and where.
    """
    import tempfile
    import shutil
    from reels_vault.extract import (
        extract_metadata, extract_audio, transcribe,
        identify_music, format_output, save_extraction,
    )

    if not VAULT.exists():
        return (f"No vault connected (looked at {VAULT}).\n"
                "Run reels-vault-connect once, or set REELS_VAULT_PATH.")

    work_dir = tempfile.mkdtemp(prefix="reel_")
    try:
        video_path, metadata = extract_metadata(url, work_dir)
        audio_path = extract_audio(video_path, work_dir)
        transcript = transcribe(audio_path, whisper_model)

        music = {}
        if not skip_music:
            try:
                music = identify_music(audio_path)
            except Exception:
                music = {}

        output = format_output(metadata, transcript, original_url=url,
                               music=music or None, topic=topic)
        save_path = save_extraction(output, metadata, str(VAULT), topic=topic)

        # Build a short, human-readable confirmation
        creator = metadata.get("author", "Unknown")
        words = len(transcript.get("text", "").split())
        rel = os.path.relpath(save_path, str(VAULT))
        lines = [
            "✅ Reel saved to your vault.",
            f"- Creator: {creator}",
            f"- Filed under: {topic or '(vault root)'}",
            f"- Transcript: {words} words ({transcript.get('language', '?')})",
        ]
        if music:
            lines.append(f"- Music: {music.get('artist', '?')} — {music.get('title', '?')}")
        lines.append(f"- Saved as: {rel}")
        return "\n".join(lines)
    except Exception as e:
        return (f"Extraction failed: {e}\n"
                "Instagram may be blocking the download — the user can retry, "
                "or run the CLI with --cookies-from chrome to authenticate.")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def run():
    # `--check` runs a standalone smoke test and exits. Everything goes to
    # stderr so it can never corrupt the stdio JSON-RPC stream.
    if "--check" in sys.argv:
        print("Reels Vault MCP Server", file=sys.stderr)
        print(f"Vault path: {VAULT}", file=sys.stderr)
        if VAULT.exists():
            print(vault_status(), file=sys.stderr)
        else:
            print("(no vault connected — run reels-vault-connect or set "
                  "REELS_VAULT_PATH)", file=sys.stderr)
        sys.exit(0)

    # Default invocation (what Claude Desktop / Cursor launch): serve over stdio.
    # A short banner on stderr is fine — clients read JSON-RPC from stdout only.
    print(f"Reels Vault MCP Server — vault: {VAULT}", file=sys.stderr)
    mcp.run()


if __name__ == "__main__":
    run()
