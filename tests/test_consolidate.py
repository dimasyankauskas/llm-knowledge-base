"""Tests for v2 consolidate stage in scripts/consolidate.py.

Tests duplicate detection, index generation, timeline generation,
and page merging.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path

import frontmatter
import pytest

from scripts.utils import write_page


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_wiki(tmp_path: Path, pages: dict[str, dict]) -> Path:
    """Create a minimal wiki structure in tmp_path.

    Args:
        pages: dict mapping filename -> {"metadata": dict, "content": str}
            Filename should be like "concepts/RAG.md" or "entities/Org.md"

    Returns:
        The wiki_dir path.
    """
    wiki_dir = tmp_path / "wiki"
    for relpath, page_data in pages.items():
        page_path = wiki_dir / relpath
        write_page(page_path, page_data.get("metadata", {}), page_data.get("content", ""))
    return wiki_dir


# ── find_duplicate_pages ────────────────────────────────────────────────────


class TestFindDuplicatePages:
    def test_find_duplicate_pages_alias_overlap(self, tmp_path):
        """Two pages with overlapping aliases are detected as duplicates."""
        wiki_dir = _make_wiki(tmp_path, {
            "concepts/RAG.md": {
                "metadata": {
                    "title": "Retrieval-Augmented Generation",
                    "type": "concept",
                    "aliases": ["RAG", "Retrieval Augmented Generation"],
                },
                "content": "RAG combines retrieval and generation.",
            },
            "concepts/Retrieval_Augmented_Generation.md": {
                "metadata": {
                    "title": "Retrieval Augmented Generation",
                    "type": "concept",
                    "aliases": ["RAG"],
                },
                "content": "RAG is a technique that augments generation with retrieval.",
            },
        })

        from scripts.consolidate import find_duplicate_pages

        dupes = find_duplicate_pages(wiki_dir=wiki_dir)

        # Should find at least one duplicate pair due to alias overlap
        assert len(dupes) >= 1
        # Check that the reason mentions alias
        alias_dupes = [d for d in dupes if "alias" in d[2].lower()]
        assert len(alias_dupes) >= 1, f"Expected alias overlap, got: {dupes}"

    def test_find_duplicate_pages_title_similarity(self, tmp_path):
        """Pages with similar titles (case-insensitive, special chars removed) are detected."""
        # Use distinct filenames that normalize identically when special chars
        # are stripped: "Neural-IR" and "Neural IR" both normalize to "neuralir"
        wiki_dir = _make_wiki(tmp_path, {
            "concepts/Neural-IR.md": {
                "metadata": {"title": "Neural IR", "type": "concept"},
                "content": "Neural information retrieval.",
            },
            "concepts/Neural_IR.md": {
                "metadata": {"title": "Neural_IR", "type": "concept"},
                "content": "Same concept, different punctuation.",
            },
        })

        from scripts.consolidate import find_duplicate_pages

        dupes = find_duplicate_pages(wiki_dir=wiki_dir)

        # Should find at least one duplicate pair due to title similarity
        assert len(dupes) >= 1
        title_dupes = [d for d in dupes if "title" in d[2].lower()]
        assert len(title_dupes) >= 1, f"Expected title similarity match, got: {dupes}"

    def test_find_no_duplicates(self, tmp_path):
        """Distinct pages with no overlap return empty list."""
        wiki_dir = _make_wiki(tmp_path, {
            "concepts/RAG.md": {
                "metadata": {"title": "RAG", "type": "concept"},
                "content": "Retrieval-augmented generation.",
            },
            "concepts/Transformers.md": {
                "metadata": {"title": "Transformers", "type": "concept"},
                "content": "Transformer architecture.",
            },
            "entities/OpenAI.md": {
                "metadata": {"title": "OpenAI", "type": "entity"},
                "content": "AI research organization.",
            },
        })

        from scripts.consolidate import find_duplicate_pages

        dupes = find_duplicate_pages(wiki_dir=wiki_dir)
        assert dupes == [], f"Expected no duplicates, got: {dupes}"


# ── generate_indexes ────────────────────────────────────────────────────────


class TestGenerateIndexes:
    def test_generate_indexes_creates_master_index(self, tmp_path):
        """_index.md is created with all wiki pages listed."""
        wiki_dir = _make_wiki(tmp_path, {
            "concepts/RAG.md": {
                "metadata": {"title": "RAG", "type": "concept", "created": "2024-01-01"},
                "content": "## Definition\nRAG combines retrieval and generation.",
            },
            "concepts/Transformers.md": {
                "metadata": {"title": "Transformers", "type": "concept", "created": "2024-02-01"},
                "content": "## Definition\nTransformer architecture.",
            },
        })

        from scripts.consolidate import generate_indexes

        generate_indexes(wiki_dir=wiki_dir)

        index_path = wiki_dir / "indexes" / "_index.md"
        assert index_path.exists(), "_index.md should be created"
        content = index_path.read_text(encoding="utf-8")
        assert "RAG" in content
        assert "Transformers" in content

    def test_generate_indexes_creates_by_topic(self, tmp_path):
        """by-topic.md is created grouping pages by topic tags."""
        wiki_dir = _make_wiki(tmp_path, {
            "concepts/RAG.md": {
                "metadata": {"title": "RAG", "type": "concept", "tags": ["retrieval", "generation"]},
                "content": "RAG combines retrieval and generation.",
            },
            "concepts/Transformers.md": {
                "metadata": {"title": "Transformers", "type": "concept", "tags": ["architecture", "generation"]},
                "content": "Transformer architecture.",
            },
        })

        from scripts.consolidate import generate_indexes

        generate_indexes(wiki_dir=wiki_dir)

        topic_path = wiki_dir / "indexes" / "by-topic.md"
        assert topic_path.exists(), "by-topic.md should be created"
        content = topic_path.read_text(encoding="utf-8")
        assert "retrieval" in content or "generation" in content

    def test_generate_indexes_creates_by_source(self, tmp_path):
        """by-source.md is created grouping pages by source_refs."""
        wiki_dir = _make_wiki(tmp_path, {
            "concepts/RAG.md": {
                "metadata": {
                    "title": "RAG",
                    "type": "concept",
                    "source_refs": ["paper_rag2020.pdf"],
                },
                "content": "RAG combines retrieval and generation.",
            },
            "concepts/Transformers.md": {
                "metadata": {
                    "title": "Transformers",
                    "type": "concept",
                    "source_refs": ["paper_attention2017.pdf"],
                },
                "content": "Transformer architecture.",
            },
        })

        from scripts.consolidate import generate_indexes

        generate_indexes(wiki_dir=wiki_dir)

        source_path = wiki_dir / "indexes" / "by-source.md"
        assert source_path.exists(), "by-source.md should be created"
        content = source_path.read_text(encoding="utf-8")
        assert "paper_rag2020.pdf" in content

    def test_generate_indexes_creates_recently_updated(self, tmp_path):
        """recently-updated.md is created with pages modified in last 7 days."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        wiki_dir = _make_wiki(tmp_path, {
            "concepts/RAG.md": {
                "metadata": {
                    "title": "RAG",
                    "type": "concept",
                    "last_updated": today,
                },
                "content": "RAG combines retrieval and generation.",
            },
            "concepts/Old_Page.md": {
                "metadata": {
                    "title": "Old Page",
                    "type": "concept",
                    "last_updated": "2020-01-01",
                },
                "content": "Old content.",
            },
        })

        from scripts.consolidate import generate_indexes

        generate_indexes(wiki_dir=wiki_dir)

        recent_path = wiki_dir / "indexes" / "recently-updated.md"
        assert recent_path.exists(), "recently-updated.md should be created"
        content = recent_path.read_text(encoding="utf-8")
        assert "RAG" in content


# ── merge_pages ─────────────────────────────────────────────────────────────


class TestMergePages:
    def test_merge_pages_combines_content(self, tmp_path):
        """Merging combines primary content with secondary's unique content."""
        wiki_dir = _make_wiki(tmp_path, {
            "concepts/RAG.md": {
                "metadata": {
                    "title": "RAG",
                    "type": "concept",
                    "confidence": "HIGH",
                    "aliases": ["Retrieval-Augmented Generation"],
                    "source_refs": ["paper_rag2020.pdf"],
                    "tags": ["retrieval", "generation"],
                },
                "content": "## Definition\nRAG combines retrieval and generation.",
            },
            "concepts/Retrieval_Augmented_Generation.md": {
                "metadata": {
                    "title": "Retrieval Augmented Generation",
                    "type": "concept",
                    "confidence": "MEDIUM",
                    "aliases": ["RAG technique"],
                    "source_refs": ["paper_rag_survey2023.pdf"],
                    "tags": ["retrieval", "survey"],
                },
                "content": "## Key Properties\nRAG reduces hallucination.",
            },
        })

        from scripts.consolidate import merge_pages

        result = merge_pages("RAG", "Retrieval_Augmented_Generation", wiki_dir=wiki_dir)

        assert result is True

        # Check primary page now has combined content
        primary_path = wiki_dir / "concepts" / "RAG.md"
        post = frontmatter.load(str(primary_path))
        content = post.content
        assert "RAG combines retrieval and generation" in content
        assert "RAG reduces hallucination" in content

    def test_merge_pages_updates_links(self, tmp_path):
        """Other pages' wikilinks pointing to secondary are updated to primary."""
        wiki_dir = _make_wiki(tmp_path, {
            "concepts/RAG.md": {
                "metadata": {"title": "RAG", "type": "concept"},
                "content": "## Definition\nRAG combines retrieval and generation.",
            },
            "concepts/Retrieval_Augmented_Generation.md": {
                "metadata": {"title": "Retrieval Augmented Generation", "type": "concept"},
                "content": "Secondary content.",
            },
            "concepts/Transformer.md": {
                "metadata": {"title": "Transformer", "type": "concept"},
                "content": "See [[Retrieval_Augmented_Generation]] for details.",
            },
        })

        from scripts.consolidate import merge_pages

        merge_pages("RAG", "Retrieval_Augmented_Generation", wiki_dir=wiki_dir)

        # Check that the Transformer page now links to RAG instead
        transformer_path = wiki_dir / "concepts" / "Transformer.md"
        content = transformer_path.read_text(encoding="utf-8")
        assert "[[RAG]]" in content
        assert "[[Retrieval_Augmented_Generation]]" not in content

    def test_merge_pages_deletes_secondary(self, tmp_path):
        """Secondary page (both .md and .provenance.json) is deleted after merge."""
        wiki_dir = _make_wiki(tmp_path, {
            "concepts/RAG.md": {
                "metadata": {"title": "RAG", "type": "concept"},
                "content": "## Definition\nRAG combines retrieval and generation.",
            },
            "concepts/Retrieval_Augmented_Generation.md": {
                "metadata": {"title": "Retrieval Augmented Generation", "type": "concept"},
                "content": "## Key Properties\nRAG reduces hallucination.",
            },
        })

        # Create a provenance sidecar for the secondary page
        sec_path = wiki_dir / "concepts" / "Retrieval_Augmented_Generation.md"
        prov_path = sec_path.with_suffix(sec_path.suffix + ".provenance.json")
        prov_path.parent.mkdir(parents=True, exist_ok=True)
        import json
        prov_path.write_text(json.dumps({"page": "Retrieval_Augmented_Generation", "content_hash": "abc123"}))

        from scripts.consolidate import merge_pages

        merge_pages("RAG", "Retrieval_Augmented_Generation", wiki_dir=wiki_dir)

        # Secondary page should be deleted
        assert not sec_path.exists(), "Secondary .md should be deleted"
        assert not prov_path.exists(), "Secondary .provenance.json should be deleted"

    def test_merge_pages_nonexistent_primary(self, tmp_path):
        """merge_pages returns False if primary page doesn't exist."""
        wiki_dir = _make_wiki(tmp_path, {
            "concepts/Some_Page.md": {
                "metadata": {"title": "Some Page", "type": "concept"},
                "content": "Some content.",
            },
        })

        from scripts.consolidate import merge_pages

        result = merge_pages("NonExistent", "Some_Page", wiki_dir=wiki_dir)
        assert result is False


# ── generate_timelines ──────────────────────────────────────────────────────


class TestGenerateTimelines:
    def test_generate_timelines_with_dated_events(self, tmp_path):
        """Timeline is generated when there are enough dated concept pages."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        pages = {}
        for i in range(5):
            name = f"Concept_{i}"
            pages[f"concepts/{name}.md"] = {
                "metadata": {
                    "title": name,
                    "type": "concept",
                    "created": f"2024-0{i+1}-01",
                },
                "content": f"## Definition\nConcept {i} definition.",
            }

        wiki_dir = _make_wiki(tmp_path, pages)

        from scripts.consolidate import generate_timelines

        generate_timelines(wiki_dir=wiki_dir)

        timelines_dir = wiki_dir / "timelines"
        assert timelines_dir.exists(), "timelines directory should be created"
        # Should have at least one timeline file
        timeline_files = list(timelines_dir.glob("*.md"))
        assert len(timeline_files) >= 1, f"Expected timeline files, found: {timeline_files}"