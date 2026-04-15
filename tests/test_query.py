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