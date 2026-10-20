#!/usr/bin/env python3
"""Low-space Obsidian reel pipeline using yt-dlp, ffmpeg, and nemo-speech."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "nemotron-3.5"
UNCLASSIFIED = "unclassified"
PENDING = "pending"
CLASSIFIED = "classified"
SHORTCODE_RE = re.compile(r"instagram\.com/(?:[\w.-]+/)?(?:reel|reels|p)/([A-Za-z0-9_-]+)")
HASHTAG_RE = re.compile(r"#([A-Za-z0-9_]+)")
BODY_FIELDS = {
    "niche": "Niche",
    "category": "Category",
    "industry": "Industry",
    "classification": "Classification",
    "topic": "Topic",
}

INDEX_TEMPLATE = """---
tags: [vault-index]
---

# Reel Vault

Every saved reel is a Markdown note under `Reels/<topic>/`.

## All Reels

```dataview
TABLE creator AS "Creator", topic AS "Topic", niche AS "Niche", extracted AS "Date"
FROM "Reels"
WHERE source
SORT extracted DESC
```
"""


class LiteError(RuntimeError):
    pass


def config_file() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "reels-vault-lite" / "config.json"


def full_config_file() -> Path:
    return Path(os.path.expanduser("~/.config/reels-vault/config.json"))


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_config() -> dict[str, Any]:
    config: dict[str, Any] = {}
    config.update(load_json(full_config_file()))
    config.update(load_json(config_file()))
    return config


def save_config(config: dict[str, Any]) -> Path:
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def normalise_vault_path(path: Path) -> Path:
    path = path.expanduser()
    try:
        path = path.resolve()
    except OSError:
        pass
    if path.name.lower() != "reel vault" and (path / ".obsidian").is_dir():
        return path / "Reel Vault"
    return path


def resolve_vault(args: argparse.Namespace, config: dict[str, Any]) -> Path:
    raw = (
        getattr(args, "vault", None)
        or os.environ.get("REELS_VAULT_PATH")
        or config.get("vault_path")
    )
    if not raw:
        raise LiteError(
            "No Obsidian vault configured. Run: "
            "reels_vault_lite.py configure --vault /path/to/ObsidianVault"
        )
    path = normalise_vault_path(Path(str(raw)))
    if not path.is_dir():
        raise LiteError(f"Obsidian vault not found: {path}")
    return path


def resolve_tool(name: str, env_var: str) -> str | None:
    override = os.environ.get(env_var)
    if override:
        return override
    found = shutil.which(name)
    if found:
        return found
    home = Path.home()
    candidates: list[Path] = []
    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
        candidates.extend(
            [
                local / "Programs" / "NeMoSpeech" / "bin" / f"{name}.exe",
                local / "ReelsVault" / "bin" / f"{name}.exe",
                home / "scoop" / "shims" / f"{name}.exe",
            ]
        )
    else:
        candidates.extend(
            [
                home / ".local" / "bin" / name,
                home / "bin" / name,
                Path("/opt/homebrew/bin") / name,
                Path("/usr/local/bin") / name,
            ]
        )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def run_command(command: list[str], cwd: Path | None = None,
                timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise LiteError(f"Command not found: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise LiteError(f"{Path(command[0]).name} timed out after {timeout}s") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        if len(detail) > 2000:
            detail = detail[-2000:]
        raise LiteError(f"{Path(command[0]).name} failed ({result.returncode}): {detail}")
    return result


def string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def slugify(value: Any) -> str:
    slug = str(value or "").lower().strip()
    slug = re.sub(r"[.]+", "-", slug)
    slug = re.sub(r"[^\w\s-]", "", slug).strip()
    slug = re.sub(r"[\s_-]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "unknown"


def extract_shortcode(url: str) -> str:
    match = SHORTCODE_RE.search(url or "")
    return match.group(1) if match else ""


def source_id(url: str) -> str:
    shortcode = extract_shortcode(url)
    if shortcode:
        return shortcode
    url = (url or "").strip()
    if not url:
        return ""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]


def note_base_name(metadata: dict[str, Any], url: str) -> str:
    handle = slugify(metadata.get("handle") or metadata.get("creator") or "unknown")
    upload_date = str(metadata.get("upload_date") or "")
    if len(upload_date) == 8 and upload_date.isdigit():
        upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
    if not upload_date:
        upload_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sid = source_id(url)
    if not sid:
        sid = hashlib.sha1(f"{handle}:{upload_date}".encode("utf-8")).hexdigest()[:10]
    return f"{handle}-reel-{upload_date}-{sid}"


def yaml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def render_frontmatter(frontmatter: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in frontmatter.items():
        if value is None or value == "":
            continue
        if isinstance(value, (list, tuple)):
            if not value:
                continue
            lines.append(f"{key}:")
            lines.extend(f"  - {yaml_scalar(item)}" for item in value)
        else:
            lines.append(f"{key}: {yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def parse_scalar(raw: str) -> Any:
    raw = raw.strip()
    if not raw:
        return ""
    if raw.startswith(('"', "[")):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            if raw.startswith("[") and raw.endswith("]"):
                inner = raw[1:-1].strip()
                if not inner:
                    return []
                return [parse_scalar(item) for item in inner.split(",") if item.strip()]
    if raw.startswith("'") and raw.endswith("'"):
        return raw[1:-1]
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        return int(raw)
    except ValueError:
        return raw


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end = index
            break
    if end is None:
        return {}, text
    frontmatter: dict[str, Any] = {}
    current: str | None = None
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.lstrip().startswith("- ") and current:
            frontmatter.setdefault(current, []).append(parse_scalar(line.split("-", 1)[1]))
            continue
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        key = key.strip()
        raw = raw.strip()
        if raw:
            frontmatter[key] = parse_scalar(raw)
            current = None
        else:
            frontmatter[key] = []
            current = key
    body = "\n".join(lines[end + 1 :]).lstrip("\n")
    return frontmatter, body


def read_note(path: Path) -> tuple[dict[str, Any], str]:
    return parse_frontmatter(path.read_text(encoding="utf-8"))


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def section_map(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    matches = list(re.finditer(r"^## (.+)$", body or "", re.M))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[match.group(1).strip()] = body[match.start():end].rstrip() + "\n"
    return sections


def preserve_sections(old_body: str, new_body: str) -> str:
    new = section_map(new_body)
    if not new:
        return new_body
    old = section_map(old_body)
    existing = {name.lower() for name in new}
    additions = [text for name, text in old.items() if name.lower() not in existing]
    rebuilt = "\n".join(text.rstrip() for text in new.values()).rstrip() + "\n"
    if additions:
        rebuilt += "\n" + "\n\n".join(text.rstrip() for text in additions).rstrip() + "\n"
    return rebuilt


def update_body_fields(body: str, updates: dict[str, Any]) -> str:
    missing: list[str] = []
    for key, label in BODY_FIELDS.items():
        if key not in updates:
            continue
        value = updates[key]
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(item) for item in value)
        line = f"- **{label}:** {value}"
        pattern = re.compile(rf"^- \*\*{re.escape(label)}:\*\*.*$", re.M)
        if pattern.search(body):
            body = pattern.sub(line, body, count=1)
        else:
            missing.append(line)
    if not missing:
        return body
    marker = "## Metadata"
    start = body.find(marker)
    if start < 0:
        return body.rstrip() + "\n\n" + "\n".join(missing) + "\n"
    next_section = body.find("\n## ", start + len(marker))
    if next_section < 0:
        next_section = len(body)
    prefix = body[:next_section].rstrip()
    suffix = body[next_section:]
    return prefix + "\n" + "\n".join(missing) + "\n" + suffix


def format_timestamp(seconds: Any) -> str:
    try:
        total = max(0, int(float(seconds or 0)))
    except (TypeError, ValueError):
        total = 0
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def normalise_metadata(raw: dict[str, Any], url: str) -> dict[str, Any]:
    source = str(raw.get("webpage_url") or raw.get("original_url") or url)
    creator = str(raw.get("uploader") or raw.get("channel") or raw.get("creator") or "Unknown")
    handle = str(raw.get("uploader_id") or raw.get("channel_id") or raw.get("uploader") or "")
    if handle.isdigit() and raw.get("uploader"):
        handle = str(raw["uploader"])
    handle = handle.lstrip("@")
    upload_date = str(raw.get("upload_date") or "")
    if not upload_date and raw.get("timestamp"):
        try:
            upload_date = datetime.fromtimestamp(
                float(raw["timestamp"]), tz=timezone.utc
            ).strftime("%Y%m%d")
        except (TypeError, ValueError, OSError):
            upload_date = ""
    caption = str(raw.get("description") or raw.get("title") or "")
    tags: list[str] = []
    for tag in string_list(raw.get("tags")):
        cleaned = str(tag).lstrip("#").strip().lower()
        if cleaned and cleaned not in tags:
            tags.append(cleaned)
    for tag in HASHTAG_RE.findall(caption):
        cleaned = tag.lower()
        if cleaned not in tags:
            tags.append(cleaned)
    return {
        "source": source,
        "source_id": source_id(source),
        "creator": creator,
        "handle": handle,
        "upload_date": upload_date,
        "duration": raw.get("duration"),
        "caption": caption,
        "tags": tags,
        "view_count": raw.get("view_count"),
        "like_count": raw.get("like_count"),
        "comment_count": raw.get("comment_count"),
    }


def fetch_metadata(
    yt_dlp: str, url: str, cookies_from: str | None, cookies: str | None
) -> dict[str, Any]:
    command = [yt_dlp, "--no-playlist", "--no-warnings", "--dump-json"]
    if cookies_from:
        command.extend(["--cookies-from-browser", cookies_from])
    if cookies:
        command.extend(["--cookies", cookies])
    command.append(url)
    result = run_command(command)
    for line in reversed(result.stdout.splitlines()):
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise LiteError("yt-dlp returned no usable metadata.")


def download_media(
    yt_dlp: str,
    ffmpeg: str,
    url: str,
    workdir: Path,
    want_video: bool,
    cookies_from: str | None,
    cookies: str | None,
) -> Path:
    prefix = "video" if want_video else "audio"
    command = [
        yt_dlp,
        "--no-playlist",
        "--no-warnings",
        "--no-progress",
        "--ffmpeg-location",
        ffmpeg,
        "-o",
        str(workdir / f"{prefix}.%(ext)s"),
    ]
    if cookies_from:
        command.extend(["--cookies-from-browser", cookies_from])
    if cookies:
        command.extend(["--cookies", cookies])
    fmt = "bv*[height<=1280]+ba/b[height<=1280]/b" if want_video else "bestaudio/best"
    command.extend(["-f", fmt, url])
    run_command(command)
    candidates = [
        path
        for path in workdir.glob(f"{prefix}.*")
        if path.is_file() and path.suffix not in {".part", ".json", ".ytdl"}
    ]
    if not candidates:
        raise LiteError("yt-dlp finished without producing a media file.")
    return max(candidates, key=lambda path: path.stat().st_size)


def extract_audio(ffmpeg: str, media: Path, workdir: Path) -> Path | None:
    wav = workdir / "audio.wav"
    command = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(media),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(wav),
    ]
    try:
        run_command(command, timeout=600)
    except LiteError as exc:
        if "does not contain any stream" in str(exc):
            return None
        raise
    if not wav.is_file():
        return None
    return wav


def unwrap_transcript(data: Any) -> dict[str, Any]:
    if isinstance(data, dict):
        for key in ("result", "data", "transcription"):
            nested = data.get(key)
            if isinstance(nested, dict):
                return nested
        return data
    return {}


def transcript_text(data: dict[str, Any]) -> str:
    for key in ("text", "transcript", "transcription"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def transcript_segments(data: dict[str, Any]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for key in ("segments", "utterances"):
        values = data.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            text = item.get("text") or item.get("transcript") or ""
            if not str(text).strip():
                continue
            segments.append(
                {
                    "start": item.get("start", item.get("start_time", 0)),
                    "text": str(text).strip(),
                }
            )
        if segments:
            return segments
    words = data.get("words")
    if isinstance(words, list) and words:
        chunk: list[str] = []
        start: Any = 0
        for word in words:
            if not isinstance(word, dict):
                continue
            text = word.get("word") or word.get("text") or ""
            if not chunk:
                start = word.get("start", word.get("start_time", 0))
            chunk.append(str(text))
            if len(chunk) >= 12:
                segments.append({"start": start, "text": " ".join(chunk).strip()})
                chunk = []
        if chunk:
            segments.append({"start": start, "text": " ".join(chunk).strip()})
    return segments


def transcribe(nemo_speech: str, wav: Path, model: str, workdir: Path) -> dict[str, Any]:
    output = workdir / "transcript.json"
    command = [
        nemo_speech,
        "transcribe",
        str(wav),
        "--model",
        model,
        "--format",
        "json",
        "--output",
        str(output),
    ]
    result = run_command(command)
    raw_text = output.read_text(encoding="utf-8") if output.is_file() else result.stdout
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise LiteError(f"nemo-speech returned invalid JSON: {exc}") from exc
    data = unwrap_transcript(data)
    text = transcript_text(data)
    segments = transcript_segments(data)
    if not text and segments:
        text = " ".join(segment["text"] for segment in segments).strip()
    language = data.get("language") or data.get("lang") or data.get("detected_language")
    if not language:
        languages = data.get("languages")
        if isinstance(languages, list) and languages:
            language = languages[0]
    return {
        "text": text or "(no speech detected)",
        "language": str(language or "auto"),
        "segments": segments,
    }


def extract_frames(
    ffmpeg: str, video: Path, workdir: Path, count: int, max_width: int, duration: Any
) -> list[dict[str, Any]]:
    try:
        length = float(duration or 0)
    except (TypeError, ValueError):
        length = 0
    if length <= 0:
        times = [1.0, 3.0, 5.0]
        while len(times) < count:
            times.append(times[-1] + 2.0)
        times = times[:count]
    else:
        times = [length * (index + 1) / (count + 1) for index in range(count)]
    frames: list[dict[str, Any]] = []
    for index, timestamp in enumerate(times, start=1):
        webp = workdir / f"frame-{index:02d}.webp"
        command = [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-ss",
            f"{timestamp:.2f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            f"scale=w='min(iw,{max_width})':h=-2",
            "-c:v",
            "libwebp",
            "-quality",
            "80",
            str(webp),
        ]
        try:
            result = subprocess.run(command, text=True, capture_output=True, timeout=60)
        except subprocess.TimeoutExpired:
            continue
        if result.returncode != 0 or not webp.is_file():
            jpg = workdir / f"frame-{index:02d}.jpg"
            command[command.index("libwebp")] = "mjpeg"
            command[command.index("-quality")] = "-q:v"
            command[command.index("-q:v") + 1] = "3"
            command[-1] = str(jpg)
            run_command(command, timeout=60)
            if jpg.is_file():
                frames.append({"path": str(jpg), "timestamp": timestamp})
        else:
            frames.append({"path": str(webp), "timestamp": timestamp})
    return frames


def format_note(
    frontmatter: dict[str, Any],
    metadata: dict[str, Any],
    transcript: dict[str, Any],
    topic: str,
    model: str,
    frames: list[dict[str, Any]],
    frames_rel: str,
) -> str:
    creator = metadata["creator"]
    handle = metadata["handle"]
    source = metadata["source"]
    lines = [render_frontmatter(frontmatter), "# Reel Extraction", ""]
    lines.append(f"**Source:** [{source}]({source})")
    lines.append(f"**Extracted:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")
    lines.extend(["## Metadata", ""])
    lines.append(f"- **Creator:** {creator}" + (f" (@{handle})" if handle else ""))
    if topic:
        lines.append(f"- **Topic:** {topic}")
    lines.append(f"- **Niche:** {frontmatter.get('niche', UNCLASSIFIED)}")
    lines.append(f"- **Category:** {frontmatter.get('category', UNCLASSIFIED)}")
    lines.append(f"- **Industry:** {frontmatter.get('industry', UNCLASSIFIED)}")
    lines.append(f"- **Classification:** {frontmatter.get('classification', PENDING)}")
    lines.append(f"- **Transcription:** NVIDIA {model} via nemo-speech (local)")
    if metadata.get("upload_date"):
        date = metadata["upload_date"]
        if len(date) == 8 and date.isdigit():
            date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
        lines.append(f"- **Upload Date:** {date}")
    if metadata.get("duration"):
        try:
            minutes, seconds = divmod(int(float(metadata["duration"])), 60)
            lines.append(f"- **Duration:** {minutes}:{seconds:02d}")
        except (TypeError, ValueError):
            pass
    for label, key in (("Views", "view_count"), ("Likes", "like_count"), ("Comments", "comment_count")):
        value = metadata.get(key)
        if value is not None:
            try:
                lines.append(f"- **{label}:** {int(value):,}")
            except (TypeError, ValueError):
                lines.append(f"- **{label}:** {value}")
    lines.append("")
    if frames and frames_rel:
        lines.extend(["## Visual Frames", ""])
        lines.append(f"> *Frames stored in `{frames_rel}/`*")
        lines.append("")
        for frame in frames:
            lines.append(
                f"- [{format_timestamp(frame.get('timestamp'))}] "
                f"![[{frames_rel}/{Path(frame['path']).name}]]"
            )
        lines.append("")
    if metadata.get("caption"):
        lines.extend(["## Caption", "", metadata["caption"], ""])
    if metadata.get("tags"):
        lines.extend(["## Hashtags", "", " ".join(f"#{tag}" for tag in metadata["tags"]), ""])
    lines.extend(
        [
            "## Transcript",
            "",
            f"*Language detected: {transcript.get('language', 'auto')}*",
            "",
            transcript.get("text") or "(no speech detected)",
            "",
        ]
    )
    if transcript.get("segments"):
        lines.extend(["## Timestamped Transcript", ""])
        for segment in transcript["segments"]:
            lines.append(
                f"[{format_timestamp(segment.get('start'))}] {segment.get('text', '').strip()}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def resolve_child(parent: Path, name: str) -> Path:
    direct = parent / name
    if direct.exists():
        return direct
    if parent.is_dir():
        lowered = name.lower()
        for child in parent.iterdir():
            if child.name.lower() == lowered:
                return child
    return direct


def append_unique(path: Path, header: str, line: str, marker: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        if marker:
            for index, existing in enumerate(lines):
                if marker in existing:
                    lines[index] = line
                    atomic_write(path, "\n".join(lines).rstrip("\n") + "\n")
                    return
        elif line in lines:
            return
    else:
        path.write_text(header, encoding="utf-8")
    current = path.read_text(encoding="utf-8") if path.exists() else header
    atomic_write(path, current.rstrip("\n") + "\n" + line + "\n")


def ensure_vault(vault: Path) -> tuple[Path, Path, Path]:
    reels = resolve_child(vault, "Reels")
    reels.mkdir(parents=True, exist_ok=True)
    index_dir = resolve_child(vault, "index")
    index_dir.mkdir(parents=True, exist_ok=True)
    for kind in ("topics", "niches", "categories", "industries"):
        (index_dir / kind).mkdir(parents=True, exist_ok=True)
    creators = resolve_child(vault, "Creators")
    creators.mkdir(parents=True, exist_ok=True)
    root_index = resolve_child(vault, "Index.md")
    if not root_index.exists():
        root_index.write_text(INDEX_TEMPLATE, encoding="utf-8")
    return reels, index_dir, creators


def remove_index_entry(vault: Path, key: str, kind: str, marker: str) -> None:
    index_dir = resolve_child(vault, "index")
    path = index_dir / f"{kind}s" / f"{slugify(key)}.md"
    if not path.is_file():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if marker not in line]
    if len(kept) != len(lines):
        atomic_write(path, "\n".join(kept).rstrip("\n") + "\n")


def update_indexes(vault: Path, frontmatter: dict[str, Any], topic: str, base_name: str) -> None:
    _, index_dir, creators = ensure_vault(vault)
    creator = frontmatter.get("creator", "Unknown")
    niche = frontmatter.get("niche") or UNCLASSIFIED
    category = frontmatter.get("category") or UNCLASSIFIED
    industry = frontmatter.get("industry") or UNCLASSIFIED
    date = frontmatter.get("extracted") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = f"- [[{base_name}]] — {creator} ({topic or 'general'}) — {date}"
    marker = f"[[{base_name}]]"
    for key, kind in ((niche, "niche"), (category, "category"), (industry, "industry")):
        append_unique(
            index_dir / f"{kind}s" / f"{slugify(key)}.md",
            f"---\ntags: [index, {kind}]\n---\n\n# {str(key).replace('-', ' ').title()}\n\n",
            entry,
            marker,
        )
    append_unique(
        index_dir / "topics" / f"{slugify(topic or 'general')}.md",
        f"---\ntags: [index, topic]\n---\n\n# {topic or 'general'}\n\n",
        entry,
        marker,
    )
    handle = slugify(frontmatter.get("handle") or creator)
    append_unique(
        creators / f"{handle}.md",
        f"---\ntags: [creator]\n---\n\n# {creator}\n\n",
        f"- [[{base_name}]] ({topic or 'general'}) — {date}",
        marker,
    )


def find_existing_note(vault: Path, source: str, sid: str) -> Path | None:
    reels = resolve_child(vault, "Reels")
    if not reels.is_dir():
        return None
    needle = sid or source_id(source)
    for path in reels.rglob("*.md"):
        frontmatter, _ = read_note(path)
        if needle and str(frontmatter.get("source_id") or "") == needle:
            return path
        current = str(frontmatter.get("source") or "")
        if current == source:
            return path
        if needle and extract_shortcode(current) == needle:
            return path
    return None


def write_note(
    vault: Path,
    metadata: dict[str, Any],
    transcript: dict[str, Any],
    topic: str,
    model: str,
    frames: list[dict[str, Any]],
) -> dict[str, Any]:
    ensure_vault(vault)
    existing = find_existing_note(vault, metadata["source"], metadata["source_id"])
    old_frontmatter: dict[str, Any] = {}
    old_body = ""
    if existing:
        old_frontmatter, old_body = read_note(existing)
        target = existing
        topic = str(topic or old_frontmatter.get("topic") or "general")
    else:
        base = note_base_name(metadata, metadata["source"])
        target = resolve_child(vault, "Reels") / slugify(topic or "general") / f"{base}.md"
    old_classification = str(old_frontmatter.get("classification") or "").lower()
    classified = old_classification in (CLASSIFIED, "done")
    labels = {
        key: (old_frontmatter.get(key)
              if old_frontmatter.get(key) not in (None, "", UNCLASSIFIED)
              else UNCLASSIFIED)
        for key in ("niche", "category", "industry")
    }
    tags = list(metadata.get("tags") or [])
    for tag in string_list(old_frontmatter.get("tags")):
        if tag not in tags:
            tags.append(tag)
    topics: list[str] = []
    for value in (old_frontmatter.get("topics"), topic):
        if isinstance(value, str):
            value = [value]
        for item in value or []:
            text = str(item).strip()
            if text and text not in topics:
                topics.append(text)
    frontmatter: dict[str, Any] = {
        "creator": metadata["creator"],
        "handle": metadata["handle"],
        "topic": topic or "general",
        "niche": labels["niche"],
        "category": labels["category"],
        "industry": labels["industry"],
        "classification": old_frontmatter.get("classification") if classified else PENDING,
        "tags": tags,
        "source": metadata["source"],
        "source_id": metadata["source_id"],
        "extracted": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    if topics:
        frontmatter["topics"] = topics
    frames_rel = ""
    if frames:
        frames_dir = target.parent / "frames" / target.stem
        frames_dir.mkdir(parents=True, exist_ok=True)
        for frame in frames:
            source_file = Path(frame["path"])
            if source_file.is_file():
                shutil.copyfile(source_file, frames_dir / source_file.name)
        frames_rel = frames_dir.relative_to(vault).as_posix()
        for frame in frames:
            if (frames_dir / Path(frame["path"]).name).is_file():
                frame["vault_path"] = f"{frames_rel}/{Path(frame['path']).name}"
    note = format_note(frontmatter, metadata, transcript, topic, model, frames, frames_rel)
    if existing:
        _, new_body = parse_frontmatter(note)
        note = render_frontmatter(frontmatter) + "\n" + preserve_sections(old_body, new_body)
    atomic_write(target, note)
    update_indexes(vault, frontmatter, topic, target.stem)
    return {
        "path": str(target),
        "ref": target.relative_to(vault).as_posix(),
        "source": metadata["source"],
        "source_id": metadata["source_id"],
        "creator": metadata["creator"],
        "handle": metadata["handle"],
        "topic": topic or "general",
        "classification": frontmatter["classification"],
        "transcript": transcript["text"],
        "language": transcript["language"],
        "frames": [frame["vault_path"] for frame in frames if frame.get("vault_path")],
    }


def resolve_note(vault: Path, ref: str) -> Path:
    direct = Path(ref).expanduser()
    if direct.is_file():
        return direct
    candidate = vault / ref
    if candidate.is_file():
        return candidate
    reels = resolve_child(vault, "Reels")
    if reels.is_dir():
        for path in reels.rglob("*.md"):
            if path.stem == ref or path.stem == Path(ref).stem:
                return path
    raise LiteError(f"Note not found: {ref}")


def classify_note(
    vault: Path,
    ref: str,
    niche: str | None,
    category: str | None,
    industry: str | None,
    tags: str | None,
) -> dict[str, Any]:
    path = resolve_note(vault, ref)
    frontmatter, body = read_note(path)
    updates: dict[str, Any] = {}
    if niche:
        updates["niche"] = niche
    if category:
        updates["category"] = category
    if industry:
        updates["industry"] = industry
    if tags:
        parsed = [tag.strip().lstrip("#").lower() for tag in tags.split(",") if tag.strip()]
        existing = string_list(frontmatter.get("tags"))
        updates["tags"] = existing + [tag for tag in parsed if tag not in existing]
    if not updates:
        raise LiteError("Provide at least one of --niche, --category, --industry, or --tags.")
    previous = {
        field: frontmatter.get(field) or UNCLASSIFIED
        for field in ("niche", "category", "industry")
    }
    updates["classification"] = CLASSIFIED
    frontmatter.update(updates)
    body = update_body_fields(body, updates)
    atomic_write(path, render_frontmatter(frontmatter) + "\n" + body)
    topic = str(frontmatter.get("topic") or "general")
    for field, old_value in previous.items():
        new_value = frontmatter.get(field) or UNCLASSIFIED
        if old_value != new_value:
            remove_index_entry(vault, old_value, field, f"[[{path.stem}]]")
    update_indexes(vault, frontmatter, topic, path.stem)
    return {
        "path": str(path),
        "ref": path.relative_to(vault).as_posix(),
        "classification": CLASSIFIED,
        "niche": frontmatter.get("niche", UNCLASSIFIED),
        "category": frontmatter.get("category", UNCLASSIFIED),
        "industry": frontmatter.get("industry", UNCLASSIFIED),
        "tags": frontmatter.get("tags") or [],
    }


def search_notes(
    vault: Path,
    query: str,
    creator: str,
    topic: str,
    limit: int,
) -> list[dict[str, Any]]:
    reels = resolve_child(vault, "Reels")
    if not reels.is_dir():
        return []
    results: list[dict[str, Any]] = []
    query_lower = query.lower()
    for path in sorted(reels.rglob("*.md")):
        frontmatter, body = read_note(path)
        if creator and creator.lower() not in str(frontmatter.get("creator", "")).lower():
            continue
        if topic and topic.lower() != str(frontmatter.get("topic", "")).lower():
            continue
        haystack = f"{frontmatter}\n{body}"
        if query_lower and query_lower not in haystack.lower():
            continue
        snippet = ""
        if query_lower:
            body_lower = body.lower()
            source_text = body if query_lower in body_lower else str(frontmatter)
            index = source_text.lower().find(query_lower)
            start = max(0, index - 60)
            snippet = " ".join(source_text[start : index + len(query) + 90].split())
        results.append(
            {
                "ref": path.relative_to(vault).as_posix(),
                "title": path.stem,
                "creator": frontmatter.get("creator", ""),
                "topic": frontmatter.get("topic", ""),
                "niche": frontmatter.get("niche", UNCLASSIFIED),
                "classification": frontmatter.get("classification", PENDING),
                "path": str(path),
                "snippet": snippet,
            }
        )
        if len(results) >= limit:
            break
    return results


def model_cache() -> Path:
    override = os.environ.get("NEMO_SPEECH_MODEL_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return local / "NeMoSpeech" / "models"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "NeMoSpeech" / "models"
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "nemo-speech" / "models"


def status(config: dict[str, Any]) -> dict[str, Any]:
    tools = {
        "yt-dlp": resolve_tool("yt-dlp", "REELS_VAULT_LITE_YTDLP"),
        "ffmpeg": resolve_tool("ffmpeg", "REELS_VAULT_LITE_FFMPEG"),
        "nemo-speech": resolve_tool("nemo-speech", "NEMO_SPEECH_BIN"),
    }
    vault_raw = os.environ.get("REELS_VAULT_PATH") or config.get("vault_path")
    vault = normalise_vault_path(Path(str(vault_raw))) if vault_raw else None
    count = 0
    if vault and vault.is_dir():
        reels = resolve_child(vault, "Reels")
        if reels.is_dir():
            count = sum(1 for _ in reels.rglob("*.md"))
    cache = model_cache()
    models = sorted(str(path) for path in cache.rglob("*.gguf")) if cache.is_dir() else []
    return {
        "config": str(config_file()),
        "vault": str(vault) if vault else "",
        "model": config.get("model") or DEFAULT_MODEL,
        "notes": count,
        "tools": tools,
        "model_cache": str(cache),
        "models": models,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Low-space Instagram reel saver for Obsidian."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    configure = subparsers.add_parser("configure", help="Save the Obsidian vault path.")
    configure.add_argument("--vault", required=True)
    configure.add_argument("--model", default="")
    configure.add_argument("--cookies-from", default="")

    save = subparsers.add_parser("save", help="Download, transcribe, and save a reel.")
    save.add_argument("url")
    save.add_argument("--vault", default="")
    save.add_argument("--topic", default="")
    save.add_argument("--model", default="")
    save.add_argument("--frames", type=int, default=0)
    save.add_argument("--frame-max-width", type=int, default=1280)
    save.add_argument("--cookies-from", default="")
    save.add_argument("--cookies", default="")
    save.add_argument("--json", action="store_true")
    save.add_argument("--keep-workdir", action="store_true")

    classify = subparsers.add_parser("classify", help="Add agent labels to a saved note.")
    classify.add_argument("ref")
    classify.add_argument("--vault", default="")
    classify.add_argument("--niche", default="")
    classify.add_argument("--category", default="")
    classify.add_argument("--industry", default="")
    classify.add_argument("--tags", default="")
    classify.add_argument("--json", action="store_true")

    search = subparsers.add_parser("search", help="Search saved reel notes.")
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--vault", default="")
    search.add_argument("--creator", default="")
    search.add_argument("--topic", default="")
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--json", action="store_true")

    subparsers.add_parser("status", help="Show dependencies, vault, and model status.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config()
    try:
        if args.command == "configure":
            vault = Path(args.vault).expanduser()
            if not vault.is_dir():
                raise LiteError(f"Obsidian vault not found: {vault}")
            vault = normalise_vault_path(vault)
            ensure_vault(vault)
            lite_config = load_json(config_file())
            lite_config["vault_path"] = str(vault)
            if args.model:
                lite_config["model"] = args.model
            if args.cookies_from:
                lite_config["cookies_from"] = args.cookies_from
            path = save_config(lite_config)
            print(json.dumps({"config": str(path), "vault": str(vault)}, indent=2))
            return 0
        if args.command == "status":
            print(json.dumps(status(config), indent=2))
            return 0
        vault = resolve_vault(args, config)
        if args.command == "search":
            results = search_notes(vault, args.query, args.creator, args.topic, args.limit)
            if args.json:
                print(json.dumps(results, indent=2, ensure_ascii=False))
            else:
                for result in results:
                    print(f"{result['ref']} — {result['creator']} ({result['topic']})")
            return 0
        if args.command == "classify":
            result = classify_note(
                vault, args.ref, args.niche, args.category, args.industry, args.tags
            )
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(f"Classified {result['ref']}")
            return 0
        if args.command == "save":
            yt_dlp = resolve_tool("yt-dlp", "REELS_VAULT_LITE_YTDLP")
            ffmpeg = resolve_tool("ffmpeg", "REELS_VAULT_LITE_FFMPEG")
            nemo_speech = resolve_tool("nemo-speech", "NEMO_SPEECH_BIN")
            missing = [
                name
                for name, value in (("yt-dlp", yt_dlp), ("ffmpeg", ffmpeg))
                if not value
            ]
            if missing:
                raise LiteError(
                    "Missing tools: "
                    + ", ".join(missing)
                    + ". Run setup.sh --install (macOS/Linux) or setup.ps1 -Install (Windows)."
                )
            model = args.model or config.get("model") or DEFAULT_MODEL
            cookies_from = args.cookies_from or config.get("cookies_from") or None
            workdir = Path(tempfile.mkdtemp(prefix="reels-vault-lite-"))
            try:
                print("[1/4] Reading metadata", file=sys.stderr)
                raw = fetch_metadata(yt_dlp, args.url, cookies_from, args.cookies or None)
                metadata = normalise_metadata(raw, args.url)
                print("[2/4] Downloading media", file=sys.stderr)
                media = download_media(
                    yt_dlp,
                    ffmpeg,
                    args.url,
                    workdir,
                    args.frames > 0,
                    cookies_from,
                    args.cookies or None,
                )
                print("[3/4] Transcribing with NVIDIA " + model, file=sys.stderr)
                audio = extract_audio(ffmpeg, media, workdir)
                if audio:
                    if not nemo_speech:
                        raise LiteError(
                            "Missing nemo-speech. Run setup.sh --install --with-model "
                            "(macOS/Linux) or setup.ps1 -Install -WithModel (Windows)."
                        )
                    transcript = transcribe(nemo_speech, audio, model, workdir)
                else:
                    print("No audio track; writing a visual-only note.", file=sys.stderr)
                    transcript = {"text": "", "language": "unknown", "segments": []}
                frames = []
                if args.frames > 0:
                    print("[4/4] Extracting frames", file=sys.stderr)
                    frames = extract_frames(
                        ffmpeg,
                        media,
                        workdir,
                        args.frames,
                        args.frame_max_width,
                        metadata.get("duration"),
                    )
                else:
                    print("[4/4] Writing note", file=sys.stderr)
                result = write_note(vault, metadata, transcript, args.topic, model, frames)
                if args.json:
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                else:
                    print(result["path"])
                return 0
            finally:
                if args.keep_workdir:
                    print(f"Kept workdir: {workdir}", file=sys.stderr)
                else:
                    shutil.rmtree(workdir, ignore_errors=True)
        raise LiteError(f"Unknown command: {args.command}")
    except LiteError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
