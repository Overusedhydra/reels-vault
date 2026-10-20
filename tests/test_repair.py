"""Repair/dedupe behavior for existing Obsidian vaults."""

from __future__ import annotations

import json
from pathlib import Path

from reels_vault.notes import CLASSIFICATION_DONE, read_note, render_note, split_frontmatter
from reels_vault.repair import repair


def _note(vault: Path, rel: str, frontmatter: dict, body: str,
          frames: list[str] | None = None) -> Path:
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_note(frontmatter, body), encoding="utf-8")
    if frames:
        directory = path.parent / "frames" / path.stem
        directory.mkdir(parents=True, exist_ok=True)
        for name in frames:
            (directory / name).write_bytes(b"RIFF")
    return path


def test_repair_merges_duplicates_repairs_frames_and_archives(tmp_path):
    vault = tmp_path / "vault"
    source = "https://www.instagram.com/reel/AbC123/"
    common = {
        "creator": "Creator",
        "handle": "creator",
        "source": source,
        "source_id": "AbC123",
    }
    canonical = _note(
        vault,
        "Reels/hooks/reel-a.md",
        {**common, "topic": "hooks", "topics": ["hooks"],
         "classification": CLASSIFICATION_DONE, "niche": "business",
         "category": "tutorial", "industry": "creator-economy",
         "tags": ["hooks"]},
        "# Reel\n\n## Metadata\n\n- **Niche:** business\n\n## Transcript\n\nhello\n\n## My Note\n\nkeep me\n",
    )
    duplicate = _note(
        vault,
        "Reels/business/reel-b.md",
        {**common, "topic": "business", "classification": "pending"},
        "# Reel\n\n## Metadata\n\n- **Niche:** unclassified\n\n## Extra\n\nkeep this too\n",
        frames=["frame-00-00-01.000.webp"],
    )
    _note(vault, "Reels/hooks/_creator-knowledge-base.md", {"creator": "Creator"},
          "# Knowledge\n\nnot a reel\n")
    (vault / "index").mkdir(exist_ok=True)
    (vault / "index" / "business.md").write_text("old index\n", encoding="utf-8")

    dry = repair(str(vault), apply=False)
    assert dry["duplicate_groups"] == 1
    assert dry["duplicate_notes"] == 1
    assert dry["frame_repairs"] >= 1
    assert dry["archive"] == ""
    assert duplicate.is_file()
    assert not (vault / "_archive").exists()

    report = repair(str(vault), apply=True)
    assert report["duplicate_groups"] == 1
    assert report["indexes_rebuilt"] == 1
    assert canonical.is_file()
    assert not duplicate.exists()

    fm, body, _ = read_note(canonical)
    assert fm["source_id"] == "AbC123"
    assert fm["classification"] == CLASSIFICATION_DONE
    assert fm["topic"] == "hooks"
    assert set(fm["topics"]) == {"hooks", "business"}
    assert "keep me" in body and "keep this too" in body
    assert "## Visual Frames" in body
    assert "general/frames" not in body
    assert "Reels/hooks/frames/reel-a/frame-00-00-01.000.webp" in body
    assert (canonical.parent / "frames" / canonical.stem / "frame-00-00-01.000.webp").is_file()
    assert (vault / "_archive").is_dir()
    archive = Path(report["archive"])
    backup = archive / "backup" / "Reels" / "hooks" / "reel-a.md"
    assert backup.is_file()
    assert "keep me" in backup.read_text(encoding="utf-8")
    assert "keep this too" not in backup.read_text(encoding="utf-8")
    assert (archive / "duplicates" / "Reels" / "business" / "reel-b.md").is_file()
    manifest = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["duplicates"][0]["kept"] == "Reels/hooks/reel-a.md"
    assert (vault / "index" / "topics" / "hooks.md").is_file()
    assert (vault / "index" / "niches" / "business.md").is_file()
    assert not (vault / "index" / "business.md").exists()

    again = repair(str(vault), apply=False)
    assert again["duplicate_groups"] == 0
    assert again["frame_repairs"] == 0
    assert again["metadata_updates"] == 0
    assert again["duplicate_stems"] == 0


def test_repair_removes_dead_frame_section(tmp_path):
    vault = tmp_path / "vault"
    note = _note(
        vault,
        "Reels/editing/dead.md",
        {"creator": "Creator", "handle": "creator", "topic": "editing",
         "source": "https://www.instagram.com/reel/Dead1/", "source_id": "Dead1",
         "classification": "pending"},
        "# Reel\n\n## Metadata\n\n- **Niche:** unclassified\n\n"
        "## Visual Frames\n\n- [00:00] ![[general/frames/dead/frame-00-00-01.jpg]]\n",
    )
    report = repair(str(vault), apply=True)
    assert report["frame_repairs"] == 1
    fm, body, _ = read_note(note)
    assert fm["source_id"] == "Dead1"
    assert "## Visual Frames" not in body


def test_repair_source_id_is_case_sensitive(tmp_path):
    vault = tmp_path / "vault"
    _note(vault, "Reels/hooks/a.md",
          {"creator": "A", "handle": "a", "topic": "hooks",
           "source": "https://www.instagram.com/reel/AbC/", "classification": "pending"},
          "# Reel\n")
    _note(vault, "Reels/hooks/b.md",
          {"creator": "B", "handle": "b", "topic": "hooks",
           "source": "https://www.instagram.com/reel/ABC/", "classification": "pending"},
          "# Reel\n")
    report = repair(str(vault), apply=True)
    assert report["duplicate_groups"] == 0
    assert report["notes"] == 2
