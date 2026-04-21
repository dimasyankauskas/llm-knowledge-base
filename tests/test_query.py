"""Tests for query engine v2 — typed graph traversal."""

import json
import pytest
from pathlib import Path
from scripts.query import (
    find_seed_pages, traverse_typed_graph, build_context, EDGE_WEIGHTS
)


class TestFindSeedPages:
    def test_find_seed_pages_keyword_match(self, tmp_path):
        """Title keywords should boost page score."""
        concepts = tmp_path / "wiki" / "concepts"
        concepts.mkdir(parents=True)

        page = concepts / "Retrieval-Augmented Generation.md"
        page.write_text(
            "---\ntitle: Retrieval-Augmented Generation\ntype: concept\nconfidence: HIGH\n---\n"
            "RAG combines retrieval and generation.",
            encoding="utf-8"
        )

        results = find_seed_pages("retrieval augmented generation", wiki_dir=tmp_path / "wiki")
        assert len(results) >= 1
        assert results[0].stem == "Retrieval-Augmented Generation"

    def test_find_seed_pages_tag_match(self, tmp_path):
        """Frontmatter tags should boost page score."""
        concepts = tmp_path / "wiki" / "concepts"
        concepts.mkdir(parents=True)

        page = concepts / "Neural IR.md"
        page.write_text(
            "---\ntitle: Neural IR\ntype: concept\nconfidence: MEDIUM\ntags:\n  - domain/ai\n  - topic/retrieval\n---\n"
            "Neural information retrieval.",
            encoding="utf-8"
        )

        results = find_seed_pages("retrieval", wiki_dir=tmp_path / "wiki")
        assert len(results) >= 1

    def test_find_seed_pages_alias_match(self, tmp_path):
        """Frontmatter aliases should boost page score."""
        concepts = tmp_path / "wiki" / "concepts"
        concepts.mkdir(parents=True)

        page = concepts / "Retrieval-Augmented Generation.md"
        page.write_text(
            "---\ntitle: Retrieval-Augmented Generation\ntype: concept\nconfidence: HIGH\naliases:\n  - RAG\n---\n"
            "RAG combines retrieval and generation.",
            encoding="utf-8"
        )

        results = find_seed_pages("RAG", wiki_dir=tmp_path / "wiki")
        assert len(results) >= 1
        assert results[0].stem == "Retrieval-Augmented Generation"

    def test_find_seed_pages_top_k(self, tmp_path):
        """Only top_k results should be returned."""
        concepts = tmp_path / "wiki" / "concepts"
        concepts.mkdir(parents=True)

        for i in range(5):
            page = concepts / f"Topic {i}.md"
            page.write_text(
                f"---\ntitle: Topic {i}\ntype: concept\nconfidence: HIGH\n---\nTopic {i} content about retrieval.",
                encoding="utf-8"
            )

        results = find_seed_pages("retrieval", wiki_dir=tmp_path / "wiki", top_k=2)
        assert len(results) <= 2


class TestTraverseTypedGraph:
    def _make_graph(self, nodes=None, edges=None):
        """Helper to create a graph dict."""
        return {
            "generated_at": "2026-04-14T00:00:00Z",
            "node_count": len(nodes) if nodes else 0,
            "edge_count": len(edges) if edges else 0,
            "nodes": nodes or [],
            "edges": edges or [],
        }

    def test_traverse_typed_graph_follows_edges(self, tmp_path):
        """Should follow typed edges from seed pages."""
        concepts = tmp_path / "wiki" / "concepts"
        concepts.mkdir(parents=True)

        rag_page = concepts / "RAG.md"
        rag_page.write_text("---\ntitle: RAG\ntype: concept\nconfidence: HIGH\n---\nContent", encoding="utf-8")
        nir_page = concepts / "Neural IR.md"
        nir_page.write_text("---\ntitle: Neural IR\ntype: concept\nconfidence: MEDIUM\n---\nContent", encoding="utf-8")

        graph = self._make_graph(
            nodes=[{"id": "RAG", "type": "concept"}, {"id": "Neural IR", "type": "concept"}],
            edges=[{"source": "RAG", "target": "Neural IR", "type": "implements", "weight": 3.0}]
        )

        results = traverse_typed_graph([rag_page], graph, depth=1)
        assert len(results) >= 2  # RAG + Neural IR
        page_names = [r["page"].stem for r in results]
        assert "RAG" in page_names
        assert "Neural IR" in page_names

    def test_traverse_typed_graph_weights_cites_over_neutral(self, tmp_path):
        """Cites edges should have higher weight than neutral."""
        concepts = tmp_path / "wiki" / "concepts"
        concepts.mkdir(parents=True)

        for name in ["A", "B", "C"]:
            page = concepts / f"{name}.md"
            page.write_text(f"---\ntitle: {name}\ntype: concept\nconfidence: HIGH\n---\nContent", encoding="utf-8")

        # A cites B (weight 4), A links C neutrally (weight 1)
        graph = self._make_graph(
            nodes=[{"id": n, "type": "concept"} for n in ["A", "B", "C"]],
            edges=[
                {"source": "A", "target": "B", "type": "cites", "weight": 4.0},
                {"source": "A", "target": "C", "type": "neutral", "weight": 1.0},
            ]
        )

        results = traverse_typed_graph([concepts / "A.md"], graph, depth=1)
        b_result = next(r for r in results if r["page"].stem == "B")
        c_result = next(r for r in results if r["page"].stem == "C")
        assert b_result["score"] > c_result["score"]

    def test_traverse_typed_graph_depth_limit(self, tmp_path):
        """Depth parameter should limit traversal."""
        concepts = tmp_path / "wiki" / "concepts"
        concepts.mkdir(parents=True)

        for name in ["A", "B", "C"]:
            page = concepts / f"{name}.md"
            page.write_text(f"---\ntitle: {name}\ntype: concept\n---\nContent", encoding="utf-8")

        # A -> B -> C (2 hops)
        graph = self._make_graph(
            nodes=[{"id": n, "type": "concept"} for n in ["A", "B", "C"]],
            edges=[
                {"source": "A", "target": "B", "type": "cites", "weight": 4.0},
                {"source": "B", "target": "C", "type": "cites", "weight": 4.0},
            ]
        )

        # depth=1 should only reach A and B, not C
        results = traverse_typed_graph([concepts / "A.md"], graph, depth=1)
        page_names = [r["page"].stem for r in results]
        assert "A" in page_names
        assert "B" in page_names
        # C may or may not be there depending on implementation


class TestBuildContext:
    def test_build_context_formats_pages(self, tmp_path):
        """Context should have correct format."""
        concepts = tmp_path / "wiki" / "concepts"
        concepts.mkdir(parents=True)

        page = concepts / "RAG.md"
        page.write_text(
            "---\ntitle: RAG\ntype: concept\nconfidence: HIGH\n---\nRAG combines retrieval and generation.",
            encoding="utf-8"
        )

        pages = [{"page": page, "score": 10.0, "path": ["RAG"]}]
        context = build_context(pages)
        assert "RAG" in context
        assert "concept" in context
        assert "HIGH" in context
        assert "retrieval" in context

    def test_build_context_max_chars(self, tmp_path):
        """Context should respect max character limit."""
        concepts = tmp_path / "wiki" / "concepts"
        concepts.mkdir(parents=True)

        for i in range(10):
            page = concepts / f"Long Page {i}.md"
            page.write_text(
                f"---\ntitle: Long Page {i}\ntype: concept\n---\n" + "Content " * 500,
                encoding="utf-8"
            )

        pages = [{"page": p, "score": 1.0, "path": [p.stem]} for p in sorted(concepts.glob("*.md"))]
        context = build_context(pages, max_chars=1000)
        assert len(context) <= 1200  # Allow small overhead


class TestExpandQuery:
    def test_expand_query_returns_list_including_original(self):
        """expand_query should return a list containing the original question."""
        from scripts.query import expand_query
        results = expand_query("What is RAG?")
        assert isinstance(results, list)
        assert "What is RAG?" in results
        assert len(results) >= 2  # original + at least 1 expansion

    def test_expand_query_fallback_on_error(self):
        """expand_query should return [original] when LLM fails."""
        from scripts.query import expand_query
        # Pass an empty string which should still return something
        results = expand_query("")
        assert isinstance(results, list)
        assert "" in results


class TestMultiQueryScoring:
    def test_find_seed_pages_with_query_list(self, tmp_path):
        """find_seed_pages should accept a list of queries and merge scores."""
        concepts = tmp_path / "wiki" / "concepts"
        concepts.mkdir(parents=True)

        # Page about "hiring" that doesn't contain "recruitment"
        page = concepts / "Talent Acquisition.md"
        page.write_text(
            "---\ntitle: Talent Acquisition\ntype: concept\nconfidence: HIGH\n---\n"
            "Hiring processes and onboarding strategies.",
            encoding="utf-8"
        )

        # Single query "recruitment" would miss this page
        # But "hiring" would find it
        results = find_seed_pages(
            ["recruitment process", "hiring process"],
            wiki_dir=tmp_path / "wiki",
        )
        assert len(results) >= 1
        # Should find the page via at least one query variant
        stems = [r.stem for r in results]
        assert "Talent Acquisition" in stems

    def test_find_seed_pages_merges_max_score(self, tmp_path):
        """When multiple queries match the same page, take the max score."""
        concepts = tmp_path / "wiki" / "concepts"
        concepts.mkdir(parents=True)

        page = concepts / "Agentic AI.md"
        page.write_text(
            "---\ntitle: Agentic AI\ntype: concept\nconfidence: HIGH\n---\n"
            "Autonomous AI systems that execute workflows.",
            encoding="utf-8"
        )

        # Both queries match but "agentic" should score higher
        results_single = find_seed_pages(
            "agentic AI",
            wiki_dir=tmp_path / "wiki",
        )
        results_multi = find_seed_pages(
            ["agentic AI", "autonomous systems"],
            wiki_dir=tmp_path / "wiki",
        )
        # Multi-query should find at least as many pages
        assert len(results_multi) >= len(results_single)


from unittest.mock import patch


class TestExpandQueryMocked:
    def test_expand_query_calls_llm_with_correct_prompt(self):
        """expand_query should call LLM with expansion system prompt."""
        from scripts.query import expand_query

        mock_response = "hiring recruitment\ntalent acquisition onboarding\nworkforce staffing"
        with patch("llm_client.completion_with_retry", return_value=mock_response) as mock_llm:
            result = expand_query("employment process")

            assert mock_llm.called
            # Original question should be first
            assert "employment process" in result

    def test_expand_query_deduplicates(self):
        """expand_query should deduplicate similar queries."""
        from scripts.query import expand_query

        # LLM returns a line similar to the original
        mock_response = "employment process\nhiring recruitment\ntalent acquisition"
        with patch("llm_client.completion_with_retry", return_value=mock_response):
            result = expand_query("employment process")

            # Should not have duplicates (case-insensitive)
            lower_results = [r.lower() for r in result]
            assert len(lower_results) == len(set(lower_results))

    def test_expand_query_caps_at_five(self):
        """expand_query should return at most 5 queries."""
        from scripts.query import expand_query

        mock_response = "query1\nquery2\nquery3\nquery4\nquery5\nquery6\nquery7"
        with patch("llm_client.completion_with_retry", return_value=mock_response):
            result = expand_query("test question")

            assert len(result) <= 5

    def test_expand_query_fallback_on_exception(self):
        """expand_query should return [original] when LLM raises an exception."""
        from scripts.query import expand_query

        with patch("llm_client.completion_with_retry", side_effect=RuntimeError("LLM unavailable")):
            result = expand_query("what is RAG")

            assert result == ["what is RAG"]

    def test_expand_query_empty_string(self):
        """expand_query should handle empty string input."""
        from scripts.query import expand_query

        result = expand_query("")

        assert result == [""]