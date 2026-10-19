#!/usr/bin/env python3
"""Reels Vault MCP server.

Exposes Obsidian and/or Notion storage to MCP clients.  Add it to your client:

    {
      "mcpServers": {
        "reels-vault": {
          "command": "python3",
          "args": ["/path/to/reels-vault/mcp_server/server.py"]
        }
      }
    }

Configuration is read from ``~/.config/reels-vault/config.json``.  The
``REELS_VAULT_PATH``, ``REELS_STORAGE``, ``NOTION_TOKEN``, and
``REELS_NOTION_DATABASE_ID`` environment variables override it.
"""

from __future__ import annotations

import json
import sys

if __package__:
    from scripts.config import load_config
    from scripts.extract_reel import run_extraction
    from scripts.storage import StorageManager, StorageError
else:
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.config import load_config
    from scripts.extract_reel import run_extraction
    from scripts.storage import StorageManager, StorageError


def _manager() -> StorageManager:
    return StorageManager(load_config())


def _json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def _check() -> None:
    print("Reels Vault MCP Server", file=sys.stderr)
    try:
        status = _manager().status()
        print(_json(status), file=sys.stderr)
    except Exception as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
    sys.exit(0)


def build_server():
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("reels-vault")

    @mcp.tool()
    def search_reels(query: str = "", creator: str = "", topic: str = "",
                     limit: int = 20) -> str:
        """Search saved reels across Obsidian and/or Notion.

        Returns compact results with a ``ref``. Pass that ref to ``read_note``
        for the full transcript. Results are capped by ``limit`` (default 20).
        """
        try:
            records = _manager().search(query, creator, topic, limit=limit)
        except StorageError as exc:
            return f"Search error: {exc}"
        if not records:
            return "No reels found."
        lines = [f"{len(records)} result(s):"]
        for record in records:
            backends = ",".join(record.get("backends") or [record.get("backend", "")])
            lines.append(
                f"\n- {record.get('title', 'Reel')} [{backends}]\n"
                f"  ref: {record.get('ref')}\n"
                f"  creator: {record.get('creator', '')} | topic: {record.get('topic', '')} | "
                f"classification: {record.get('classification', '')}\n"
                f"  source: {record.get('source', '')}\n"
                f"  {record.get('snippet', '')[:500]}"
            )
        return "\n".join(lines)

    @mcp.tool()
    def list_topics() -> str:
        """List topics and reel counts across configured backends."""
        topics = _manager().list_topics()
        if not topics:
            return "No topics yet. Extract a reel first."
        return "\n".join(f"- {row['topic']} ({row['count']} reel(s))" for row in topics)

    @mcp.tool()
    def list_creators() -> str:
        """List creators and reel counts across configured backends."""
        creators = _manager().list_creators()
        if not creators:
            return "No creators yet."
        return "\n".join(
            f"- {row['creator']} (@{row.get('handle', '')}) — {row['count']} reel(s)"
            for row in creators
        )

    @mcp.tool()
    def read_note(ref: str) -> str:
        """Read a note by its ``ref`` from search results or list_unclassified.

        Obsidian refs look like ``Reels/topic/note.md``. Notion refs start with
        ``notion:`` followed by the page id.
        """
        try:
            return _manager().read(ref)
        except FileNotFoundError:
            return f"Not found: {ref}"
        except StorageError as exc:
            return f"Error: {exc}"

    @mcp.tool()
    def vault_status() -> str:
        """Show configured storage backends and reel counts."""
        return _json(_manager().status())

    @mcp.tool()
    def extract_reel(url: str, topic: str = "", whisper_model: str = "base",
                     skip_music: bool = False, skip_frames: bool = False,
                     storage: str = "") -> str:
        """Download, transcribe, and save a reel to Obsidian and/or Notion.

        Classification is deliberately left pending. After this returns, read
        the note and call ``classify_reel`` with niche/category/industry/tags.
        """
        logs: list[str] = []
        try:
            result = run_extraction(
                url, whisper_model=whisper_model, topic=topic,
                no_music=skip_music, no_frames=skip_frames,
                save=True, storage=storage or None,
                log=lambda message: logs.append(message),
            )
        except Exception as exc:
            return f"Extraction failed: {exc}\n" + "\n".join(logs[-10:])

        refs = []
        for item in result.get("saved", []):
            refs.append(f"- {item['backend']}: {item.get('ref') or item.get('path') or item.get('url')}")
        header = "\n".join(logs[-12:])
        warning = ""
        if result.get("errors"):
            warning = "\nWarnings:\n" + "\n".join(f"- {error}" for error in result["errors"])
        return (
            f"{header}\n\nSaved:\n" + ("\n".join(refs) or "- (nothing saved)") +
            f"\n\nClassification is pending. Use the note below, then call classify_reel.\n"
            f"{warning}\n\n--- NOTE ---\n{result.get('note', '')}"
        )

    @mcp.tool()
    def list_unclassified(limit: int = 100) -> str:
        """List notes waiting for AI classification."""
        rows = _manager().list_unclassified(limit)
        if not rows:
            return "No unclassified reels."
        lines = []
        for row in rows:
            lines.append(
                f"- ref: {row.get('ref')} | creator: {row.get('creator', '')} | "
                f"topic: {row.get('topic', '')} | title: {row.get('title', '')}"
            )
        return "\n".join(lines)

    @mcp.tool()
    def classify_reel(ref: str, niche: str, category: str, industry: str,
                      tags: str = "", topic: str = "") -> str:
        """Apply the agent's classification to a saved reel.

        ``tags`` is a comma-separated string. Values are freeform unless the
        user has configured ``~/.config/reels-vault/taxonomy.json``.
        """
        updates = {
            "niche": niche,
            "category": category,
            "industry": industry,
            "classification": "classified",
        }
        if tags.strip():
            updates["tags"] = [part.strip() for part in tags.split(",") if part.strip()]
        if topic.strip():
            updates["topic"] = topic.strip()
        try:
            from scripts.classify import load_taxonomy, validate
            from scripts.config import taxonomy_path
            updates = validate(updates, load_taxonomy(taxonomy_path()))
            results = _manager().update_metadata(ref, updates)
            _manager().reindex()
        except FileNotFoundError:
            return f"Not found: {ref}"
        except StorageError as exc:
            return f"Classification failed: {exc}"
        return f"Classified {ref}\n" + _json(results)

    @mcp.tool()
    def reindex() -> str:
        """Rebuild generated Obsidian index and creator pages."""
        try:
            count = _manager().reindex()
        except StorageError as exc:
            return f"Reindex failed: {exc}"
        return f"Reindexed {count} reel(s)."

    return mcp


def main() -> None:
    if "--check" in sys.argv:
        _check()
    if "-h" in sys.argv or "--help" in sys.argv:
        print("Usage: reels-vault-mcp [--check]", file=sys.stderr)
        return
    try:
        server = build_server()
    except ImportError as exc:
        print(
            "The MCP extra is not installed. Run: pip install -e '.[mcp]'\n"
            f"({exc})",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"Reels Vault MCP Server — {_json(_manager().status())}", file=sys.stderr)
    server.run()


if __name__ == "__main__":
    main()
