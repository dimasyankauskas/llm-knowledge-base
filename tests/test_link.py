"""Tests for v2 link stage in scripts/link.py.

Tests typed edge extraction, graph building, bidirectional link verification,
and graph persistence.
"""

import json
from pathlib import Path

import frontmatter
import pytest

from scripts.link import (
    build_typed_graph,
    extract_typed_edges,
    save_graph,
    verify_bidirectional_links,
)
from scripts.utils import write_page


# ── Helpers ──────────────────────────────────────────────────────────────────

_DEFAULT_WEIGHTS = {
    "cites": 4,
    "contradicts": 3,
    "implements": 3,
    "extends": 2,
    "prerequisite_of": 2,
    "trades_off": 1,
    "derived_from": 2,
    "neutral": 1,
}


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


# ── extract_typed_edges ──────────────────────────────────────────────────────


class TestExtractTypedEdges:
    def test_extract_typed_edges_implements(self):
        """'RAG implements [[Neural IR]]' produces edge type 'implements'."""
        content = "RAG implements [[Neural IR]] for retrieval."
        edges = extract_typed_edges(content, "RAG")
        neural_edges = [e for e in edges if e["target"] == "Neural IR"]
        assert len(neural_edges) >= 1
        assert neural_edges[0]["type"] == "implements"
        assert neural_edges[0]["source"] == "RAG"

    def test_extract_typed_edges_contradicts(self):
        """'This contradicts [[Pure Gen]]' produces edge type 'contradicts'."""
        content = "This approach contradicts [[Pure Gen]] in key ways."
        edges = extract_typed_edges(content, "Hybrid Model")
        pure_edges = [e for e in edges if e["target"] == "Pure Gen"]
        assert len(pure_edges) >= 1
        assert pure_edges[0]["type"] == "contradicts"
        assert pure_edges[0]["source"] == "Hybrid Model"

    def test_extract_typed_edges_untyped_default(self):
        """'See [[RAG]] for details' produces edge type 'neutral'."""
        content = "See [[RAG]] for details on retrieval-augmented generation."
        edges = extract_typed_edges(content, "Overview")
        rag_edges = [e for e in edges if e["target"] == "RAG"]
        assert len(rag_edges) >= 1
        assert rag_edges[0]["type"] == "neutral"
        assert rag_edges[0]["source"] == "Overview"

    def test_extract_typed_edges_from_frontmatter(self):
        """Frontmatter related_concepts with ':implements' suffix produces typed edge."""
        metadata = {
            "title": "RAG",
            "type": "concept",
            "confidence": "HIGH",
            "related_concepts": [
                "[[Neural IR]]:implements",
                "[[Dense Retrieval]]:extends",
            ],
        }
        content = "RAG combines retrieval and generation."
        edges = extract_typed_edges(content, "RAG", relation_types=None, metadata=metadata)
        # Should find the frontmatter typed edges
        impl_edges = [e for e in edges if e["target"] == "Neural IR" and e["type"] == "implements"]
        extends_edges = [e for e in edges if e["target"] == "Dense Retrieval" and e["type"] == "extends"]
        assert len(impl_edges) >= 1, f"Expected implements edge for Neural IR, got: {edges}"
        assert len(extends_edges) >= 1, f"Expected extends edge for Dense Retrieval, got: {edges}"


# ── build_typed_graph ────────────────────────────────────────────────────────


class TestBuildTypedGraph:
    def test_build_typed_graph_creates_nodes(self, tmp_path):
        """Graph has nodes for each wiki page."""
        wiki_dir = _make_wiki(tmp_path, {
            "concepts/RAG.md": {
                "metadata": {"title": "RAG", "type": "concept", "confidence": "HIGH"},
                "content": "RAG implements [[Neural IR]].",
            },
            "concepts/Neural_IR.md": {
                "metadata": {"title": "Neural IR", "type": "concept", "confidence": "MEDIUM"},
                "content": "Neural IR is a paradigm.",
            },
        })
        graph = build_typed_graph(wiki_dir=wiki_dir)
        node_ids = {n["id"] for n in graph["nodes"]}
        assert "RAG" in node_ids
        assert "Neural_IR" in node_ids
        assert graph["node_count"] >= 2

    def test_build_typed_graph_creates_typed_edges(self, tmp_path):
        """Graph has typed edges with correct weights."""
        wiki_dir = _make_wiki(tmp_path, {
            "concepts/RAG.md": {
                "metadata": {"title": "RAG", "type": "concept", "confidence": "HIGH"},
                "content": "RAG implements [[Neural IR]].",
            },
            "concepts/Neural_IR.md": {
                "metadata": {"title": "Neural IR", "type": "concept", "confidence": "MEDIUM"},
                "content": "Neural IR extends [[Information Retrieval]].",
            },
            "concepts/Information_Retrieval.md": {
                "metadata": {"title": "Information Retrieval", "type": "concept", "confidence": "HIGH"},
                "content": "Overview of IR.",
            },
        })
        graph = build_typed_graph(wiki_dir=wiki_dir)
        # Find the implements edge from RAG -> Neural_IR
        impl_edges = [
            e for e in graph["edges"]
            if e["source"] == "RAG" and e["target"] == "Neural_IR" and e["type"] == "implements"
        ]
        assert len(impl_edges) >= 1
        assert impl_edges[0]["weight"] == _DEFAULT_WEIGHTS["implements"]

        # Find the extends edge
        extends_edges = [
            e for e in graph["edges"]
            if e["source"] == "Neural_IR" and e["target"] == "Information_Retrieval" and e["type"] == "extends"
        ]
        assert len(extends_edges) >= 1
        assert extends_edges[0]["weight"] == _DEFAULT_WEIGHTS["extends"]

    def test_build_typed_graph_skips_index_pages(self, tmp_path):
        """Pages starting with '_' are skipped."""
        wiki_dir = _make_wiki(tmp_path, {
            "concepts/RAG.md": {
                "metadata": {"title": "RAG", "type": "concept", "confidence": "HIGH"},
                "content": "RAG is retrieval-augmented generation.",
            },
            "indexes/_index.md": {
                "metadata": {"title": "Index", "type": "index"},
                "content": "# Index\n\n- [[RAG]]",
            },
        })
        graph = build_typed_graph(wiki_dir=wiki_dir)
        node_ids = {n["id"] for n in graph["nodes"]}
        # RAG should be included, _index should be skipped
        assert "RAG" in node_ids
        assert "_index" not in node_ids


# ── verify_bidirectional_links ────────────────────────────────────────────────


class TestVerifyBidirectionalLinks:
    def test_verify_bidirectional_links_missing(self, tmp_path):
        """Detect missing reverse link for a typed relation."""
        wiki_dir = _make_wiki(tmp_path, {
            "concepts/RAG.md": {
                "metadata": {"title": "RAG", "type": "concept", "confidence": "HIGH"},
                "content": "RAG implements [[Neural IR]].",
            },
            "concepts/Neural_IR.md": {
                "metadata": {"title": "Neural IR", "type": "concept", "confidence": "MEDIUM"},
                "content": "Neural IR is a paradigm. No link back to RAG here.",
            },
        })
        issues = verify_bidirectional_links(wiki_dir=wiki_dir)
        # Should find that RAG -> Neural_IR (implements) has no reverse
        missing_impl = [
            i for i in issues
            if i["source"] == "RAG" and i["target"] == "Neural_IR" and i["type"] == "implements"
        ]
        assert len(missing_impl) >= 1, f"Expected missing reverse for RAG->Neural_IR, got: {issues}"
        assert missing_impl[0]["has_reverse"] is False

    def test_verify_bidirectional_links_present(self, tmp_path):
        """When both directions exist, no issues are reported."""
        wiki_dir = _make_wiki(tmp_path, {
            "concepts/RAG.md": {
                "metadata": {"title": "RAG", "type": "concept", "confidence": "HIGH"},
                "content": "RAG implements [[Neural IR]].",
            },
            "concepts/Neural_IR.md": {
                "metadata": {"title": "Neural IR", "type": "concept", "confidence": "MEDIUM"},
                "content": "Neural IR is implemented by [[RAG]].",
            },
        })
        issues = verify_bidirectional_links(wiki_dir=wiki_dir)
        # There should be no issue for the RAG <-> Neural_IR pair
        # (both directions exist with typed relations)
        rag_neural_issues = [
            i for i in issues
            if (i["source"] == "RAG" and i["target"] == "Neural_IR")
            or (i["source"] == "Neural_IR" and i["target"] == "RAG")
        ]
        assert len(rag_neural_issues) == 0, f"Expected no issues for bidirectional RAG<->Neural_IR, got: {rag_neural_issues}"


# ── save_graph ────────────────────────────────────────────────────────────────


class TestSaveGraph:
    def test_save_graph_writes_json(self, tmp_path):
        """_graph.json is written correctly to the wiki directory."""
        wiki_dir = _make_wiki(tmp_path, {
            "concepts/RAG.md": {
                "metadata": {"title": "RAG", "type": "concept", "confidence": "HIGH"},
                "content": "RAG implements [[Neural IR]].",
            },
        })
        graph = build_typed_graph(wiki_dir=wiki_dir)
        save_graph(graph, wiki_dir=wiki_dir)

        graph_path = wiki_dir / "_graph.json"
        assert graph_path.exists(), "_graph.json should be written"

        saved = json.loads(graph_path.read_text(encoding="utf-8"))
        assert saved["node_count"] == graph["node_count"]
        assert saved["edge_count"] == graph["edge_count"]
        assert "generated_at" in saved
        assert "nodes" in saved
        assert "edges" in saved