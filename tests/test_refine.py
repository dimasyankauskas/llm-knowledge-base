"""Tests for the refine stage — gap analysis, contradiction detection,
counter-argument hints, staleness checking, and task aggregation."""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter
import pytest

from scripts.utils import write_page, write_provenance, hash_content
from scripts.refine import (
    find_thin_pages,
    find_contradictions,
    find_gap_pages,
    check_staleness_all,
    find_pages_without_counter_args,
    generate_refinement_tasks,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_wiki_dir(tmp_path: Path) -> Path:
    """Create wiki/ with concepts/ and entities/ subdirs."""
    wiki_dir = tmp_path / "wiki"
    (wiki_dir / "concepts").mkdir(parents=True, exist_ok=True)
    (wiki_dir / "entities").mkdir(parents=True, exist_ok=True)
    return wiki_dir


def _make_sources_dir(tmp_path: Path) -> Path:
    """Create sources/ directory."""
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    return sources_dir


def _write_concept(
    wiki_dir: Path,
    name: str,
    content: str,
    confidence: str = "HIGH",
    extra_metadata: dict | None = None,
) -> Path:
    """Write a concept page to wiki/concepts/."""
    concepts_dir = wiki_dir / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    page_path = concepts_dir / f"{name}.md"
    metadata = {
        "title": name.replace("_", " "),
        "type": "concept",
        "confidence": confidence,
        "created": "2025-01-01",
        "source_refs": ["test.md"],
        "content_hash": hash_content(content),
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    write_page(page_path, metadata, content)
    return page_path


def _write_entity(
    wiki_dir: Path,
    name: str,
    content: str,
) -> Path:
    """Write an entity page to wiki/entities/."""
    entities_dir = wiki_dir / "entities"
    entities_dir.mkdir(parents=True, exist_ok=True)
    page_path = entities_dir / f"{name}.md"
    metadata = {
        "title": name.replace("_", " "),
        "type": "entity",
        "entity_type": "organization",
        "created": "2025-01-01",
        "source_refs": ["test.md"],
        "content_hash": hash_content(content),
    }
    write_page(page_path, metadata, content)
    return page_path


# ── find_thin_pages ─────────────────────────────────────────────────────────


class TestFindThinPages:
    def test_find_thin_pages_with_few_sections(self, tmp_path):
        """Page with 1 content section is thin."""
        wiki_dir = _make_wiki_dir(tmp_path)
        content = "## Definition\n\nSome content.\n"
        _write_concept(wiki_dir, "Thin_Concept", content)

        result = find_thin_pages(wiki_dir=wiki_dir)
        assert len(result) == 1
        assert result[0]["page"] == "Thin_Concept"
        assert result[0]["section_count"] == 1
        assert result[0]["type"] == "concept"

    def test_find_thin_pages_with_enough_sections(self, tmp_path):
        """Page with 3+ sections is not thin."""
        wiki_dir = _make_wiki_dir(tmp_path)
        content = (
            "## Definition\n\nDef.\n\n"
            "## Key Properties\n\nProps.\n\n"
            "## How It Works\n\nWorks.\n"
        )
        _write_concept(wiki_dir, "Thick_Concept", content)

        result = find_thin_pages(wiki_dir=wiki_dir)
        thick_names = [r["page"] for r in result]
        assert "Thick_Concept" not in thick_names


# ── find_contradictions ──────────────────────────────────────────────────────


class TestFindContradictions:
    def test_find_contradictions_unresolved(self, tmp_path):
        """Page with unresolved contradiction callout is detected."""
        wiki_dir = _make_wiki_dir(tmp_path)
        content = (
            "## Definition\n\n"
            "Some claim.\n\n"
            "> [!warning] CONTRADICTION\n"
            "> This contradicts X.\n"
            "> UNRESOLVED\n\n"
            "## Key Properties\n\nProps.\n"
        )
        _write_concept(wiki_dir, "Contradicted", content)

        result = find_contradictions(wiki_dir=wiki_dir)
        assert len(result) == 1
        assert result[0]["page"] == "Contradicted"
        assert result[0]["callout_count"] == 1

    def test_find_contradictions_resolved(self, tmp_path):
        """Page with resolved contradiction is not flagged."""
        wiki_dir = _make_wiki_dir(tmp_path)
        content = (
            "## Definition\n\n"
            "Some claim.\n\n"
            "> [!warning] CONTRADICTION\n"
            "> This contradicts X.\n"
            "> RESOLVED: We accept X.\n\n"
            "## Key Properties\n\nProps.\n"
        )
        _write_concept(wiki_dir, "Resolved_Concept", content)

        result = find_contradictions(wiki_dir=wiki_dir)
        names = [r["page"] for r in result]
        assert "Resolved_Concept" not in names

    def test_find_contradictions_no_contradiction(self, tmp_path):
        """Page without contradictions is clean."""
        wiki_dir = _make_wiki_dir(tmp_path)
        content = "## Definition\n\nNo contradictions here.\n\n## Key Properties\n\nProps.\n"
        _write_concept(wiki_dir, "Clean_Concept", content)

        result = find_contradictions(wiki_dir=wiki_dir)
        assert len(result) == 0


# ── find_gap_pages ───────────────────────────────────────────────────────────


class TestFindGapPages:
    def test_find_gap_pages_broken_link(self, tmp_path):
        """Wikilink to non-existent page is a gap."""
        wiki_dir = _make_wiki_dir(tmp_path)
        content = "## Definition\n\nSee [[Missing_Page]] for details.\n"
        _write_concept(wiki_dir, "Source_Page", content)

        result = find_gap_pages(wiki_dir=wiki_dir)
        assert len(result) >= 1
        gap_targets = [r["target"] for r in result]
        assert "Missing_Page" in gap_targets

    def test_find_gap_pages_valid_link(self, tmp_path):
        """Wikilink to existing page is not a gap."""
        wiki_dir = _make_wiki_dir(tmp_path)
        # Create two pages that link to each other
        content_a = "## Definition\n\nSee [[Page_B]] for details.\n"
        content_b = "## Definition\n\nSee [[Page_A]] for details.\n"
        _write_concept(wiki_dir, "Page_A", content_a)
        _write_concept(wiki_dir, "Page_B", content_b)

        result = find_gap_pages(wiki_dir=wiki_dir)
        gap_targets = [r["target"] for r in result]
        assert "Page_A" not in gap_targets
        assert "Page_B" not in gap_targets


# ── find_pages_without_counter_args ──────────────────────────────────────────


class TestFindPagesWithoutCounterArgs:
    def test_find_pages_without_counter_args(self, tmp_path):
        """HIGH confidence page without counter-arguments section is flagged."""
        wiki_dir = _make_wiki_dir(tmp_path)
        content = (
            "## Definition\n\nDef.\n\n"
            "## Key Properties\n\nProps.\n\n"
            "## How It Works\n\nWorks.\n"
        )
        _write_concept(wiki_dir, "High_No_Counter", content, confidence="HIGH")

        result = find_pages_without_counter_args(wiki_dir=wiki_dir)
        assert len(result) == 1
        assert result[0]["page"] == "High_No_Counter"
        assert result[0]["confidence"] == "HIGH"

    def test_find_pages_with_counter_args(self, tmp_path):
        """HIGH confidence page with counter-arguments section is not flagged."""
        wiki_dir = _make_wiki_dir(tmp_path)
        content = (
            "## Definition\n\nDef.\n\n"
            "## Key Properties\n\nProps.\n\n"
            "## Counter-Arguments\n\nSome counters.\n"
        )
        _write_concept(wiki_dir, "High_With_Counter", content, confidence="HIGH")

        result = find_pages_without_counter_args(wiki_dir=wiki_dir)
        names = [r["page"] for r in result]
        assert "High_With_Counter" not in names


# ── check_staleness_all ─────────────────────────────────────────────────────


class TestCheckStalenessAll:
    def test_check_staleness_stale_page(self, tmp_path):
        """Page with changed source hash is detected as stale."""
        wiki_dir = _make_wiki_dir(tmp_path)
        sources_dir = _make_sources_dir(tmp_path)

        # Create a source file
        source_file = sources_dir / "test.md"
        source_file.write_text("Original content", encoding="utf-8")

        # Create a concept page
        content = "## Definition\n\nDef.\n"
        page_path = _write_concept(wiki_dir, "Stale_Concept", content)

        # Write provenance with an old hash
        from scripts.utils import hash_file
        old_hash = "old_hash_that_doesnt_match"
        write_provenance(page_path, {
            "page": "Stale_Concept",
            "content_hash": "abc123",
            "sources": [{"file": "test.md", "content_hash": old_hash, "sections_used": []}],
            "claims": [],
            "derived_concepts": [],
        })

        result = check_staleness_all(wiki_dir=wiki_dir, sources_dir=sources_dir)
        assert "Stale_Concept" in result

    def test_check_staleness_fresh_page(self, tmp_path):
        """Page with matching source hash is not stale."""
        wiki_dir = _make_wiki_dir(tmp_path)
        sources_dir = _make_sources_dir(tmp_path)

        # Create a source file
        source_file = sources_dir / "test.md"
        source_file.write_text("Original content", encoding="utf-8")

        # Create a concept page
        content = "## Definition\n\nDef.\n"
        page_path = _write_concept(wiki_dir, "Fresh_Concept", content)

        # Write provenance with current hash
        from scripts.utils import hash_file
        current_hash = hash_file(source_file)
        write_provenance(page_path, {
            "page": "Fresh_Concept",
            "content_hash": "abc123",
            "sources": [{"file": "test.md", "content_hash": current_hash, "sections_used": []}],
            "claims": [],
            "derived_concepts": [],
        })

        result = check_staleness_all(wiki_dir=wiki_dir, sources_dir=sources_dir)
        assert "Fresh_Concept" not in result


# ── generate_refinement_tasks ────────────────────────────────────────────────


class TestGenerateRefinementTasks:
    def test_generate_refinement_tasks(self, tmp_path):
        """Aggregates all types of tasks with correct priorities."""
        wiki_dir = _make_wiki_dir(tmp_path)
        sources_dir = _make_sources_dir(tmp_path)

        # Thin page (1 section)
        _write_concept(
            wiki_dir, "Thin", "## Definition\n\nThin page.\n"
        )

        # Page with unresolved contradiction
        contra_content = (
            "## Definition\n\n"
            "Some claim.\n\n"
            "> [!warning] CONTRADICTION\n"
            "> Conflicting info.\n"
            "> UNRESOLVED\n\n"
            "## Key Properties\n\nProps.\n"
        )
        _write_concept(wiki_dir, "Contradicted", contra_content)

        # Page linking to non-existent target (gap)
        gap_content = "## Definition\n\nSee [[NonExistent]].\n"
        _write_concept(wiki_dir, "Linker", gap_content)

        # HIGH confidence page without counter-arguments
        no_counter_content = (
            "## Definition\n\nDef.\n\n"
            "## Key Properties\n\nProps.\n\n"
            "## How It Works\n\nWorks.\n"
        )
        _write_concept(wiki_dir, "NoCounter", no_counter_content, confidence="HIGH")

        tasks = generate_refinement_tasks(
            wiki_dir=wiki_dir,
            sources_dir=sources_dir,
        )

        task_types = [t["task_type"] for t in tasks]
        assert "thin_page" in task_types
        assert "contradiction" in task_types
        assert "gap" in task_types
        assert "missing_counter_args" in task_types

        # Check severity assignments
        contra_tasks = [t for t in tasks if t["task_type"] == "contradiction"]
        assert all(t["severity"] == "high" for t in contra_tasks)

        gap_tasks = [t for t in tasks if t["task_type"] == "gap"]
        assert all(t["severity"] == "high" for t in gap_tasks)

        thin_tasks = [t for t in tasks if t["task_type"] == "thin_page"]
        assert all(t["severity"] == "medium" for t in thin_tasks)

        counter_tasks = [t for t in tasks if t["task_type"] == "missing_counter_args"]
        assert all(t["severity"] == "low" for t in counter_tasks)

        # Each task must have task_type, severity, page, details
        for t in tasks:
            assert "task_type" in t
            assert "severity" in t
            assert "page" in t
            assert "details" in t