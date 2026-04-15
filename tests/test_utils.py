"""Tests for v2 utility functions in scripts/utils.py."""

import json
from pathlib import Path

import pytest

from scripts.utils import (
    DRAFTS_DIR,
    STATE_PATH,
    HEALTH_PATH,
    LOG_PATH,
    hash_content,
    extract_wikilinks,
    extract_typed_relations,
    read_provenance,
    write_provenance,
)


# ── Constants ──────────────────────────────────────────────────────────


def test_drafts_dir_path():
    """DRAFTS_DIR points to wiki/drafts."""
    assert DRAFTS_DIR.name == "drafts"
    assert DRAFTS_DIR.parent.name == "wiki"


def test_state_path():
    """STATE_PATH points to wiki/_state.json."""
    assert STATE_PATH.name == "_state.json"
    assert STATE_PATH.parent.name == "wiki"


def test_health_path():
    """HEALTH_PATH points to wiki/_health.json."""
    assert HEALTH_PATH.name == "_health.json"
    assert HEALTH_PATH.parent.name == "wiki"


# ── hash_content ──────────────────────────────────────────────────────


def test_hash_content_deterministic():
    """Same input produces same hash."""
    assert hash_content("hello") == hash_content("hello")


def test_hash_content_different():
    """Different inputs produce different hashes."""
    assert hash_content("hello") != hash_content("world")


def test_hash_content_returns_hex_string():
    """Hash is a 16-char hex string."""
    result = hash_content("test")
    assert isinstance(result, str)
    assert len(result) == 16
    assert all(c in "0123456789abcdef" for c in result)


# ── extract_wikilinks ─────────────────────────────────────────────────


def test_extract_basic_wikilink():
    """Extract a simple wikilink."""
    content = "See [[Neural IR]] for details."
    assert extract_wikilinks(content) == ["Neural IR"]


def test_extract_wikilink_with_alias():
    """Extract wikilink target, ignoring alias after pipe."""
    content = "See [[Neural IR|NR]] for details."
    assert extract_wikilinks(content) == ["Neural IR"]


def test_extract_multiple_wikilinks():
    """Extract multiple wikilinks from content."""
    content = "[[RAG]] implements [[Neural IR]] and extends [[Dense Retrieval]]."
    result = extract_wikilinks(content)
    assert result == ["RAG", "Neural IR", "Dense Retrieval"]


# ── extract_typed_relations ────────────────────────────────────────────


def test_extract_typed_relations_implements():
    """Detect 'implements' relation type from context before wikilink."""
    content = "RAG implements [[Neural IR]] for search."
    result = extract_typed_relations(content)
    assert len(result) == 1
    assert result[0]["target"] == "Neural IR"
    assert result[0]["type"] == "implements"


def test_extract_typed_relations_contradicts():
    """Detect 'contradicts' relation type from context before wikilink."""
    content = "This approach contradicts [[BM25]] in practice."
    result = extract_typed_relations(content)
    assert len(result) == 1
    assert result[0]["target"] == "BM25"
    assert result[0]["type"] == "contradicts"


def test_extract_typed_relations_untyped_default():
    """Untyped wikilinks default to 'neutral' type."""
    content = "See [[Neural IR]] for details."
    result = extract_typed_relations(content)
    assert len(result) == 1
    assert result[0]["target"] == "Neural IR"
    assert result[0]["type"] == "neutral"


# ── Provenance sidecar ────────────────────────────────────────────────


def test_write_and_read_provenance(tmp_path):
    """Write provenance sidecar, then read it back."""
    page_path = tmp_path / "concepts" / "RAG.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text("# RAG")

    data = {
        "sources": ["paper1.pdf"],
        "extracted_at": "2026-04-14",
        "confidence": "HIGH",
    }
    write_provenance(page_path, data)

    result = read_provenance(page_path)
    assert result is not None
    assert result["sources"] == ["paper1.pdf"]
    assert result["extracted_at"] == "2026-04-14"
    assert result["confidence"] == "HIGH"


def test_read_provenance_missing_file(tmp_path):
    """Reading provenance for a page with no sidecar returns None."""
    page_path = tmp_path / "concepts" / "Missing.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text("# Missing")

    result = read_provenance(page_path)
    assert result is None