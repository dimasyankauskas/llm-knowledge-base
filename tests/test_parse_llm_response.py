"""Tests for LLM response parser module."""

from __future__ import annotations

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


from parse_llm_response import (
    parse_single_page,
    parse_multi_page_response,
    validate_page_wikilinks,
    extract_page_title,
    split_pages,
)


class TestParseSinglePage:
    """Tests for single page parsing."""

    def test_parses_frontmatter_and_content(self):
        """Should correctly parse YAML frontmatter and markdown content."""
        raw = """---
title: Test Page
type: concept
confidence: HIGH
created: '2026-04-19'
source_refs: []
content_hash: abc123
---
## Definition

This is a test concept.

## Key Properties

- Property one
- Property two
"""
        fm, content = parse_single_page(raw)
        assert fm["title"] == "Test Page"
        assert fm["type"] == "concept"
        assert "test concept" in content

    def test_injects_content_hash_if_tbd(self):
        """Should replace content_hash: TBD with actual hash."""
        raw = """---
title: Test Page
type: concept
content_hash: TBD
---
## Definition

Content here.
"""
        fm, content = parse_single_page(raw)
        assert fm["content_hash"] != "TBD"
        assert len(fm["content_hash"]) > 0

    def test_raises_on_empty_content(self):
        """Should raise ValueError when content is empty."""
        raw = """---
title: Test
type: concept
---
"""
        with pytest.raises(ValueError, match="content is empty"):
            parse_single_page(raw)

    def test_sets_default_type_if_missing(self):
        """Should set page type to default if not in frontmatter."""
        raw = """---
title: Test
---
## Definition

Content.
"""
        fm, _ = parse_single_page(raw, page_type="concept")
        assert fm["type"] == "concept"


class TestSplitPages:
    """Tests for multi-page splitting."""

    def test_single_page_no_separator(self):
        """Should return single page when no --- separators."""
        text = "## Definition\n\nContent only."
        pages = split_pages(text)
        assert len(pages) == 1

    def test_multiple_pages_separated(self):
        """Should split on --- separators."""
        # LLM output format without blank lines between pages
        text = """---
title: Page One
---
Content one.
---
---
title: Page Two
---
Content two.
"""
        pages = split_pages(text)
        assert len(pages) == 2
        for page in pages:
            assert page.startswith("---")

    def test_page_without_frontmatter_still_found(self):
        """Should find pages even if first one lacks frontmatter."""
        text = """This is intro text.

---
title: Page One
---
## Definition

Content.
"""
        pages = split_pages(text)
        assert len(pages) >= 1

    def test_multiple_frontmatter_blocks_merged(self):
        """Should merge pages with multiple frontmatter blocks into one.

        When the LLM outputs content_hash block + full frontmatter + body
        (with the second --- closing the frontmatter), split_pages should
        produce one page and parse_single_page should use the LAST
        frontmatter block.
        """
        text = """---
content_hash: abc123
type: concept
---

---
title: Real Page Title
type: concept
confidence: HIGH
created: '2026-04-20'
source_refs: []
---

## Definition

Content here.
"""
        pages = split_pages(text)
        assert len(pages) == 1
        # The single page should contain both frontmatter keys
        assert "title: Real Page Title" in pages[0]
        assert "content_hash: abc123" in pages[0]
        # And parse should get the right title from the last frontmatter
        fm, content = parse_single_page(pages[0])
        assert fm.get("title") == "Real Page Title"
        assert fm.get("confidence") == "HIGH"
        assert "## Definition" in content


class TestExtractPageTitle:
    """Tests for title extraction."""

    def test_prefers_frontmatter_title(self):
        """Should use frontmatter title over H1."""
        fm = {"title": "Frontmatter Title"}
        content = "# H1 Title\n## Definition\nContent."
        title = extract_page_title(fm, content, "default")
        assert title == "Frontmatter Title"

    def test_falls_back_to_h1(self):
        """Should extract H1 from content if no frontmatter title."""
        fm = {}
        content = "# Actual H1 Title\n## Definition\nContent."
        title = extract_page_title(fm, content, "default")
        assert title == "Actual H1 Title"

    def test_uses_default_when_neither(self):
        """Should use default when no frontmatter or H1."""
        fm = {}
        content = "## Definition\nNo title here."
        title = extract_page_title(fm, content, "My Default")
        assert title == "My Default"


class TestValidatePageWikilinks:
    """Tests for wikilink validation."""

    def test_all_links_valid(self):
        """Should return empty list when all links resolve."""
        content = "See [[Page One]] and [[Page Two]]."
        existing = {"Page One", "Page Two"}
        broken = validate_page_wikilinks(content, existing)
        assert broken == []

    def test_reports_broken_links(self):
        """Should return list of broken link targets."""
        content = "See [[Page One]] and [[Missing Page]]."
        existing = {"Page One"}
        broken = validate_page_wikilinks(content, existing)
        assert broken == ["Missing Page"]

    def test_case_insensitive_matching(self):
        """Wikilink matching should be case-insensitive."""
        content = "See [[page one]]."  # lowercase
        existing = {"Page One"}  # different case
        broken = validate_page_wikilinks(content, existing)
        assert broken == []

    def test_pending_pages_also_valid(self):
        """Should accept links to pages being created in same batch."""
        content = "See [[New Page]]."
        existing = {"Existing Page"}
        pending = {"New Page"}
        broken = validate_page_wikilinks(content, existing, pending)
        assert broken == []