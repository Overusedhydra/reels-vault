#!/usr/bin/env python3
"""
Reels Vault — Extract transcript and metadata from an Instagram Reel.

Pipeline: yt-dlp (download) → ffmpeg (audio) → Whisper (transcript) → Shazam (music).
Classification is intentionally left to the calling AI agent.
Notes are saved to Obsidian, Notion, or both.

Usage:
    reels-vault <reel_url> --topic content-creation
"""

import sys
import os
import re
import json
import argparse
import subprocess
import tempfile
import asyncio
import shutil
from datetime import datetime, timezone

from . import __version__
from .config import load_config
from .notes import (
    CLASSIFICATION_PENDING,
    UNCLASSIFIED,
    dump_frontmatter,
    slugify,
    source_id,
    split_frontmatter,
)
from .storage import StorageManager

_DOWNLOAD_TIMEOUT = 600
_PROBE_TIMEOUT = 30
_FRAME_TIMEOUT = 60


# ---------------------------------------------------------------------------
# Tool resolution
# ---------------------------------------------------------------------------

def _resolve_tool(name: str) -> str:
    """Find a CLI tool, preferring the one installed in this Python's env."""
    filenames = [name]
    if os.name == "nt" and not name.lower().endswith(".exe"):
        filenames.insert(0, f"{name}.exe")
    for filename in filenames:
        venv_bin = os.path.join(os.path.dirname(sys.executable), filename)
        if os.path.exists(venv_bin):
            return venv_bin
    return name


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

_IG_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"


def _parse_count(raw: str):
    """Parse '709', '8,516' or '44K' into an int."""
    s = (raw or "").strip().replace(",", "").replace(" ", "")
    mult = 1
    if s and s[-1].upper() in "KMB":
        mult = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[s[-1].upper()]
        s = s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        return None


def _parse_instagram_meta(page_meta: dict) -> dict:
    """Build a yt-dlp-shaped metadata dict from Instagram Open Graph tags."""
    title = page_meta.get("title", "") or ""
    desc = page_meta.get("description", "") or ""

    author = title.split(" on Instagram")[0].strip() or "Unknown"
    caption = desc
    handle = ""
    upload_date = ""
    like_count = None
    comment_count = None

    # "706 likes, 147 comments - angus.sewell on September 21, 2026: "caption""
    m = re.match(
        r'^(?P<likes>[\d.,]+\s*[KMB]?)\s+likes?,\s*(?P<comments>[\d.,]+\s*[KMB]?)\s+comments?\s*-\s*'
        r'(?P<handle>@?[\w.]+)\s+on\s+(?P<date>[A-Za-z]+\s+\d{1,2},\s+\d{4}):\s*'
        r'"?(?P<caption>.*?)"?\s*$',
        desc, re.S,
    )
    if m:
        like_count = _parse_count(m.group("likes"))
        comment_count = _parse_count(m.group("comments"))
        handle = m.group("handle").lstrip("@")
        caption = m.group("caption").strip()
        try:
            upload_date = datetime.strptime(m.group("date").replace("  ", " "),
                                             "%B %d, %Y").strftime("%Y%m%d")
        except ValueError:
            upload_date = ""

    hashtags = re.findall(r"#(\w+)", caption or desc)

    return {
        "author": author,
        "author_handle": handle,
        "title": title,
        "caption": caption or desc,
        "like_count": like_count,
        "comment_count": comment_count,
        "upload_date": upload_date,
        "url": page_meta.get("url", ""),
        "hashtags": hashtags,
        "thumbnail": page_meta.get("image", ""),
    }


def _scrape_reel(context, url: str, output_dir: str) -> tuple:
    """Download one reel into ``output_dir`` using an existing browser context."""
    video_path = os.path.join(output_dir, "reel.mp4")
    page = context.new_page()
    try:
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception:
            pass
        page.wait_for_timeout(5000)

        video_url = page.evaluate(r"""
            () => {
                const html = document.documentElement.innerHTML;
                const vidMatch = html.match(/"video_versions":\s*(\[{.*?}\])/);
                if (vidMatch) {
                    try {
                        const versions = JSON.parse(vidMatch[1]);
                        for (const v of versions) {
                            if (v && v.url && typeof v.url === 'string') {
                                return v.url.replace(/\\u0026/g, '&').replace(/\u0026/g, '&');
                            }
                        }
                    } catch(e) {}
                }
                const m2 = html.match(/"video_url":\s*"(https:[^"]+)"/);
                if (m2) return m2[1].replace(/\\u0026/g, '&').replace(/\u0026/g, '&');
                return null;
            }
        """)

        if not video_url:
            raise RuntimeError("Could not extract video URL from page")

        import urllib.request
        req = urllib.request.Request(video_url, headers={
            "User-Agent": _IG_UA,
            "Referer": "https://www.instagram.com/",
        })
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
        with open(video_path, "wb") as f:
            f.write(data)

        page_meta = page.evaluate(r"""
            () => {
                const data = {};
                const tags = document.querySelectorAll('meta[property^="og:"]');
                tags.forEach(t => {
                    const key = t.getAttribute('property').replace('og:', '');
                    data[key] = t.content;
                });
                const desc = document.querySelector('meta[name="description"]');
                if (desc) data['description'] = desc.content;
                return data;
            }
        """) or {}
        page_meta["url"] = url
        metadata = _parse_instagram_meta(page_meta)
    finally:
        page.close()

    return video_path, metadata


def _load_playwright_cookies(session_file: str | None) -> list[dict]:
    """Read a Playwright storage_state file or a plain cookie list."""
    if not session_file or not os.path.exists(session_file):
        return []
    try:
        with open(session_file, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    cookies = data.get("cookies") if isinstance(data, dict) else data
    if not isinstance(cookies, list):
        return []
    return [item for item in cookies if isinstance(item, dict) and item.get("name")]


def _netscape_cookie_file(session_file: str | None, output_dir: str) -> str | None:
    """Convert Playwright JSON cookies into a yt-dlp/curl Netscape cookie file."""
    cookies = _load_playwright_cookies(session_file)
    if not cookies:
        return None
    path = os.path.join(output_dir, ".cookies.txt")
    lines = ["# Netscape HTTP Cookie File", ""]
    for cookie in cookies:
        domain = str(cookie.get("domain") or "")
        if not domain:
            continue
        expires = cookie.get("expires")
        try:
            expires = int(expires) if expires else 0
        except (TypeError, ValueError):
            expires = 0
        lines.append("\t".join([
            domain,
            "TRUE" if domain.startswith(".") else "FALSE",
            str(cookie.get("path") or "/"),
            "TRUE" if cookie.get("secure") else "FALSE",
            str(expires),
            str(cookie.get("name") or ""),
            str(cookie.get("value") or ""),
        ]))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def _download_via_playwright(url: str, output_dir: str, session_file: str = None,
                             context=None) -> tuple:
    """Download a reel with Playwright. Reuses ``context`` when supplied so a
    bulk run can share one browser instead of relaunching per URL."""
    if context is not None:
        return _scrape_reel(context, url, output_dir)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(user_agent=_IG_UA)
            cookies = _load_playwright_cookies(session_file)
            if cookies:
                ctx.add_cookies(cookies)
            return _scrape_reel(ctx, url, output_dir)
        finally:
            browser.close()


def _download_via_instaloader(url: str, output_dir: str, session_file: str = None) -> tuple:
    """Download a reel using instaloader."""
    import instaloader

    shortcode_match = re.search(r"(?:/reel/|/reels/|/p/)([A-Za-z0-9_-]+)", url)
    if not shortcode_match:
        raise RuntimeError(f"Could not extract shortcode from URL: {url}")
    shortcode = shortcode_match.group(1)
    video_path = os.path.join(output_dir, "reel.mp4")

    loader = instaloader.Instaloader(
        download_videos=True,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        dirname_pattern=output_dir,
        filename_pattern="reel",
    )
    if session_file and os.path.exists(session_file):
        try:
            loader.load_session_from_file("", filename=session_file)
        except TypeError:
            loader.load_session_from_file("", session_file)
        except Exception as e:
            print(f"  Warning: Failed to load instaloader session: {e}", file=sys.stderr)

    try:
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
        loader.download_post(post, target="")
    except Exception as e:
        raise RuntimeError(f"instaloader failed: {e}")

    for filename in os.listdir(output_dir):
        if filename.endswith(".mp4"):
            src = os.path.join(output_dir, filename)
            if src != video_path:
                shutil.move(src, video_path)
            break
    if not os.path.isfile(video_path):
        raise RuntimeError("instaloader did not download an mp4")

    caption = post.caption or ""
    return video_path, {
        "author": post.owner_username,
        "author_handle": post.owner_username,
        "title": f"Reel by @{post.owner_username}",
        "caption": caption,
        "view_count": getattr(post, "video_view_count", None),
        "like_count": post.likes,
        "comment_count": post.comments,
        "duration_seconds": getattr(post, "video_duration", None),
        "upload_date": post.date_utc.strftime("%Y%m%d"),
        "url": url,
        "hashtags": [tag.lstrip("#") for tag in getattr(post, "caption_hashtags", [])],
        "thumbnail": post.url,
    }


def extract_metadata(url: str, output_dir: str, cookies_from: str = None,
                     session_file: str = None, downloader: str = "auto") -> tuple:
    """Download a reel and return ``(video_path, metadata)``.

    ``url`` may be a local media file produced by ``bulk_import.py``; a sidecar
    ``.json`` next to it supplies the metadata and no network is used.
    ``downloader`` selects yt-dlp, Playwright, or yt-dlp-with-fallback (auto).
    """
    video_path = os.path.join(output_dir, "reel.mp4")
    info_path = os.path.join(output_dir, "reel.info.json")

    if os.path.isfile(url):
        shutil.copy2(url, video_path)
        stem = os.path.splitext(url)[0]
        metadata = {}
        for cand in (stem + ".json", stem + ".info.json"):
            if os.path.isfile(cand):
                with open(cand) as fh:
                    metadata = json.load(fh)
                break
        metadata.setdefault("url", url)
        return video_path, metadata

    if downloader == "playwright":
        return _download_via_playwright(url, output_dir, session_file=session_file)
    if downloader == "instaloader":
        return _download_via_instaloader(url, output_dir, session_file=session_file)

    cmd = [
        _resolve_tool("yt-dlp"),
        "--write-info-json",
        "--no-playlist",
        "-o", video_path,
    ]
    if cookies_from:
        cmd.extend(["--cookies-from-browser", cookies_from])
    cookie_file = None if cookies_from else _netscape_cookie_file(session_file, output_dir)
    if cookie_file:
        cmd.extend(["--cookies", cookie_file])
    cmd.append(url)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=_DOWNLOAD_TIMEOUT)
    finally:
        if cookie_file and os.path.exists(cookie_file):
            os.remove(cookie_file)
    if result.returncode != 0:
        if downloader == "yt-dlp":
            raise RuntimeError(f"yt-dlp failed: {result.stderr.strip()[-500:]}")
        print("yt-dlp failed, trying Playwright fallback...", file=sys.stderr)
        return _download_via_playwright(url, output_dir, session_file=session_file)

    if not os.path.exists(video_path):
        for f in os.listdir(output_dir):
            if f.endswith(".mp4"):
                video_path = os.path.join(output_dir, f)
                break

    if not os.path.exists(info_path):
        for f in os.listdir(output_dir):
            if f.endswith(".info.json"):
                info_path = os.path.join(output_dir, f)
                break

    metadata = {}
    if os.path.exists(info_path):
        with open(info_path) as fh:
            raw = json.load(fh)
            metadata = {
                "author": raw.get("uploader") or raw.get("channel") or raw.get("uploader_id", "Unknown"),
                "author_handle": raw.get("channel") or raw.get("uploader_id", ""),
                "title": raw.get("title", ""),
                "caption": raw.get("description", ""),
                "view_count": raw.get("view_count"),
                "like_count": raw.get("like_count"),
                "comment_count": raw.get("comment_count"),
                "duration_seconds": raw.get("duration"),
                "upload_date": raw.get("upload_date", ""),
                "url": raw.get("webpage_url", url),
                "hashtags": [t for t in raw.get("tags", []) if isinstance(t, str)],
                "thumbnail": raw.get("thumbnail", ""),
            }

    return video_path, metadata


# ---------------------------------------------------------------------------
# Frame extraction — for visual analysis by vision-capable models
# ---------------------------------------------------------------------------

def extract_frames(video_path: str, output_dir: str, interval: float = 1.0,
                   max_frames: int = 60, quality: int = 75,
                   max_width: int = 1280) -> list:
    """Extract key frames from video at regular intervals using ffmpeg.

    Frames are written as WebP (quality ``quality``) — roughly half the bytes
    of the JPEGs this used to emit, at *higher* fidelity. Falls back to JPEG
    only if the encoder is unavailable.
    """
    frames_dir = os.path.join(output_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    duration = _get_video_duration(video_path)
    if duration <= 0:
        return []
    count = min(max_frames, max(1, int(duration / interval)))
    actual_interval = duration / count if count > 1 else 0
    frame_paths = []
    for i in range(count):
        ts = i * actual_interval
        ts_str = f"{int(ts // 3600):02d}-{int((ts % 3600) // 60):02d}-{ts % 60:06.3f}"
        frame_path = os.path.join(frames_dir, f"frame-{ts_str}.webp")
        scale = ["-vf", f"scale='min({max_width},iw)':-2"] if max_width else []
        cmd = [_resolve_tool("ffmpeg"), "-y", "-ss", str(ts),
               "-i", video_path, "-vframes", "1", *scale,
               "-c:v", "libwebp", "-quality", str(quality), "-compression_level", "6",
               frame_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=_FRAME_TIMEOUT)
        if result.returncode == 0 and os.path.exists(frame_path):
            frame_paths.append({"path": frame_path, "timestamp": ts})
            continue

        # Fallback: JPEG if libwebp is missing from this ffmpeg build.
        frame_path = os.path.join(frames_dir, f"frame-{ts_str}.jpg")
        cmd2 = [_resolve_tool("ffmpeg"), "-y", "-ss", str(ts),
                "-i", video_path, "-vframes", "1", *scale, "-q:v", "10", frame_path]
        result = subprocess.run(cmd2, capture_output=True, text=True, timeout=_FRAME_TIMEOUT)
        if result.returncode == 0 and os.path.exists(frame_path):
            frame_paths.append({"path": frame_path, "timestamp": ts})
    return frame_paths


def _get_video_duration(video_path: str) -> float:
    """Return video duration in seconds via ffprobe, or -1 on failure."""
    cmd = [_resolve_tool("ffprobe"), "-v", "error", "-show_entries",
           "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=_PROBE_TIMEOUT)
    try:
        return float(result.stdout.strip())
    except (ValueError, TypeError):
        return -1.0

# ---------------------------------------------------------------------------
# Audio / transcription / music
# ---------------------------------------------------------------------------

def has_audio_stream(video_path: str) -> bool:
    """Return False when ffprobe confirms the video has no audio track."""
    cmd = [
        _resolve_tool("ffprobe"), "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=index", "-of", "csv=p=0", video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=_PROBE_TIMEOUT)
    if result.returncode != 0:
        return True  # let ffmpeg produce the real error
    return bool(result.stdout.strip())


def extract_audio(video_path: str, output_dir: str) -> str | None:
    """Extract mono 16kHz WAV from video.

    Returns ``None`` for silent videos instead of failing the whole extraction.
    """
    if not has_audio_stream(video_path):
        return None
    audio_path = os.path.join(output_dir, "audio.wav")
    cmd = [
        _resolve_tool("ffmpeg"), "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=_DOWNLOAD_TIMEOUT)
    if result.returncode != 0:
        if "does not contain any stream" in (result.stderr or ""):
            return None
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()}")
    return audio_path


def transcribe(audio_path: str, model_name: str = "base") -> dict:
    """Transcribe audio with Whisper."""
    import whisper
    model = whisper.load_model(model_name)
    result = model.transcribe(audio_path)
    return {
        "text": result["text"].strip(),
        "language": result.get("language", "unknown"),
        "segments": [
            {"start": seg["start"], "end": seg["end"], "text": seg["text"].strip()}
            for seg in result.get("segments", [])
        ],
    }


def identify_music(audio_path: str) -> dict:
    """Identify the music track via Shazam."""
    from shazamio import Shazam
    result = asyncio.run(Shazam().recognize(audio_path))
    track = result.get("track")
    if not track:
        return {}

    album = ""
    for section in track.get("sections", []):
        for meta in section.get("metadata", []):
            if meta.get("title", "").lower() == "album":
                album = meta.get("text", "")
                break
        if album:
            break

    return {
        "title": track.get("title", ""),
        "artist": track.get("subtitle", ""),
        "album": album,
        "genre": track.get("genres", {}).get("primary", ""),
        "shazam_url": track.get("url", ""),
    }


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_output(metadata: dict, transcript: dict, original_url: str = "",
                 music: dict = None, topic: str = "", smart_meta: dict = None,
                 frames: list = None, frames_vault_rel_dir: str = "",
                 classification: str = CLASSIFICATION_PENDING) -> str:
    """Format extraction results as a tagged markdown note."""
    creator = metadata.get("author", "Unknown")
    handle = metadata.get("author_handle") or metadata.get("author_id", "")
    tags = [t.lower().strip() for t in (metadata.get("hashtags") or []) if isinstance(t, str)]
    extracted = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    url_display = original_url or metadata.get("url", "")

    smart_meta = smart_meta or {}
    niche = smart_meta.get("niche") or UNCLASSIFIED
    category = smart_meta.get("category") or UNCLASSIFIED
    industry = smart_meta.get("industry") or UNCLASSIFIED

    frontmatter = {
        "creator": creator,
        "niche": niche,
        "category": category,
        "industry": industry,
        "classification": classification,
        "source": url_display,
        "extracted": extracted,
    }
    sid = source_id(url_display)
    if sid:
        frontmatter["source_id"] = sid
    if handle:
        frontmatter["handle"] = handle
    if topic:
        frontmatter["topic"] = topic
        frontmatter["topics"] = [topic]
    if tags:
        frontmatter["tags"] = tags

    lines = [dump_frontmatter(frontmatter), "# Reel Extraction", ""]
    lines.append(f"**Source:** [{url_display}]({url_display})")
    lines.append(f"**Extracted:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")

    lines += ["## Metadata", ""]
    lines.append(f"- **Creator:** {creator} (@{handle})" if handle else f"- **Creator:** {creator}")
    if topic:
        lines.append(f"- **Topic:** {topic}")
    lines.append(f"- **Niche:** {niche}")
    lines.append(f"- **Category:** {category}")
    lines.append(f"- **Industry:** {industry}")
    lines.append(f"- **Classification:** {classification}")
    if metadata.get("upload_date"):
        d = metadata["upload_date"]
        lines.append(f"- **Upload Date:** {d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else f"- **Upload Date:** {d}")
    if metadata.get("duration_seconds"):
        mins, secs = divmod(int(metadata["duration_seconds"]), 60)
        lines.append(f"- **Duration:** {mins}:{secs:02d}")
    for label, key in (("Views", "view_count"), ("Likes", "like_count"), ("Comments", "comment_count")):
        if metadata.get(key) is not None:
            try:
                lines.append(f"- **{label}:** {int(metadata[key]):,}")
            except (TypeError, ValueError):
                lines.append(f"- **{label}:** {metadata[key]}")
    lines.append("")

    if frames and frames_vault_rel_dir:
        lines += ["## Visual Frames", ""]
        lines.append(f"> *Frames stored in `{frames_vault_rel_dir}/` — load for visual analysis*")
        lines.append("")
        for f in frames:
            ts = f.get("timestamp", 0)
            mins, secs = divmod(int(ts), 60)
            fname = os.path.basename(f["path"])
            lines.append(f"- [{mins:02d}:{secs:02d}] ![[{frames_vault_rel_dir}/{fname}]]")
        lines.append("")

        lines += ["## Key Frame", ""]
        lines.append("After viewing the frames above, identify and mark **one frame** where:")
        lines.append("- Any on-screen text/prompt/code is **fully visible** (no face or hand blocking it)")
        lines.append("- The creator has moved aside to reveal content")
        lines.append("")
        lines.append("Format: `KEY: [mm:ss] — <what is visible on screen>`")
        lines.append("")

    if music:
        lines += ["## Music", ""]
        lines.append(f"- **Song:** {music.get('title', 'Unknown')}")
        lines.append(f"- **Artist:** {music.get('artist', 'Unknown')}")
        if music.get("album"):
            lines.append(f"- **Album:** {music['album']}")
        if music.get("genre"):
            lines.append(f"- **Genre:** {music['genre']}")
        if music.get("shazam_url"):
            lines.append(f"- **Shazam:** [{music['shazam_url']}]({music['shazam_url']})")
        lines.append("")

    if metadata.get("caption"):
        lines += ["## Caption", "", metadata["caption"], ""]
    if tags:
        lines += ["## Hashtags", "", " ".join(f"#{t}" for t in tags), ""]

    lines += ["## Transcript", "",
              f"*Language detected: {transcript.get('language', 'unknown')}*", "",
              transcript.get("text", "(no speech detected)"), ""]

    if transcript.get("segments"):
        lines += ["## Timestamped Transcript", ""]
        for seg in transcript["segments"]:
            mins, secs = divmod(int(seg["start"]), 60)
            lines.append(f"[{mins:02d}:{secs:02d}] {seg['text']}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Shared pipeline
# ---------------------------------------------------------------------------

def _default_smart_meta() -> dict:
    """Classification is intentionally left to the calling AI agent."""
    return {
        "niche": UNCLASSIFIED,
        "category": UNCLASSIFIED,
        "industry": UNCLASSIFIED,
    }


def run_extraction(url: str, whisper_model: str = "base", topic: str = "",
                   no_music: bool = False, no_frames: bool = False,
                   frame_interval: float = 1.0, frame_max_width: int = 1280,
                   cookies_from: str = None, session_file: str = None,
                   downloader: str = "auto", output_dir: str = None,
                   save_dir: str = None, save: bool = True,
                   storage: str = None, log=None) -> dict:
    """Run the full extraction pipeline and optionally save the note.

    This is the single implementation used by both the CLI and the MCP server.
    The AI agent that calls this function is responsible for classification;
    the saved note starts with ``classification: pending``.
    """
    def emit(message: str) -> None:
        if log:
            log(message)

    cfg = load_config()
    if save_dir:
        cfg = dict(cfg)
        cfg.update({"storage": "obsidian", "vault_path": os.path.expanduser(save_dir)})
        manager = StorageManager(cfg, "obsidian")
    else:
        manager = StorageManager(cfg, storage)

    work_dir = output_dir or tempfile.mkdtemp(prefix="reel_")
    own_temp = not output_dir
    emit("Loading cached reel..." if os.path.isfile(url) else "Downloading reel...")

    try:
        video_path, metadata = extract_metadata(
            url, work_dir, cookies_from=cookies_from,
            session_file=session_file, downloader=downloader,
        )
        source = metadata.get("url") or (url if url.startswith(("http://", "https://")) else "")

        emit("Extracting audio...")
        audio_path = extract_audio(video_path, work_dir)
        if audio_path:
            emit(f"Transcribing with Whisper ({whisper_model})...")
            transcript = transcribe(audio_path, whisper_model)
        else:
            emit("No audio track found; saving a visual-only note.")
            transcript = {"text": "", "language": "unknown", "segments": []}

        music = {}
        if audio_path and not no_music:
            emit("Identifying music with Shazam...")
            try:
                music = identify_music(audio_path)
                if music:
                    emit(f"  Found: {music.get('artist')} - {music.get('title')}")
                else:
                    emit("  No music identified (may be speech-only)")
            except Exception as exc:
                emit(f"  Shazam failed: {exc}")

        smart_meta = _default_smart_meta()
        emit("Classification: pending (the AI agent fills this in after extraction)")

        frames = []
        if not no_frames and manager.supports_frames:
            emit("Extracting visual frames...")
            try:
                frames = extract_frames(video_path, work_dir, interval=frame_interval,
                                        max_width=frame_max_width)
                emit(f"  Captured {len(frames)} frames")
            except Exception as exc:
                emit(f"  Frame extraction failed: {exc}")

        base_name = manager.resolve_base(metadata, topic, source)
        frames_rel = ""
        if frames and manager.supports_frames:
            frames_rel = manager.frames_rel_dir(topic, source, base_name)

        note = format_output(
            metadata, transcript, original_url=source or url,
            music=music or None, topic=topic, smart_meta=smart_meta,
            frames=frames, frames_vault_rel_dir=frames_rel,
            classification=CLASSIFICATION_PENDING,
        )

        frontmatter, _ = split_frontmatter(note)

        saved: list[dict] = []
        errors: list[str] = []
        if save and manager.configured_backends():
            result = manager.save(note, frontmatter, metadata, transcript, music,
                                  topic, base_name, frames)
            saved = result["saved"]
            errors = result["errors"]
            for item in saved:
                location = item.get("path") or item.get("url") or item.get("ref")
                emit(f"Saved ({item['backend']}): {location}")
            if frames_rel and any(item.get("backend") == "obsidian" for item in saved):
                for frame in frames:
                    frame["vault_path"] = f"{frames_rel}/{os.path.basename(frame['path'])}"
                    frame.pop("path", None)
            for error in errors:
                emit(f"Warning: {error}")
        elif save:
            errors.append("No storage backend is configured. Run reels-vault-connect.")

        if own_temp:
            for frame in frames:
                frame.pop("path", None)

        return {
            "url": source or url,
            "base_name": base_name,
            "metadata": metadata,
            "transcript": transcript,
            "music": music,
            "smart_meta": smart_meta,
            "classification": CLASSIFICATION_PENDING,
            "note": note,
            "frames": frames,
            "saved": saved,
            "errors": errors,
        }
    finally:
        if own_temp and os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract and save an Instagram Reel to your vault."
    )
    parser.add_argument("--version", action="version", version=f"reels-vault {__version__}")
    parser.add_argument("url", help="Instagram Reel URL or a local cached video")
    parser.add_argument("--whisper-model", default="base",
                        help="Whisper model: tiny, base, small, medium, large (default: base)")
    parser.add_argument("--output-dir", default=None,
                        help="Directory for temporary files (default: system temp)")
    parser.add_argument("--save-dir", default=None,
                        help="Override Obsidian vault location for this run")
    parser.add_argument("--storage", choices=["obsidian", "notion", "both"], default=None,
                        help="Override the configured storage backend")
    parser.add_argument("--topic", default="",
                        help="Topic to file this reel under (e.g. 'content-creation')")
    parser.add_argument("--json", action="store_true",
                        help="Print JSON to stdout (the note is still saved as Markdown)")
    parser.add_argument("--no-save", action="store_true",
                        help="Extract only; do not write to a storage backend")
    parser.add_argument("--no-music", action="store_true",
                        help="Skip Shazam music identification")
    parser.add_argument("--cookies-from", default=None,
                        help="Browser to read cookies from (e.g. chrome, firefox)")
    parser.add_argument("--session-file", default=None,
                        help="Path to an Instagram session file")
    parser.add_argument("--downloader", default="auto",
                        choices=["auto", "yt-dlp", "playwright", "instaloader"],
                        help="How to fetch the reel (default: yt-dlp, Playwright on failure)")
    parser.add_argument("--no-frames", action="store_true",
                        help="Skip frame extraction for visual analysis")
    parser.add_argument("--frame-interval", type=float, default=1.0,
                        help="Seconds between frame captures (default: 1.0)")
    parser.add_argument("--frame-max-width", type=int, default=1280,
                        help="Maximum frame width in pixels (default: 1280)")
    args = parser.parse_args()

    try:
        result = run_extraction(
            args.url, whisper_model=args.whisper_model, topic=args.topic,
            no_music=args.no_music, no_frames=args.no_frames,
            frame_interval=args.frame_interval, frame_max_width=args.frame_max_width,
            cookies_from=args.cookies_from, session_file=args.session_file,
            downloader=args.downloader, output_dir=args.output_dir,
            save_dir=args.save_dir, save=not args.no_save,
            storage=args.storage, log=lambda message: print(message, file=sys.stderr),
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2, default=str, ensure_ascii=False))
    else:
        print(result["note"])
    if result.get("errors"):
        for error in result["errors"]:
            print(f"Warning: {error}", file=sys.stderr)


if __name__ == "__main__":
    main()
