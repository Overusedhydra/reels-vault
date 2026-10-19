#!/usr/bin/env python3
"""Bulk-import Instagram Reel URLs into the configured storage backend.

Two phases: one shared Playwright browser downloads every reel into a local
cache, then each cached file is run through extract_reel.py offline (Whisper,
Shazam, frames, save).  The child process reads the same config, so it writes
to Obsidian, Notion, or both without duplicating that logic here.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

if __package__:
    from . import config as config_mod
    from .extract_reel import _IG_UA, _download_via_playwright, _load_playwright_cookies
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import config as config_mod
    from extract_reel import _IG_UA, _download_via_playwright, _load_playwright_cookies

REEL_ID_RE = re.compile(r"instagram\.com/(?:[\w.-]+/)?(?:reel|reels|p)/([A-Za-z0-9_-]+)")
URL_RE = re.compile(
    r"https?://(?:[\w.-]+\.)?instagram\.com/(?:[\w.-]+/)*(?:reel|reels|p)/[A-Za-z0-9_-]+/?"
)


def read_urls(source: str) -> list[str]:
    """Accept a path to a file of URLs, or raw URL arguments."""
    urls, seen = [], set()
    text = Path(source).read_text(encoding="utf-8") if os.path.isfile(source) else source
    for match in URL_RE.finditer(text):
        url = match.group(0)
        rid = reel_id(url)
        if rid not in seen:
            seen.add(rid)
            urls.append(url)
    return urls


def reel_id(url: str) -> str:
    match = REEL_ID_RE.search(url)
    return match.group(1) if match else url


def existing_in_vault(vault: str) -> set[str]:
    """Reel IDs already saved in an Obsidian vault."""
    found: set[str] = set()
    root = Path(vault)
    if not root.is_dir():
        return found
    for md in root.rglob("*.md"):
        try:
            text = md.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in REEL_ID_RE.finditer(text):
            found.add(match.group(1))
    return found


def download_all(urls: list[str], cache_dir: str, session_file: str, delay: float) -> list[str]:
    """Download every uncached reel through one shared browser."""
    from playwright.sync_api import sync_playwright

    os.makedirs(cache_dir, exist_ok=True)
    todo = [u for u in urls if not os.path.isfile(os.path.join(cache_dir, f"{reel_id(u)}.mp4"))]
    print(f"Download phase: {len(todo)} to fetch, {len(urls) - len(todo)} already cached",
          file=sys.stderr)
    if not todo:
        return []

    failures: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=_IG_UA)
        cookies = _load_playwright_cookies(session_file)
        if cookies:
            context.add_cookies(cookies)
        try:
            for i, url in enumerate(todo, 1):
                rid = reel_id(url)
                target = os.path.join(cache_dir, f"{rid}.mp4")
                print(f"[{i}/{len(todo)}] {rid}", file=sys.stderr, end="", flush=True)
                try:
                    video_path, metadata = _download_via_playwright(url, cache_dir, context=context)
                    if os.path.isfile(video_path) and video_path != target:
                        if os.path.isfile(target):
                            os.remove(target)
                        os.rename(video_path, target)
                    metadata["url"] = url
                    with open(os.path.join(cache_dir, f"{rid}.json"), "w", encoding="utf-8") as fh:
                        json.dump(metadata, fh, indent=2, default=str, ensure_ascii=False)
                    print(f" ok ({os.path.getsize(target) // 1024} KB, "
                          f"{metadata.get('author_handle') or metadata.get('author')})",
                          file=sys.stderr)
                except Exception as exc:
                    print(f" FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
                    failures.append(url)
                    for junk in ("reel.mp4", "reel.info.json"):
                        path = os.path.join(cache_dir, junk)
                        if os.path.isfile(path):
                            os.remove(path)
                if i < len(todo) and delay:
                    time.sleep(delay)
        finally:
            browser.close()
    return failures


def process_all(urls: list[str], cache_dir: str, topic: str, args,
                vault: str = "") -> tuple[int, int, int, list[str]]:
    """Run the full extraction pipeline for each cached reel."""
    done = skipped = failed = 0
    failures: list[str] = []
    already = existing_in_vault(vault) if vault else set()
    todo = []
    for url in urls:
        rid = reel_id(url)
        if rid in already:
            skipped += 1
            continue
        if not os.path.isfile(os.path.join(cache_dir, f"{rid}.mp4")):
            print(f"[skip] {rid}: not cached", file=sys.stderr)
            failed += 1
            failures.append(url)
            continue
        todo.append(url)

    print(f"Process phase: {len(todo)} to extract, {skipped} already stored", file=sys.stderr)
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extract_reel.py")
    for i, url in enumerate(todo, 1):
        rid = reel_id(url)
        mp4 = os.path.join(cache_dir, f"{rid}.mp4")
        print(f"[{i}/{len(todo)}] {rid}", file=sys.stderr, end="", flush=True)
        cmd = [sys.executable, script, mp4, "--topic", topic,
               "--whisper-model", args.whisper_model, "--downloader", "auto"]
        if args.storage:
            cmd += ["--storage", args.storage]
        if args.no_music:
            cmd.append("--no-music")
        if args.no_frames:
            cmd.append("--no-frames")
        elif args.frame_interval != 1.0:
            cmd += ["--frame-interval", str(args.frame_interval)]
        started = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                                errors="replace")
        if result.returncode != 0:
            tail = (result.stderr or "").strip().splitlines()[-3:]
            print(f" FAIL after {time.time()-started:.0f}s: {' | '.join(tail)}", file=sys.stderr)
            failed += 1
            failures.append(url)
        else:
            print(f" ok ({time.time()-started:.0f}s)", file=sys.stderr)
            done += 1
    return done, skipped, failed, failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk-import Instagram reels into storage.")
    parser.add_argument("source", help="File of reel URLs, or raw URLs separated by spaces")
    parser.add_argument("--topic", required=True, help="Topic folder (e.g. agentic-ai)")
    parser.add_argument("--cache-dir", default=os.path.expanduser("~/.cache/reels-vault/bulk"))
    parser.add_argument("--whisper-model", default="base")
    parser.add_argument("--session-file", default="",
                        help="Playwright storage_state JSON (default: config sessions.playwright)")
    parser.add_argument("--storage", choices=["obsidian", "notion", "both"], default=None)
    parser.add_argument("--delay", type=float, default=3.0,
                        help="Seconds between downloads (default: 3)")
    parser.add_argument("--frame-interval", type=float, default=1.0)
    parser.add_argument("--no-music", action="store_true")
    parser.add_argument("--no-frames", action="store_true")
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--process-only", action="store_true")
    args = parser.parse_args()

    cfg = config_mod.load_config()
    storage = args.storage or config_mod.storage_backend(cfg)
    vault = config_mod.vault_path(cfg) if storage in ("obsidian", "both") else ""
    if storage in ("obsidian", "both") and (not vault or not os.path.isdir(vault)):
        sys.exit("Obsidian is not connected. Run scripts/connect.py first.")
    session_file = args.session_file or config_mod.session_paths(cfg)["playwright"]

    urls = read_urls(args.source)
    if not urls:
        sys.exit("No Instagram reel URLs found in input.")
    print(f"{len(urls)} unique reels | topic '{args.topic}' | storage {storage}", file=sys.stderr)

    failures: list[str] = []
    if not args.process_only:
        failures += download_all(urls, args.cache_dir, session_file, args.delay)
    if args.download_only:
        print(f"Download done. {len(failures)} failed.", file=sys.stderr)
        for url in failures:
            print(f"  {url}", file=sys.stderr)
        return

    done, skipped, failed, process_failures = process_all(
        urls, args.cache_dir, args.topic, args, vault,
    )
    failures += process_failures
    print(f"\nDone: {done} extracted, {skipped} already stored, {failed} failed.",
          file=sys.stderr)
    if failures:
        print("Failed URLs (re-run with --process-only after fixing):", file=sys.stderr)
        for url in failures:
            print(f"  {url}", file=sys.stderr)


if __name__ == "__main__":
    main()
