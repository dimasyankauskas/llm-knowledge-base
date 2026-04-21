"""Tests for v2 extract stage in scripts/extract.py."""

import json
from pathlib import Path

import pytest

from scripts.extract import (
    check_dedup,
    classify_source_type,
    read_source,
    register_source,
)


# ── classify_source_type ────────────────────────────────────────────────


def test_classify_source_type_pdf():
    """PDF files are classified as 'paper'."""
    assert classify_source_type(Path("paper.pdf")) == "paper"


def test_classify_source_type_md():
    """Markdown files are classified as 'article'."""
    assert classify_source_type(Path("notes.md")) == "article"


def test_classify_source_type_txt():
    """Text files are classified as 'article'."""
    assert classify_source_type(Path("notes.txt")) == "article"


def test_classify_source_type_transcript():
    """Filenames containing 'transcript' are classified as 'transcript'."""
    assert classify_source_type(Path("meeting-transcript.md")) == "transcript"


def test_classify_source_type_transcript_pdf():
    """PDF with 'transcript' in name is still classified as 'transcript'."""
    assert classify_source_type(Path("interview-transcript.pdf")) == "transcript"


def test_classify_source_type_code():
    """Python files are classified as 'code-doc'."""
    assert classify_source_type(Path("module.py")) == "code-doc"


def test_classify_source_type_js():
    """JavaScript files are classified as 'code-doc'."""
    assert classify_source_type(Path("app.js")) == "code-doc"


def test_classify_source_type_ts():
    """TypeScript files are classified as 'code-doc'."""
    assert classify_source_type(Path("app.ts")) == "code-doc"


def test_classify_source_type_go():
    """Go files are classified as 'code-doc'."""
    assert classify_source_type(Path("main.go")) == "code-doc"


def test_classify_source_type_rs():
    """Rust files are classified as 'code-doc'."""
    assert classify_source_type(Path("lib.rs")) == "code-doc"


def test_classify_source_type_java():
    """Java files are classified as 'code-doc'."""
    assert classify_source_type(Path("Main.java")) == "code-doc"


def test_classify_source_type_unknown():
    """Unknown file extensions default to 'article'."""
    assert classify_source_type(Path("data.csv")) == "article"


# ── read_source ─────────────────────────────────────────────────────────


def test_read_source_text(tmp_path):
    """Read a .txt file and return its content."""
    f = tmp_path / "notes.txt"
    f.write_text("Hello world", encoding="utf-8")
    assert read_source(f) == "Hello world"


def test_read_source_md(tmp_path):
    """Read a .md file and return its content."""
    f = tmp_path / "notes.md"
    f.write_text("# Title\n\nSome content", encoding="utf-8")
    content = read_source(f)
    assert "# Title" in content
    assert "Some content" in content


def test_read_source_json(tmp_path):
    """Read a .json file and return its content."""
    f = tmp_path / "data.json"
    f.write_text('{"key": "value"}', encoding="utf-8")
    content = read_source(f)
    assert "key" in content


def test_read_source_yaml(tmp_path):
    """Read a .yaml file and return its content."""
    f = tmp_path / "config.yaml"
    f.write_text("version: 2.0", encoding="utf-8")
    content = read_source(f)
    assert "version" in content


# ── register_source ──────────────────────────────────────────────────────


def test_register_source_adds_to_manifest(tmp_path):
    """Registering a source adds it to the manifest."""
    # Create a source file
    source_file = tmp_path / "article.md"
    source_file.write_text("# Test Article\n\nContent here.", encoding="utf-8")

    manifest_path = tmp_path / "sources" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"version": "1.0", "description": "Test", "sources": []}),
        encoding="utf-8",
    )

    entry = register_source(source_file, "article", manifest_path=manifest_path)

    assert entry is not None
    assert entry["filename"] == "article.md"
    assert entry["source_type"] == "article"
    assert entry["status"] == "ingested"
    assert "content_hash" in entry
    assert "ingested_at" in entry

    # Verify manifest was written
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["sources"]) == 1
    assert manifest["sources"][0]["filename"] == "article.md"


def test_register_source_repairs_empty_manifest(tmp_path):
    """Registering into a clean {} manifest initializes required keys."""
    source_file = tmp_path / "article.md"
    source_file.write_text("# Test Article\n\nContent here.", encoding="utf-8")

    manifest_path = tmp_path / "sources" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{}", encoding="utf-8")

    entry = register_source(source_file, "article", manifest_path=manifest_path)

    assert entry is not None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["version"] == "1.0"
    assert manifest["description"] == "Registry of ingested sources"
    assert len(manifest["sources"]) == 1


def test_register_source_detects_duplicate(tmp_path):
    """Registering the same source twice detects the duplicate."""
    source_file = tmp_path / "article.md"
    source_file.write_text("# Test Article\n\nContent here.", encoding="utf-8")

    manifest_path = tmp_path / "sources" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"version": "1.0", "description": "Test", "sources": []}),
        encoding="utf-8",
    )

    # First registration should succeed
    entry1 = register_source(source_file, "article", manifest_path=manifest_path)
    assert entry1 is not None

    # Second registration of same content should return None (duplicate)
    entry2 = register_source(source_file, "article", manifest_path=manifest_path)
    assert entry2 is None

    # Verify only one entry in manifest
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["sources"]) == 1


# ── check_dedup ──────────────────────────────────────────────────────────


def test_check_dedup_new_source(tmp_path):
    """check_dedup returns False for a source not yet in the manifest."""
    source_file = tmp_path / "new_article.md"
    source_file.write_text("# New Article\n\nBrand new content.", encoding="utf-8")

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"version": "1.0", "description": "Test", "sources": []}),
        encoding="utf-8",
    )

    assert check_dedup(source_file, manifest_path) is False


def test_check_dedup_existing_source(tmp_path):
    """check_dedup returns True for a source already in the manifest."""
    source_file = tmp_path / "existing.md"
    source_file.write_text("# Existing Article\n\nContent.", encoding="utf-8")

    from scripts.utils import hash_content

    content_hash = hash_content(source_file.read_text(encoding="utf-8"))

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "version": "1.0",
            "description": "Test",
            "sources": [
                {
                    "filename": "existing.md",
                    "source_type": "article",
                    "content_hash": content_hash,
                    "ingested_at": "2026-04-14T00:00:00+00:00",
                    "status": "ingested",
                    "concepts_generated": [],
                    "entities_generated": [],
                }
            ],
        }),
        encoding="utf-8",
    )

    assert check_dedup(source_file, manifest_path) is True
