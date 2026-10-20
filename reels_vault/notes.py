#!/usr/bin/env python3
"""Markdown/frontmatter helpers shared by the CLI, storage backends, and MCP."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

UNCLASSIFIED = "unclassified"
CLASSIFICATION_PENDING = "pending"
CLASSIFICATION_DONE = "classified"

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", re.S)
_SHORTCODE_RE = re.compile(r"instagram\.com/(?:[\w.-]+/)?(?:reel|reels|p)/([A-Za-z0-9_-]+)")
_BODY_FIELDS = {
    "niche": "Niche",
    "category": "Category",
    "industry": "Industry",
    "classification": "Classification",
    "topic": "Topic",
}


def slugify(value: Any) -> str:
    """Turn arbitrary text into a safe, stable file/folder name."""
    slug = str(value or "").lower().strip()
    slug = re.sub(r"[.]+", "-", slug)
    slug = re.sub(r"[^\w\s-]", "", slug).strip()
    slug = re.sub(r"[\s_-]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "unknown"


def extract_shortcode(url: str) -> str:
    """Return the Instagram shortcode from a reel/post URL, or an empty string."""
    match = _SHORTCODE_RE.search(url or "")
    return match.group(1) if match else ""


def source_id(url: str) -> str:
    """A stable identifier for a source URL.

    Instagram shortcodes are case-sensitive, so they are preserved verbatim.
    An empty source returns an empty id instead of a shared hash of ``""``.
    """
    shortcode = extract_shortcode(url)
    if shortcode:
        return shortcode
    url = (url or "").strip()
    if not url:
        return ""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]


def normalize_source(url: str) -> str:
    """Canonical identity for an Instagram URL; other URLs are trimmed."""
    shortcode = extract_shortcode(url)
    if shortcode:
        return f"instagram:{shortcode}"
    return (url or "").strip().rstrip("/")


def same_source(left: str, right: str, left_id: str = "", right_id: str = "") -> bool:
    """Compare sources by shortcode when possible, else by normalized URL."""
    lid = left_id or source_id(left)
    rid = right_id or source_id(right)
    if lid and rid:
        return lid == rid
    return bool(left or right) and normalize_source(left) == normalize_source(right)


def note_base_name(metadata: dict[str, Any], url: str = "") -> str:
    """Build a deterministic note basename (creator + date + shortcode)."""
    handle = slugify(metadata.get("author_handle") or metadata.get("author") or "unknown")
    upload_date = str(metadata.get("upload_date") or "")
    if len(upload_date) == 8 and upload_date.isdigit():
        upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
    if not upload_date:
        upload_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sid = source_id(url or metadata.get("url", ""))
    if not sid:
        payload = json.dumps(metadata, sort_keys=True, default=str, ensure_ascii=False)
        sid = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]
    return f"{handle}-reel-{upload_date}-{sid}"


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split a markdown note into ``(frontmatter, body)``.

    A note without valid frontmatter returns ``({}, text)``.
    """
    match = _FRONTMATTER_RE.match(text or "")
    if not match:
        return {}, text or ""
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return data, (text or "")[match.end():]


def dump_frontmatter(data: dict[str, Any]) -> str:
    """Serialize frontmatter as valid YAML (quotes handles, colons, URLs)."""
    payload = yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).strip()
    return f"---\n{payload}\n---\n"


def render_note(frontmatter: dict[str, Any], body: str) -> str:
    return dump_frontmatter(frontmatter) + "\n" + body.lstrip("\n")


def read_note(path: str | os.PathLike[str]) -> tuple[dict[str, Any], str, str]:
    """Read ``(frontmatter, body, raw_text)`` from a note."""
    text = Path(path).read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(text)
    return frontmatter, body, text


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def section_map(body: str) -> dict[str, str]:
    """Split a Markdown body into ``heading -> section text`` (heading included)."""
    sections: dict[str, str] = {}
    matches = list(re.finditer(r"^## (.+)$", body or "", re.M))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[match.group(1).strip()] = body[match.start():end].rstrip() + "\n"
    return sections


def preserve_sections(old_body: str, new_body: str,
                      generated: Iterable[str] = ()) -> str:
    """Keep user-authored sections that a re-extraction did not regenerate.

    Generated section names are replaced by the new extraction. Every other
    section is kept, so manual notes and ``KEY:`` annotations survive re-saves.
    """
    generated = {name.lower() for name in generated}
    old = section_map(old_body)
    new = section_map(new_body)
    if not new:
        return new_body
    new_names = {name.lower() for name in new}
    # A generated Key Frame section is instructions; keep manual KEY lines.
    for name, text in new.items():
        if name.lower() != "key frame":
            continue
        old_text = next((value for key, value in old.items() if key.lower() == "key frame"), "")
        keys = [line for line in old_text.splitlines() if line.strip().upper().startswith("KEY:")]
        if keys:
            heading, _, rest = text.partition("\n")
            new[name] = heading + "\n" + "\n".join(keys) + "\n" + rest.lstrip("\n")
    additions = [
        text for name, text in old.items()
        if name.lower() not in generated and name.lower() not in new_names
    ]
    rebuilt = "\n".join(text.rstrip() for text in new.values()).rstrip() + "\n"
    if additions:
        rebuilt += "\n" + "\n\n".join(text.rstrip() for text in additions).rstrip() + "\n"
    return rebuilt


def update_body_metadata(body: str, updates: dict[str, Any]) -> str:
    """Update the ``- **Niche:** ...`` lines inside a note body."""
    for key, label in _BODY_FIELDS.items():
        if key not in updates:
            continue
        value = updates[key]
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(item) for item in value)
        line = f"- **{label}:** {value}"
        pattern = re.compile(rf"^- \*\*{re.escape(label)}:\*\*.*$", re.M)
        if pattern.search(body):
            body = pattern.sub(line, body, count=1)
        elif key == "classification":
            anchor = re.search(r"^- \*\*Industry:\*\*.*$", body, re.M)
            if anchor:
                body = body[:anchor.end()] + "\n" + line + body[anchor.end():]
    return body


def update_note_metadata(path: str | os.PathLike[str], updates: dict[str, Any]) -> dict[str, Any]:
    """Merge ``updates`` into a note's frontmatter and visible metadata lines."""
    note_path = Path(path)
    frontmatter, body, _ = read_note(note_path)
    frontmatter.update(updates)
    body = update_body_metadata(body, updates)
    _atomic_write(note_path, render_note(frontmatter, body))
    return frontmatter
