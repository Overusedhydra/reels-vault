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
          "command": "python3",
          "args": ["/path/to/reels-vault/mcp_server/server.py"],
          "env": { "REELS_VAULT_PATH": "/path/to/your-vault/Reel Vault" }
        }
      }
    }

REELS_VAULT_PATH defaults to the vault you connected via `scripts/connect.py`.
Run it standalone (`python3 mcp_server/server.py`) for a quick smoke test.
"""

import os
import sys
from pathlib import Path

# Allow importing the shared config from scripts/
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from mcp.server.fastmcp import FastMCP
from config import load_config


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
                f"Set REELS_VAULT_PATH or run scripts/connect.py.")
    reels = sum(1 for _ in _iter_notes("extracts"))
    return (f"Vault: {VAULT}\n"
            f"Reels: {reels}\n"
            f"Path: {VAULT}")


if __name__ == "__main__":
    # Standalone smoke test (doesn't start the server loop)
    print("Reels Vault MCP Server")
    print(f"Vault path: {VAULT}")
    if VAULT.exists():
        print(vault_status())
    else:
        print("(no vault connected — run scripts/connect.py or set REELS_VAULT_PATH)")
