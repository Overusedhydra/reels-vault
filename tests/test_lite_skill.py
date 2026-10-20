"""Smoke tests for the low-space skill helper."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "reels-vault-lite" / "scripts" / "reels_vault_lite.py"
SPEC = importlib.util.spec_from_file_location("reels_vault_lite", SCRIPT)
assert SPEC and SPEC.loader
lite = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lite)


def test_frontmatter_round_trip():
    frontmatter = {
        "creator": "ACME: Labs",
        "handle": "@acme:labs",
        "topic": "a: b",
        "tags": ["#ads", "two: words"],
        "source": "https://www.instagram.com/reel/AAA/?x=1&y=2",
        "classification": "pending",
    }
    parsed, body = lite.parse_frontmatter(lite.render_frontmatter(frontmatter) + "\nbody\n")
    assert parsed["creator"] == "ACME: Labs"
    assert parsed["handle"] == "@acme:labs"
    assert parsed["topic"] == "a: b"
    assert parsed["tags"] == ["#ads", "two: words"]
    assert parsed["source"].endswith("?x=1&y=2")
    assert body.strip() == "body"


def test_normalise_metadata_hashtags_and_source_id():
    metadata = lite.normalise_metadata(
        {
            "webpage_url": "https://www.instagram.com/reel/ABC123/",
            "uploader": "Test Creator",
            "uploader_id": "@testcreator",
            "upload_date": "20260101",
            "description": "Hooks #hooks #ads",
            "tags": ["hooks"],
        },
        "https://www.instagram.com/reel/ABC123/",
    )
    assert metadata["source_id"] == "ABC123"
    assert metadata["handle"] == "testcreator"
    assert metadata["tags"] == ["hooks", "ads"]


def test_parse_inline_yaml_list():
    parsed, _ = lite.parse_frontmatter("---\ntags: [ads, marketing]\n---\n")
    assert parsed["tags"] == ["ads", "marketing"]


def test_index_updates_are_idempotent(tmp_path):
    index = tmp_path / "index.md"
    lite.append_unique(index, "header\n", "- [[note]] old-date", "[[note]]")
    lite.append_unique(index, "header\n", "- [[note]] new-date", "[[note]]")
    text = index.read_text(encoding="utf-8")
    assert text.count("[[note]]") == 1
    assert "new-date" in text
    assert "old-date" not in text


def _fake_tools(tmp_path: Path) -> tuple[Path, Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    yt_dlp = bin_dir / "yt-dlp"
    ffmpeg = bin_dir / "ffmpeg"
    nemo = bin_dir / "nemo-speech"
    yt_dlp.write_text(
        """#!/usr/bin/env python3
import json, pathlib, sys
args = sys.argv[1:]
if "--dump-json" in args:
    print(json.dumps({
        "id": "ABC123",
        "webpage_url": "https://www.instagram.com/reel/ABC123/",
        "uploader": "Test Creator",
        "uploader_id": "testcreator",
        "upload_date": "20260101",
        "duration": 5,
        "description": "A test reel about hooks #hooks #ads",
        "tags": ["hooks"],
        "view_count": 1234,
        "like_count": 56,
        "comment_count": 7,
    }))
    raise SystemExit(0)
out = None
for index, arg in enumerate(args):
    if arg == "-o":
        out = args[index + 1]
if not out:
    raise SystemExit("missing -o")
pathlib.Path(out.replace("%(ext)s", "wav")).write_bytes(b"RIFF")
""",
        encoding="utf-8",
    )
    ffmpeg.write_text(
        """#!/usr/bin/env python3
import pathlib, sys
pathlib.Path(sys.argv[-1]).write_bytes(b"RIFF")
""",
        encoding="utf-8",
    )
    nemo.write_text(
        """#!/usr/bin/env python3
import json, pathlib, sys
out = None
for index, arg in enumerate(sys.argv):
    if arg == "--output":
        out = sys.argv[index + 1]
if not out:
    raise SystemExit("missing --output")
pathlib.Path(out).write_text(json.dumps({
    "text": "This is a test transcript about hooks.",
    "languages": ["en"],
    "segments": [{"start": 0, "text": "This is a test transcript about hooks."}],
}))
""",
        encoding="utf-8",
    )
    for path in (yt_dlp, ffmpeg, nemo):
        path.chmod(0o755)
    return yt_dlp, ffmpeg, nemo


def test_configure_uses_reel_vault_subfolder(tmp_path, monkeypatch):
    vault = tmp_path / "Obsidian"
    vault.mkdir()
    (vault / ".obsidian").mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(lite, "full_config_file", lambda: tmp_path / "missing.json")
    monkeypatch.delenv("REELS_VAULT_PATH", raising=False)

    assert lite.main(["configure", "--vault", str(vault)]) == 0
    saved = lite.load_json(lite.config_file())
    assert Path(saved["vault_path"]) == vault / "Reel Vault"
    assert (vault / "Reel Vault" / "Reels").is_dir()


def test_configure_does_not_copy_full_config_secrets(tmp_path, monkeypatch):
    vault = tmp_path / "Obsidian"
    vault.mkdir()
    (vault / ".obsidian").mkdir()
    full = tmp_path / "full.json"
    full.write_text('{"notion":{"token":"secret"},"vault_path":"/old"}', encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(lite, "full_config_file", lambda: full)
    monkeypatch.delenv("REELS_VAULT_PATH", raising=False)

    assert lite.main(["configure", "--vault", str(vault)]) == 0
    saved = lite.load_json(lite.config_file())
    assert "notion" not in saved


def test_save_without_audio_writes_visual_only_note(tmp_path, monkeypatch, capsys):
    yt_dlp, _, _ = _fake_tools(tmp_path)
    silent_ffmpeg = tmp_path / "silent-ffmpeg"
    silent_ffmpeg.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "sys.stderr.write('Output file does not contain any stream\\n')\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )
    silent_ffmpeg.chmod(0o755)
    monkeypatch.setenv("REELS_VAULT_LITE_YTDLP", str(yt_dlp))
    monkeypatch.setenv("REELS_VAULT_LITE_FFMPEG", str(silent_ffmpeg))
    monkeypatch.setenv("NEMO_SPEECH_BIN", str(tmp_path / "missing-nemo"))
    vault = tmp_path / "vault"
    vault.mkdir()

    assert lite.main([
        "save", "https://www.instagram.com/reel/ABC123/",
        "--vault", str(vault), "--topic", "hooks", "--frames", "0", "--json",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["language"] == "unknown"
    assert result["transcript"] == ""
    assert "no speech detected" in (vault / result["ref"]).read_text(encoding="utf-8")


def test_save_classify_resave_and_search(tmp_path, monkeypatch, capsys):
    yt_dlp, ffmpeg, nemo = _fake_tools(tmp_path)
    monkeypatch.setenv("REELS_VAULT_LITE_YTDLP", str(yt_dlp))
    monkeypatch.setenv("REELS_VAULT_LITE_FFMPEG", str(ffmpeg))
    monkeypatch.setenv("NEMO_SPEECH_BIN", str(nemo))
    vault = tmp_path / "vault"
    vault.mkdir()

    assert lite.main(
        [
            "save",
            "https://www.instagram.com/reel/ABC123/",
            "--vault",
            str(vault),
            "--topic",
            "hooks",
            "--json",
        ]
    ) == 0
    result = json.loads(capsys.readouterr().out)
    note = vault / result["ref"]
    assert note.is_file()
    frontmatter, body = lite.read_note(note)
    assert frontmatter["creator"] == "Test Creator"
    assert frontmatter["classification"] == "pending"
    assert frontmatter["source_id"] == "ABC123"
    assert result["language"] == "en"
    assert "This is a test transcript" in body

    assert lite.main(
        [
            "classify",
            result["ref"],
            "--vault",
            str(vault),
            "--niche",
            "business",
            "--category",
            "marketing",
            "--industry",
            "education",
            "--tags",
            "ads,promotion",
        ]
    ) == 0
    frontmatter, body = lite.read_note(note)
    assert frontmatter["classification"] == "classified"
    assert frontmatter["niche"] == "business"
    assert "- **Niche:** business" in body
    assert "promotion" in frontmatter["tags"]
    marker = f"[[{note.stem}]]"
    assert marker not in (vault / "index" / "niches" / "unclassified.md").read_text(encoding="utf-8")
    assert marker in (vault / "index" / "niches" / "business.md").read_text(encoding="utf-8")

    frontmatter, body = lite.read_note(note)
    frontmatter["classification"] = "done"
    note.write_text(lite.render_frontmatter(frontmatter) + "\n" + body, encoding="utf-8")

    assert lite.main(
        [
            "save",
            "https://www.instagram.com/reel/ABC123/",
            "--vault",
            str(vault),
            "--topic",
            "hooks",
            "--json",
        ]
    ) == 0
    capsys.readouterr()
    frontmatter, body = lite.read_note(note)
    assert frontmatter["classification"] == "done"
    assert frontmatter["category"] == "marketing"
    assert "- **Niche:** business" in body
    assert "- **Classification:** done" in body

    assert lite.main(["search", "transcript", "--vault", str(vault), "--json"]) == 0
    results = json.loads(capsys.readouterr().out)
    assert len(results) == 1
    assert results[0]["ref"] == result["ref"]
