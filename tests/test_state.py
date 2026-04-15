"""Tests for state management — _state.json and _health.json generation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.state import (
    generate_health,
    generate_state,
    load_health,
    load_state,
    save_health,
    save_state,
)
from scripts.utils import write_page, write_provenance, hash_content


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_concept(path: Path, title: str, content: str = "", **metadata) -> Path:
    """Create a minimal concept page in a wiki tree."""
    defaults = {
        "title": title,
        "type": "concept",
        "confidence": "HIGH",
        "created": "2026-04-14",
        "source_refs": [],
        "content_hash": hash_content(content),
    }
    defaults.update(metadata)
    write_page(path, defaults, content)
    return path


def _make_entity(path: Path, title: str, content: str = "", **metadata) -> Path:
    """Create a minimal entity page in a wiki tree."""
    defaults = {
        "title": title,
        "type": "entity",
        "entity_type": "organization",
        "created": "2026-04-14",
        "source_refs": [],
        "content_hash": hash_content(content),
    }
    defaults.update(metadata)
    write_page(path, defaults, content)
    return path


def _build_wiki(tmp_path: Path) -> Path:
    """Create a minimal wiki directory structure under tmp_path."""
    wiki_dir = tmp_path / "wiki"
    (wiki_dir / "concepts").mkdir(parents=True)
    (wiki_dir / "entities").mkdir(parents=True)
    (wiki_dir / "indexes").mkdir(parents=True)
    return wiki_dir


def _minimal_schema() -> dict:
    """Return a minimal SCHEMA.yaml-like dict for testing."""
    return {
        "version": "2.0",
        "page_types": {
            "concept": {
                "required_frontmatter": [
                    "title", "type", "confidence", "created",
                    "source_refs", "content_hash",
                ],
                "required_sections": [
                    "Definition", "Key Properties", "How It Works",
                    "Relationships", "Open Questions", "Sources",
                ],
                "section_rules": {"Definition": "facts_only"},
                "min_outlinks": 2,
            },
            "entity": {
                "required_frontmatter": [
                    "title", "type", "entity_type",
                    "created", "source_refs", "content_hash",
                ],
                "required_sections": [
                    "Overview", "Contributions", "Relationships", "Sources",
                ],
                "min_outlinks": 1,
            },
            "index": {"auto_generated": True},
            "timeline": {
                "required_frontmatter": ["title", "type", "created"],
            },
        },
        "confidence_levels": {
            "HIGH": {"description": "Multiple independent sources agree", "color": "green"},
            "MEDIUM": {"description": "Single source, well-established claim", "color": "yellow"},
            "LOW": {"description": "Inference, single mention, or contested", "color": "red"},
        },
        "relation_types": [
            "implements", "extends", "contradicts", "cites",
            "prerequisite_of", "trades_off", "derived_from",
        ],
        "validation": {
            "broken_links": {"severity": "ERROR"},
            "orphan_pages": {"severity": "WARNING"},
        },
        "contradiction": {
            "callout_type": "warning",
            "resolution_callout": "success",
        },
    }


# ── generate_state ──────────────────────────────────────────────────────────

class TestGenerateStateContainsSchemaSummary:
    """State includes schema_version, page_types, required_fields."""

    def test_state_has_schema_version(self, tmp_path):
        wiki_dir = _build_wiki(tmp_path)
        state = generate_state(wiki_dir=wiki_dir, schema=_minimal_schema())
        assert "schema_version" in state
        assert state["schema_version"] == "2.0"

    def test_state_has_page_types(self, tmp_path):
        wiki_dir = _build_wiki(tmp_path)
        state = generate_state(wiki_dir=wiki_dir, schema=_minimal_schema())
        assert "page_types" in state
        assert "concept" in state["page_types"]
        assert "entity" in state["page_types"]

    def test_state_has_required_fields(self, tmp_path):
        wiki_dir = _build_wiki(tmp_path)
        state = generate_state(wiki_dir=wiki_dir, schema=_minimal_schema())
        assert "required_fields" in state
        assert "concept" in state["required_fields"]
        assert "title" in state["required_fields"]["concept"]


class TestGenerateStateListsPages:
    """State has pages dict with type, confidence, tags."""

    def test_state_includes_pages(self, tmp_path):
        wiki_dir = _build_wiki(tmp_path)
        _make_concept(
            wiki_dir / "concepts" / "RAG.md",
            "RAG",
            "## Definition\nRAG combines retrieval and generation.\n",
        )
        state = generate_state(wiki_dir=wiki_dir, schema=_minimal_schema())
        assert "pages" in state
        assert "RAG" in state["pages"]

    def test_page_has_type_and_confidence(self, tmp_path):
        wiki_dir = _build_wiki(tmp_path)
        _make_concept(
            wiki_dir / "concepts" / "RAG.md",
            "RAG",
            "## Definition\nRAG combines retrieval and generation.\n",
            confidence="MEDIUM",
        )
        state = generate_state(wiki_dir=wiki_dir, schema=_minimal_schema())
        page = state["pages"]["RAG"]
        assert page["type"] == "concept"
        assert page["confidence"] == "MEDIUM"

    def test_page_has_tags(self, tmp_path):
        wiki_dir = _build_wiki(tmp_path)
        _make_concept(
            wiki_dir / "concepts" / "RAG.md",
            "RAG",
            "## Definition\nRAG combines retrieval and generation.\n",
            tags=["domain/ai", "topic/retrieval"],
        )
        state = generate_state(wiki_dir=wiki_dir, schema=_minimal_schema())
        page = state["pages"]["RAG"]
        assert page["tags"] == ["domain/ai", "topic/retrieval"]

    def test_page_has_outlinks(self, tmp_path):
        wiki_dir = _build_wiki(tmp_path)
        _make_concept(
            wiki_dir / "concepts" / "RAG.md",
            "RAG",
            "## Definition\nRAG extends [[Retrieval]] and cites [[Generation]].\n",
        )
        state = generate_state(wiki_dir=wiki_dir, schema=_minimal_schema())
        page = state["pages"]["RAG"]
        assert "Retrieval" in page["outlinks"]
        assert "Generation" in page["outlinks"]

    def test_page_has_inlinks(self, tmp_path):
        wiki_dir = _build_wiki(tmp_path)
        _make_concept(
            wiki_dir / "concepts" / "RAG.md",
            "RAG",
            "## Definition\nRAG combines retrieval and generation.\n",
        )
        _make_concept(
            wiki_dir / "concepts" / "Retrieval.md",
            "Retrieval",
            "## Definition\nSee also [[RAG]].\n",
        )
        state = generate_state(wiki_dir=wiki_dir, schema=_minimal_schema())
        rag_page = state["pages"]["RAG"]
        assert "Retrieval" in rag_page["inlinks"]


class TestGenerateStateTracksThinPages:
    """Thin pages (fewer than 2 content sections) are identified."""

    def test_thin_page_detected(self, tmp_path):
        wiki_dir = _build_wiki(tmp_path)
        # Only frontmatter, no sections at all
        _make_concept(
            wiki_dir / "concepts" / "Thin.md",
            "Thin",
            "Just a stub with no sections.",
        )
        state = generate_state(wiki_dir=wiki_dir, schema=_minimal_schema())
        assert "Thin" in state["thin_pages"]

    def test_non_thin_page_not_listed(self, tmp_path):
        wiki_dir = _build_wiki(tmp_path)
        _make_concept(
            wiki_dir / "concepts" / "Rich.md",
            "Rich",
            "## Definition\nSome definition.\n\n## Key Properties\nSome properties.\n",
        )
        state = generate_state(wiki_dir=wiki_dir, schema=_minimal_schema())
        assert "Rich" not in state.get("thin_pages", [])


class TestGenerateStateDetectsContradictions:
    """Pages with CONTRADICTION callout are listed in active_contradictions."""

    def test_contradiction_detected(self, tmp_path):
        wiki_dir = _build_wiki(tmp_path)
        content = (
            "## Definition\n"
            "Some claim.\n\n"
            "> [!warning] CONTRADICTION\n"
            "> This contradicts [[Other]].\n"
        )
        _make_concept(
            wiki_dir / "concepts" / "Conflict.md",
            "Conflict",
            content,
        )
        state = generate_state(wiki_dir=wiki_dir, schema=_minimal_schema())
        assert "Conflict" in state["active_contradictions"]

    def test_no_contradiction(self, tmp_path):
        wiki_dir = _build_wiki(tmp_path)
        _make_concept(
            wiki_dir / "concepts" / "Peaceful.md",
            "Peaceful",
            "## Definition\nAll is well.\n",
        )
        state = generate_state(wiki_dir=wiki_dir, schema=_minimal_schema())
        assert "Peaceful" not in state.get("active_contradictions", [])


# ── generate_health ─────────────────────────────────────────────────────────

class TestGenerateHealthFromLintResults:
    """Health dict has errors, warnings counts from lint results."""

    def test_health_counts_errors_and_warnings(self):
        lint_results = [
            {"code": "broken_links", "page": "A", "message": "Broken link", "severity": "ERROR"},
            {"code": "missing_frontmatter", "page": "B", "message": "Missing field", "severity": "ERROR"},
            {"code": "orphan_pages", "page": "C", "message": "Orphan page", "severity": "WARNING"},
            {"code": "low_connectivity", "page": "D", "message": "Low outlinks", "severity": "WARNING"},
        ]
        health = generate_health(lint_results=lint_results)
        assert health["errors"] == 2
        assert health["warnings"] == 2
        assert health["orphans"] == 1
        assert health["broken_links"] == 1

    def test_health_issues_list(self):
        lint_results = [
            {"code": "broken_links", "page": "A", "message": "Broken link", "severity": "ERROR"},
            {"code": "orphan_pages", "page": "C", "message": "Orphan page", "severity": "WARNING"},
        ]
        health = generate_health(lint_results=lint_results)
        assert len(health["issues"]) == 2
        assert health["issues"][0]["code"] == "broken_links"
        assert health["issues"][0]["severity"] == "ERROR"
        assert health["issues"][1]["severity"] == "WARNING"

    def test_health_has_last_lint(self):
        health = generate_health(lint_results=[])
        assert "last_lint" in health


# ── save and load round-trips ───────────────────────────────────────────────

class TestSaveAndLoadState:
    """Round-trip state to disk."""

    def test_save_and_load_state(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        state = {
            "schema_version": "2.0",
            "last_updated": "2026-04-14",
            "page_types": ["concept", "entity"],
            "pages": {"RAG": {"type": "concept"}},
        }
        save_state(state, wiki_dir=wiki_dir)
        loaded = load_state(wiki_dir=wiki_dir)
        assert loaded["schema_version"] == "2.0"
        assert "RAG" in loaded["pages"]

    def test_load_state_missing_file(self, tmp_path):
        wiki_dir = tmp_path / "nonexistent"
        loaded = load_state(wiki_dir=wiki_dir)
        assert loaded == {}


class TestSaveAndLoadHealth:
    """Round-trip health to disk."""

    def test_save_and_load_health(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        health = {
            "errors": 3,
            "warnings": 5,
            "orphans": 1,
            "broken_links": 2,
            "last_lint": "2026-04-14",
            "issues": [],
        }
        save_health(health, wiki_dir=wiki_dir)
        loaded = load_health(wiki_dir=wiki_dir)
        assert loaded["errors"] == 3
        assert loaded["warnings"] == 5
        assert loaded["last_lint"] == "2026-04-14"

    def test_load_health_missing_file(self, tmp_path):
        wiki_dir = tmp_path / "nonexistent"
        loaded = load_health(wiki_dir=wiki_dir)
        assert loaded == {}