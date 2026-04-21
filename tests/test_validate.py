"""Tests for the validate stage — frontmatter, sections, wikilinks, provenance,
fact/inference separation, draft validation, and draft promotion."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.schema import load_schema, get_page_type_config, get_section_rules
from scripts.utils import (
    DRAFTS_DIR,
    CONCEPTS_DIR,
    ENTITIES_DIR,
    write_page,
    write_provenance,
    read_page,
    extract_wikilinks,
)
from scripts.validate import (
    ValidationIssue,
    ValidationReport,
    validate_frontmatter,
    validate_sections,
    validate_wikilinks,
    validate_provenance,
    validate_fact_inference_separation,
    validate_draft,
    promote_draft,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_draft(
    tmp_path: Path,
    filename: str = "Test_Concept.md",
    metadata: dict | None = None,
    content: str = "",
) -> Path:
    """Create a draft page under tmp_path/wiki/drafts/."""
    drafts = tmp_path / "wiki" / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    page_path = drafts / filename

    if metadata is None:
        metadata = {
            "title": filename.replace(".md", "").replace("_", " "),
            "type": "concept",
            "confidence": "HIGH",
            "created": "2025-01-01",
            "source_refs": ["test_source.md"],
            "content_hash": "abc123",
        }

    import frontmatter

    post = frontmatter.Post(content, **metadata)
    page_path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return page_path


def _make_concept_content() -> str:
    """Return a valid concept page body with all required sections.

    Uses [[Test_Concept]] as a self-referencing wikilink so the link
    resolves (the draft page itself is included in all_page_names).
    """
    return """\
## Definition

A test concept definition with [source: test.md, §1].

## Key Properties

- Property one [source: test.md, §2]
- Property two [source: test.md, §3]

## How It Works

This is a mixed section. Some facts [source: test.md, §4] and some inference.

## Relationships

- [[Test_Concept]] relates to this [source: test.md, §5].

## Open Questions

> [!note] Inference: We might explore this further.

## Sources

- test.md
"""


def _make_entity_content() -> str:
    """Return a valid entity page body with all required sections.

    Uses [[Test_Entity]] as a self-referencing wikilink so the link
    resolves (the draft page itself is included in all_page_names).
    """
    return """\
## Overview

An entity overview with [source: entity_source.md, §1].

## Contributions

- Contributed to X [source: entity_source.md, §2]

## Relationships

- [[Test_Entity]] [source: entity_source.md, §3]

## Sources

- entity_source.md
"""


def _write_schema(tmp_path: Path) -> Path:
    """Write a copy of the real SCHEMA.yaml into tmp_path for tests."""
    real_schema = Path(__file__).parent.parent / "SCHEMA.yaml"
    schema_text = real_schema.read_text(encoding="utf-8")
    dest = tmp_path / "SCHEMA.yaml"
    dest.write_text(schema_text, encoding="utf-8")
    return dest


# ── validate_frontmatter ──────────────────────────────────────────────────────


class TestValidateFrontmatter:
    def test_validate_frontmatter_missing_fields(self, tmp_path):
        """Detect missing required frontmatter fields."""
        schema = load_schema()
        page_path = _make_draft(
            tmp_path,
            metadata={
                "title": "Missing Fields",
                "type": "concept",
                # missing: confidence, created, source_refs, content_hash
            },
        )
        issues = validate_frontmatter(page_path, schema)
        error_codes = [i.code for i in issues if i.severity == "ERROR"]
        assert "MISSING_FRONTMATTER" in error_codes
        # Should report multiple missing fields
        missing_field_msgs = [i.message for i in issues if i.code == "MISSING_FRONTMATTER"]
        assert len(missing_field_msgs) >= 3

    def test_validate_frontmatter_valid(self, tmp_path):
        """Valid frontmatter passes with no errors."""
        schema = load_schema()
        page_path = _make_draft(tmp_path)
        issues = validate_frontmatter(page_path, schema)
        error_issues = [i for i in issues if i.severity == "ERROR"]
        assert len(error_issues) == 0

    def test_validate_frontmatter_invalid_type(self, tmp_path):
        """Detect unknown page type."""
        schema = load_schema()
        page_path = _make_draft(
            tmp_path,
            metadata={
                "title": "Bad Type",
                "type": "nonexistent_type",
            },
        )
        issues = validate_frontmatter(page_path, schema)
        error_codes = [i.code for i in issues if i.severity == "ERROR"]
        assert "INVALID_TYPE" in error_codes


# ── validate_sections ──────────────────────────────────────────────────────────


class TestValidateSections:
    def test_validate_sections_missing_required(self, tmp_path):
        """Detect missing required sections."""
        schema = load_schema()
        page_path = _make_draft(
            tmp_path,
            content="## Only One Section\n\nSome content.\n",
        )
        issues = validate_sections(page_path, schema)
        missing_codes = [i.code for i in issues]
        assert "MISSING_SECTION" in missing_codes

    def test_validate_sections_empty_section(self, tmp_path):
        """Detect empty required sections (section heading with no content)."""
        schema = load_schema()
        # Build content with all required sections but some empty
        content = """\
## Definition

## Key Properties

## How It Works

Some content here.

## Relationships

## Open Questions

## Sources

"""
        page_path = _make_draft(tmp_path, content=content)
        issues = validate_sections(page_path, schema)
        empty_codes = [i.code for i in issues]
        assert "EMPTY_SECTION" in empty_codes


# ── validate_wikilinks ────────────────────────────────────────────────────────


class TestValidateWikilinks:
    def test_validate_wikilinks_broken(self, tmp_path):
        """Detect broken wikilinks that don't resolve to any page."""
        page_path = _make_draft(
            tmp_path,
            content="See [[Nonexistent Page]] for details.\n",
        )
        all_page_names = {"Test_Concept", "Other_Concept"}
        issues = validate_wikilinks(page_path, all_page_names)
        broken_codes = [i.code for i in issues]
        assert "BROKEN_LINK" in broken_codes

    def test_validate_wikilinks_valid(self, tmp_path):
        """Valid wikilinks pass with no errors."""
        page_path = _make_draft(
            tmp_path,
            content="See [[Other_Concept]] for details.\n",
        )
        all_page_names = {"Test_Concept", "Other_Concept"}
        issues = validate_wikilinks(page_path, all_page_names)
        broken_issues = [i for i in issues if i.code == "BROKEN_LINK"]
        assert len(broken_issues) == 0


# ── validate_provenance ───────────────────────────────────────────────────────


class TestValidateProvenance:
    def test_validate_provenance_missing(self, tmp_path):
        """Detect missing provenance sidecar."""
        page_path = _make_draft(tmp_path)
        # Don't create a .provenance.json sidecar
        issues = validate_provenance(page_path)
        error_codes = [i.code for i in issues]
        assert "MISSING_CONTENT_HASH" in error_codes

    def test_validate_provenance_valid(self, tmp_path):
        """Valid provenance sidecar passes."""
        page_path = _make_draft(tmp_path)
        prov_data = {
            "page": "Test_Concept",
            "content_hash": "abc123",
            "sources": [],
            "claims": [],
            "derived_concepts": [],
        }
        write_provenance(page_path, prov_data)
        issues = validate_provenance(page_path)
        error_issues = [i for i in issues if i.severity == "ERROR"]
        assert len(error_issues) == 0


# ── validate_fact_inference_separation ────────────────────────────────────────


class TestValidateFactInferenceSeparation:
    def test_validate_fact_inference_unmarked(self, tmp_path):
        """Detect unmarked inference in a facts_only section."""
        schema = load_schema()
        # Definition section is facts_only — a claim without [source: ...] is
        # an unmarked inference
        content = """\
## Definition

This concept will revolutionize the field and is the most important idea of the decade.

## Key Properties

- Property one [source: test.md, §2]

## How It Works

Some content.

## Relationships

- Relates to [[Something]] [source: test.md, §3]

## Open Questions

What next?

## Sources

- test.md
"""
        page_path = _make_draft(tmp_path, content=content)
        issues = validate_fact_inference_separation(page_path, schema)
        unmarked_codes = [i.code for i in issues]
        assert "UNMARKED_INFERENCE" in unmarked_codes

    def test_validate_fact_inference_marked_ok(self, tmp_path):
        """Properly marked inference in a facts_only section passes."""
        schema = load_schema()
        content = """\
## Definition

RAG combines retrieval and generation [source: lewis2020.pdf, §1].

> [!note] Inference: RAG will eventually replace most fine-tuning.

## Key Properties

- Reduces hallucination [source: lewis2020.pdf, §3]

## How It Works

Mixed content here.

## Relationships

- [[Retrieval]] [source: lewis2020.pdf, §4]

## Open Questions

What next?

## Sources

- lewis2020.pdf
"""
        page_path = _make_draft(tmp_path, content=content)
        issues = validate_fact_inference_separation(page_path, schema)
        unmarked_issues = [i for i in issues if i.code == "UNMARKED_INFERENCE"]
        assert len(unmarked_issues) == 0


# ── validate_draft (integration) ──────────────────────────────────────────────


class TestValidateDraft:
    def test_validate_draft_valid(self, tmp_path):
        """A complete, valid draft passes all checks with zero errors."""
        schema = load_schema()
        page_path = _make_draft(tmp_path, content=_make_concept_content())
        # Add provenance sidecar
        write_provenance(page_path, {
            "page": "Test_Concept",
            "content_hash": "abc123",
            "sources": [],
            "claims": [],
            "derived_concepts": [],
        })

        wiki_dir = tmp_path / "wiki"
        report = validate_draft(page_path, schema=schema, wiki_dir=wiki_dir)
        assert not report.has_errors, (
            f"Expected no errors, but got: {[str(i) for i in report.issues if i.severity == 'ERROR']}"
        )

    def test_validate_draft_invalid_stays(self, tmp_path):
        """An invalid draft should report errors but stay in drafts/."""
        schema = load_schema()
        # Missing most required frontmatter fields and sections
        page_path = _make_draft(
            tmp_path,
            metadata={"title": "Broken", "type": "concept"},
            content="## Definition\n\nSome content without sources.\n",
        )
        # No provenance sidecar

        report = validate_draft(page_path, schema=schema, wiki_dir=tmp_path / "wiki")
        assert report.has_errors
        # The page should still be in drafts/
        assert page_path.exists()


# ── promote_draft ────────────────────────────────────────────────────────────


class TestPromoteDraft:
    def test_promote_draft_valid(self, tmp_path):
        """A valid draft is moved to concepts/."""
        schema = load_schema()
        page_path = _make_draft(tmp_path, content=_make_concept_content())
        write_provenance(page_path, {
            "page": "Test_Concept",
            "content_hash": "abc123",
            "sources": [],
            "claims": [],
            "derived_concepts": [],
        })

        wiki_dir = tmp_path / "wiki"
        # Create concepts/ and entities/ dirs
        (wiki_dir / "concepts").mkdir(parents=True, exist_ok=True)
        (wiki_dir / "entities").mkdir(parents=True, exist_ok=True)

        new_path = promote_draft(page_path, schema=schema, wiki_dir=wiki_dir)
        assert new_path is not None
        assert new_path.exists()
        assert "concepts" in str(new_path)
        # Original draft should be gone
        assert not page_path.exists()

    def test_promote_draft_invalid(self, tmp_path):
        """An invalid draft is NOT moved (stays in drafts/)."""
        schema = load_schema()
        page_path = _make_draft(
            tmp_path,
            metadata={"title": "Broken", "type": "concept"},
            content="## Definition\n\nNo sources, no sections.\n",
        )

        wiki_dir = tmp_path / "wiki"
        (wiki_dir / "concepts").mkdir(parents=True, exist_ok=True)
        (wiki_dir / "entities").mkdir(parents=True, exist_ok=True)

        result = promote_draft(page_path, schema=schema, wiki_dir=wiki_dir)
        assert result is None
        # Draft should still exist
        assert page_path.exists()

    def test_promote_draft_entity(self, tmp_path):
        """An entity draft is moved to entities/."""
        schema = load_schema()
        entity_metadata = {
            "title": "Test Entity",
            "type": "entity",
            "entity_type": "organization",
            "created": "2025-01-01",
            "source_refs": ["entity_source.md"],
            "content_hash": "def456",
        }
        page_path = _make_draft(
            tmp_path,
            filename="Test_Entity.md",
            metadata=entity_metadata,
            content=_make_entity_content(),
        )
        write_provenance(page_path, {
            "page": "Test_Entity",
            "content_hash": "def456",
            "sources": [],
            "claims": [],
            "derived_concepts": [],
        })

        wiki_dir = tmp_path / "wiki"
        (wiki_dir / "concepts").mkdir(parents=True, exist_ok=True)
        (wiki_dir / "entities").mkdir(parents=True, exist_ok=True)

        new_path = promote_draft(page_path, schema=schema, wiki_dir=wiki_dir)
        assert new_path is not None
        assert new_path.exists()
        assert "entities" in str(new_path)

    def test_promote_draft_merges_existing_page_sources(self, tmp_path):
        """A draft with an existing title merges source_refs instead of losing prior evidence."""
        schema = load_schema()
        wiki_dir = tmp_path / "wiki"
        concepts = wiki_dir / "concepts"
        concepts.mkdir(parents=True, exist_ok=True)
        (wiki_dir / "entities").mkdir(parents=True, exist_ok=True)

        existing = concepts / "Test_Concept.md"
        write_page(
            existing,
            {
                "title": "Test Concept",
                "type": "concept",
                "confidence": "MEDIUM",
                "created": "2025-01-01",
                "source_refs": ["first.md"],
                "content_hash": "oldhash",
            },
            _make_concept_content().replace("test.md", "first.md"),
        )
        write_provenance(existing, {
            "page": "Test_Concept",
            "content_hash": "oldhash",
            "sources": [{"file": "first.md", "content_hash": "111"}],
            "claims": [],
            "derived_concepts": [],
        })

        draft = _make_draft(
            tmp_path,
            filename="Test_Concept.md",
            metadata={
                "title": "Test Concept",
                "type": "concept",
                "confidence": "HIGH",
                "created": "2025-01-02",
                "source_refs": ["second.md"],
                "content_hash": "newhash",
            },
            content=_make_concept_content().replace("test.md", "second.md"),
        )
        write_provenance(draft, {
            "page": "Test_Concept",
            "content_hash": "newhash",
            "sources": [{"file": "second.md", "content_hash": "222"}],
            "claims": [],
            "derived_concepts": [],
        })

        promoted = promote_draft(draft, schema=schema, wiki_dir=wiki_dir)

        assert promoted == existing
        assert not draft.exists()
        post = read_page(existing)
        assert post.metadata["source_refs"] == ["first.md", "second.md"]
        prov = json.loads(existing.with_suffix(".md.provenance.json").read_text(encoding="utf-8"))
        assert {source["file"] for source in prov["sources"]} == {"first.md", "second.md"}
        assert prov["claims"]


# ── ValidationIssue / ValidationReport ────────────────────────────────────────


class TestValidationIssueAndReport:
    def test_validation_issue_str(self):
        """ValidationIssue __str__ includes icon, code, page, and message."""
        issue = ValidationIssue("ERROR", "MISSING_FRONTMATTER", "RAG", "Missing field: confidence")
        s = str(issue)
        assert "MISSING_FRONTMATTER" in s
        assert "RAG" in s
        assert "confidence" in s

    def test_validation_report_properties(self):
        """ValidationReport correctly counts errors and warnings."""
        report = ValidationReport(Path("/tmp/test.md"), "Test")
        report.add_error("E1", "error msg 1")
        report.add_warning("W1", "warning msg 1")
        report.add_error("E2", "error msg 2")

        assert report.has_errors is True
        assert report.error_count == 2
        assert report.warning_count == 1
        assert len(report.issues) == 3

    def test_validation_report_no_errors(self):
        """ValidationReport with only warnings has no errors."""
        report = ValidationReport(Path("/tmp/test.md"), "Test")
        report.add_warning("W1", "warning msg 1")
        assert report.has_errors is False
        assert report.error_count == 0
        assert report.warning_count == 1
