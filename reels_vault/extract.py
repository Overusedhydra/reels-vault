#!/usr/bin/env python3
"""
Reels Vault — Extract transcript and metadata from an Instagram Reel.

Pipeline: yt-dlp (download) → ffmpeg (audio) → Whisper (transcript) → Shazam (music).
Smart metadata (niche, category, industry) is auto-detected from content.
Indexes grow in the vault as reels are saved.

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
from pathlib import Path

from reels_vault.config import load_config


# ---------------------------------------------------------------------------
# Smart metadata detection — keyword-based, no API needed
# ---------------------------------------------------------------------------

NICHE_KEYWORDS = {
    "content-creation": ["content", "creator", "reels", "tiktok", "youtube", "instagram", "video", "editing", "camera", "filming"],
    "marketing": ["marketing", "ads", "funnel", "conversion", "brand", "audience", "growth", "traffic", "leads"],
    "copywriting": ["copy", "headline", "hook", "script", "storytelling", "persuasion", "words", "writing"],
    "e-commerce": ["shopify", "product", "store", "dropshipping", "ecommerce", "sales", "checkout", "cart"],
    "finance": ["investing", "stocks", "crypto", "money", "wealth", "budget", "savings", "income", "passive"],
    "fitness": ["workout", "gym", "muscle", "diet", "nutrition", "training", "protein", "exercise", "health"],
    "ai-tools": ["ai", "chatgpt", "automation", "workflow", "tool", "software", "productivity", "prompt"],
    "personal-brand": ["personal brand", "authority", "influence", "following", "audience", "niche", "monetize"],
    "mindset": ["mindset", "motivation", "discipline", "habits", "goals", "success", "failure", "growth mindset"],
    "sales": ["selling", "close", "objection", "pitch", "deal", "revenue", "client", "prospect", "outbound"],
}

CATEGORY_KEYWORDS = {
    "tutorial": ["how to", "step by step", "tutorial", "guide", "learn", "teach", "explain", "walkthrough"],
    "tip": ["tip", "trick", "hack", "secret", "quick", "easy", "simple", "fast"],
    "story": ["story", "journey", "started", "began", "experience", "lesson", "mistake", "failed"],
    "rant": ["everyone", "nobody", "stop", "why do", "truth is", "real talk", "unpopular opinion"],
    "listicle": ["top", "best", "worst", "things", "ways", "reasons", "things to", "rules"],
    "case-study": ["case study", "result", "before and after", "exactly how", "generated", "made"],
}

INDUSTRY_KEYWORDS = {
    "saas": ["saas", "software", "subscription", "mrr", "arr", "churn", "trial", "freemium"],
    "agency": ["agency", "client", "retainer", "service", "consulting", "freelance"],
    "ecommerce": ["shopify", "ecommerce", "e-commerce", "dropshipping", "product", "fulfillment"],
    "creator-economy": ["creator", "influencer", "sponsor", "brand deal", "monetize", "audience"],
    "health-wellness": ["health", "wellness", "supplement", "fitness", "nutrition", "mental health"],
    "real-estate": ["real estate", "property", "rental", "mortgage", "flip", "housing"],
    "education": ["course", "teach", "learn", "student", "education", "coaching", "mentor"],
    "crypto-web3": ["crypto", "web3", "nft", "blockchain", "defi", "bitcoin", "ethereum"],
}


def detect_metadata(text: str) -> dict:
    """Analyze text and detect niche, category, industry from keywords."""
    text_lower = text.lower()
    scores = {}

    # Detect niche
    for niche, keywords in NICHE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[niche] = score
    niche = max(scores, key=scores.get) if scores else "general"

    # Detect category
    scores = {}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[cat] = score
    category = max(scores, key=scores.get) if scores else "general"

    # Detect industry
    scores = {}
    for ind, keywords in INDUSTRY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[ind] = score
    industry = max(scores, key=scores.get) if scores else "general"

    return {"niche": niche, "category": category, "industry": industry}


# ---------------------------------------------------------------------------
# Tool resolution
# ---------------------------------------------------------------------------

def _resolve_tool(name: str) -> str:
    """Find a CLI tool, preferring the one installed in this Python's env."""
    venv_bin = os.path.join(os.path.dirname(sys.executable), name)
    if os.path.exists(venv_bin):
        return venv_bin
    return name


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def _download_via_playwright(url: str, output_dir: str, session_file: str = None) -> tuple:
    """Fallback downloader using Playwright."""
    from playwright.sync_api import sync_playwright

    video_path = os.path.join(output_dir, "reel.mp4")
    metadata = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        )

        if session_file and os.path.exists(session_file):
            try:
                with open(session_file) as f:
                    cookies = json.load(f)
                if cookies:
                    context.add_cookies(cookies)
            except Exception:
                pass

        page = context.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception:
            pass
        page.wait_for_timeout(5000)

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

        import urllib.request
        req = urllib.request.Request(video_url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://www.instagram.com/",
        })
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
        with open(video_path, "wb") as f:
            f.write(data)

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


def extract_metadata(url: str, output_dir: str, cookies_from: str = None, session_file: str = None) -> tuple:
    """Download reel and extract metadata using yt-dlp, with Playwright fallback."""
    video_path = os.path.join(output_dir, "reel.mp4")
    info_path = os.path.join(output_dir, "reel.info.json")

    cmd = [
        _resolve_tool("yt-dlp"),
        "--write-info-json",
        "--no-playlist",
        "-o", video_path,
    ]
    if cookies_from:
        cmd.extend(["--cookies-from-browser", cookies_from])
    cmd.append(url)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
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
# Audio / transcription / music
# ---------------------------------------------------------------------------

def extract_audio(video_path: str, output_dir: str) -> str:
    """Extract mono 16kHz WAV from video using ffmpeg."""
    audio_path = os.path.join(output_dir, "audio.wav")
    cmd = [
        _resolve_tool("ffmpeg"), "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
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

def _slugify(value: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", str(value).lower()).strip()
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug or "unknown"


def format_output(metadata: dict, transcript: dict, original_url: str = "",
                 music: dict = None, topic: str = "", smart_meta: dict = None) -> str:
    """Format extraction results as a tagged markdown note."""
    creator = metadata.get("author", "Unknown")
    handle = metadata.get("author_handle") or metadata.get("author_id", "")
    tags = [t.lower().strip() for t in metadata.get("hashtags", []) if isinstance(t, str)]
    extracted = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    url_display = original_url or metadata.get("url", "")

    # Smart metadata
    niche = smart_meta.get("niche", "general") if smart_meta else "general"
    category = smart_meta.get("category", "general") if smart_meta else "general"
    industry = smart_meta.get("industry", "general") if smart_meta else "general"

    # Frontmatter
    fm = ["---"]
    fm.append(f'creator: "{creator}"')
    if handle:
        fm.append(f"handle: {handle}")
    if topic:
        fm.append(f"topic: {topic}")
    fm.append(f"niche: {niche}")
    fm.append(f"category: {category}")
    fm.append(f"industry: {industry}")
    if tags:
        fm.append(f"tags: [{', '.join(tags)}]")
    fm.append(f"source: {url_display}")
    fm.append(f"extracted: {extracted}")
    fm.append("---")

    lines = list(fm)
    lines += ["", "# Reel Extraction", ""]
    lines.append(f"**Source:** [{url_display}]({url_display})")
    lines.append(f"**Extracted:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")

    # Metadata
    lines += ["## Metadata", ""]
    lines.append(f"- **Creator:** {creator} (@{handle})" if handle else f"- **Creator:** {creator}")
    lines.append(f"- **Niche:** {niche}")
    lines.append(f"- **Category:** {category}")
    lines.append(f"- **Industry:** {industry}")
    if metadata.get("upload_date"):
        d = metadata["upload_date"]
        lines.append(f"- **Upload Date:** {d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else f"- **Upload Date:** {d}")
    if metadata.get("duration_seconds"):
        mins, secs = divmod(int(metadata["duration_seconds"]), 60)
        lines.append(f"- **Duration:** {mins}:{secs:02d}")
    for label, key in (("Views", "view_count"), ("Likes", "like_count"), ("Comments", "comment_count")):
        if metadata.get(key) is not None:
            lines.append(f"- **{label}:** {metadata[key]:,}")
    lines.append("")

    # Music
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

    # Caption + hashtags
    if metadata.get("caption"):
        lines += ["## Caption", "", metadata["caption"], ""]
    if tags:
        lines += ["## Hashtags", "", " ".join(f"#{t}" for t in tags), ""]

    # Transcript
    lines += ["## Transcript", "",
              f"*Language detected: {transcript.get('language', 'unknown')}*", "",
              transcript.get("text", "(no speech detected)"), ""]

    # Timestamped segments
    if transcript.get("segments"):
        lines += ["## Timestamped Transcript", ""]
        for seg in transcript["segments"]:
            mins, secs = divmod(int(seg["start"]), 60)
            lines.append(f"[{mins:02d}:{secs:02d}] {seg['text']}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Index building — grows as reels are saved
# ---------------------------------------------------------------------------

def _update_indexes(vault_path: str, metadata: dict, smart_meta: dict, topic: str):
    """Append this reel's entry to the vault's index files."""
    index_dir = os.path.join(vault_path, "index")
    os.makedirs(index_dir, exist_ok=True)

    creator = metadata.get("author", "Unknown")
    handle = metadata.get("author_handle", "")
    niche = smart_meta.get("niche", "general")
    category = smart_meta.get("category", "general")
    industry = smart_meta.get("industry", "general")
    extracted = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    url = metadata.get("url", "")
    slug = _slugify(metadata.get("author_handle") or creator)

    entry = f"- [[{slug}-reel-*]] — {creator} ({topic}) — {extracted}"

    # Update niche index
    niche_file = os.path.join(index_dir, f"{niche}.md")
    if not os.path.exists(niche_file):
        with open(niche_file, "w") as f:
            f.write(f"---\ntags: [index, niche]\n---\n\n# {niche.title()}\n\n")
    with open(niche_file, "a") as f:
        f.write(entry + "\n")

    # Update category index
    cat_file = os.path.join(index_dir, f"{category}.md")
    if not os.path.exists(cat_file):
        with open(cat_file, "w") as f:
            f.write(f"---\ntags: [index, category]\n---\n\n# {category.title()}\n\n")
    with open(cat_file, "a") as f:
        f.write(entry + "\n")

    # Update industry index
    ind_file = os.path.join(index_dir, f"{industry}.md")
    if not os.path.exists(ind_file):
        with open(ind_file, "w") as f:
            f.write(f"---\ntags: [index, industry]\n---\n\n# {industry.title()}\n\n")
    with open(ind_file, "a") as f:
        f.write(entry + "\n")

    # Update creator index
    creators_dir = os.path.join(vault_path, "creators")
    os.makedirs(creators_dir, exist_ok=True)
    creator_file = os.path.join(creators_dir, f"{slug}.md")
    if not os.path.exists(creator_file):
        with open(creator_file, "w") as f:
            f.write(f"---\ntags: [creator]\n---\n\n# {creator}\n\n")
    with open(creator_file, "a") as f:
        f.write(f"- [[{slug}-reel-*]] ({topic}) — {extracted}\n")

    # Update main index
    main_index = os.path.join(vault_path, "Index.md")
    if os.path.exists(main_index):
        with open(main_index) as f:
            content = f.read()
        # Add to "All Reels" dataview if not already there
        if f'"{niche}"' not in content:
            pass  # dataview handles this automatically


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save_extraction(output: str, metadata: dict, save_dir: str, topic: str = "") -> str:
    """Save the reel into <save-dir>/<topic>/ as a tagged markdown note."""
    target_dir = os.path.join(save_dir, _slugify(topic)) if topic else save_dir
    os.makedirs(target_dir, exist_ok=True)

    handle = _slugify(metadata.get("author_handle") or metadata.get("author", "unknown"))
    upload_date = metadata.get("upload_date", "")
    if len(upload_date) == 8:
        upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
    if not upload_date:
        upload_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    filepath = os.path.join(target_dir, f"{handle}-reel-{upload_date}.md")
    counter = 2
    while os.path.exists(filepath):
        filepath = os.path.join(target_dir, f"{handle}-reel-{upload_date}-{counter}.md")
        counter += 1

    with open(filepath, "w") as f:
        f.write(output)
    return filepath


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract and save an Instagram Reel to your vault."
    )
    parser.add_argument("url", help="Instagram Reel URL")
    parser.add_argument("--whisper-model", default="base",
                        help="Whisper model: tiny, base, small, medium, large (default: base)")
    parser.add_argument("--output-dir", default=None,
                        help="Directory for temporary files (default: system temp)")
    parser.add_argument("--save-dir", default=None,
                        help="Override vault location (default: your connected vault)")
    parser.add_argument("--topic", default=None,
                        help="Topic to file this reel under (e.g. 'content-creation')")
    parser.add_argument("--json", action="store_true",
                        help="Output raw JSON instead of markdown")
    parser.add_argument("--no-music", action="store_true",
                        help="Skip Shazam music identification")
    parser.add_argument("--cookies-from", default=None,
                        help="Browser to read cookies from (e.g. chrome, firefox)")
    parser.add_argument("--session-file", default=None,
                        help="Path to Instagram session cookies JSON")
    args = parser.parse_args()

    work_dir = args.output_dir or tempfile.mkdtemp(prefix="reel_")
    own_temp = not args.output_dir

    try:
        print("Downloading reel...", file=sys.stderr)
        video_path, metadata = extract_metadata(args.url, work_dir, cookies_from=args.cookies_from, session_file=args.session_file)

        print("Extracting audio...", file=sys.stderr)
        audio_path = extract_audio(video_path, work_dir)

        print(f"Transcribing with Whisper ({args.whisper_model})...", file=sys.stderr)
        transcript = transcribe(audio_path, args.whisper_model)

        music = {}
        if not args.no_music:
            print("Identifying music with Shazam...", file=sys.stderr)
            try:
                music = identify_music(audio_path)
                if music:
                    print(f"  Found: {music.get('artist')} - {music.get('title')}", file=sys.stderr)
                else:
                    print("  No music identified (may be speech-only)", file=sys.stderr)
            except Exception as e:
                print(f"  Shazam failed: {e}", file=sys.stderr)

        # Smart metadata detection from transcript + caption
        analyze_text = " ".join([
            metadata.get("caption", ""),
            metadata.get("title", ""),
            transcript.get("text", ""),
            " ".join(metadata.get("hashtags", [])),
        ])
        smart_meta = detect_metadata(analyze_text)
        print(f"  Detected: niche={smart_meta['niche']}, category={smart_meta['category']}, industry={smart_meta['industry']}", file=sys.stderr)

        if args.json:
            output = json.dumps(
                {"metadata": metadata, "transcript": transcript, "music": music, "smart_meta": smart_meta},
                indent=2, default=str,
            )
        else:
            output = format_output(metadata, transcript,
                                   original_url=args.url, music=music or None,
                                   topic=args.topic or "", smart_meta=smart_meta)

        print(output)

        # Determine save location
        save_dir = args.save_dir
        if not save_dir:
            try:
                connected = load_config().get("vault_path", "")
                if connected and os.path.isdir(connected):
                    save_dir = connected
            except Exception:
                pass

        if save_dir:
            save_path = save_extraction(output, metadata,
                                        os.path.expanduser(save_dir), topic=args.topic or "")
            # Build indexes
            _update_indexes(os.path.expanduser(save_dir), metadata, smart_meta, args.topic or "")
            where = f" under topic '{args.topic}'" if args.topic else ""
            print(f"\nSaved to vault{where}:\n  {save_path}", file=sys.stderr)
        elif not args.json:
            print("\n(Tip: run reels-vault-connect once to auto-file reels into your "
                  "Obsidian vault.)", file=sys.stderr)

    finally:
        if own_temp and os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
