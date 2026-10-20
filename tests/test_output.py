"""Smoke tests for the parts we own: formatting, parsing, and Obsidian storage."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from reels_vault.extract import format_output  # noqa: E402
from reels_vault.notes import (  # noqa: E402
    CLASSIFICATION_DONE,
    CLASSIFICATION_PENDING,
    dump_frontmatter,
    slugify,
    split_frontmatter,
    source_id,
    update_note_metadata,
)
from reels_vault.storage import StorageManager, StorageError  # noqa: E402


def _metadata(**overrides):
    data = {
        "author": "Alex Hormozi",
        "author_handle": "hormozi",
        "title": "Test Reel",
        "caption": "A caption",
        "view_count": 44000,
        "like_count": 44000,
        "duration_seconds": 60,
        "hashtags": ["ads", "marketing"],
        "upload_date": "20260204",
        "url": "https://www.instagram.com/reel/AAA/",
    }
    data.update(overrides)
    return data


def _transcript(text="Here's the transcript."):
    return {
        "text": text,
        "language": "en",
        "segments": [{"start": 0.0, "end": 5.0, "text": text}],
    }


def _save(manager, source="https://www.instagram.com/reel/AAA/", topic="content-creation",
          **metadata_overrides):
    metadata = _metadata(url=source, **metadata_overrides)
    note = format_output(metadata, _transcript(), original_url=source, topic=topic)
    frontmatter, _ = split_frontmatter(note)
    base = manager.resolve_base(metadata, topic, source)
    manager.save(note, frontmatter, metadata, _transcript(), {}, topic, base)
    return base, frontmatter, metadata


def test_format_output_has_valid_frontmatter():
    output = format_output(_metadata(), _transcript(), original_url="https://www.instagram.com/reel/AAA/",
                           topic="content-creation")
    frontmatter, body = split_frontmatter(output)

    assert frontmatter["creator"] == "Alex Hormozi"
    assert frontmatter["handle"] == "hormozi"
    assert frontmatter["topic"] == "content-creation"
    assert frontmatter["tags"] == ["ads", "marketing"]
    assert frontmatter["classification"] == CLASSIFICATION_PENDING
    assert frontmatter["source_id"] == "AAA"
    assert "## Transcript" in body
    assert "Here's the transcript." in body
    assert "## Timestamped Transcript" in body
    assert "[00:00]" in body


def test_format_output_minimal():
    output = format_output({"author": "Unknown"}, {"text": "", "language": "unknown",
                                                    "segments": []})
    frontmatter, body = split_frontmatter(output)
    assert frontmatter["creator"] == "Unknown"
    assert frontmatter["niche"] == "unclassified"
    assert "## Transcript" in body


def test_yaml_survives_colons_quotes_and_at_signs():
    raw = dump_frontmatter({
        "creator": "ACME: Labs",
        "handle": "@acme:labs",
        "topic": "a: b",
        "tags": ["#ads", "two: words"],
        "source": "https://www.instagram.com/reel/AAA/?x=1&y=2",
    })
    parsed, _ = split_frontmatter(raw + "\nbody")
    assert parsed["creator"] == "ACME: Labs"
    assert parsed["handle"] == "@acme:labs"
    assert parsed["topic"] == "a: b"
    assert parsed["tags"] == ["#ads", "two: words"]
    assert parsed["source"].endswith("?x=1&y=2")


def test_invalid_frontmatter_is_ignored():
    assert split_frontmatter("no frontmatter") == ({}, "no frontmatter")
    parsed, body = split_frontmatter("---\n: bad: yaml\n---\nbody")
    assert parsed == {}
    assert body == "body"


def test_slugify():
    assert slugify("Alex Hormozi") == "alex-hormozi"
    assert slugify(" Hello   World! ") == "hello-world"
    assert slugify("") == "unknown"


def test_obsidian_save_search_update_and_read():
    with tempfile.TemporaryDirectory() as tmp:
        manager = StorageManager({"vault_path": tmp, "storage": "obsidian"}, "obsidian")
        base, frontmatter, metadata = _save(manager)

        path = Path(tmp) / "Reels" / "content-creation" / f"{base}.md"
        assert path.is_file()
        assert (Path(tmp) / "Creators" / "hormozi.md").is_file()
        assert (Path(tmp) / "Index.md").is_file()

        hits = manager.search(query="transcript")
        assert len(hits) == 1
        assert hits[0]["source"] == metadata["url"]

        ref = hits[0]["ref"]
        assert manager.obsidian.source_for(ref) == metadata["url"]
        manager.update_metadata(ref, {"classification": CLASSIFICATION_DONE,
                                      "niche": "business"})
        updated, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        assert updated["classification"] == CLASSIFICATION_DONE
        assert updated["niche"] == "business"
        assert "**Niche:** business" in manager.read(ref)


def test_resave_preserves_classification_and_cross_topic_identity():
    with tempfile.TemporaryDirectory() as tmp:
        manager = StorageManager({"vault_path": tmp, "storage": "obsidian"}, "obsidian")
        base, _, _ = _save(manager)
        path = Path(tmp) / "Reels" / "content-creation" / f"{base}.md"
        ref = f"Reels/content-creation/{base}.md"
        manager.update_metadata(ref, {"classification": CLASSIFICATION_DONE,
                                      "niche": "business"})
        with path.open("a", encoding="utf-8") as fh:
            fh.write("\n## My Note\n\nmanual note\n")

        again, _, _ = _save(manager, topic="hooks")
        assert again == base
        assert not (Path(tmp) / "Reels" / "hooks" / f"{base}.md").exists()
        frontmatter, body = split_frontmatter(path.read_text(encoding="utf-8"))
        assert frontmatter["classification"] == CLASSIFICATION_DONE
        assert frontmatter["niche"] == "business"
        assert "manual note" in body
        assert "**Niche:** business" in body
        assert "**Classification:** classified" in body
        assert frontmatter["topics"] == ["content-creation", "hooks"]


def test_source_id_is_case_sensitive_and_empty_is_not_shared():
    assert source_id("https://www.instagram.com/reel/AbC/") == "AbC"
    assert source_id("") == ""
    assert source_id("   ") == ""


def test_obsidian_indexes_are_namespaced():
    with tempfile.TemporaryDirectory() as tmp:
        manager = StorageManager({"vault_path": tmp, "storage": "obsidian"}, "obsidian")
        _save(manager)
        assert (Path(tmp) / "index" / "topics" / "content-creation.md").is_file()
        assert (Path(tmp) / "index" / "niches" / "unclassified.md").is_file()
        assert not (Path(tmp) / "index" / "content-creation.md").exists()
        assert manager.reindex() == 1


def test_duplicate_source_reuses_note_and_storage_is_traversal_safe():
    with tempfile.TemporaryDirectory() as tmp:
        manager = StorageManager({"vault_path": tmp, "storage": "obsidian"}, "obsidian")
        base, _, _ = _save(manager)
        again, _, _ = _save(manager)
        assert base == again
        assert len(list((Path(tmp) / "Reels" / "content-creation").glob("*.md"))) == 1

        try:
            manager.read("../outside.md")
        except (StorageError, FileNotFoundError):
            pass
        else:
            raise AssertionError("path traversal was not rejected")


def test_update_note_metadata_keeps_body():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "note.md"
        body = "# Note\n\n- **Niche:** unclassified\n- **Classification:** pending\n"
        path.write_text(dump_frontmatter({"niche": "unclassified"}) + "\n" + body,
                        encoding="utf-8")
        update_note_metadata(path, {"niche": "business", "classification": CLASSIFICATION_DONE})
        frontmatter, body = split_frontmatter(path.read_text(encoding="utf-8"))
        assert frontmatter["niche"] == "business"
        assert frontmatter["classification"] == CLASSIFICATION_DONE
        assert "# Note" in body
        assert "**Niche:** business" in body
        assert "**Classification:** classified" in body


class FakeNotionStore:
    """Minimal in-memory stand-in for the Notion HTTP client."""

    def __init__(self):
        from reels_vault.storage import NOTION_PROPERTIES, NotionStore
        self.store = NotionStore({"token": "test", "database_id": "a" * 32})
        self.store._schema = {
            name: {**definition, "type": next(iter(definition))}
            for name, definition in NOTION_PROPERTIES.items()
        }
        self.pages: dict[str, dict] = {}
        self.children: dict[str, list] = {}
        self.deleted: list[str] = []

    def _request(self, method, path, payload=None):
        self.store._request_calls = getattr(self.store, "_request_calls", []) + [(method, path)]
        if method == "POST" and path.endswith("/query"):
            flt = (payload or {}).get("filter") or {}
            source = (flt.get("url") or {}).get("equals")
            results = [page for page in self.pages.values()
                       if not source or page.get("_source") == source]
            return {"results": results, "has_more": False}
        if method == "POST" and path == "/pages":
            page_id = f"page-{len(self.pages) + 1}"
            page = {"id": page_id, "url": f"https://notion.so/{page_id}",
                    "properties": dict(payload["properties"]),
                    "_source": (payload["properties"].get("Source") or {}).get("url")}
            self.pages[page_id] = page
            self.children[page_id] = [
                {**block, "id": f"block-{len(self.children.get(page_id, [])) + i}"}
                for i, block in enumerate(payload.get("children") or [])
            ]
            return page
        if method == "PATCH" and path.startswith("/pages/"):
            page = self.pages[path.rsplit("/", 1)[-1]]
            page["properties"].update(payload["properties"])
            return page
        if method == "GET" and "/children" in path:
            page_id = path.split("/")[2]
            return {"results": self.children.get(page_id, []), "has_more": False}
        if method == "PATCH" and "/children" in path:
            page_id = path.split("/")[2]
            self.children.setdefault(page_id, []).extend(
                {**block, "id": f"block-{len(self.children[page_id]) + i}"}
                for i, block in enumerate(payload["children"])
            )
            return {}
        if method == "DELETE":
            self.deleted.append(path)
            return {}
        raise AssertionError((method, path, payload))


def test_notion_save_reuses_page_and_updates_metadata():
    fake = FakeNotionStore()
    fake.store._request = fake._request
    metadata = _metadata()
    note = format_output(metadata, _transcript(), original_url=metadata["url"],
                         topic="content-creation")
    frontmatter, _ = split_frontmatter(note)

    first = fake.store.save(note, frontmatter, metadata, _transcript(), {},
                            "content-creation", "base")
    second = fake.store.save(note, frontmatter, metadata, _transcript(), {},
                             "content-creation", "base")
    assert first["ref"] == second["ref"]
    assert len(fake.pages) == 1
    assert fake.children["page-1"]

    fake.store.update_metadata(first["ref"], {"niche": "business",
                                               "category": "tip",
                                               "industry": "saas",
                                               "topics": ["content-creation", "hooks"],
                                               "tags": ["hooks"],
                                               "classification": CLASSIFICATION_DONE})
    props = fake.pages["page-1"]["properties"]
    assert props["Niche"]["rich_text"][0]["text"]["content"] == "business"
    assert props["Classification"]["select"]["name"] == CLASSIFICATION_DONE
    assert fake.deleted
    assert fake.children["page-1"]

    fake.store.save(note, frontmatter, metadata, _transcript(), {},
                    "content-creation", "base")
    props = fake.pages["page-1"]["properties"]
    assert props["Niche"]["rich_text"][0]["text"]["content"] == "business"
    assert props["Category"]["rich_text"][0]["text"]["content"] == "tip"
    assert props["Industry"]["rich_text"][0]["text"]["content"] == "saas"
    assert props["Classification"]["select"]["name"] == CLASSIFICATION_DONE
    assert {tag["name"] for tag in props["Tags"]["multi_select"]} == {"hooks", "ads", "marketing"}
    assert props["Topics"]["rich_text"][0]["text"]["content"] == "content-creation, hooks"


def test_both_mode_classification_updates_matching_notion_page():
    with tempfile.TemporaryDirectory() as tmp:
        manager = StorageManager({"vault_path": tmp, "storage": "both"}, "both")
        fake = FakeNotionStore()
        fake.store._request = fake._request
        manager.notion = fake.store

        base, _, metadata = _save(manager)
        ref = f"Reels/content-creation/{base}.md"
        manager.update_metadata(ref, {"niche": "business",
                                      "classification": CLASSIFICATION_DONE})
        assert fake.pages
        page = next(iter(fake.pages.values()))
        assert page["properties"]["Niche"]["rich_text"][0]["text"]["content"] == "business"


def test_bulk_url_parsing_and_deduplication():
    from reels_vault.bulk_import import read_urls, reel_id

    text = """
    https://www.instagram.com/reel/AAA/?utm_source=x
    https://www.instagram.com/reels/AAA/
    https://instagram.com/someuser/p/BBB/
    not a url
    """
    urls = read_urls(text)
    assert [reel_id(url) for url in urls] == ["AAA", "BBB"]
    assert read_urls("https://www.instagram.com/reel/CCC/") == [
        "https://www.instagram.com/reel/CCC/"
    ]


def test_storage_backend_resolution():
    from reels_vault.config import storage_backend

    for var in ("REELS_STORAGE",):
        os.environ.pop(var, None)
    assert storage_backend({"storage": "notion", "vault_path": "/tmp/v"}) == "notion"
    assert storage_backend({"notion": {"database_id": "x"}}) == "notion"
    assert storage_backend({}) == "obsidian"
    os.environ["REELS_STORAGE"] = "both"
    try:
        assert storage_backend({"storage": "obsidian"}) == "both"
    finally:
        os.environ.pop("REELS_STORAGE", None)


def test_creator_username_normalization():
    from reels_vault.import_creator import clean_username, default_topic

    assert clean_username("@garyvee") == "garyvee"
    assert clean_username("https://www.instagram.com/garyvee/") == "garyvee"
    assert default_topic("Gary Vee") == "gary-vee"


def test_playwright_cookie_conversion():
    from reels_vault.extract import _netscape_cookie_file

    with tempfile.TemporaryDirectory() as tmp:
        session = Path(tmp) / "state.json"
        session.write_text('{"cookies":[{"name":"sessionid","value":"abc","domain":".instagram.com",'
                           '"path":"/","expires":4102444800,"secure":true}],"origins":[]}',
                           encoding="utf-8")
        path = _netscape_cookie_file(str(session), tmp)
        text = Path(path).read_text(encoding="utf-8")
        assert "sessionid" in text and "instagram.com" in text
        assert text.startswith("# Netscape HTTP Cookie File")
        assert os.stat(path).st_mode & 0o777 == 0o600
