"""Integration test: full pipeline from source ingestion to state generation."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from typing import Optional

from scripts.schema import load_schema
from scripts.validate import validate_draft
from scripts.link import build_typed_graph
from scripts.refine import generate_refinement_tasks
from scripts.lint import lint
from scripts.consolidate import generate_indexes
from scripts.state import generate_state, generate_health, save_state, save_health
from scripts.utils import (
    write_page, hash_content, write_provenance,
)


@pytest.fixture
def wiki_env(tmp_path):
    """Set up a minimal wiki environment for integration tests."""
    # Create directory structure
    for d in ["concepts", "entities", "indexes", "timelines", "drafts"]:
        (tmp_path / "wiki" / d).mkdir(parents=True)

    # Create sources directory
    for d in ["article", "paper", "transcript", "code-doc"]:
        (tmp_path / "sources" / d).mkdir(parents=True)

    # Create manifest
    manifest = {"version": "1.0", "sources": []}
    (tmp_path / "sources" / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    # Create a test source file for provenance references
    test_source = tmp_path / "sources" / "article" / "test-source.md"
    test_source.write_text("# Test Source\n\nContent about RAG and neural IR.", encoding="utf-8")

    # Create _graph.json
    (tmp_path / "wiki" / "_graph.json").write_text(
        json.dumps({"generated_at": "", "node_count": 0, "edge_count": 0, "nodes": [], "edges": []}),
        encoding="utf-8",
    )

    return tmp_path


def _write_concept(wiki_dir: Path, name: str, title: str, content: str,
                   tags: Optional[list[str]] = None, aliases: Optional[list[str]] = None,
                   confidence: str = "HIGH", source_refs: Optional[list[str]] = None,
                   related: Optional[list[str]] = None):
    """Helper to write a concept page with required frontmatter."""
    page_path = wiki_dir / "concepts" / f"{name}.md"
    metadata = {
        "title": title,
        "type": "concept",
        "confidence": confidence,
        "created": "2026-04-15",
        "source_refs": source_refs or ["test-source.md"],
        "content_hash": hash_content(content),
    }
    if tags:
        metadata["tags"] = tags
    if aliases:
        metadata["aliases"] = aliases
    if related:
        metadata["related_concept"] = related

    write_page(page_path, metadata, content)

    # Create provenance sidecar
    prov = {
        "page": name,
        "content_hash": hash_content(content),
        "claims": [],
        "sources": [{"file": s, "sections_used": []} for s in (source_refs or ["test-source.md"])],
        "last_verified": "2026-04-15",
    }
    write_provenance(page_path, prov)

    return page_path


class TestFullPipeline:
    def test_ingest_and_state(self, wiki_env):
        """Test that creating pages and running state produces expected output."""
        wiki_dir = wiki_env / "wiki"

        # Create two concept pages that link to each other
        _write_concept(
            wiki_dir, "RAG", "Retrieval-Augmented Generation",
            "## Definition\n\nRAG combines retrieval and generation.\n\n"
            "## Key Properties\n\nUses external knowledge.\n\n"
            "## How It Works\n\nRetrieve then generate.\n\n"
            "## Relationships\n\n- Implements [[Neural IR]]:implements\n- Extends [[Information Retrieval]]:extends\n\n"
            "## Open Questions\n\nHow to optimize retrieval?\n\n"
            "## Sources\n\n- test-source.md",
            tags=["domain/ai", "topic/retrieval"],
        )
        _write_concept(
            wiki_dir, "Neural IR", "Neural Information Retrieval",
            "## Definition\n\nNeural IR uses deep learning for search.\n\n"
            "## Key Properties\n\nLearns semantic representations.\n\n"
            "## How It Works\n\nEncode query and documents.\n\n"
            "## Relationships\n\n- Cited by [[RAG]]:cites\n\n"
            "## Open Questions\n\nBest architecture?\n\n"
            "## Sources\n\n- test-source.md",
            tags=["domain/ai", "topic/retrieval"],
        )

        # Build graph
        schema = load_schema()
        graph = build_typed_graph(wiki_dir=wiki_dir, schema=schema)

        # Verify graph has nodes and edges
        assert len(graph["nodes"]) >= 2
        assert len(graph["edges"]) >= 1

        # Generate state
        state = generate_state(wiki_dir=wiki_dir, schema=schema)
        assert "schema_version" in state
        assert "pages" in state
        assert len(state["pages"]) >= 2

        # Save and reload
        save_state(state, wiki_dir=wiki_dir)
        loaded = json.loads((wiki_dir / "_state.json").read_text(encoding="utf-8"))
        assert loaded["schema_version"] == "2.0"

    def test_lint_detects_broken_link(self, wiki_env):
        """Test that lint catches broken wikilinks."""
        wiki_dir = wiki_env / "wiki"
        sources_dir = wiki_env / "sources"

        # Create a page with a broken link
        _write_concept(
            wiki_dir, "Broken Link Page", "Test Page",
            "## Definition\n\nReferences [[Nonexistent Page]].\n\n"
            "## Key Properties\n\nTest.\n\n"
            "## How It Works\n\nTest.\n\n"
            "## Relationships\n\nSee [[Nonexistent Page]]:cites\n\n"
            "## Open Questions\n\nTest?\n\n"
            "## Sources\n\n- test-source.md",
        )

        issues = lint(wiki_dir=wiki_dir, sources_dir=sources_dir)
        broken = [i for i in issues if i.code == "BROKEN_LINK"]
        assert len(broken) >= 1

    def test_validate_rejects_invalid_draft(self, wiki_env):
        """Test that validation rejects a draft missing required frontmatter."""
        wiki_dir = wiki_env / "wiki"
        schema = load_schema()

        # Create an invalid draft (missing confidence)
        draft_path = wiki_dir / "drafts" / "Bad Draft.md"
        write_page(draft_path, {"title": "Bad Draft", "type": "concept"}, "Invalid content.")

        report = validate_draft(draft_path, schema)
        assert report.has_errors
        assert report.error_count > 0

    def test_state_reflects_wiki_health(self, wiki_env):
        """Test that _state.json reflects wiki health status."""
        wiki_dir = wiki_env / "wiki"
        sources_dir = wiki_env / "sources"

        # Create a valid concept page
        _write_concept(
            wiki_dir, "Health Test", "Health Test Page",
            "## Definition\n\nTest page.\n\n"
            "## Key Properties\n\nTest.\n\n"
            "## How It Works\n\nTest.\n\n"
            "## Relationships\n\nTest.\n\n"
            "## Open Questions\n\nTest?\n\n"
            "## Sources\n\n- test-source.md",
            confidence="MEDIUM",
        )

        # Run lint
        issues = lint(wiki_dir=wiki_dir, sources_dir=sources_dir)

        # Generate health from lint results
        issues_dicts = [
            {"severity": i.severity, "code": i.code, "page": i.page, "message": i.message}
            for i in issues
        ]
        health = generate_health(wiki_dir=wiki_dir, lint_results=issues_dicts)
        assert "errors" in health
        assert "warnings" in health
        assert "last_lint" in health

    def test_consolidate_generates_indexes(self, wiki_env):
        """Test that consolidate generates index pages."""
        wiki_dir = wiki_env / "wiki"

        # Create a concept page
        _write_concept(
            wiki_dir, "Index Test", "Index Test Page",
            "## Definition\n\nTest page for index generation.\n\n"
            "## Key Properties\n\nHas tags.\n\n"
            "## How It Works\n\nTest.\n\n"
            "## Relationships\n\nTest.\n\n"
            "## Open Questions\n\nTest?\n\n"
            "## Sources\n\n- test-source.md",
            tags=["domain/ai"],
        )

        schema = load_schema()
        generate_indexes(wiki_dir=wiki_dir, schema=schema)

        # Check that index file was created
        index_dir = wiki_dir / "indexes"
        assert index_dir.exists()
        index_file = index_dir / "_index.md"
        assert index_file.exists()

    def test_refine_detects_tasks(self, wiki_env):
        """Test that refine generates refinement tasks."""
        wiki_dir = wiki_env / "wiki"
        sources_dir = wiki_env / "sources"

        # Create a page
        _write_concept(
            wiki_dir, "Refine Test", "Refine Test Page",
            "## Definition\n\nTest page.\n\n"
            "## Key Properties\n\nTest.\n\n"
            "## How It Works\n\nTest.\n\n"
            "## Relationships\n\nSee [[Nonexistent Page]].\n\n"
            "## Open Questions\n\nTest?\n\n"
            "## Sources\n\n- test-source.md",
        )

        tasks = generate_refinement_tasks(wiki_dir=wiki_dir, sources_dir=sources_dir)
        assert isinstance(tasks, list)

    def test_graph_traversal_from_real_pages(self, wiki_env):
        """Test that typed graph is built correctly from real pages."""
        wiki_dir = wiki_env / "wiki"

        # Create two linked concepts
        _write_concept(
            wiki_dir, "RAG", "Retrieval-Augmented Generation",
            "## Definition\n\nRAG combines retrieval and generation.\n\n"
            "## Key Properties\n\nUses external knowledge.\n\n"
            "## How It Works\n\nRetrieve then generate.\n\n"
            "## Relationships\n\n- Implements [[Neural IR]]:implements\n\n"
            "## Open Questions\n\nHow to optimize?\n\n"
            "## Sources\n\n- test-source.md",
            tags=["domain/ai"],
        )
        _write_concept(
            wiki_dir, "Neural IR", "Neural Information Retrieval",
            "## Definition\n\nNeural IR uses deep learning.\n\n"
            "## Key Properties\n\nSemantic search.\n\n"
            "## How It Works\n\nEncode and retrieve.\n\n"
            "## Relationships\n\n- Cited by [[RAG]]:cites\n\n"
            "## Open Questions\n\nBest model?\n\n"
            "## Sources\n\n- test-source.md",
            tags=["domain/ai", "topic/retrieval"],
        )

        schema = load_schema()
        graph = build_typed_graph(wiki_dir=wiki_dir, schema=schema)

        # Verify structure
        node_ids = [n["id"] for n in graph["nodes"]]
        assert "RAG" in node_ids
        assert "Neural IR" in node_ids

        # Verify typed edges
        edge_types = [(e["source"], e["target"], e["type"]) for e in graph["edges"]]
        implements_edges = [e for e in edge_types if e[2] == "implements"]
        assert len(implements_edges) >= 1