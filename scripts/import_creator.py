#!/usr/bin/env python3
"""Import recent reels from an Instagram creator username."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

if __package__:
    from . import config as config_mod
    from .bulk_import import existing_in_vault, reel_id
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import config as config_mod
    from bulk_import import existing_in_vault, reel_id


def clean_username(value: str) -> str:
    """Accept @name, profile URL, or raw username."""
    value = value.strip()
    match = re.search(r"instagram\.com/([^/?#]+)/?", value)
    if match:
        value = match.group(1)
    return value.lstrip("@").strip("/")


def load_session(loader, session_file: str) -> None:
    if not session_file:
        return
    path = Path(os.path.expanduser(session_file))
    try:
        if path.read_bytes()[:1] != b"\x80":
            raise SystemExit(f"Not an instaloader session file: {path}")
    except OSError as exc:
        raise SystemExit(f"Cannot read session file {path}: {exc}") from exc
    loader.load_session_from_file("", filename=str(path))


def creator_reel_urls(username: str, limit: int, max_scan: int,
                      session_file: str = "") -> list[str]:
    try:
        import instaloader
    except ImportError as exc:
        raise SystemExit("instaloader is not installed. Run: pip install -e .") from exc

    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
    )
    load_session(loader, session_file)
    profile = instaloader.Profile.from_username(loader.context, username)

    urls = []
    for scanned, post in enumerate(profile.get_posts(), 1):
        if scanned > max_scan or len(urls) >= limit:
            break
        if post.is_video:
            urls.append(f"https://www.instagram.com/reel/{post.shortcode}/")
    return urls


def default_topic(username: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", username.lower()).strip("-") or "instagram"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find recent reels from a creator and optionally import them."
    )
    parser.add_argument("creator", help="Instagram username, @handle, or profile URL")
    parser.add_argument("--limit", type=int, default=25,
                        help="How many video posts to collect (default: 25)")
    parser.add_argument("--max-scan", type=int, default=200,
                        help="How many recent posts to inspect while looking for reels")
    parser.add_argument("--topic", default="",
                        help="Topic folder (default: creator username)")
    parser.add_argument("--output", default="",
                        help="Write URL list here (default: cache file)")
    parser.add_argument("--session-file", default="",
                        help="Instaloader session (default: config sessions.instaloader)")
    parser.add_argument("--storage", choices=["obsidian", "notion", "both"], default=None)
    parser.add_argument("--import", dest="run_import", action="store_true",
                        help="Immediately run bulk_import.py on the collected URLs")
    parser.add_argument("--download-only", action="store_true",
                        help="Pass --download-only to bulk_import.py")
    parser.add_argument("--process-only", action="store_true",
                        help="Pass --process-only to bulk_import.py")
    parser.add_argument("--no-music", action="store_true")
    parser.add_argument("--no-frames", action="store_true")
    parser.add_argument("--whisper-model", default="base")
    parser.add_argument("--delay", type=float, default=3.0)
    args = parser.parse_args()

    cfg = config_mod.load_config()
    storage = args.storage or config_mod.storage_backend(cfg)
    username = clean_username(args.creator)
    topic = args.topic or default_topic(username)
    out = Path(args.output or f"~/.cache/reels-vault/creators/{username}.txt").expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    session_file = args.session_file or config_mod.session_paths(cfg)["instaloader"]
    urls = creator_reel_urls(username, args.limit, args.max_scan, session_file)

    vault = config_mod.vault_path(cfg) if storage in ("obsidian", "both") else ""
    if vault and os.path.isdir(vault):
        already = existing_in_vault(vault)
        urls = [url for url in urls if reel_id(url) not in already]

    out.write_text("\n".join(urls) + ("\n" if urls else ""), encoding="utf-8")
    print(f"{len(urls)} reel URL(s) written to {out}")
    if not args.run_import or not urls:
        return

    script = Path(__file__).with_name("bulk_import.py")
    cmd = [
        sys.executable, str(script), str(out), "--topic", topic,
        "--whisper-model", args.whisper_model, "--delay", str(args.delay),
        "--storage", storage,
    ]
    if args.download_only:
        cmd.append("--download-only")
    if args.process_only:
        cmd.append("--process-only")
    if args.no_music:
        cmd.append("--no-music")
    if args.no_frames:
        cmd.append("--no-frames")
    raise SystemExit(subprocess.run(cmd).returncode)


if __name__ == "__main__":
    main()
