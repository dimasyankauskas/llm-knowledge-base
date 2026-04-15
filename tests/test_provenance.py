"""Tests for the provenance module — claim tracking and staleness detection."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.provenance import (
    add_claim,
    add_source,
    check_staleness,
    create_provenance,
    get_claim_sources,
    get_stale_pages,
)
from scripts.utils import write_provenance, read_provenance, hash_content, hash_file


# ── create_provenance ────────────────────────────────────────────────────

class TestCreateProvenance:
    def test_create_basic_provenance(self):
        """create_provenance returns correct structure with required fields."""
        prov = create_provenance(
            page="Retrieval-Augmented Generation",
            content_hash="a3f2b1c8",
        )
        assert prov["page"] == "Retrieval-Augmented Generation"
        assert prov["content_hash"] == "a3f2b1c8"
        assert prov["sources"] == []
        assert prov["claims"] == []
        assert prov["derived_concepts"] == []

    def test_create_provenance_with_sources(self):
        """Sources are included when passed to create_provenance."""
        sources = [
            {
                "file": "lewis2020_rag.pdf",
                "content_hash": "8e4d2f1a",
                "sections_used": ["Abstract", "Results"],
            }
        ]
        prov = create_provenance(
            page="RAG",
            content_hash="a3f2b1c8",
            sources=sources,
        )
        assert len(prov["sources"]) == 1
        assert prov["sources"][0]["file"] == "lewis2020_rag.pdf"
        assert prov["sources"][0]["content_hash"] == "8e4d2f1a"
        assert prov["sources"][0]["sections_used"] == ["Abstract", "Results"]


# ── add_claim ────────────────────────────────────────────────────────────

class TestAddClaim:
    def test_add_fact_claim(self):
        """Adding a fact claim with corroborated=False."""
        prov = create_provenance(page="RAG", content_hash="abc123")
        prov = add_claim(
            prov,
            text="RAG combines retrieval and generation",
            claim_type="fact",
            sources=["lewis2020_rag.pdf"],
        )
        assert len(prov["claims"]) == 1
        claim = prov["claims"][0]
        assert claim["id"] == "claim-1"
        assert claim["text"] == "RAG combines retrieval and generation"
        assert claim["type"] == "fact"
        assert claim["sources"] == ["lewis2020_rag.pdf"]
        assert claim["corroborated"] is False
        assert "last_verified" in claim

    def test_add_inference_claim(self):
        """Adding an inference claim with corroborated=True."""
        prov = create_provenance(page="RAG", content_hash="abc123")
        prov = add_claim(
            prov,
            text="RAG will replace fine-tuning for most tasks",
            claim_type="inference",
            sources=["lewis2020_rag.pdf", "gao2023_retrieval.md"],
            corroborated=True,
        )
        assert len(prov["claims"]) == 1
        claim = prov["claims"][0]
        assert claim["type"] == "inference"
        assert claim["corroborated"] is True
        assert len(claim["sources"]) == 2

    def test_add_multiple_claims(self):
        """Adding multiple claims increments IDs."""
        prov = create_provenance(page="RAG", content_hash="abc123")
        prov = add_claim(prov, "Claim A", "fact", ["src1.pdf"])
        prov = add_claim(prov, "Claim B", "inference", ["src2.pdf"])
        assert len(prov["claims"]) == 2
        assert prov["claims"][0]["id"] == "claim-1"
        assert prov["claims"][1]["id"] == "claim-2"


# ── add_source ───────────────────────────────────────────────────────────

class TestAddSource:
    def test_add_source(self):
        """Adding a source reference to provenance."""
        prov = create_provenance(page="RAG", content_hash="abc123")
        prov = add_source(
            prov,
            file="lewis2020_rag.pdf",
            content_hash="8e4d2f1a",
            sections_used=["Abstract", "Results"],
        )
        assert len(prov["sources"]) == 1
        assert prov["sources"][0]["file"] == "lewis2020_rag.pdf"
        assert prov["sources"][0]["content_hash"] == "8e4d2f1a"
        assert prov["sources"][0]["sections_used"] == ["Abstract", "Results"]

    def test_add_source_no_sections(self):
        """Adding a source without sections defaults to empty list."""
        prov = create_provenance(page="RAG", content_hash="abc123")
        prov = add_source(
            prov,
            file="lewis2020_rag.pdf",
            content_hash="8e4d2f1a",
        )
        assert prov["sources"][0]["sections_used"] == []


# ── check_staleness ──────────────────────────────────────────────────────

class TestCheckStaleness:
    def test_check_staleness_stale_source(self, tmp_path):
        """Detects when source hash doesn't match current file hash."""
        # Create a source file
        source_file = tmp_path / "lewis2020_rag.pdf"
        source_file.write_text("original content", encoding="utf-8")
        original_hash = hash_file(source_file)

        prov = create_provenance(page="RAG", content_hash="abc123")
        prov = add_source(prov, "lewis2020_rag.pdf", original_hash, ["Abstract"])

        # Now change the source file
        source_file.write_text("modified content", encoding="utf-8")

        stale = check_staleness(prov, sources_dir=tmp_path)
        assert "lewis2020_rag.pdf" in stale

    def test_check_staleness_no_staleness(self, tmp_path):
        """No staleness when hashes match."""
        source_file = tmp_path / "lewis2020_rag.pdf"
        source_file.write_text("original content", encoding="utf-8")
        original_hash = hash_file(source_file)

        prov = create_provenance(page="RAG", content_hash="abc123")
        prov = add_source(prov, "lewis2020_rag.pdf", original_hash, ["Abstract"])

        stale = check_staleness(prov, sources_dir=tmp_path)
        assert stale == []

    def test_check_staleness_missing_file(self, tmp_path):
        """Treats missing source file as stale."""
        prov = create_provenance(page="RAG", content_hash="abc123")
        prov = add_source(prov, "nonexistent.pdf", "somehash", [])

        stale = check_staleness(prov, sources_dir=tmp_path)
        assert "nonexistent.pdf" in stale


# ── get_stale_pages ──────────────────────────────────────────────────────

class TestGetStalePages:
    def test_get_stale_pages(self, tmp_path):
        """Finds pages with stale sources across concepts/ and entities/."""
        # Set up directories
        wiki_dir = tmp_path / "wiki"
        concepts_dir = wiki_dir / "concepts"
        entities_dir = wiki_dir / "entities"
        sources_dir = tmp_path / "sources"
        concepts_dir.mkdir(parents=True)
        entities_dir.mkdir(parents=True)
        sources_dir.mkdir()

        # Create a source file
        source_file = sources_dir / "lewis2020_rag.pdf"
        source_file.write_text("original content", encoding="utf-8")
        original_hash = hash_file(source_file)

        # Create a concept page with provenance
        concept_page = concepts_dir / "RAG.md"
        concept_page.write_text("---\ntitle: RAG\n---\nContent", encoding="utf-8")

        prov = create_provenance(page="RAG", content_hash="abc123")
        prov = add_source(prov, "lewis2020_rag.pdf", original_hash, ["Abstract"])
        write_provenance(concept_page, prov)

        # Create an entity page with provenance (up-to-date source)
        entity_page = entities_dir / "Anthropic.md"
        entity_page.write_text("---\ntitle: Anthropic\n---\nContent", encoding="utf-8")
        entity_source = sources_dir / "anthropic_about.txt"
        entity_source.write_text("entity content", encoding="utf-8")
        entity_hash = hash_file(entity_source)

        entity_prov = create_provenance(page="Anthropic", content_hash="def456")
        entity_prov = add_source(entity_prov, "anthropic_about.txt", entity_hash, [])
        write_provenance(entity_page, entity_prov)

        # Now modify the RAG source to make it stale
        source_file.write_text("modified content", encoding="utf-8")

        stale_pages = get_stale_pages(wiki_dir, sources_dir)
        assert "RAG" in stale_pages
        assert "Anthropic" not in stale_pages

    def test_get_stale_pages_no_provenance(self, tmp_path):
        """Pages without provenance sidecars are skipped."""
        wiki_dir = tmp_path / "wiki"
        concepts_dir = wiki_dir / "concepts"
        entities_dir = wiki_dir / "entities"
        sources_dir = tmp_path / "sources"
        concepts_dir.mkdir(parents=True)
        entities_dir.mkdir(parents=True)
        sources_dir.mkdir()

        # Create a page with no sidecar
        concept_page = concepts_dir / "Orphan.md"
        concept_page.write_text("---\ntitle: Orphan\n---\nContent", encoding="utf-8")

        stale_pages = get_stale_pages(wiki_dir, sources_dir)
        assert stale_pages == []


# ── get_claim_sources ────────────────────────────────────────────────────

class TestGetClaimSources:
    def test_get_claim_sources(self):
        """Retrieves sources for a specific claim by ID."""
        prov = create_provenance(page="RAG", content_hash="abc123")
        prov = add_claim(
            prov,
            text="RAG combines retrieval and generation",
            claim_type="fact",
            sources=["lewis2020_rag.pdf", "gao2023_retrieval.md"],
        )
        prov = add_claim(
            prov,
            text="RAG reduces hallucination",
            claim_type="fact",
            sources=["lewis2020_rag.pdf"],
        )

        sources = get_claim_sources(prov, "claim-1")
        assert sources == ["lewis2020_rag.pdf", "gao2023_retrieval.md"]

        sources2 = get_claim_sources(prov, "claim-2")
        assert sources2 == ["lewis2020_rag.pdf"]

    def test_get_claim_sources_not_found(self):
        """Returns empty list for unknown claim ID."""
        prov = create_provenance(page="RAG", content_hash="abc123")
        prov = add_claim(prov, "Some claim", "fact", ["src.pdf"])

        sources = get_claim_sources(prov, "claim-999")
        assert sources == []