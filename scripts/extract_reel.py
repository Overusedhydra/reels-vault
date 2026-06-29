#!/usr/bin/env python3
"""
Reels Vault — Extract transcript and metadata from an Instagram Reel.

Uses yt-dlp to download the video (with Playwright fallback),
openai-whisper to transcribe the audio, and shazamio to identify music.

Usage:
    python3 scripts/extract_reel.py <reel_url> [--whisper-model base] [--save-dir ./extractions]

Dependencies:
    brew install yt-dlp ffmpeg
    pip3 install openai-whisper shazamio playwright
    playwright install chromium
"""

import sys
import os
import json
import argparse
import subprocess
import tempfile
import asyncio
import shutil
from datetime import datetime, timezone


def _download_via_playwright(url: str, output_dir: str) -> tuple:
    """Fallback downloader using Playwright (no Chrome keychain needed)."""
    from playwright.sync_api import sync_playwright

    video_path = os.path.join(output_dir, "reel.mp4")
    metadata = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        )

        # Load saved session cookies if available
        session_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".session", "instagram.json")
        if os.path.exists(session_file):
            try:
                with open(session_file) as f:
                    cookies = json.load(f)
                if cookies:
                    context.add_cookies(cookies)
                    print(f"  Loaded {len(cookies)} session cookies", file=sys.stderr)
            except Exception:
                pass

        page = context.new_page()
        print(f"  Navigating to reel...", file=sys.stderr)
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception:
            pass
        page.wait_for_timeout(5000)

        # Extract video URL from page source using video_versions
        video_url = page.evaluate("""
            () => {
                const html = document.documentElement.innerHTML;
                const vidMatch = html.match(/"video_versions":\\s*(\\[{.*?}\\])/);
                if (vidMatch) {
                    try {
                        const versions = JSON.parse(vidMatch[1]);
                        for (const v of versions) {
                            if (v && v.url && typeof v.url === 'string') {
                                return v.url.replace(/\\\\u0026/g, '&').replace(/\\u0026/g, '&');
                            }
                        }
                    } catch(e) {}
                }
                const m2 = html.match(/"video_url":\\s*"(https:[^"]+)"/);
                if (m2) return m2[1].replace(/\\\\u0026/g, '&').replace(/\\u0026/g, '&');
                return null;
            }
        """)

        if not video_url:
            browser.close()
            raise RuntimeError("Could not extract video URL from page")

        print(f"  Downloading video...", file=sys.stderr)
        import urllib.request
        req = urllib.request.Request(video_url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://www.instagram.com/",
        })
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
        with open(video_path, "wb") as f:
            f.write(data)
        print(f"  Downloaded {len(data):,} bytes", file=sys.stderr)

        # Extract metadata from page
        page_meta = page.evaluate("""
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
        """)
        if page_meta:
            metadata = {
                "author": page_meta.get("title", "").split(" on Instagram")[0].strip(),
                "caption": page_meta.get("description", ""),
                "url": url,
                "title": page_meta.get("title", ""),
            }

        browser.close()

    return video_path, metadata


def extract_metadata(url: str, output_dir: str, cookies_from: str = None) -> dict:
    """Download reel and extract metadata using yt-dlp, with Playwright fallback."""
    video_path = os.path.join(output_dir, "reel.mp4")
    info_path = os.path.join(output_dir, "reel.info.json")

    # Try yt-dlp first
    cmd = [
        "yt-dlp",
        "--write-info-json",
        "--no-playlist",
        "-o", video_path,
    ]
    if cookies_from:
        cmd.extend(["--cookies-from-browser", cookies_from])
    cmd.append(url)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"yt-dlp failed, trying Playwright fallback...", file=sys.stderr)
        return _download_via_playwright(url, output_dir)

    # yt-dlp may name the file slightly differently; find it
    if not os.path.exists(video_path):
        for f in os.listdir(output_dir):
            if f.endswith(".mp4"):
                video_path = os.path.join(output_dir, f)
                break

    # load info json
    metadata = {}
    if not os.path.exists(info_path):
        for f in os.listdir(output_dir):
            if f.endswith(".info.json"):
                info_path = os.path.join(output_dir, f)
                break

    if os.path.exists(info_path):
        with open(info_path) as fh:
            raw = json.load(fh)
            metadata = {
                "author": raw.get("uploader") or raw.get("channel") or raw.get("uploader_id", "Unknown"),
                "author_handle": raw.get("channel") or raw.get("uploader_id", ""),
                "author_id": raw.get("uploader_id") or raw.get("channel_id", ""),
                "title": raw.get("title", ""),
                "caption": raw.get("description", ""),
                "view_count": raw.get("view_count"),
                "like_count": raw.get("like_count"),
                "comment_count": raw.get("comment_count"),
                "duration_seconds": raw.get("duration"),
                "upload_date": raw.get("upload_date", ""),
                "url": raw.get("webpage_url", url),
                "hashtags": raw.get("tags", []),
                "thumbnail": raw.get("thumbnail", ""),
                "comments": [
                    {
                        "author": c.get("author", ""),
                        "text": c.get("text", ""),
                        "like_count": c.get("like_count", 0),
                    }
                    for c in raw.get("comments", [])
                ],
            }

    return video_path, metadata


def extract_audio(video_path: str, output_dir: str) -> str:
    """Extract audio track from video using ffmpeg."""
    audio_path = os.path.join(output_dir, "audio.wav")
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()}")
    return audio_path


async def identify_music(audio_path: str) -> dict:
    """Identify music in the audio using Shazam (via shazamio)."""
    from shazamio import Shazam

    shazam = Shazam()
    result = await shazam.recognize(audio_path)

    track = result.get("track")
    if not track:
        return None

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
        "cover_art": track.get("images", {}).get("coverart", ""),
    }


def transcribe(audio_path: str, model_name: str = "base") -> dict:
    """Transcribe audio using openai-whisper."""
    import whisper

    model = whisper.load_model(model_name)
    result = model.transcribe(audio_path)
    return {
        "text": result["text"].strip(),
        "language": result.get("language", "unknown"),
        "segments": [
            {
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"].strip(),
            }
            for seg in result.get("segments", [])
        ],
    }


def extract_frames(video_path: str, output_dir: str, interval: float = 2.0) -> list:
    """Extract key frames from video at regular intervals using ffmpeg."""
    frames_dir = os.path.join(output_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"fps=1/{interval}",
        "-frame_pts", "1",
        os.path.join(frames_dir, "frame_%04d.jpg"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Frame extraction warning: {result.stderr}", file=sys.stderr)
        return []

    frames = []
    frame_files = sorted(f for f in os.listdir(frames_dir) if f.endswith(".jpg"))
    for i, fname in enumerate(frame_files):
        timestamp = i * interval
        frames.append({
            "timestamp": timestamp,
            "path": os.path.join(frames_dir, fname),
            "filename": fname,
        })

    return frames


def format_output(metadata: dict, transcript: dict, frames: list = None, original_url: str = "", music: dict = None) -> str:
    """Format extraction results as structured text."""
    lines = []
    lines.append("# Instagram Reel Extraction")
    lines.append("")
    url_display = original_url or metadata.get('url', '')
    lines.append(f"**Source:** [{url_display}]({url_display})")
    lines.append(f"**Extracted:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")

    # Metadata
    lines.append("## Metadata")
    lines.append("")
    handle = metadata.get('author_handle') or metadata.get('author_id', '')
    lines.append(f"- **Creator:** {metadata.get('author', 'Unknown')} (@{handle})")
    lines.append(f"- **Original URL:** [{url_display}]({url_display})")
    if metadata.get("upload_date"):
        d = metadata["upload_date"]
        formatted = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d
        lines.append(f"- **Upload Date:** {formatted}")
    if metadata.get("duration_seconds"):
        dur = metadata["duration_seconds"]
        mins, secs = divmod(int(dur), 60)
        lines.append(f"- **Duration:** {mins}:{secs:02d}")
    if metadata.get("view_count") is not None:
        lines.append(f"- **Views:** {metadata['view_count']:,}")
    if metadata.get("like_count") is not None:
        lines.append(f"- **Likes:** {metadata['like_count']:,}")
    if metadata.get("comment_count") is not None:
        lines.append(f"- **Comments:** {metadata['comment_count']:,}")
    lines.append("")

    # Music
    if music:
        lines.append("## Music")
        lines.append("")
        lines.append(f"- **Song:** {music.get('title', 'Unknown')}")
        lines.append(f"- **Artist:** {music.get('artist', 'Unknown')}")
        if music.get("album"):
            lines.append(f"- **Album:** {music['album']}")
        if music.get("genre"):
            lines.append(f"- **Genre:** {music['genre']}")
        if music.get("shazam_url"):
            lines.append(f"- **Shazam:** [{music['shazam_url']}]({music['shazam_url']})")
        lines.append("")

    # Caption
    if metadata.get("caption"):
        lines.append("## Caption")
        lines.append("")
        lines.append(metadata["caption"])
        lines.append("")

    # Hashtags
    if metadata.get("hashtags"):
        lines.append("## Hashtags")
        lines.append("")
        lines.append(" ".join(f"#{tag}" for tag in metadata["hashtags"]))
        lines.append("")

    # Top Comments
    if metadata.get("comments"):
        lines.append("## Top Comments")
        lines.append("")
        lines.append(f"*{len(metadata['comments'])} comments extracted*")
        lines.append("")
        for comment in metadata["comments"]:
            likes = comment.get("like_count", 0)
            likes_str = f" ({likes} likes)" if likes else ""
            lines.append(f"- **@{comment['author']}**{likes_str}: {comment['text']}")
        lines.append("")

    # Transcript
    lines.append("## Transcript")
    lines.append("")
    lines.append(f"*Language detected: {transcript.get('language', 'unknown')}*")
    lines.append("")
    lines.append(transcript.get("text", "(no speech detected)"))
    lines.append("")

    # Timestamped segments
    if transcript.get("segments"):
        lines.append("## Timestamped Transcript")
        lines.append("")
        for seg in transcript["segments"]:
            start = seg["start"]
            mins, secs = divmod(int(start), 60)
            lines.append(f"[{mins:02d}:{secs:02d}] {seg['text']}")
        lines.append("")

    # Frame-by-frame breakdown
    if frames:
        lines.append("## Frame-by-Frame Breakdown")
        lines.append("")
        lines.append(f"*{len(frames)} key frames extracted*")
        lines.append("")
        for frame in frames:
            ts = frame["timestamp"]
            mins, secs = divmod(int(ts), 60)
            lines.append(f"### [{mins:02d}:{secs:02d}] {frame['filename']}")
            lines.append("")
            lines.append(f"![Frame at {mins:02d}:{secs:02d}]({frame['path']})")
            lines.append("")

    return "\n".join(lines)


def save_extraction(output: str, metadata: dict, save_dir: str) -> str:
    """Save extraction markdown to the designated directory."""
    os.makedirs(save_dir, exist_ok=True)

    handle = metadata.get("author_handle") or metadata.get("author", "unknown")
    upload_date = metadata.get("upload_date", "")
    if len(upload_date) == 8:
        upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"

    filename = f"{handle}-reel-{upload_date}.md"
    filepath = os.path.join(save_dir, filename)

    # Avoid overwriting — append a number if file exists
    counter = 2
    while os.path.exists(filepath):
        filename = f"{handle}-reel-{upload_date}-{counter}.md"
        filepath = os.path.join(save_dir, filename)
        counter += 1

    with open(filepath, "w") as f:
        f.write(output)

    return filepath


def main():
    parser = argparse.ArgumentParser(description="Extract transcript and metadata from an Instagram Reel")
    parser.add_argument("url", help="Instagram Reel URL")
    parser.add_argument("--whisper-model", default="base",
                        help="Whisper model size: tiny, base, small, medium, large (default: base)")
    parser.add_argument("--output-dir", default=None,
                        help="Directory for temporary files (default: system temp)")
    parser.add_argument("--save-dir", default=None,
                        help="Directory to save the extraction markdown (e.g., ~/notes/reels)")
    parser.add_argument("--json", action="store_true",
                        help="Output raw JSON instead of formatted text")
    parser.add_argument("--frame-interval", type=float, default=2.0,
                        help="Seconds between extracted frames (default: 2.0)")
    parser.add_argument("--no-frames", action="store_true",
                        help="Skip frame extraction")
    parser.add_argument("--cookies-from", default=None,
                        help="Browser to extract cookies from (e.g., chrome, firefox)")
    args = parser.parse_args()

    work_dir = args.output_dir or tempfile.mkdtemp(prefix="reel_")

    print(f"Downloading reel...", file=sys.stderr)
    video_path, metadata = extract_metadata(args.url, work_dir, cookies_from=args.cookies_from)

    print(f"Extracting audio...", file=sys.stderr)
    audio_path = extract_audio(video_path, work_dir)

    print(f"Transcribing with whisper ({args.whisper_model})...", file=sys.stderr)
    transcript = transcribe(audio_path, args.whisper_model)

    frames = []
    if not args.no_frames:
        print(f"Extracting frames (every {args.frame_interval}s)...", file=sys.stderr)
        frames = extract_frames(video_path, work_dir, args.frame_interval)

    music = None
    print("Identifying music with Shazam...", file=sys.stderr)
    try:
        music = asyncio.run(identify_music(audio_path))
        if music:
            print(f"  Found: {music['artist']} - {music['title']}", file=sys.stderr)
        else:
            print("  No music identified (may be speech-only)", file=sys.stderr)
    except Exception as e:
        print(f"  Shazam failed: {e}", file=sys.stderr)

    if args.json:
        output = json.dumps({"metadata": metadata, "transcript": transcript, "frames": frames, "music": music}, indent=2, default=str)
    else:
        output = format_output(metadata, transcript, frames=frames, original_url=args.url, music=music)

    print(output)

    if args.save_dir:
        save_path = save_extraction(output, metadata, os.path.expanduser(args.save_dir))
        print(f"\nSaved to: {save_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
