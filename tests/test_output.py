"""Smoke tests for Reels Vault — tests the parts we own (formatting, parsing)."""

from reels_vault.extract import format_output, _slugify
from datetime import datetime, timezone


def test_format_output_has_frontmatter():
    metadata = {
        "author": "Alex Hormozi",
        "author_handle": "hormozi",
        "title": "Test Reel",
        "caption": "A caption",
        "view_count": 44000,
        "like_count": 44000,
        "duration_seconds": 60,
        "hashtags": ["ads", "marketing"],
        "upload_date": "20260204",
    }
    transcript = {
        "text": "Here's the transcript.",
        "language": "en",
        "segments": [{"start": 0.0, "end": 5.0, "text": "Here's the transcript."}],
    }
    output = format_output(metadata, transcript, original_url="https://ig.com/reel/1", topic="content-creation")

    assert "creator: \"Alex Hormozi\"" in output
    assert "handle: hormozi" in output
    assert "topic: content-creation" in output
    assert "tags: [ads, marketing]" in output
    assert "---" in output
    assert "## Transcript" in output
    assert "Here's the transcript." in output
    assert "## Timestamped Transcript" in output
    assert "[00:00]" in output


def test_format_output_minimal():
    metadata = {"author": "Unknown"}
    transcript = {"text": "", "language": "unknown", "segments": []}
    output = format_output(metadata, transcript)
    assert "creator: \"Unknown\"" in output
    assert "## Transcript" in output


def test_slugify():
    assert _slugify("Alex Hormozi") == "alex-hormozi"
    assert _slugify(" Hello   World! ") == "hello-world"
    assert _slugify("") == "unknown"


def test_empty_metadata_doesnt_crash():
    metadata = {"author": "Test", "view_count": None, "like_count": None}
    transcript = {"text": "Hello", "language": "en", "segments": []}
    output = format_output(metadata, transcript)
    assert "Test" in output
    assert "Hello" in output


if __name__ == "__main__":
    test_format_output_has_frontmatter()
    test_format_output_minimal()
    test_slugify()
    test_empty_metadata_doesnt_crash()
    print("✅ All smoke tests passed")
