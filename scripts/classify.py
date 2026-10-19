#!/usr/bin/env python3
"""Apply AI-agent classification to one or more extracted reels.

Extraction never guesses a niche/category/industry.  The skill or MCP client
reads the note, decides the metadata, and calls this command:

    python3 scripts/classify.py --note "Reels/hooks/foo.md" \
        --metadata-json '{"niche":"marketing","category":"tutorial","industry":"creator-economy","tags":["hooks"]}'

Using ``--list-unclassified`` lets an agent fetch the pending queue.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

if __package__:
    from .config import load_config, taxonomy_path
    from .notes import CLASSIFICATION_DONE, UNCLASSIFIED
    from .storage import StorageManager, StorageError
else:
    from config import load_config, taxonomy_path
    from notes import CLASSIFICATION_DONE, UNCLASSIFIED
    from storage import StorageManager, StorageError

FIELDS = ("niche", "category", "industry")
TAXONOMY_FIELDS = {
    "niche": "niches",
    "category": "categories",
    "industry": "industries",
}


def load_taxonomy(path: str) -> dict[str, list[str]]:
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageError(f"Could not read taxonomy {path}: {exc}") from exc
    return {
        field: [str(item) for item in data.get(key, []) if str(item).strip()]
        for field, key in TAXONOMY_FIELDS.items()
        if isinstance(data.get(key), list)
    }


def validate(updates: dict[str, Any], taxonomy: dict[str, list[str]]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for field in FIELDS:
        value = updates.get(field)
        if value is None:
            continue
        value = str(value).strip()
        if not value:
            value = UNCLASSIFIED
        allowed = taxonomy.get(field) or []
        if allowed and value not in allowed:
            raise StorageError(
                f"{field}='{value}' is not in {taxonomy_path()}. "
                f"Allowed: {', '.join(allowed)}"
            )
        clean[field] = value
    if "tags" in updates:
        raw = updates["tags"]
        if isinstance(raw, str):
            raw = [part.strip() for part in raw.split(",")]
        clean["tags"] = [str(item).strip() for item in raw if str(item).strip()]
    if updates.get("topic"):
        clean["topic"] = str(updates["topic"]).strip()
    clean["classification"] = str(updates.get("classification") or CLASSIFICATION_DONE)
    return clean


def _read_metadata(args) -> dict[str, Any]:
    if args.metadata_json:
        return json.loads(args.metadata_json)
    if args.metadata_file:
        return json.loads(Path(args.metadata_file).read_text(encoding="utf-8"))
    if not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
        if raw:
            return json.loads(raw)
    raise StorageError("Provide --metadata-json, --metadata-file, or JSON on stdin.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify an extracted reel using the agent's own AI.")
    parser.add_argument("--note", default="", help="Note ref from search/list-unclassified")
    parser.add_argument("--source", default="", help="Find the note by its Instagram source URL")
    parser.add_argument("--metadata-json", default="", help="Classification JSON")
    parser.add_argument("--metadata-file", default="", help="Path to a classification JSON file")
    parser.add_argument("--list-unclassified", action="store_true", help="List pending notes as JSON")
    parser.add_argument("--reindex", action="store_true", help="Rebuild Obsidian indexes")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--storage", choices=["obsidian", "notion", "both"], default=None)
    parser.add_argument("--taxonomy", default="", help="Override taxonomy JSON path")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    cfg = load_config()
    manager = StorageManager(cfg, args.storage)
    try:
        if args.reindex:
            count = manager.reindex()
            print(json.dumps({"reindexed": count}) if args.json else f"Reindexed {count} notes.")
            return

        if args.list_unclassified:
            pending = manager.list_unclassified(args.limit)
            if args.json:
                print(json.dumps(pending, indent=2, ensure_ascii=False, default=str))
            else:
                for item in pending:
                    print(f"- {item.get('ref')} | {item.get('creator', '')} | {item.get('title', '')}")
            return

        updates = _read_metadata(args)
        taxonomy = load_taxonomy(args.taxonomy or taxonomy_path(cfg))
        updates = validate(updates, taxonomy)

        ref = args.note
        if not ref and args.source:
            found = manager.find_source(args.source)
            if not found:
                raise StorageError(f"No note found for source: {args.source}")
            ref = found["ref"]
        if not ref:
            raise StorageError("Provide --note or --source.")

        results = manager.update_metadata(ref, updates)
        manager.reindex()
        payload = {"updated": results, "metadata": updates}
        print(json.dumps(payload, indent=2, default=str) if args.json else
              f"Classified {ref}: niche={updates.get('niche')}, category={updates.get('category')}, "
              f"industry={updates.get('industry')}")
    except FileNotFoundError:
        print(f"Error: note not found: {args.note or args.source}", file=sys.stderr)
        sys.exit(1)
    except StorageError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
