#!/usr/bin/env python3
"""Audit and repair an Obsidian Reel Vault.

The repair is conservative: it keeps one canonical note per Instagram
shortcode, merges user-authored sections, rebuilds frame references from the
files on disk, and moves duplicates into an archive instead of deleting them.
Dry-run is the default.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import __version__
from .config import load_config, vault_path
from .notes import (
    CLASSIFICATION_DONE,
    CLASSIFICATION_PENDING,
    UNCLASSIFIED,
    atomic_write_bytes,
    read_note,
    render_note,
    section_map,
    source_id,
    split_frontmatter,
    update_body_metadata,
)
from .storage import ObsidianStore

_FRAME_REF_RE = re.compile(r"!\[\[([^\]|]+?\.(?:webp|jpe?g|png))", re.I)
_FRAME_NAME_RE = re.compile(r"^frame-(\d{2})-(\d{2})-(\d{2})(?:\.\d+)?\.", re.I)
_FRAME_INDEX_RE = re.compile(r"^frame-(\d+)$", re.I)
_GENERATED = {"visual frames", "key frame"}


@dataclass
class Note:
    path: Path
    fm: dict[str, Any]
    body: str
    source: str
    sid: str
    topic: str
    mtime: float

    @property
    def rel(self) -> str:
        return self.path.as_posix()


def _topic_for(path: Path, reels: Path, fm: dict[str, Any]) -> str:
    topic = str(fm.get("topic") or "").strip()
    if topic:
        return topic
    try:
        parent = path.parent.relative_to(reels).parts[0]
    except (ValueError, IndexError):
        return "general"
    return parent if parent and parent != "frames" else "general"


def _backup(path: Path, root: Path, backup_root: Path | None) -> None:
    if backup_root is None:
        return
    target = backup_root / path.relative_to(root)
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def collect(store: ObsidianStore) -> tuple[list[Note], list[Path]]:
    reels = store.reels_dir
    notes: list[Note] = []
    skipped: list[Path] = []
    for path in store.iter_reels():
        try:
            fm, body, _ = read_note(path)
        except (OSError, UnicodeDecodeError) as exc:
            skipped.append(path)
            continue
        source = str(fm.get("source") or "").strip()
        if not source:
            skipped.append(path)
            continue
        sid = str(fm.get("source_id") or "").strip() or source_id(source)
        if not sid:
            skipped.append(path)
            continue
        notes.append(Note(path=path, fm=fm, body=body, source=source, sid=sid,
                          topic=_topic_for(path, reels, fm), mtime=path.stat().st_mtime))
    return notes, skipped


def score(note: Note) -> tuple[int, int, int, float]:
    fm = note.fm
    classified = str(fm.get("classification") or "").lower() in (CLASSIFICATION_DONE, "done")
    rich = sum(1 for key in ("niche", "category", "industry")
               if fm.get(key) not in (None, "", UNCLASSIFIED))
    keys = us = 0
    for section in section_map(note.body).values():
        keys += sum(1 for line in section.splitlines() if line.strip().upper().startswith("KEY:"))
        us += sum(1 for line in section.splitlines() if line.strip())
    frames = len(frame_files(note))
    base = (100 if classified else 0) + rich * 10 + keys * 5 + frames * 3
    return base, len(note.body), us, note.mtime


def frame_dir(note: Note) -> Path:
    return note.path.parent / "frames" / note.path.stem


def frame_files(note: Note) -> list[Path]:
    directory = frame_dir(note)
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.iterdir()
                  if path.is_file() and path.suffix.lower() in {".webp", ".jpg", ".jpeg", ".png"})


def frame_timestamp(name: str) -> str:
    match = _FRAME_NAME_RE.match(name)
    if match:
        hours, minutes, seconds = (int(match.group(i)) for i in (1, 2, 3))
        total = hours * 3600 + minutes * 60 + seconds
        return f"{total // 60:02d}:{total % 60:02d}"
    match = _FRAME_INDEX_RE.match(Path(name).stem)
    if match:
        total = max(0, int(match.group(1)) - 1)
        return f"{total // 60:02d}:{total % 60:02d}"
    return "00:00"


def frame_refs(note: Note) -> list[str]:
    match = re.search(r"^## Visual Frames\s*$", note.body, re.M)
    if not match:
        return []
    end = re.search(r"^## ", note.body[match.end():], re.M)
    section = note.body[match.end():match.end() + end.start()] if end else note.body[match.end():]
    return [item.strip() for item in _FRAME_REF_RE.findall(section)]


def ref_exists(root: Path, note: Note, ref: str) -> bool:
    if (root / ref).is_file():
        return True
    return (note.path.parent / ref).is_file()


def frames_need_repair(root: Path, note: Note) -> bool:
    files = frame_files(note)
    refs = frame_refs(note)
    if not files:
        return bool(refs)
    if not refs:
        return True
    expected = {f"{frame_dir(note).relative_to(root).as_posix()}/{path.name}" for path in files}
    if any(not ref_exists(root, note, ref) for ref in refs):
        return True
    return any(path not in refs for path in expected)


def key_frame_section() -> str:
    return "\n".join([
        "## Key Frame",
        "",
        "After viewing the frames above, identify and mark **one frame** where:",
        "- Any on-screen text/prompt/code is **fully visible** (no face or hand blocking it)",
        "- The creator has moved aside to reveal content",
        "",
        "Format: `KEY: [mm:ss] — <what is visible on screen>`",
    ])


def visual_section(root: Path, note: Note, files: Iterable[Path]) -> str:
    rel = f"{frame_dir(note).relative_to(root).as_posix()}"
    lines = ["## Visual Frames", "",
             f"> *Frames stored in `{rel}/` — load for visual analysis*", ""]
    for path in files:
        lines.append(f"- [{frame_timestamp(path.name)}] ![[{rel}/{path.name}]]")
    return "\n".join(lines)


def _split_preamble(body: str) -> tuple[str, dict[str, str]]:
    first = re.search(r"^## ", body or "", re.M)
    preamble = (body or "")[:first.start()] if first else (body or "")
    return preamble, section_map(body)


def _merge_sections(base: str, extra_bodies: Iterable[str]) -> tuple[str, dict[str, str]]:
    preamble, base_sections = _split_preamble(base)
    merged: dict[str, str] = {}
    lower: dict[str, str] = {}
    for name, text in base_sections.items():
        merged[name] = text
        lower[name.lower()] = name
    for body in extra_bodies:
        _, sections = _split_preamble(body)
        for name, text in sections.items():
            key = name.lower()
            if key == "visual frames":
                continue
            if key not in lower:
                merged[name] = text
                lower[key] = name
            elif key == "key frame":
                existing = merged[lower[key]]
                keys = [line for line in text.splitlines()
                        if line.strip().upper().startswith("KEY:") and line not in existing]
                if keys:
                    merged[lower[key]] = existing.rstrip() + "\n" + "\n".join(keys) + "\n"
    return preamble, merged


def _body_with_frames(preamble: str, sections: dict[str, str],
                      root: Path, note: Note, files: list[Path]) -> str:
    sections = {name: text for name, text in sections.items() if name.lower() != "visual frames"}
    frame_text = visual_section(root, note, files) if files else ""
    if files and not any(name.lower() == "key frame" for name in sections):
        sections["Key Frame"] = key_frame_section()
    parts: list[str] = []
    if preamble.strip():
        parts.append(preamble.rstrip())
    inserted = not files
    for name, text in sections.items():
        parts.append(text.rstrip())
        if not inserted and name.lower() == "metadata":
            parts.append(frame_text)
            inserted = True
    if not inserted:
        parts.append(frame_text)
    return "\n\n".join(parts).rstrip() + "\n"


def merge_group(root: Path, canonical: Note, extras: list[Note],
                apply: bool, backup_root: Path | None) -> Note:
    preamble, sections = _merge_sections(canonical.body, [note.body for note in extras])
    files = frame_files(canonical)
    for extra in extras:
        for path in frame_files(extra):
            files.append(path)
    merged_fm = dict(canonical.fm)
    merged_fm["source_id"] = canonical.sid
    if canonical.source:
        merged_fm["source"] = canonical.source
    topics: list[str] = []
    for note in [canonical] + extras:
        values = note.fm.get("topics") or []
        if isinstance(values, str):
            values = [values]
        for value in [note.fm.get("topic"), note.topic, *values]:
            text = str(value or "").strip()
            if text and text not in topics:
                topics.append(text)
    if topics:
        merged_fm["topics"] = topics
    if not merged_fm.get("topic"):
        merged_fm["topic"] = topics[0] if topics else canonical.topic
    for key in ("niche", "category", "industry"):
        if merged_fm.get(key) in (None, "", UNCLASSIFIED):
            for note in extras:
                if note.fm.get(key) not in (None, "", UNCLASSIFIED):
                    merged_fm[key] = note.fm[key]
                    break
    if str(merged_fm.get("classification") or "").lower() not in (CLASSIFICATION_DONE, "done"):
        for note in extras:
            if str(note.fm.get("classification") or "").lower() in (CLASSIFICATION_DONE, "done"):
                merged_fm["classification"] = note.fm.get("classification")
                break
    merged_fm.setdefault("classification", CLASSIFICATION_PENDING)
    tags: list[str] = []
    for note in [canonical] + extras:
        values = note.fm.get("tags") or []
        if isinstance(values, str):
            values = [values]
        for value in values:
            text = str(value).strip()
            if text and text not in tags:
                tags.append(text)
    if tags:
        merged_fm["tags"] = tags

    merged = Note(path=canonical.path, fm=merged_fm, body=canonical.body,
                  source=canonical.source, sid=canonical.sid,
                  topic=str(merged_fm.get("topic") or canonical.topic),
                  mtime=canonical.mtime)

    # Frames must be copied before duplicate frame dirs are archived.
    destinations = frame_dir(merged)
    if apply:
        destinations.mkdir(parents=True, exist_ok=True)
        for path in files:
            target = destinations / path.name
            if not target.exists():
                shutil.copy2(path, target)
        merged_files = frame_files(merged)
    else:
        merged_files = files
    body = _body_with_frames(preamble, sections, root, merged, merged_files)
    body = update_body_metadata(body, merged_fm)
    merged.body = body

    if apply:
        _backup(canonical.path, root, backup_root)
        atomic_write_bytes(canonical.path, render_note(merged_fm, body).encode("utf-8"))
    return merged


def repair_frames(root: Path, note: Note, apply: bool,
                  backup_root: Path | None = None) -> bool:
    files = frame_files(note)
    if not frames_need_repair(root, note):
        return False
    preamble, sections = _split_preamble(note.body)
    body = _body_with_frames(preamble, sections, root, note, files)
    if apply:
        _backup(note.path, root, backup_root)
        atomic_write_bytes(note.path, render_note(note.fm, body).encode("utf-8"))
    note.body = body
    return True


def add_metadata(note: Note, apply: bool, backup_root: Path | None,
                 root: Path) -> bool:
    updates: dict[str, Any] = {}
    if not note.fm.get("source_id"):
        updates["source_id"] = note.sid
    if not note.fm.get("classification"):
        updates["classification"] = CLASSIFICATION_PENDING
    values = note.fm.get("topics") or []
    if isinstance(values, str):
        values = [values]
    topics = [str(value) for value in values if str(value).strip()]
    if note.topic and note.topic not in topics:
        topics.append(note.topic)
    if topics and note.fm.get("topics") != topics:
        updates["topics"] = topics
    if note.topic and note.fm.get("topic") != note.topic:
        updates["topic"] = note.topic
    if not updates:
        return False
    note.fm.update(updates)
    body_updates = {key: value for key, value in updates.items()
                    if key in ("classification", "topic")}
    if body_updates:
        note.body = update_body_metadata(note.body, body_updates)
    if apply:
        _backup(note.path, root, backup_root)
        atomic_write_bytes(note.path, render_note(note.fm, note.body).encode("utf-8"))
    return True


def repair(vault: str, apply: bool = False, dedupe: bool = True,
           frames: bool = True, indexes: bool = True) -> dict[str, Any]:
    root = Path(vault).expanduser().resolve()
    store = ObsidianStore(str(root))
    if not store.reels_dir.is_dir():
        raise FileNotFoundError(f"No Reels folder in {root}")
    notes, skipped = collect(store)
    groups: dict[str, list[Note]] = defaultdict(list)
    for note in notes:
        groups[note.sid].append(note)
    duplicate_groups = {sid: items for sid, items in groups.items() if len(items) > 1}

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    archive = root / "_archive" / f"reels-vault-repair-{stamp}"
    backup_root = archive / "backup"
    manifest: dict[str, Any] = {
        "created": datetime.now(timezone.utc).isoformat(),
        "vault": str(root),
        "duplicates": [],
        "notes": [],
    }

    metadata_changes = 0
    frame_repairs = 0
    duplicate_extras = 0
    by_path = {note.path: note for note in notes}

    for items in (duplicate_groups.values() if dedupe else []):
        items.sort(key=score, reverse=True)
        canonical = items[0]
        extras = items[1:]
        duplicate_extras += len(extras)
        merged = merge_group(root, canonical, extras, apply, backup_root if apply else None)
        canonical.fm = merged.fm
        canonical.body = merged.body
        canonical.topic = merged.topic
        canonical.sid = merged.sid
        if apply:
            for extra in extras:
                target = archive / "duplicates" / extra.path.relative_to(root)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(extra.path), str(target))
                extra_frames = frame_dir(extra)
                if extra_frames.is_dir():
                    shutil.move(str(extra_frames),
                                str(archive / "duplicates" / extra_frames.relative_to(root)))
                manifest["duplicates"].append({
                    "kept": canonical.path.relative_to(root).as_posix(),
                    "archived": extra.path.relative_to(root).as_posix(),
                })
                by_path.pop(extra.path, None)

    metadata_changes += len(duplicate_groups) if dedupe else 0
    for note in notes:
        if note.path not in by_path:
            continue
        if add_metadata(note, apply, backup_root if apply else None, root):
            metadata_changes += 1
        if frames and repair_frames(root, note, apply, backup_root if apply else None):
            frame_repairs += 1

    stems: dict[str, int] = defaultdict(int)
    for note in by_path.values():
        stems[note.path.stem] += 1
    duplicate_stems = sum(count - 1 for count in stems.values() if count > 1)

    index_count = 0
    if apply and indexes:
        index_count = store.rebuild_indexes()
        if manifest["duplicates"] or metadata_changes or frame_repairs:
            (archive).mkdir(parents=True, exist_ok=True)
            (archive / "manifest.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return {
        "vault": str(root),
        "apply": apply,
        "notes": len(notes),
        "skipped": len(skipped),
        "duplicate_groups": len(duplicate_groups) if dedupe else 0,
        "duplicate_notes": duplicate_extras,
        "frame_notes": sum(1 for note in notes if frame_files(note)),
        "frame_repairs": frame_repairs,
        "metadata_updates": metadata_changes,
        "duplicate_stems": duplicate_stems,
        "indexes_rebuilt": index_count,
        "archive": str(archive) if apply and (duplicate_extras or metadata_changes or frame_repairs) else "",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit and repair an Obsidian Reel Vault.")
    parser.add_argument("--version", action="version", version=f"reels-vault-repair {__version__}")
    parser.add_argument("--vault", default="", help="Vault root (defaults to configured vault)")
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    parser.add_argument("--no-dedupe", action="store_true", help="Skip duplicate archiving")
    parser.add_argument("--no-frames", action="store_true", help="Skip frame reference repair")
    parser.add_argument("--no-index", action="store_true", help="Skip index rebuild")
    parser.add_argument("--json", action="store_true", help="Print a JSON report")
    args = parser.parse_args()

    target = args.vault or vault_path(load_config())
    if not target:
        print("Error: no vault configured. Pass --vault or run reels-vault-connect.", file=sys.stderr)
        sys.exit(1)
    try:
        report = repair(target, apply=args.apply, dedupe=not args.no_dedupe,
                        frames=not args.no_frames, indexes=not args.no_index)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"Vault: {report['vault']}")
        print(f"Notes: {report['notes']} (skipped {report['skipped']})")
        print(f"Duplicate groups: {report['duplicate_groups']} ({report['duplicate_notes']} extras)")
        print(f"Frame notes: {report['frame_notes']}, repairs needed: {report['frame_repairs']}")
        print(f"Metadata updates: {report['metadata_updates']}")
        print(f"Duplicate stems: {report['duplicate_stems']}")
        if report["apply"]:
            print(f"Indexes rebuilt: {report['indexes_rebuilt']}")
            if report["archive"]:
                print(f"Archive/backup: {report['archive']}")
        else:
            print("Dry run — pass --apply to write changes.")


if __name__ == "__main__":
    main()
