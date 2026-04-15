"""Tests for the lint stage v2 — 12 schema-driven lint checks."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.lint import (
    LintIssue,
    check_broken_links,
    check_orphan_pages,
    check_frontmatter,
    check_sources,
    check_low_connectivity,
    check_staleness,
    check_contradictions,
    check_empty_sections,
    check_duplicate_concepts,
    check_unmarked_inference,
    check_missing_content_hash,
    lint,
)
from scripts.schema import load_schema
from scripts.utils import (
    write_page,
    write_provenance,
    hash_file,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_wiki_dir(tmp_path: Path) -> Path:
    """Create and return a wiki directory structure under tmp_path."""
    wiki_dir = tmp_path / "wiki"
    (wiki_dir / "concepts").mkdir(parents=True, exist_ok=True)
    (wiki_dir / "entities").mkdir(parents=True, exist_ok=True)
    (wiki_dir / "indexes").mkdir(parents=True, exist_ok=True)
    return wiki_dir


def _make_concept_page(
    wiki_dir: Path,
    name: str = "Test_Concept",
    metadata: dict | None = None,
    content: str | None = None,
) -> Path:
    """Create a concept page with valid frontmatter and content."""
    concepts = wiki_dir / "concepts"
    concepts.mkdir(parents=True, exist_ok=True)
    page_path = concepts / f"{name}.md"

    if metadata is None:
        metadata = {
            "title": name.replace("_", " "),
            "type": "concept",
            "confidence": "HIGH",
            "created": "2025-01-01",
            "source_refs": ["test_source.md"],
            "content_hash": "abc123",
        }

    if content is None:
        content = """\
## Definition

A test concept definition with [source: test.md, §1].

## Key Properties

- Property one [source: test.md, §2]

## How It Works

Mixed content here.

## Relationships

- [[Test_Concept]] [source: test.md, §3]

## Open Questions

> [!note] Inference: Something to explore.

## Sources

- test.md
"""

    write_page(page_path, metadata, content)
    return page_path


def _make_entity_page(
    wiki_dir: Path,
    name: str = "Test_Entity",
    metadata: dict | None = None,
    content: str | None = None,
) -> Path:
    """Create an entity page with valid frontmatter and content."""
    entities = wiki_dir / "entities"
    entities.mkdir(parents=True, exist_ok=True)
    page_path = entities / f"{name}.md"

    if metadata is None:
        metadata = {
            "title": name.replace("_", " "),
            "type": "entity",
            "entity_type": "organization",
            "created": "2025-01-01",
            "source_refs": ["test_source.md"],
            "content_hash": "def456",
        }

    if content is None:
        content = """\
## Overview

Entity overview with [source: entity_source.md, §1].

## Contributions

- Contributed to X [source: entity_source.md, §2]

## Relationships

- [[Test_Entity]] [source: entity_source.md, §3]

## Sources

- entity_source.md
"""

    write_page(page_path, metadata, content)
    return page_path


def _make_index_page(wiki_dir: Path, name: str = "_index") -> Path:
    """Create an index page (starts with _)."""
    indexes = wiki_dir / "indexes"
    indexes.mkdir(parents=True, exist_ok=True)
    page_path = indexes / f"{name}.md"
    write_page(page_path, {"title": "Index", "type": "index"}, "# Index\n")
    return page_path


def _all_page_names(pages: list[Path]) -> set[str]:
    """Extract all page stem names from a list of paths (case-insensitive ready)."""
    return {p.stem for p in pages}


# ── check_broken_links ────────────────────────────────────────────────────────


class TestBrokenLinks:
    def test_broken_link_detected(self, tmp_path):
        """Detect wikilinks that point to non-existent pages."""
        wiki_dir = _make_wiki_dir(tmp_path)
        page = _make_concept_page(
            wiki_dir,
            content="See [[Nonexistent_Page]] for details.\n",
        )
        pages = [page]
        all_names = _all_page_names(pages)

        issues = check_broken_links(pages, all_names)
        assert len(issues) > 0
        assert issues[0].code == "BROKEN_LINK"
        assert issues[0].severity == "ERROR"
        assert "Nonexistent_Page" in issues[0].message

    def test_broken_link_valid(self, tmp_path):
        """Valid wikilinks produce no broken-link issues."""
        wiki_dir = _make_wiki_dir(tmp_path)
        page = _make_concept_page(
            wiki_dir,
            content="See [[Test_Concept]] for details.\n",
        )
        pages = [page]
        all_names = _all_page_names(pages)

        issues = check_broken_links(pages, all_names)
        broken = [i for i in issues if i.code == "BROKEN_LINK"]
        assert len(broken) == 0


# ── check_orphan_pages ────────────────────────────────────────────────────────


class TestOrphanPages:
    def test_orphan_page_detected(self, tmp_path):
        """Detect pages with 0 inlinks and 0 outlinks."""
        wiki_dir = _make_wiki_dir(tmp_path)
        # Create an isolated page (no wikilinks in or out)
        page = _make_concept_page(
            wiki_dir,
            name="Isolated",
            content="## Definition\n\nNo links at all.\n",
        )
        pages = [page]

        issues = check_orphan_pages(pages)
        orphan_codes = [i.code for i in issues]
        assert "ORPHAN_PAGE" in orphan_codes

    def test_orphan_page_index_skipped(self, tmp_path):
        """Index pages (starting with _) are not flagged as orphans."""
        wiki_dir = _make_wiki_dir(tmp_path)
        idx = _make_index_page(wiki_dir, name="_topics")

        issues = check_orphan_pages([idx])
        orphan_codes = [i.code for i in issues]
        assert "ORPHAN_PAGE" not in orphan_codes


# ── check_frontmatter ─────────────────────────────────────────────────────────


class TestFrontmatter:
    def test_frontmatter_missing_field(self, tmp_path):
        """Detect missing required frontmatter fields for the page type."""
        wiki_dir = _make_wiki_dir(tmp_path)
        schema = load_schema()
        # Create a concept page missing 'confidence' and 'created'
        page = _make_concept_page(
            wiki_dir,
            metadata={"title": "Incomplete", "type": "concept"},
        )
        pages = [page]

        issues = check_frontmatter(pages, schema)
        missing_codes = [i.code for i in issues]
        assert "MISSING_FRONTMATTER" in missing_codes

    def test_frontmatter_valid(self, tmp_path):
        """Valid frontmatter produces no issues."""
        wiki_dir = _make_wiki_dir(tmp_path)
        schema = load_schema()
        page = _make_concept_page(wiki_dir)
        pages = [page]

        issues = check_frontmatter(pages, schema)
        error_issues = [i for i in issues if i.severity == "ERROR"]
        assert len(error_issues) == 0

    def test_frontmatter_invalid_type(self, tmp_path):
        """Detect unknown page type."""
        wiki_dir = _make_wiki_dir(tmp_path)
        schema = load_schema()
        page = _make_concept_page(
            wiki_dir,
            metadata={"title": "Bad Type", "type": "nonexistent"},
        )
        pages = [page]

        issues = check_frontmatter(pages, schema)
        invalid_codes = [i.code for i in issues]
        assert "INVALID_TYPE" in invalid_codes


# ── check_sources ─────────────────────────────────────────────────────────────


class TestSources:
    def test_no_sources_detected(self, tmp_path):
        """Detect pages without source citations."""
        wiki_dir = _make_wiki_dir(tmp_path)
        # Page with no [source: ...] in content and no source_refs in frontmatter
        page = _make_concept_page(
            wiki_dir,
            name="No_Sources",
            metadata={"title": "No Sources", "type": "concept", "confidence": "HIGH", "created": "2025-01-01"},
            content="## Definition\n\nSome unsourced claim.\n",
        )
        pages = [page]

        issues = check_sources(pages)
        no_src_codes = [i.code for i in issues]
        assert "NO_SOURCES" in no_src_codes


# ── check_low_connectivity ────────────────────────────────────────────────────


class TestLowConnectivity:
    def test_low_connectivity_detected(self, tmp_path):
        """Detect concept pages with fewer than min_outlinks outgoing links."""
        wiki_dir = _make_wiki_dir(tmp_path)
        schema = load_schema()
        # Create a concept page with only 0 outgoing links
        page = _make_concept_page(
            wiki_dir,
            name="Low_Link",
            content="## Definition\n\nSourced claim [source: x.md].\n\n## Key Properties\n\n- Prop [source: x.md]\n\n## How It Works\n\nStuff.\n\n## Relationships\n\nNo links.\n\n## Open Questions\n\n?\n\n## Sources\n\n- x.md\n",
        )
        pages = [page]

        issues = check_low_connectivity(pages, schema)
        low_codes = [i.code for i in issues]
        assert "LOW_CONNECTIVITY" in low_codes


# ── check_staleness ──────────────────────────────────────────────────────────


class TestStaleness:
    def test_staleness_detected(self, tmp_path):
        """Detect pages whose source content hashes have changed."""
        wiki_dir = _make_wiki_dir(tmp_path)
        sources_dir = tmp_path / "sources"
        sources_dir.mkdir(parents=True, exist_ok=True)

        # Create a source file
        source_file = sources_dir / "test_source.md"
        source_file.write_text("Original content", encoding="utf-8")
        original_hash = hash_file(source_file)

        # Create a concept page with provenance sidecar pointing to the source
        page = _make_concept_page(wiki_dir, name="Stale_Page")
        prov_data = {
            "page": "Stale_Page",
            "content_hash": "abc123",
            "sources": [
                {"file": "test_source.md", "content_hash": original_hash, "sections_used": ["all"]},
            ],
            "claims": [],
            "derived_concepts": [],
        }
        write_provenance(page, prov_data)

        # Now change the source file so the hash doesn't match
        source_file.write_text("Modified content", encoding="utf-8")

        issues = check_staleness([page], sources_dir=sources_dir)
        stale_codes = [i.code for i in issues]
        assert "STALE_PAGE" in stale_codes

    def test_staleness_not_stale(self, tmp_path):
        """Pages whose sources match are not flagged as stale."""
        wiki_dir = _make_wiki_dir(tmp_path)
        sources_dir = tmp_path / "sources"
        sources_dir.mkdir(parents=True, exist_ok=True)

        source_file = sources_dir / "test_source.md"
        source_file.write_text("Original content", encoding="utf-8")
        original_hash = hash_file(source_file)

        page = _make_concept_page(wiki_dir, name="Fresh_Page")
        prov_data = {
            "page": "Fresh_Page",
            "content_hash": "abc123",
            "sources": [
                {"file": "test_source.md", "content_hash": original_hash, "sections_used": ["all"]},
            ],
            "claims": [],
            "derived_concepts": [],
        }
        write_provenance(page, prov_data)

        issues = check_staleness([page], sources_dir=sources_dir)
        stale_codes = [i.code for i in issues]
        assert "STALE_PAGE" not in stale_codes


# ── check_contradictions ─────────────────────────────────────────────────────


class TestContradictions:
    def test_contradiction_unresolved(self, tmp_path):
        """Detect unresolved contradiction callouts."""
        wiki_dir = _make_wiki_dir(tmp_path)
        page = _make_concept_page(
            wiki_dir,
            name="Contradiction_Page",
            content="## Definition\n\nSome content.\n\n> [!warning] CONTRADICTION\n> Status:** UNRESOLVED\n> X contradicts Y.\n",
        )

        issues = check_contradictions([page])
        contra_codes = [i.code for i in issues]
        assert "UNRESOLVED_CONTRADICTION" in contra_codes

    def test_contradiction_resolved(self, tmp_path):
        """Resolved contradictions are not flagged."""
        wiki_dir = _make_wiki_dir(tmp_path)
        page = _make_concept_page(
            wiki_dir,
            name="Resolved_Page",
            content="## Definition\n\nSome content.\n\n> [!success] RESOLVED\n> Status:** RESOLVED\n> X and Y are compatible.\n",
        )

        issues = check_contradictions([page])
        contra_codes = [i.code for i in issues]
        assert "UNRESOLVED_CONTRADICTION" not in contra_codes


# ── check_duplicate_concepts ─────────────────────────────────────────────────


class TestDuplicateConcepts:
    def test_duplicate_concept_detected(self, tmp_path):
        """Detect pages with same title (case-insensitive, special chars removed)."""
        wiki_dir = _make_wiki_dir(tmp_path)
        page1 = _make_concept_page(wiki_dir, name="Neural_IR")
        page2 = _make_concept_page(wiki_dir, name="neural_ir")
        # The second one needs a unique path — put it in entities
        entities = wiki_dir / "entities"
        entities.mkdir(parents=True, exist_ok=True)
        page2_path = entities / "neural_ir.md"
        write_page(
            page2_path,
            {"title": "neural ir", "type": "concept", "confidence": "HIGH", "created": "2025-01-01"},
            "## Definition\n\nSame concept different case.\n",
        )

        issues = check_duplicate_concepts([page1, page2_path])
        dup_codes = [i.code for i in issues]
        assert "DUPLICATE_CONCEPT" in dup_codes


# ── check_empty_sections ─────────────────────────────────────────────────────


class TestEmptySections:
    def test_empty_section_detected(self, tmp_path):
        """Detect required sections with placeholder/empty content."""
        wiki_dir = _make_wiki_dir(tmp_path)
        page = _make_concept_page(
            wiki_dir,
            name="Empty_Sec",
            content="## Definition\n\n*To be documented*\n\n## Key Properties\n\n*To be expanded*\n\n## How It Works\n\nContent here.\n\n## Relationships\n\n- [[Empty_Sec]] [source: x.md]\n\n## Open Questions\n\n?\n\n## Sources\n\n- x.md\n",
        )

        issues = check_empty_sections([page])
        empty_codes = [i.code for i in issues]
        assert "EMPTY_SECTION" in empty_codes


# ── check_unmarked_inference ─────────────────────────────────────────────────


class TestUnmarkedInference:
    def test_unmarked_inference_detected(self, tmp_path):
        """Detect claims without source citations in facts_only sections."""
        wiki_dir = _make_wiki_dir(tmp_path)
        schema = load_schema()
        # Definition is facts_only — a long claim without [source:] is flagged
        page = _make_concept_page(
            wiki_dir,
            name="Unmarked_Inf",
            content="## Definition\n\nThis concept will completely revolutionize the entire field of study and is the most important idea of the decade.\n\n## Key Properties\n\n- Sourced [source: test.md, §1]\n\n## How It Works\n\nMixed.\n\n## Relationships\n\n- [[Unmarked_Inf]] [source: test.md]\n\n## Open Questions\n\n?\n\n## Sources\n\n- test.md\n",
        )

        issues = check_unmarked_inference([page], schema)
        inf_codes = [i.code for i in issues]
        assert "UNMARKED_INFERENCE" in inf_codes


# ── check_missing_content_hash ────────────────────────────────────────────────


class TestMissingContentHash:
    def test_missing_content_hash_detected(self, tmp_path):
        """Detect pages without .provenance.json sidecar."""
        wiki_dir = _make_wiki_dir(tmp_path)
        page = _make_concept_page(wiki_dir, name="No_Hash")
        # Do NOT create a provenance sidecar

        issues = check_missing_content_hash([page])
        missing_codes = [i.code for i in issues]
        assert "MISSING_CONTENT_HASH" in missing_codes

    def test_missing_content_hash_has_sidecar(self, tmp_path):
        """Pages with provenance sidecar are not flagged."""
        wiki_dir = _make_wiki_dir(tmp_path)
        page = _make_concept_page(wiki_dir, name="Has_Hash")
        write_provenance(page, {
            "page": "Has_Hash",
            "content_hash": "abc123",
            "sources": [],
            "claims": [],
            "derived_concepts": [],
        })

        issues = check_missing_content_hash([page])
        missing_codes = [i.code for i in issues]
        assert "MISSING_CONTENT_HASH" not in missing_codes


# ── lint (integration) ──────────────────────────────────────────────────────


class TestLintIntegration:
    def test_lint_returns_all_issues(self, tmp_path):
        """lint() runs all 12 checks and returns a combined list."""
        wiki_dir = _make_wiki_dir(tmp_path)
        schema = load_schema()
        sources_dir = tmp_path / "sources"
        sources_dir.mkdir(parents=True, exist_ok=True)

        # Create a concept page with multiple problems
        page = _make_concept_page(
            wiki_dir,
            name="Problematic",
            metadata={"title": "Problematic", "type": "concept"},
            content="## Definition\n\nNo source claim that is quite long and unsupported.\n\n## Key Properties\n\n*To be expanded*\n\n## How It Works\n\nSee [[Nonexistent]] [source: x.md].\n\n## Relationships\n\nNo links.\n\n## Open Questions\n\n> [!warning] CONTRADICTION\n> Status:** UNRESOLVED\n\n## Sources\n\n- x.md\n",
        )
        # No provenance sidecar, no sources_dir content

        issues = lint(wiki_dir=wiki_dir, sources_dir=sources_dir, schema=schema, verbose=False)
        # Should find issues from multiple checks
        all_codes = {i.code for i in issues}
        # At minimum: MISSING_FRONTMATTER, BROKEN_LINK, UNRESOLVED_CONTRADICTION,
        # MISSING_CONTENT_HASH, NO_SOURCES, EMPTY_SECTION, UNMARKED_INFERENCE
        assert len(all_codes) >= 3  # Multiple distinct checks fire

    def test_lint_json_output(self, tmp_path, capsys):
        """lint() with verbose=False returns issues; JSON serialization works."""
        wiki_dir = _make_wiki_dir(tmp_path)
        schema = load_schema()
        sources_dir = tmp_path / "sources"
        sources_dir.mkdir(parents=True, exist_ok=True)

        _make_concept_page(wiki_dir, name="Json_Test")

        issues = lint(wiki_dir=wiki_dir, sources_dir=sources_dir, schema=schema, verbose=False)
        # Verify we can serialize the issues to JSON (as the --json CLI flag would)
        output = json.dumps([
            {"severity": i.severity, "code": i.code, "page": i.page, "message": i.message}
            for i in issues
        ], indent=2)
        data = json.loads(output)
        assert isinstance(data, list)
        for entry in data:
            assert "severity" in entry
            assert "code" in entry
            assert "page" in entry
            assert "message" in entry