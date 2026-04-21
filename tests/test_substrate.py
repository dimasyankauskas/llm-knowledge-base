"""Tests for agent substrate commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.substrate import (
    build_agent_ingest_plan,
    build_context_pack,
    build_triage,
    draft_artifact,
    render_agent_ingest_plan,
    scaffold_page,
)
from scripts.utils import write_page


def _make_wiki(tmp_path: Path) -> Path:
    wiki_dir = tmp_path / "wiki"
    (wiki_dir / "concepts").mkdir(parents=True)
    (wiki_dir / "entities").mkdir()
    (wiki_dir / "drafts").mkdir()
    return wiki_dir


def _write_health(wiki_dir: Path) -> None:
    health = {
        "errors": 0,
        "warnings": 2,
        "issues": [
            {
                "code": "BROKEN_LINK",
                "page": "Agentic UX Strategy",
                "message": "Links to [[Product Strategy]] which does not exist",
                "severity": "WARNING",
            },
            {
                "code": "STALE_PAGE",
                "page": "Agentic UX Strategy",
                "message": "Source content changed",
                "severity": "WARNING",
            },
        ],
    }
    (wiki_dir / "_health.json").write_text(json.dumps(health), encoding="utf-8")


def _write_graph(wiki_dir: Path) -> None:
    graph = {
        "nodes": [
            {"id": "Agentic UX Strategy", "type": "concept", "confidence": "HIGH"},
        ],
        "edges": [
            {
                "source": "Agentic UX Strategy",
                "target": "Product Strategy",
                "type": "extends",
                "weight": 2,
            }
        ],
    }
    (wiki_dir / "_graph.json").write_text(json.dumps(graph), encoding="utf-8")


def _write_agentic_page(wiki_dir: Path) -> Path:
    page = wiki_dir / "concepts" / "Agentic UX Strategy.md"
    write_page(
        page,
        {
            "title": "Agentic UX Strategy",
            "type": "concept",
            "confidence": "HIGH",
            "created": "2026-04-20",
            "source_refs": ["case-study.md"],
            "content_hash": "abc123",
        },
        """## Definition

Agentic UX case studies should explain transformation, not just features [source: case-study.md, §Narrative Framework].

## Key Properties

- Trust calibration matters [source: case-study.md, §Trust].

## How It Works

Use [[Product Strategy]]:extends to connect product framing.

## Relationships

- [[Product Strategy]]:extends

## Open Questions

- What metrics prove success?

## Sources

- [source: case-study.md, §Narrative Framework]
""",
    )
    return page


class TestContextPack:
    def test_context_pack_returns_pages_claims_and_warnings(self, tmp_path):
        wiki_dir = _make_wiki(tmp_path)
        _write_agentic_page(wiki_dir)
        _write_graph(wiki_dir)
        _write_health(wiki_dir)

        pack = build_context_pack(
            "best practices for case studies",
            wiki_dir=wiki_dir,
        )

        assert pack["schema_version"] == "1.0"
        assert pack["wiki"]["health"]["status"] == "warning"
        assert pack["context"]["pages"][0]["title"] == "Agentic UX Strategy"
        assert pack["context"]["claims"]
        assert "Product Strategy" in pack["warnings"]["missing_pages"]

    def test_context_pack_prioritizes_exact_fresh_page_over_stale_related_page(self, tmp_path):
        wiki_dir = _make_wiki(tmp_path)
        fresh = wiki_dir / "concepts" / "AI UX Case Study Strategy.md"
        write_page(
            fresh,
            {
                "title": "AI UX Case Study Strategy",
                "type": "concept",
                "confidence": "MEDIUM",
                "created": "2026-04-20",
                "source_refs": ["fresh.md"],
                "content_hash": "fresh",
            },
            """## Definition

AI UX case studies need trust, workflow, and evidence framing [source: fresh.md, §Strategy].

## Key Properties

- Case study evidence matters [source: fresh.md, §Evidence].

## How It Works

Use [[Old AI Product Strategy]]:extends.

## Relationships

- [[Old AI Product Strategy]]:extends

## Open Questions

- Which metric is strongest?

## Sources

- [source: fresh.md, §Strategy]
""",
        )
        stale = wiki_dir / "concepts" / "Old AI Product Strategy.md"
        write_page(
            stale,
            {
                "title": "Old AI Product Strategy",
                "type": "concept",
                "confidence": "HIGH",
                "created": "2025-01-01",
                "source_refs": ["old.md"],
                "content_hash": "old",
            },
            """## Definition

Old strategy content mentions AI UX and case studies [source: old.md, §Old].

## Key Properties

- Old property [source: old.md, §Old].

## How It Works

Use [[AI UX Case Study Strategy]]:extends.

## Relationships

- [[AI UX Case Study Strategy]]:extends

## Open Questions

- Is this stale?

## Sources

- [source: old.md, §Old]
""",
        )
        (wiki_dir / "_health.json").write_text(json.dumps({
            "errors": 0,
            "warnings": 1,
            "issues": [{
                "code": "STALE_PAGE",
                "page": "Old AI Product Strategy",
                "message": "Source content changed",
                "severity": "WARNING",
            }],
        }), encoding="utf-8")
        (wiki_dir / "_graph.json").write_text(json.dumps({
            "nodes": [
                {"id": "AI UX Case Study Strategy", "type": "concept", "confidence": "MEDIUM"},
                {"id": "Old AI Product Strategy", "type": "concept", "confidence": "HIGH"},
            ],
            "edges": [
                {
                    "source": "Old AI Product Strategy",
                    "target": "AI UX Case Study Strategy",
                    "type": "extends",
                    "weight": 2,
                }
            ],
        }), encoding="utf-8")

        pack = build_context_pack("AI UX Case Study Strategy", wiki_dir=wiki_dir)

        assert pack["context"]["pages"][0]["title"] == "AI UX Case Study Strategy"


class TestAgentIngestPlan:
    def test_agent_ingest_plan_is_model_free_and_finds_candidates(self, tmp_path):
        wiki_dir = _make_wiki(tmp_path)
        _write_agentic_page(wiki_dir)
        source = tmp_path / "case-study.md"
        source.write_text(
            "# Agentic UX Strategy\n\nTrust calibration and case study evidence matter.",
            encoding="utf-8",
        )

        plan = build_agent_ingest_plan(source, source_type="article", wiki_dir=wiki_dir)

        assert plan["mode"] == "agent-first"
        assert plan["source"]["filename"] == "case-study.md"
        assert plan["external_model_policy"]["default"] == "not_required"
        assert plan["merge_candidates"][0]["title"] == "Agentic UX Strategy"

    def test_render_agent_ingest_plan_includes_commands(self, tmp_path):
        wiki_dir = _make_wiki(tmp_path)
        source = tmp_path / "source.md"
        source.write_text("# Source\n\nContent", encoding="utf-8")

        plan = build_agent_ingest_plan(source, wiki_dir=wiki_dir)
        rendered = render_agent_ingest_plan(plan)

        assert "Agent-First Ingestion Plan" in rendered
        assert "wiki validate" in rendered
        assert "No external model is required" in rendered


class TestTriage:
    def test_triage_orders_missing_and_stale_items(self, tmp_path):
        wiki_dir = _make_wiki(tmp_path)
        _write_agentic_page(wiki_dir)
        _write_health(wiki_dir)

        triage = build_triage(wiki_dir=wiki_dir)

        assert triage["status"] == "warning"
        assert triage["counts"]["missing_pages"] == 1
        item_types = {item["type"] for item in triage["items"]}
        assert "missing_page" in item_types
        assert "stale_page" in item_types


class TestScaffold:
    def test_scaffold_creates_concept_draft(self, tmp_path):
        wiki_dir = _make_wiki(tmp_path)

        draft = scaffold_page("Product Strategy", wiki_dir=wiki_dir)

        assert draft.exists()
        text = draft.read_text(encoding="utf-8")
        assert "type: concept" in text
        assert "## Definition" in text

    def test_scaffold_does_not_overwrite_existing_draft(self, tmp_path):
        wiki_dir = _make_wiki(tmp_path)
        scaffold_page("Product Strategy", wiki_dir=wiki_dir)

        with pytest.raises(FileExistsError):
            scaffold_page("Product Strategy", wiki_dir=wiki_dir)


class TestDraftArtifact:
    def test_draft_artifact_preserves_citations(self, tmp_path):
        wiki_dir = _make_wiki(tmp_path)
        _write_agentic_page(wiki_dir)
        _write_graph(wiki_dir)
        _write_health(wiki_dir)

        artifact = draft_artifact("case-study", "Agentic UX Strategy", wiki_dir=wiki_dir)

        assert Path(tmp_path / artifact["path"]).exists()
        assert "case-study.md" in artifact["content"]
        assert "## Evidence" in artifact["content"]
