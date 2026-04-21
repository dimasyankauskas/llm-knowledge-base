"""Tests for wiki quality and source coverage reports."""

from __future__ import annotations

from pathlib import Path

from scripts.quality import page_quality, source_coverage
from scripts.utils import write_page, write_provenance


def _make_wiki_and_source(tmp_path: Path) -> tuple[Path, Path, Path]:
    wiki_dir = tmp_path / "wiki"
    sources_dir = tmp_path / "sources"
    (wiki_dir / "concepts").mkdir(parents=True)
    (wiki_dir / "entities").mkdir()
    (sources_dir / "articles").mkdir(parents=True)

    source = sources_dir / "articles" / "case.md"
    source.write_text(
        "# Strategy\n\nTrust framing.\n\n## Evidence\n\nMetrics and proof.\n\n## Risks\n\nAdoption risk.\n",
        encoding="utf-8",
    )

    page = wiki_dir / "concepts" / "AI UX Case Study Strategy.md"
    write_page(
        page,
        {
            "title": "AI UX Case Study Strategy",
            "type": "concept",
            "confidence": "MEDIUM",
            "created": "2026-04-20",
            "source_refs": ["case.md"],
            "content_hash": "abc",
        },
        """## Definition

AI UX case studies need trust framing [source: case.md, §Strategy].

## Key Properties

- Evidence should include metrics [source: case.md, §Evidence].

## How It Works

Connect [[Agentic UX]] to [[Product Strategy]].

## Relationships

- [[Agentic UX]]:extends
- [[Product Strategy]]:extends

## Open Questions

- How should risk be represented?

## Sources

- [source: case.md, §Strategy]
""",
    )
    write_provenance(page, {
        "page": "AI UX Case Study Strategy",
        "content_hash": "abc",
        "sources": [{"file": "case.md", "content_hash": "wrong"}],
        "claims": [],
        "derived_concepts": [],
    })
    return wiki_dir, sources_dir, source


def test_source_coverage_reports_uncovered_sections(tmp_path):
    wiki_dir, sources_dir, source = _make_wiki_and_source(tmp_path)

    report = source_coverage(str(source), wiki_dir=wiki_dir, sources_dir=sources_dir)

    assert report["source"] == "case.md"
    assert report["claims"] >= 2
    assert "Risks" in report["sections"]["uncovered"]
    assert report["score"] > 0


def test_page_quality_refreshes_claims(tmp_path):
    wiki_dir, _sources_dir, _source = _make_wiki_and_source(tmp_path)

    report = page_quality("AI UX Case Study Strategy", wiki_dir=wiki_dir)

    assert report["pages"][0]["claims"] >= 2
    assert report["pages"][0]["citations"] >= 2
