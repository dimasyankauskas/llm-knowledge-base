"""Quality and coverage checks for agent-usable wiki content."""

from __future__ import annotations

import json
import re
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from lint import lint
from provenance import check_staleness, refresh_page_claims
from utils import SOURCES_DIR, WIKI_DIR, page_exists, read_page, read_provenance


SOURCE_REF_PATTERN = re.compile(r"\[source:\s*([^,\]]+),\s*§([^\]]+)\]")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def _resolve_source(source: str, sources_dir: Path = SOURCES_DIR) -> Path:
    source_path = Path(source)
    if source_path.exists():
        return source_path
    direct = sources_dir / source
    if direct.exists():
        return direct
    for candidate in sources_dir.rglob(Path(source).name):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(source)


def _source_sections(source_path: Path) -> list[str]:
    text = source_path.read_text(encoding="utf-8")
    sections = [match.group(2).strip() for match in HEADING_PATTERN.finditer(text)]
    return sections or ["document"]


def _wiki_pages(wiki_dir: Path) -> list[Path]:
    pages: list[Path] = []
    for subdir in ("concepts", "entities"):
        pages.extend(sorted((wiki_dir / subdir).glob("*.md")))
    return pages


def source_coverage(source: str, wiki_dir: Path = WIKI_DIR, sources_dir: Path = SOURCES_DIR) -> dict[str, Any]:
    """Report how much of a source is represented in cited wiki pages."""
    source_path = _resolve_source(source, sources_dir=sources_dir)
    source_name = source_path.name
    sections = _source_sections(source_path)
    cited_sections: set[str] = set()
    pages: list[dict[str, Any]] = []
    claims = 0

    for page_path in _wiki_pages(wiki_dir):
        if "drafts" in page_path.parts or page_path.name.startswith("_"):
            continue
        try:
            post = read_page(page_path)
        except Exception:
            continue
        source_refs = [Path(str(ref)).name for ref in post.metadata.get("source_refs", []) or []]
        inline_refs = SOURCE_REF_PATTERN.findall(post.content)
        inline_sources = [Path(source).name for source, _section in inline_refs]
        if source_name not in source_refs and source_name not in inline_sources:
            continue

        page_claims = [
            ref_section.strip()
            for ref_source, ref_section in inline_refs
            if Path(ref_source).name == source_name
        ]
        cited_sections.update(page_claims)
        claims += len(page_claims)
        pages.append({
            "title": post.metadata.get("title", page_path.stem),
            "path": str(page_path.relative_to(wiki_dir.parent)),
            "claims": len(page_claims),
            "confidence": post.metadata.get("confidence", ""),
        })

    normalized_cited = {section.lower() for section in cited_sections}
    uncovered = [
        section for section in sections
        if section.lower() not in normalized_cited
    ]
    coverage_ratio = 1.0 if not sections else round((len(sections) - len(uncovered)) / len(sections), 3)
    source_chars = len(source_path.read_text(encoding="utf-8"))

    return {
        "source": source_name,
        "source_path": str(source_path),
        "source_chars": source_chars,
        "truncation_risk": source_chars > 100_000,
        "pages": pages,
        "claims": claims,
        "sections": {
            "total": len(sections),
            "cited": sorted(cited_sections),
            "uncovered": uncovered,
            "coverage_ratio": coverage_ratio,
        },
        "score": min(100, round(40 * bool(pages) + 30 * min(claims, 10) / 10 + 30 * coverage_ratio)),
    }


def page_quality(page: str | None = None, wiki_dir: Path = WIKI_DIR) -> dict[str, Any]:
    """Score page or whole-wiki quality for agent/human usefulness."""
    with redirect_stdout(StringIO()):
        issues = lint()
    issue_counts: dict[str, int] = {}
    issues_by_page: dict[str, list[Any]] = {}
    for issue in issues:
        issue_counts[issue.code] = issue_counts.get(issue.code, 0) + 1
        issues_by_page.setdefault(issue.page, []).append(issue)

    candidates = []
    if page:
        page_path = None
        if wiki_dir == WIKI_DIR:
            page_path = page_exists(page)
        if page_path is None:
            for candidate in _wiki_pages(wiki_dir):
                if candidate.stem.lower() == page.lower():
                    page_path = candidate
                    break
        if not page_path:
            raise FileNotFoundError(page)
        candidates = [page_path]
    else:
        candidates = [p for p in _wiki_pages(wiki_dir) if not p.name.startswith("_")]

    page_reports: list[dict[str, Any]] = []
    for page_path in candidates:
        post = read_page(page_path)
        prov = refresh_page_claims(page_path) or read_provenance(page_path) or {}
        citations = len(SOURCE_REF_PATTERN.findall(post.content))
        wikilinks = len(re.findall(r"\[\[[^\]]+\]\]", post.content))
        claims = len(prov.get("claims", []))
        stale_sources = check_staleness(prov, wiki_dir.parent / "sources") if prov else []
        sections = len(re.findall(r"^##\s+", post.content, flags=re.MULTILINE))

        score = 100
        if not prov:
            score -= 25
        if citations == 0:
            score -= 20
        if claims == 0:
            score -= 15
        if wikilinks < 2 and post.metadata.get("type") == "concept":
            score -= 10
        if stale_sources:
            score -= 20
        if sections < 4:
            score -= 10
        for issue in issues_by_page.get(page_path.stem, []):
            if issue.code == "BROKEN_LINK":
                score -= 2
            elif issue.code == "UNMARKED_INFERENCE":
                score -= 8
            elif issue.severity == "ERROR":
                score -= 20
            else:
                score -= 3

        page_reports.append({
            "title": post.metadata.get("title", page_path.stem),
            "path": str(page_path.relative_to(wiki_dir.parent)),
            "type": post.metadata.get("type", ""),
            "confidence": post.metadata.get("confidence", ""),
            "score": max(0, score),
            "citations": citations,
            "claims": claims,
            "wikilinks": wikilinks,
            "sections": sections,
            "stale_sources": stale_sources,
            "warnings": len([issue for issue in issues_by_page.get(page_path.stem, []) if issue.severity == "WARNING"]),
            "errors": len([issue for issue in issues_by_page.get(page_path.stem, []) if issue.severity == "ERROR"]),
        })

    avg_score = round(sum(p["score"] for p in page_reports) / len(page_reports), 1) if page_reports else 0
    return {
        "scope": page or "wiki",
        "score": avg_score,
        "pages": page_reports,
        "lint": {
            "errors": sum(1 for issue in issues if issue.severity == "ERROR"),
            "warnings": sum(1 for issue in issues if issue.severity == "WARNING"),
            "by_code": issue_counts,
        },
    }


def dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)
