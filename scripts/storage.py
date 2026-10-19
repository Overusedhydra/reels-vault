#!/usr/bin/env python3
"""Storage backends for Reels Vault.

Obsidian is a folder of Markdown notes.  Notion is a database of pages.
``both`` writes to each configured backend and reports partial failures instead
of losing the local copy.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

if __package__:
    from . import config as config_mod
    from .notes import (
        CLASSIFICATION_DONE,
        CLASSIFICATION_PENDING,
        UNCLASSIFIED,
        note_base_name,
        read_note,
        slugify,
        update_note_metadata,
    )
else:  # running as a script
    import config as config_mod
    from notes import (
        CLASSIFICATION_DONE,
        CLASSIFICATION_PENDING,
        UNCLASSIFIED,
        note_base_name,
        read_note,
        slugify,
        update_note_metadata,
    )


class StorageError(RuntimeError):
    """Raised when no configured backend could complete an operation."""


# ---------------------------------------------------------------------------
# Obsidian
# ---------------------------------------------------------------------------

INDEX_TEMPLATE = """---
tags: [vault-index]
---

# Reel Vault

Every saved reel is a Markdown note under `Reels/<topic>/`.  Classification is
filled in by the AI agent after extraction.

## All Reels

```dataview
TABLE creator AS "Creator", topic AS "Topic", niche AS "Niche", extracted AS "Date"
FROM "Reels"
WHERE source
SORT extracted DESC
```
"""


def _resolve_child(parent: Path, name: str) -> Path:
    """Find an existing child case-insensitively, else return the canonical path."""
    direct = parent / name
    if direct.exists():
        return direct
    if parent.is_dir():
        lowered = name.lower()
        for child in parent.iterdir():
            if child.name.lower() == lowered:
                return child
    return direct


class ObsidianStore:
    backend = "obsidian"

    def __init__(self, root: str):
        self.root = Path(root).expanduser() if root else None

    @property
    def configured(self) -> bool:
        return bool(self.root)

    def ensure(self) -> None:
        if not self.root:
            raise StorageError("Obsidian is not connected. Run scripts/connect.py.")
        self.root.mkdir(parents=True, exist_ok=True)
        self.reels_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.creators_dir.mkdir(parents=True, exist_ok=True)
        index = self.root / "Index.md"
        if not index.exists():
            index.write_text(INDEX_TEMPLATE, encoding="utf-8")

    @property
    def reels_dir(self) -> Path:
        return _resolve_child(self.root, "Reels")

    @property
    def index_dir(self) -> Path:
        return _resolve_child(self.root, "index")

    @property
    def creators_dir(self) -> Path:
        return _resolve_child(self.root, "Creators")

    def topic_dir(self, topic: str) -> Path:
        return self.reels_dir / slugify(topic or "general")

    def iter_reels(self) -> Iterable[Path]:
        if not self.root or not self.reels_dir.is_dir():
            return
        for path in sorted(self.reels_dir.rglob("*.md")):
            yield path

    def _note_record(self, path: Path) -> dict[str, Any] | None:
        try:
            frontmatter, body, _ = read_note(path)
        except (OSError, UnicodeDecodeError):
            return None
        rel = str(path.relative_to(self.root))
        return {
            "ref": rel,
            "backend": self.backend,
            "title": path.stem,
            "creator": frontmatter.get("creator", ""),
            "handle": frontmatter.get("handle", ""),
            "topic": frontmatter.get("topic", ""),
            "niche": frontmatter.get("niche", UNCLASSIFIED),
            "category": frontmatter.get("category", UNCLASSIFIED),
            "industry": frontmatter.get("industry", UNCLASSIFIED),
            "classification": frontmatter.get("classification", CLASSIFICATION_PENDING),
            "source": frontmatter.get("source", ""),
            "extracted": frontmatter.get("extracted", ""),
            "path": str(path),
            "text": body,
        }

    def resolve_base(self, metadata: dict[str, Any], topic: str, source: str) -> str:
        """Reuse an existing note for the same source, else a stable new name."""
        if not self.root:
            return note_base_name(metadata, source)
        target = self.topic_dir(topic)
        candidate = target / f"{note_base_name(metadata, source)}.md"
        if candidate.exists():
            frontmatter, _, _ = read_note(candidate)
            if frontmatter.get("source") == source or not source:
                return candidate.stem
        if target.is_dir():
            for note in target.glob("*.md"):
                frontmatter, _, _ = read_note(note)
                if source and frontmatter.get("source") == source:
                    return note.stem
        return note_base_name(metadata, source)

    def save(self, note: str, frontmatter: dict[str, Any], metadata: dict[str, Any],
             transcript: dict[str, Any], music: dict[str, Any], topic: str,
             base_name: str, frames: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        self.ensure()
        target_dir = self.topic_dir(topic)
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{base_name}.md"
        path.write_text(note, encoding="utf-8")

        if frames:
            frames_dir = target_dir / "frames" / base_name
            frames_dir.mkdir(parents=True, exist_ok=True)
            for frame in frames:
                src = Path(frame["path"])
                if src.is_file():
                    (frames_dir / src.name).write_bytes(src.read_bytes())

        self.update_indexes(frontmatter, topic, base_name)
        return {
            "backend": self.backend,
            "path": str(path),
            "ref": str(path.relative_to(self.root)),
            "url": "",
        }

    def _append_unique(self, path: Path, header: str, line: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if line in path.read_text(encoding="utf-8").splitlines():
                return
        else:
            path.write_text(header, encoding="utf-8")
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def update_indexes(self, frontmatter: dict[str, Any], topic: str, base_name: str) -> None:
        creator = frontmatter.get("creator", "Unknown")
        niche = frontmatter.get("niche") or UNCLASSIFIED
        category = frontmatter.get("category") or UNCLASSIFIED
        industry = frontmatter.get("industry") or UNCLASSIFIED
        date = frontmatter.get("extracted") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        entry = f"- [[{base_name}]] — {creator} ({topic or 'general'}) — {date}"
        for key, kind in ((niche, "niche"), (category, "category"), (industry, "industry")):
            self._append_unique(
                self.index_dir / f"{slugify(key)}.md",
                f"---\ntags: [index, {kind}]\n---\n\n# {str(key).replace('-', ' ').title()}\n\n",
                entry,
            )
        if topic:
            self._append_unique(
                self.index_dir / f"{slugify(topic)}.md",
                f"---\ntags: [index, topic]\n---\n\n# {topic}\n\n",
                entry,
            )
        handle = slugify(frontmatter.get("handle") or creator)
        self._append_unique(
            self.creators_dir / f"{handle}.md",
            f"---\ntags: [creator]\n---\n\n# {creator}\n\n",
            f"- [[{base_name}]] ({topic or 'general'}) — {date}",
        )

    def rebuild_indexes(self) -> int:
        """Rebuild generated index/creator pages from reel notes."""
        if not self.root:
            raise StorageError("Obsidian is not connected.")
        self.ensure()
        if self.index_dir.is_dir():
            for path in self.index_dir.glob("*.md"):
                path.unlink()
        if self.creators_dir.is_dir():
            for path in self.creators_dir.glob("*.md"):
                path.unlink()
        count = 0
        for path in self.iter_reels():
            record = self._note_record(path)
            if not record:
                continue
            fm, _, _ = read_note(path)
            self.update_indexes(fm, str(fm.get("topic") or ""), path.stem)
            count += 1
        return count

    def search(self, query: str = "", creator: str = "", topic: str = "",
               limit: int = 20) -> list[dict[str, Any]]:
        q = (query or "").lower()
        c = (creator or "").lower()
        t = (topic or "").lower()
        hits: list[dict[str, Any]] = []
        for path in self.iter_reels():
            record = self._note_record(path)
            if not record:
                continue
            text = record.pop("text", "")
            if c and c not in str(record.get("creator", "")).lower() and c not in str(record.get("handle", "")).lower():
                continue
            if t and t not in str(record.get("topic", "")).lower():
                continue
            haystack = " ".join(str(record.get(key, "")) for key in
                                ("title", "creator", "handle", "topic", "niche",
                                 "category", "industry", "source")) + "\n" + text
            if q and q not in haystack.lower():
                continue
            if q:
                idx = haystack.lower().find(q)
                start = max(0, idx - 100)
                snippet = haystack[start:start + 320].replace("\n", " ").strip()
            else:
                snippet = text.strip().replace("\n", " ")[:260]
            record["snippet"] = snippet
            hits.append(record)
            if len(hits) >= max(1, limit):
                break
        return hits

    def read(self, ref: str) -> str:
        if not self.root:
            raise StorageError("Obsidian is not connected.")
        target = (self.root / ref).resolve()
        try:
            target.relative_to(self.root.resolve())
        except ValueError as exc:
            raise StorageError("Path must stay inside the vault.") from exc
        if not target.is_file():
            raise FileNotFoundError(ref)
        return target.read_text(encoding="utf-8")

    def list_topics(self) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for path in self.iter_reels():
            record = self._note_record(path)
            if record:
                topic = str(record.get("topic") or "general")
                counts[topic] = counts.get(topic, 0) + 1
        return [{"topic": key, "count": value} for key, value in sorted(counts.items())]

    def list_creators(self) -> list[dict[str, Any]]:
        counts: dict[str, dict[str, Any]] = {}
        for path in self.iter_reels():
            record = self._note_record(path)
            if not record:
                continue
            name = str(record.get("creator") or "Unknown")
            row = counts.setdefault(name, {"creator": name, "handle": record.get("handle", ""), "count": 0})
            row["count"] += 1
        return sorted(counts.values(), key=lambda item: item["creator"].lower())

    def status(self) -> dict[str, Any]:
        if not self.root:
            return {"backend": self.backend, "configured": False, "path": ""}
        return {
            "backend": self.backend,
            "configured": True,
            "path": str(self.root),
            "reels": sum(1 for _ in self.iter_reels()) if self.reels_dir.is_dir() else 0,
            "topics": len(self.list_topics()),
            "creators": len(self.list_creators()),
        }

    def list_unclassified(self, limit: int = 100) -> list[dict[str, Any]]:
        out = []
        for path in self.iter_reels():
            record = self._note_record(path)
            if not record:
                continue
            if record.get("classification") not in (CLASSIFICATION_DONE, "done", "classified"):
                record.pop("text", None)
                out.append(record)
                if len(out) >= max(1, limit):
                    break
        return out

    def find_source(self, source: str) -> dict[str, Any] | None:
        for path in self.iter_reels():
            frontmatter, _, _ = read_note(path)
            if frontmatter.get("source") == source:
                return {"backend": self.backend, "ref": str(path.relative_to(self.root)),
                        "path": str(path)}
        return None

    def source_for(self, ref: str) -> str:
        path = (self.root / ref).resolve()
        try:
            path.relative_to(self.root.resolve())
        except ValueError:
            return ""
        if not path.is_file():
            return ""
        frontmatter, _, _ = read_note(path)
        return str(frontmatter.get("source", ""))

    def update_metadata(self, ref: str, updates: dict[str, Any]) -> dict[str, Any]:
        path = (self.root / ref).resolve()
        try:
            path.relative_to(self.root.resolve())
        except ValueError as exc:
            raise StorageError("Path must stay inside the vault.") from exc
        return update_note_metadata(path, updates)


# ---------------------------------------------------------------------------
# Notion
# ---------------------------------------------------------------------------

NOTION_API = "https://api.notion.com/v1"
NOTION_PROPERTIES = {
    "Name": {"title": {}},
    "Creator": {"rich_text": {}},
    "Handle": {"rich_text": {}},
    "Topic": {"rich_text": {}},
    "Niche": {"rich_text": {}},
    "Category": {"rich_text": {}},
    "Industry": {"rich_text": {}},
    "Tags": {"multi_select": {"options": []}},
    "Source": {"url": {}},
    "Extracted": {"date": {}},
    "Classification": {"select": {"options": [{"name": CLASSIFICATION_PENDING},
                                                  {"name": CLASSIFICATION_DONE}]}},
    "Music": {"rich_text": {}},
    "Language": {"rich_text": {}},
    "Views": {"number": {"format": "number"}},
    "Likes": {"number": {"format": "number"}},
    "Comments": {"number": {"format": "number"}},
}


def _notion_page_id(value: str) -> str:
    """Normalize a Notion page/database URL or ID."""
    if not value:
        return ""
    text = value.strip()
    match = re.search(r"([0-9a-fA-F]{32})", text.replace("-", ""))
    if not match:
        return text
    raw = match.group(1).lower()
    return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"


class NotionStore:
    backend = "notion"

    def __init__(self, settings: dict[str, Any]):
        self.token = settings.get("token", "")
        self.database_id = _notion_page_id(settings.get("database_id", ""))
        self.parent_page_id = _notion_page_id(settings.get("parent_page_id", ""))
        self.version = settings.get("version", "2022-06-28")
        self._schema: dict[str, Any] = {}

    @property
    def configured(self) -> bool:
        return bool(self.token and (self.database_id or self.parent_page_id))

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.token:
            raise StorageError("Notion token is missing. Set NOTION_TOKEN or rerun connect.py.")
        body = json.dumps(payload or {}).encode("utf-8") if method != "GET" else None
        req = urllib.request.Request(
            f"{NOTION_API}{path}",
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": self.version,
                "Content-Type": "application/json",
            },
        )
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                if exc.code == 429 and attempt < 2:
                    time.sleep(float(exc.headers.get("Retry-After", "1")))
                    continue
                raise StorageError(f"Notion API {exc.code}: {detail[:500]}") from exc
            except urllib.error.URLError as exc:
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise StorageError(f"Notion network error: {exc}") from exc
        raise StorageError("Notion request failed")

    def ensure(self) -> None:
        if not self.token:
            raise StorageError("Notion token is missing. Set NOTION_TOKEN or rerun connect.py.")
        if not self.database_id:
            if not self.parent_page_id:
                raise StorageError(
                    "Notion database is not configured. Run scripts/connect.py --storage notion."
                )
            created = self._request("POST", "/databases", {
                "parent": {"type": "page_id", "page_id": self.parent_page_id},
                "title": [{"type": "text", "text": {"content": "Reels Vault"}}],
                "properties": NOTION_PROPERTIES,
            })
            self.database_id = created.get("id", "")
            if not self.database_id:
                raise StorageError("Notion did not return a database id.")
        if not self._schema:
            database = self._request("GET", f"/databases/{self.database_id}")
            self._schema = database.get("properties") or {}
            missing = {}
            has_title = any(prop.get("type") == "title" for prop in self._schema.values())
            for name, definition in NOTION_PROPERTIES.items():
                if name in self._schema:
                    continue
                if definition.get("title") and has_title:
                    continue
                missing[name] = definition
            if missing:
                updated = self._request("PATCH", f"/databases/{self.database_id}",
                                        {"properties": missing})
                self._schema = updated.get("properties") or {**self._schema, **missing}

    def _find_property(self, name: str, expected: str | None = None) -> str | None:
        if not self._schema:
            return name
        prop = self._schema.get(name)
        if prop and (expected is None or prop.get("type") == expected):
            return name
        if expected == "title":
            for key, value in self._schema.items():
                if value.get("type") == "title":
                    return key
        if expected:
            for key, value in self._schema.items():
                if value.get("type") == expected and key.lower() == name.lower():
                    return key
        return None

    def _rich_text(self, value: Any) -> dict[str, Any]:
        return {"rich_text": [{"type": "text", "text": {"content": str(value)[:1900]}}] if value else []}

    def _properties(self, frontmatter: dict[str, Any], metadata: dict[str, Any],
                    topic: str) -> dict[str, Any]:
        props: dict[str, Any] = {}
        title_name = self._find_property("Name", "title")
        if title_name:
            props[title_name] = {"title": [{"type": "text", "text": {
                "content": str(frontmatter.get("name") or frontmatter.get("title") or
                               metadata.get("title") or "Reel")[:1900]}}]}
        mapping = {
            "Creator": ("creator", "rich_text"),
            "Handle": ("handle", "rich_text"),
            "Topic": ("topic", "rich_text"),
            "Niche": ("niche", "rich_text"),
            "Category": ("category", "rich_text"),
            "Industry": ("industry", "rich_text"),
            "Music": ("music", "rich_text"),
            "Language": ("language", "rich_text"),
        }
        for prop_name, (key, kind) in mapping.items():
            target = self._find_property(prop_name, kind)
            if target:
                value = topic if key == "topic" and topic else frontmatter.get(key, metadata.get(key, ""))
                props[target] = self._rich_text(value)
        target = self._find_property("Tags", "multi_select")
        if target:
            tags = frontmatter.get("tags") or []
            props[target] = {"multi_select": [{"name": str(tag)[:100]} for tag in tags if str(tag).strip()]}
        target = self._find_property("Source", "url")
        if target:
            source = str(frontmatter.get("source", ""))
            props[target] = {"url": source if source.startswith(("http://", "https://")) else None}
        target = self._find_property("Extracted", "date")
        if target:
            date = str(frontmatter.get("extracted", ""))
            props[target] = {"date": {"start": date} if date else None}
        target = self._find_property("Classification", "select")
        if target:
            props[target] = {"select": {"name": str(frontmatter.get("classification") or CLASSIFICATION_PENDING)}}
        for prop_name, key in (("Views", "view_count"), ("Likes", "like_count"), ("Comments", "comment_count")):
            target = self._find_property(prop_name, "number")
            if target:
                try:
                    props[target] = {"number": int(metadata[key]) if metadata.get(key) is not None else None}
                except (TypeError, ValueError):
                    props[target] = {"number": None}
        return props

    def _text_blocks(self, heading: str, text: str) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = [{
            "object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": heading}}]},
        }]
        text = (text or "").strip()
        if not text:
            return blocks
        for start in range(0, min(len(text), 120_000), 1800):
            chunk = text[start:start + 1800]
            blocks.append({
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": chunk}}]},
            })
        return blocks

    def _blocks(self, metadata: dict[str, Any], transcript: dict[str, Any],
                music: dict[str, Any], topic: str) -> list[dict[str, Any]]:
        meta_lines = [
            f"Creator: {metadata.get('author', 'Unknown')}",
            f"Handle: {metadata.get('author_handle', '')}",
            f"Topic: {topic or 'general'}",
            f"Source: {metadata.get('url', '')}",
        ]
        blocks: list[dict[str, Any]] = [
            {"object": "block", "type": "heading_2", "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "Metadata"}}]}},
        ]
        for line in meta_lines:
            if line.split(": ", 1)[-1]:
                blocks.append({"object": "block", "type": "bulleted_list_item",
                               "bulleted_list_item": {"rich_text": [
                                   {"type": "text", "text": {"content": line}}]}})
        if metadata.get("caption"):
            blocks += self._text_blocks("Caption", metadata["caption"])
        if music:
            blocks += self._text_blocks("Music", " — ".join(
                str(music.get(key, "")) for key in ("artist", "title") if music.get(key)))
        blocks += self._text_blocks(
            "Transcript",
            transcript.get("text", "") or "(no speech detected)",
        )
        if transcript.get("segments"):
            lines = []
            for seg in transcript["segments"]:
                mins, secs = divmod(int(seg.get("start", 0)), 60)
                lines.append(f"[{mins:02d}:{secs:02d}] {seg.get('text', '')}")
            blocks += self._text_blocks("Timestamped Transcript", "\n".join(lines))
        return blocks[:900]

    def _append_children(self, page_id: str, blocks: list[dict[str, Any]]) -> None:
        for start in range(0, len(blocks), 90):
            self._request("PATCH", f"/blocks/{page_id}/children",
                          {"children": blocks[start:start + 90]})

    def _delete_children(self, page_id: str) -> None:
        block_ids: list[str] = []
        cursor = None
        while True:
            query = "?page_size=100" + (f"&start_cursor={cursor}" if cursor else "")
            data = self._request("GET", f"/blocks/{page_id}/children{query}")
            block_ids.extend(block["id"] for block in data.get("results", []) if block.get("id"))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
        for block_id in block_ids:
            try:
                self._request("DELETE", f"/blocks/{block_id}")
            except StorageError:
                pass

    def _find_page(self, source: str) -> dict[str, Any] | None:
        if not source:
            return None
        self.ensure()
        target = self._find_property("Source", "url")
        if not target:
            return None
        data = self._request("POST", f"/databases/{self.database_id}/query", {
            "filter": {"property": target, "url": {"equals": source}},
            "page_size": 1,
        })
        results = data.get("results") or []
        return results[0] if results else None

    def save(self, note: str, frontmatter: dict[str, Any], metadata: dict[str, Any],
             transcript: dict[str, Any], music: dict[str, Any], topic: str,
             base_name: str, frames: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        self.ensure()
        source = str(frontmatter.get("source", ""))
        props = self._properties(frontmatter, metadata, topic)
        existing = self._find_page(source)
        blocks = self._blocks(metadata, transcript, music, topic)
        if existing:
            page_id = existing["id"]
            self._request("PATCH", f"/pages/{page_id}", {"properties": props})
            self._delete_children(page_id)
            self._append_children(page_id, blocks)
            return {"backend": self.backend, "ref": f"notion:{page_id}",
                    "url": existing.get("url", ""), "id": page_id}
        page = self._request("POST", "/pages", {
            "parent": {"type": "database_id", "database_id": self.database_id},
            "properties": props,
            "children": blocks[:90],
        })
        page_id = page.get("id", "")
        if len(blocks) > 90:
            self._append_children(page_id, blocks[90:])
        return {"backend": self.backend, "ref": f"notion:{page_id}",
                "url": page.get("url", ""), "id": page_id}

    def _query_all(self, filter: dict[str, Any] | None = None, page_size: int = 100,
                   max_pages: int = 20) -> list[dict[str, Any]]:
        self.ensure()
        results: list[dict[str, Any]] = []
        cursor = None
        for _ in range(max_pages):
            payload: dict[str, Any] = {"page_size": page_size, "sorts": [
                {"timestamp": "created_time", "direction": "descending"}]}
            if filter:
                payload["filter"] = filter
            if cursor:
                payload["start_cursor"] = cursor
            data = self._request("POST", f"/databases/{self.database_id}/query", payload)
            results.extend(data.get("results", []))
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
        return results

    def _page_value(self, page: dict[str, Any], name: str, kind: str) -> Any:
        props = page.get("properties", {})
        target = self._find_property(name, kind) or name
        prop = props.get(target) or {}
        if kind == "title":
            return "".join(part.get("plain_text", "") for part in prop.get("title", []))
        if kind == "rich_text":
            return "".join(part.get("plain_text", "") for part in prop.get("rich_text", []))
        if kind == "select":
            return (prop.get("select") or {}).get("name", "")
        if kind == "multi_select":
            return [item.get("name", "") for item in prop.get("multi_select", [])]
        if kind == "url":
            return prop.get("url") or ""
        if kind == "date":
            return (prop.get("date") or {}).get("start", "")
        if kind == "number":
            return prop.get("number")
        return ""

    def _record(self, page: dict[str, Any]) -> dict[str, Any]:
        return {
            "ref": f"notion:{page.get('id', '')}",
            "backend": self.backend,
            "title": self._page_value(page, "Name", "title") or "Reel",
            "creator": self._page_value(page, "Creator", "rich_text"),
            "handle": self._page_value(page, "Handle", "rich_text"),
            "topic": self._page_value(page, "Topic", "rich_text"),
            "niche": self._page_value(page, "Niche", "rich_text") or UNCLASSIFIED,
            "category": self._page_value(page, "Category", "rich_text") or UNCLASSIFIED,
            "industry": self._page_value(page, "Industry", "rich_text") or UNCLASSIFIED,
            "classification": self._page_value(page, "Classification", "select") or CLASSIFICATION_PENDING,
            "source": self._page_value(page, "Source", "url"),
            "extracted": self._page_value(page, "Extracted", "date"),
            "url": page.get("url", ""),
        }

    def search(self, query: str = "", creator: str = "", topic: str = "",
               limit: int = 20) -> list[dict[str, Any]]:
        self.ensure()
        conditions = []
        if query:
            ors = []
            for name, kind in (("Name", "title"), ("Creator", "rich_text"), ("Topic", "rich_text")):
                prop = self._find_property(name, kind)
                if prop:
                    ors.append({"property": prop, kind: {"contains": query}})
            if ors:
                conditions.append({"or": ors})
        if creator:
            prop = self._find_property("Creator", "rich_text")
            if prop:
                conditions.append({"property": prop, "rich_text": {"contains": creator}})
        if topic:
            prop = self._find_property("Topic", "rich_text")
            if prop:
                conditions.append({"property": prop, "rich_text": {"contains": topic}})
        filter = None
        if len(conditions) == 1:
            filter = conditions[0]
        elif conditions:
            filter = {"and": conditions}
        records = [self._record(page) for page in self._query_all(filter=filter)]
        for record in records:
            record["snippet"] = " ".join(
                str(record.get(key, "")) for key in ("creator", "handle", "topic", "niche", "source")
            ).strip()
        return records[:max(1, limit)]

    def read(self, ref: str) -> str:
        self.ensure()
        page_id = ref[len("notion:"):] if ref.startswith("notion:") else ref
        page = self._request("GET", f"/pages/{page_id}")
        lines = []
        cursor = None
        while True:
            query = "?page_size=100" + (f"&start_cursor={cursor}" if cursor else "")
            data = self._request("GET", f"/blocks/{page_id}/children{query}")
            for block in data.get("results", []):
                kind = block.get("type", "")
                payload = block.get(kind, {}) or {}
                rich = payload.get("rich_text", [])
                text = "".join(part.get("plain_text", "") for part in rich)
                if not text:
                    continue
                if kind.startswith("heading"):
                    lines.append(f"\n## {text}\n")
                elif kind in ("bulleted_list_item", "numbered_list_item"):
                    lines.append(f"- {text}")
                else:
                    lines.append(text)
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
        title = self._page_value(page, "Name", "title")
        body = "\n".join(lines).strip()
        return f"# {title}\n\n{body}\n" if title else body + "\n"

    def list_topics(self) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for record in (self._record(page) for page in self._query_all()):
            topic = str(record.get("topic") or "general")
            counts[topic] = counts.get(topic, 0) + 1
        return [{"topic": key, "count": value} for key, value in sorted(counts.items())]

    def list_creators(self) -> list[dict[str, Any]]:
        counts: dict[str, dict[str, Any]] = {}
        for record in (self._record(page) for page in self._query_all()):
            name = str(record.get("creator") or "Unknown")
            row = counts.setdefault(name, {"creator": name, "handle": record.get("handle", ""), "count": 0})
            row["count"] += 1
        return sorted(counts.values(), key=lambda item: item["creator"].lower())

    def status(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "configured": self.configured,
            "database_id": self.database_id,
            "url": f"https://www.notion.so/{self.database_id.replace('-', '')}" if self.database_id else "",
        }

    def list_unclassified(self, limit: int = 100) -> list[dict[str, Any]]:
        self.ensure()
        prop = self._find_property("Classification", "select")
        filter = None
        if prop:
            filter = {"or": [
                {"property": prop, "select": {"equals": CLASSIFICATION_PENDING}},
                {"property": prop, "select": {"is_empty": True}},
            ]}
        records = [self._record(page) for page in self._query_all(filter=filter)]
        records = [record for record in records
                   if record.get("classification") not in (CLASSIFICATION_DONE, "done", "classified")]
        return records[:max(1, limit)]

    def source_for(self, ref: str) -> str:
        self.ensure()
        page_id = ref[len("notion:"):] if ref.startswith("notion:") else ref
        page = self._request("GET", f"/pages/{page_id}")
        return str(self._page_value(page, "Source", "url"))

    def find_source(self, source: str) -> dict[str, Any] | None:
        page = self._find_page(source)
        if not page:
            return None
        return {"backend": self.backend, "ref": f"notion:{page['id']}", "url": page.get("url", "")}

    def update_metadata(self, ref: str, updates: dict[str, Any], base_name: str = "") -> dict[str, Any]:
        self.ensure()
        page_id = ref[len("notion:"):] if ref.startswith("notion:") else ref
        props: dict[str, Any] = {}
        for name, kind in (("Niche", "rich_text"), ("Category", "rich_text"),
                           ("Industry", "rich_text"), ("Topic", "rich_text"),
                           ("Creator", "rich_text"), ("Handle", "rich_text")):
            key = name.lower()
            if key in updates:
                target = self._find_property(name, kind)
                if target:
                    props[target] = self._rich_text(updates[key])
        if "tags" in updates:
            target = self._find_property("Tags", "multi_select")
            if target:
                props[target] = {"multi_select": [{"name": str(tag)[:100]} for tag in updates["tags"]]}
        target = self._find_property("Classification", "select")
        if target:
            props[target] = {"select": {"name": str(updates.get("classification", CLASSIFICATION_DONE))}}
        if props:
            self._request("PATCH", f"/pages/{page_id}", {"properties": props})
        return {"backend": self.backend, "ref": f"notion:{page_id}"}


# ---------------------------------------------------------------------------
# Multi-backend manager
# ---------------------------------------------------------------------------

class StorageManager:
    def __init__(self, cfg: dict[str, Any] | None = None, backend: str | None = None):
        self.config = cfg if cfg is not None else config_mod.load_config()
        self.backend = (backend or config_mod.storage_backend(self.config)).lower()
        self.obsidian: ObsidianStore | None = None
        self.notion: NotionStore | None = None
        if self.backend in ("obsidian", "both"):
            root = config_mod.vault_path(self.config)
            self.obsidian = ObsidianStore(root) if root else None
        if self.backend in ("notion", "both"):
            settings = config_mod.notion_config(self.config)
            self.notion = NotionStore(settings)

    @property
    def supports_frames(self) -> bool:
        return self.obsidian is not None

    def configured_backends(self) -> list[str]:
        out = []
        if self.obsidian and self.obsidian.configured:
            out.append("obsidian")
        if self.notion and self.notion.configured:
            out.append("notion")
        return out

    def resolve_base(self, metadata: dict[str, Any], topic: str, source: str) -> str:
        if self.obsidian and self.obsidian.configured:
            return self.obsidian.resolve_base(metadata, topic, source)
        return note_base_name(metadata, source)

    def save(self, note: str, frontmatter: dict[str, Any], metadata: dict[str, Any],
             transcript: dict[str, Any], music: dict[str, Any], topic: str,
             base_name: str, frames: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        saved, errors = [], []
        if self.obsidian:
            try:
                saved.append(self.obsidian.save(note, frontmatter, metadata, transcript,
                                                music, topic, base_name, frames))
            except Exception as exc:
                errors.append(f"obsidian: {exc}")
        if self.notion:
            try:
                saved.append(self.notion.save(note, frontmatter, metadata, transcript,
                                              music, topic, base_name, frames))
            except Exception as exc:
                errors.append(f"notion: {exc}")
        if not saved:
            detail = "; ".join(errors) or "No storage backend configured."
            raise StorageError(detail)
        return {"saved": saved, "errors": errors}

    def search(self, query: str = "", creator: str = "", topic: str = "",
               limit: int = 20) -> list[dict[str, Any]]:
        combined: list[dict[str, Any]] = []
        errors: list[str] = []
        stores = [store for store in (self.obsidian, self.notion) if store and store.configured]
        for store in stores:
            try:
                combined.extend(store.search(query, creator, topic, limit))
            except Exception as exc:
                errors.append(f"{store.backend}: {exc}")
        if not combined and errors:
            raise StorageError("; ".join(errors))
        # De-duplicate the same source saved to both backends.
        seen: dict[str, dict[str, Any]] = {}
        for record in combined:
            key = record.get("source") or record.get("ref")
            if key in seen:
                seen[key].setdefault("backends", [seen[key]["backend"]])
                if record["backend"] not in seen[key]["backends"]:
                    seen[key]["backends"].append(record["backend"])
                continue
            record["backends"] = [record["backend"]]
            seen[key] = record
        results = list(seen.values())
        return results[:max(1, limit)]

    def read(self, ref: str) -> str:
        if ref.startswith("notion:"):
            if not self.notion:
                raise StorageError("Notion is not configured.")
            return self.notion.read(ref)
        if not self.obsidian:
            raise StorageError("Obsidian is not configured.")
        return self.obsidian.read(ref)

    def list_topics(self) -> list[dict[str, Any]]:
        stores = [store for store in (self.obsidian, self.notion) if store and store.configured]
        if self.obsidian and self.obsidian.configured:
            return self.obsidian.list_topics()
        for store in stores:
            return store.list_topics()
        return []

    def list_creators(self) -> list[dict[str, Any]]:
        if self.obsidian and self.obsidian.configured:
            return self.obsidian.list_creators()
        if self.notion and self.notion.configured:
            return self.notion.list_creators()
        return []

    def status(self) -> dict[str, Any]:
        out = {"storage": self.backend, "backends": []}
        for store in (self.obsidian, self.notion):
            if store:
                try:
                    out["backends"].append(store.status())
                except Exception as exc:
                    out["backends"].append({"backend": store.backend, "error": str(exc)})
        return out

    def list_unclassified(self, limit: int = 100) -> list[dict[str, Any]]:
        out = []
        seen: set[str] = set()
        for store in (self.obsidian, self.notion):
            if store and store.configured:
                try:
                    for record in store.list_unclassified(limit):
                        key = str(record.get("source") or record.get("ref"))
                        if key in seen:
                            continue
                        seen.add(key)
                        out.append(record)
                except Exception:
                    pass
        return out[:max(1, limit)]

    def find_source(self, source: str) -> dict[str, Any] | None:
        for store in (self.obsidian, self.notion):
            if store and store.configured:
                try:
                    found = store.find_source(source)
                    if found:
                        return found
                except Exception:
                    pass
        return None

    def update_metadata(self, ref: str, updates: dict[str, Any]) -> list[dict[str, Any]]:
        results = []
        if ref.startswith("notion:"):
            if not self.notion:
                raise StorageError("Notion is not configured.")
            results.append(self.notion.update_metadata(ref, updates))
            if self.obsidian:
                source = str(updates.get("source", "")) or self.notion.source_for(ref)
                found = self.obsidian.find_source(source) if source else None
                if found:
                    results.append(self.obsidian.update_metadata(found["ref"], updates))
            return results
        if self.obsidian:
            results.append(self.obsidian.update_metadata(ref, updates))
        if self.notion and self.notion.configured:
            source = str(updates.get("source", ""))
            if not source and self.obsidian:
                source = self.obsidian.source_for(ref)
            if source:
                found = self.notion.find_source(source)
                if found:
                    results.append(self.notion.update_metadata(found["ref"], updates))
        return results

    def reindex(self) -> int:
        if self.obsidian:
            return self.obsidian.rebuild_indexes()
        return 0
