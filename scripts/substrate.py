"""Agent Wiki Substrate commands.

Builds model-free context packs, triage queues, scaffolds, and draft artifacts
from the existing file-based wiki.
"""

from __future__ import annotations

import json
import re
import sys
import textwrap
from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

from lint import lint
from query import find_seed_pages, traverse_typed_graph
from state import generate_health, generate_state, save_health, save_state
from provenance import extract_claims_from_page
from utils import (
    GRAPH_PATH,
    WIKI_DIR,
    hash_content,
    page_exists,
    read_page,
    write_page,
)


SCHEMA_VERSION = "1.0"
SOURCE_REF_PATTERN = re.compile(r"\[source:\s*([^,\]]+),\s*§([^\]]+)\]")
MISSING_LINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")
SECTION_PATTERN = re.compile(r"^##\s+(.+)$", re.MULTILINE)
MARKDOWN_HEADING_PATTERN = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _wiki_root(wiki_dir: Path) -> Path:
    return wiki_dir.parent


def _relative_path(path: Path, wiki_dir: Path) -> str:
    try:
        return str(path.relative_to(_wiki_root(wiki_dir)))
    except ValueError:
        return str(path)


def _load_graph(wiki_dir: Path) -> dict[str, Any]:
    graph_path = wiki_dir / "_graph.json"
    if not graph_path.exists() and wiki_dir == WIKI_DIR:
        graph_path = GRAPH_PATH
    if not graph_path.exists():
        return {}
    try:
        return json.loads(graph_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _current_health(wiki_dir: Path) -> dict[str, Any]:
    if wiki_dir == WIKI_DIR:
        with redirect_stdout(StringIO()):
            issues = lint()
        health = generate_health(lint_results=[
            {
                "severity": issue.severity,
                "code": issue.code,
                "page": issue.page,
                "message": issue.message,
            }
            for issue in issues
        ])
        save_health(health)
        state = generate_state()
        save_state(state)
        return health

    health_path = wiki_dir / "_health.json"
    if health_path.exists():
        try:
            return json.loads(health_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"errors": 0, "warnings": 0, "issues": []}


def _health_status(health: dict[str, Any]) -> str:
    if health.get("errors", 0) > 0:
        return "error"
    if health.get("warnings", 0) > 0:
        return "warning"
    return "ok"


def _page_names(wiki_dir: Path) -> set[str]:
    names: set[str] = set()
    for subdir in ("concepts", "entities"):
        page_dir = wiki_dir / subdir
        if page_dir.exists():
            names.update(page.stem for page in page_dir.glob("*.md"))
    return names


def _sections(content: str) -> list[str]:
    return [match.group(1).strip() for match in SECTION_PATTERN.finditer(content)]


def _extract_claims(page: Path, max_claims: int = 5) -> list[dict[str, Any]]:
    claims = extract_claims_from_page(page, max_claims=max_claims)
    for claim in claims:
        claim["page"] = page.stem
    return claims


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2
    }


def _pack_score(query: str, page_item: dict[str, Any], post_content: str) -> float:
    query_tokens = _tokens(query)
    title = str(page_item.get("title", ""))
    title_tokens = _tokens(title)
    content_tokens = _tokens(post_content[:2000])
    score = float(page_item.get("score", 0))

    if query.strip().lower() == title.strip().lower():
        score += 100
    if title.lower() in query.lower() or query.lower() in title.lower():
        score += 35
    score += 14 * len(query_tokens & title_tokens)
    score += 2 * len(query_tokens & content_tokens)
    if page_item.get("traversal_path", [title])[0] == Path(page_item.get("path", title)).stem:
        score += 10
    confidence = str(page_item.get("confidence", "")).upper()
    score += {"HIGH": 8, "MEDIUM": 4, "LOW": 0}.get(confidence, 0)
    if page_item.get("stale"):
        score -= 30
    return round(score, 2)


def _issue_missing_target(message: str) -> str | None:
    match = MISSING_LINK_PATTERN.search(message)
    return match.group(1) if match else None


def _missing_pages_from_health(health: dict[str, Any]) -> list[str]:
    missing: set[str] = set()
    for issue in health.get("issues", []):
        code = str(issue.get("code", "")).upper()
        if code in {"BROKEN_LINK", "BROKEN_LINKS"}:
            target = _issue_missing_target(str(issue.get("message", "")))
            if target:
                missing.add(target)
    return sorted(missing)


def _relationships_for_pages(graph: dict[str, Any], page_titles: set[str], existing: set[str]) -> list[dict[str, Any]]:
    relationships: list[dict[str, Any]] = []
    for edge in graph.get("edges", []):
        source = edge.get("source", "")
        target = edge.get("target", "")
        if source not in page_titles and target not in page_titles:
            continue
        relationships.append({
            "source": source,
            "target": target,
            "type": edge.get("type", "neutral"),
            "weight": edge.get("weight", 1),
            "target_exists": target in existing,
        })
    return relationships


def build_context_pack(
    query: str,
    depth: int = 2,
    top_k: int = 5,
    wiki_dir: Path | None = None,
) -> dict[str, Any]:
    """Build an agent-readable context pack without calling an LLM."""
    wiki_dir = wiki_dir or WIKI_DIR
    health = _current_health(wiki_dir)
    graph = _load_graph(wiki_dir)
    seed_pages = find_seed_pages(query, wiki_dir=wiki_dir, top_k=top_k)
    traversed = traverse_typed_graph(seed_pages, graph, depth=depth)
    existing = _page_names(wiki_dir)

    page_items: list[dict[str, Any]] = []
    all_claims: list[dict[str, Any]] = []
    state = generate_state(wiki_dir=wiki_dir)
    state_pages = state.get("pages", {})

    for item in traversed:
        page = item["page"]
        try:
            post = read_page(page)
        except Exception:
            continue
        page_state = state_pages.get(page.stem, {})
        page_item = {
            "title": post.metadata.get("title", page.stem),
            "path": _relative_path(page, wiki_dir),
            "type": post.metadata.get("type", "unknown"),
            "confidence": post.metadata.get("confidence", ""),
            "stale": bool(page_state.get("stale", False)),
            "score": item.get("score", 0),
            "traversal_path": item.get("path", [page.stem]),
            "sections": _sections(post.content),
        }
        page_item["rank_score"] = _pack_score(query, page_item, post.content)
        page_items.append(page_item)
        all_claims.extend(_extract_claims(page))

    page_items.sort(key=lambda page: page.get("rank_score", page.get("score", 0)), reverse=True)
    page_rank: dict[str, int] = {}
    for index, page in enumerate(page_items):
        page_rank[str(page["title"])] = index
        page_rank[Path(str(page["path"])).stem] = index
    all_claims.sort(key=lambda claim: page_rank.get(claim.get("page", ""), 999))

    page_titles = {page["title"] for page in page_items} | {Path(page["path"]).stem for page in page_items}
    relationships = _relationships_for_pages(graph, page_titles, existing)
    stale_pages = sorted(
        page["title"] for page in page_items if page.get("stale")
    )
    missing_pages = sorted(set(_missing_pages_from_health(health)) | {
        rel["target"] for rel in relationships if not rel["target_exists"]
    })

    return {
        "schema_version": SCHEMA_VERSION,
        "query": query,
        "generated_at": _now(),
        "wiki": {
            "root": str(wiki_dir),
            "health": {
                "status": _health_status(health),
                "errors": health.get("errors", 0),
                "warnings": health.get("warnings", 0),
            },
        },
        "context": {
            "summary": _extractive_summary(all_claims),
            "pages": page_items,
            "claims": all_claims[:20],
        },
        "relationships": relationships,
        "warnings": {
            "stale_pages": stale_pages,
            "missing_pages": missing_pages,
            "contradictions": state.get("active_contradictions", []),
        },
        "suggested_next_actions": _suggest_actions(missing_pages, stale_pages, health),
    }


def build_agent_ingest_plan(
    source_path: Path,
    source_type: str = "article",
    wiki_dir: Path | None = None,
    max_candidates: int = 5,
) -> dict[str, Any]:
    """Build a model-free ingestion plan for the current CLI agent.

    The active agent remains responsible for reading, reasoning, and writing.
    The wiki provides source metadata, schema rails, merge candidates, commands,
    and validation gates without calling an external model.
    """
    wiki_dir = wiki_dir or WIKI_DIR
    source_path = Path(source_path)
    text = source_path.read_text(encoding="utf-8", errors="replace")
    source_hash = hash_content(text)
    headings = _source_headings(text)
    candidates = _candidate_pages_for_source(text, wiki_dir, limit=max_candidates)
    health = _current_health(wiki_dir)
    source_name = source_path.name
    concept_sections = [
        "Definition",
        "Key Properties",
        "How It Works",
        "Relationships",
        "Open Questions",
        "Sources",
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "agent-first",
        "generated_at": _now(),
        "source": {
            "path": str(source_path),
            "filename": source_name,
            "type": source_type,
            "bytes": source_path.stat().st_size,
            "characters": len(text),
            "content_hash": source_hash,
            "large_source": len(text) > 100_000,
            "headings": headings[:24],
        },
        "wiki": {
            "root": str(wiki_dir),
            "health": {
                "status": _health_status(health),
                "errors": health.get("errors", 0),
                "warnings": health.get("warnings", 0),
            },
        },
        "merge_candidates": candidates,
        "page_contract": {
            "type": "concept",
            "required_frontmatter": [
                "title",
                "type",
                "confidence",
                "created",
                "source_refs",
                "content_hash",
            ],
            "required_sections": concept_sections,
            "citation_format": f"[source: {source_name}, §section]",
            "relationship_syntax": "[[Target Page]]:relation_type",
        },
        "agent_workflow": [
            "Read the source directly; do not call another model unless the user asks for unattended automation.",
            "Check merge_candidates before creating new pages; merge into existing pages when they represent the same concept.",
            "Create atomic wiki/drafts/*.md pages with one concept per page and inline source citations.",
            "Use LOW confidence for inferences, MEDIUM for single-source facts, and HIGH only when multiple independent sources agree.",
            "Run `wiki validate`, then `wiki rebuild`, then `wiki quality --json`.",
            "Use `wiki coverage <source> --json` to verify the source is represented.",
        ],
        "suggested_commands": [
            f'wiki register "{source_path}" --type {source_type}',
            'wiki pack "related context" --json',
            'wiki scaffold "Concept Title" --type concept',
            "wiki validate",
            "wiki rebuild",
            "wiki quality --json",
            f'wiki coverage "{source_path}" --json',
        ],
        "external_model_policy": {
            "default": "not_required",
            "use_external_model_when": [
                "running unattended batch ingestion",
                "processing low-value sources without an active CLI agent",
                "using a cheap local model for first-pass draft suggestions",
            ],
            "avoid_external_model_when": [
                "a capable CLI agent is already reading and writing the wiki",
                "source quality requires human/agent judgment",
                "large one-shot extraction would create timeout or over-compression risk",
            ],
        },
    }


def render_agent_ingest_plan(plan: dict[str, Any]) -> str:
    """Render an agent ingestion plan for humans and CLI agents."""
    source = plan["source"]
    health = plan["wiki"]["health"]
    headings = "\n".join(f"- {heading['text']}" for heading in source.get("headings", [])[:10])
    if not headings:
        headings = "- No markdown headings detected."
    candidates = "\n".join(
        f"- {candidate['title']} ({candidate['path']}, score {candidate['score']})"
        for candidate in plan.get("merge_candidates", [])
    )
    if not candidates:
        candidates = "- No strong merge candidates found."
    commands = "\n".join(f"- `{command}`" for command in plan["suggested_commands"])
    workflow = "\n".join(f"{index}. {step}" for index, step in enumerate(plan["agent_workflow"], start=1))

    return f"""# Agent-First Ingestion Plan

Source: `{source['path']}`
Type: `{source['type']}`
Characters: {source['characters']}
Hash: `{source['content_hash']}`
Large source: {str(source['large_source']).lower()}
Wiki health: {health['status']} ({health['errors']} errors, {health['warnings']} warnings)

## Why This Is Agent-First

The active CLI agent should read the source and write the wiki pages. The wiki provides durable memory, schema validation, provenance, graph links, quality checks, and retrieval packs. No external model is required for this workflow.

## Source Headings

{headings}

## Merge Candidates

{candidates}

## Page Contract

- Type: `concept`
- Required sections: {", ".join(plan["page_contract"]["required_sections"])}
- Citation format: `{plan["page_contract"]["citation_format"]}`
- Relationship syntax: `{plan["page_contract"]["relationship_syntax"]}`

## Agent Workflow

{workflow}

## Suggested Commands

{commands}
"""


def _source_headings(text: str) -> list[dict[str, Any]]:
    headings: list[dict[str, Any]] = []
    for match in MARKDOWN_HEADING_PATTERN.finditer(text):
        level = len(match.group(1))
        title = match.group(2).strip()
        if title:
            headings.append({"level": level, "text": title})
    return headings


def _candidate_pages_for_source(text: str, wiki_dir: Path, limit: int = 5) -> list[dict[str, Any]]:
    source_tokens = _tokens(text[:50_000])
    candidates: list[dict[str, Any]] = []
    for subdir in ("concepts", "entities", "drafts"):
        page_dir = wiki_dir / subdir
        if not page_dir.exists():
            continue
        for page in page_dir.glob("*.md"):
            if page.name.startswith("_"):
                continue
            try:
                post = read_page(page)
            except Exception:
                continue
            title = str(post.metadata.get("title", page.stem))
            title_tokens = _tokens(title)
            page_tokens = _tokens(post.content[:5000])
            title_overlap = len(source_tokens & title_tokens)
            content_overlap = len(source_tokens & page_tokens)
            score = (title_overlap * 10) + content_overlap
            if score <= 0:
                continue
            candidates.append({
                "title": title,
                "path": _relative_path(page, wiki_dir),
                "type": post.metadata.get("type", "unknown"),
                "confidence": post.metadata.get("confidence", ""),
                "score": score,
            })
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[:limit]


def _extractive_summary(claims: list[dict[str, Any]]) -> str:
    if not claims:
        return ""
    return "\n".join(_claim_as_markdown(claim) for claim in claims[:3])


def _suggest_actions(missing_pages: list[str], stale_pages: list[str], health: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    for page in missing_pages[:3]:
        actions.append(f'Scaffold missing page: {page}')
    for page in stale_pages[:3]:
        actions.append(f"Refresh stale page: {page}")
    if health.get("errors", 0):
        actions.append("Fix lint errors before creating new content")
    return actions


def build_triage(wiki_dir: Path | None = None) -> dict[str, Any]:
    """Build a prioritized maintenance queue."""
    wiki_dir = wiki_dir or WIKI_DIR
    health = _current_health(wiki_dir)
    state = generate_state(wiki_dir=wiki_dir)
    pages = state.get("pages", {})
    items: list[dict[str, Any]] = []
    missing_counts: dict[str, int] = {}
    missing_sources: dict[str, set[str]] = {}

    for issue in health.get("issues", []):
        code = str(issue.get("code", "")).upper()
        page = issue.get("page", "")
        message = issue.get("message", "")
        if code in {"BROKEN_LINK", "BROKEN_LINKS"}:
            target = _issue_missing_target(str(message))
            if target:
                missing_counts[target] = missing_counts.get(target, 0) + 1
                missing_sources.setdefault(target, set()).add(str(page))
            continue
        if code in {"STALE_PAGE", "STALE_PAGES"}:
            items.append(_triage_item("stale_page", str(page), str(message), pages))
            continue
        if code in {"UNRESOLVED_CONTRADICTION", "CONTRADICTION"}:
            items.append(_triage_item("contradiction", str(page), str(message), pages))
            continue
        if str(issue.get("severity", "")).upper() == "ERROR":
            items.append(_triage_item("error", str(page), str(message), pages))

    for target, count in missing_counts.items():
        sources = sorted(missing_sources.get(target, set()))
        score = 20 + (count * 10)
        items.append({
            "id": f"missing-page:{target}",
            "type": "missing_page",
            "priority": _priority(score),
            "score": score,
            "title": target,
            "reason": f"Linked from {count} page(s): {', '.join(sources[:3])}",
            "command": f'wiki scaffold "{target}" --type concept',
        })

    for page in state.get("thin_pages", []):
        items.append(_manual_item("thin_page", page, 15, "Page has very few sections"))
    for page in state.get("stale_pages", []):
        if not any(item["id"] == f"stale-page:{page}" for item in items):
            items.append(_manual_item("stale_page", page, 25, "Source content has changed"))

    items.sort(key=lambda item: item.get("score", 0), reverse=True)
    missing_pages = sorted(missing_counts.keys())
    return {
        "schema_version": SCHEMA_VERSION,
        "status": _health_status(health),
        "counts": {
            "errors": health.get("errors", 0),
            "warnings": health.get("warnings", 0),
            "stale_pages": len(state.get("stale_pages", [])),
            "missing_pages": len(missing_pages),
            "contradictions": len(state.get("active_contradictions", [])),
            "thin_pages": len(state.get("thin_pages", [])),
        },
        "items": items,
    }


def _triage_item(issue_type: str, page: str, reason: str, pages: dict[str, Any]) -> dict[str, Any]:
    score_by_type = {
        "error": 100,
        "contradiction": 50,
        "stale_page": 25,
    }
    score = score_by_type.get(issue_type, 10)
    confidence = pages.get(page, {}).get("confidence", "")
    if confidence == "HIGH":
        score += 15
    elif confidence == "MEDIUM":
        score += 8
    return {
        "id": f"{issue_type.replace('_', '-')}:{page}",
        "type": issue_type,
        "priority": _priority(score),
        "score": score,
        "title": page,
        "reason": reason,
        "command": "wiki health",
    }


def _manual_item(issue_type: str, page: str, score: int, reason: str) -> dict[str, Any]:
    return {
        "id": f"{issue_type.replace('_', '-')}:{page}",
        "type": issue_type,
        "priority": _priority(score),
        "score": score,
        "title": page,
        "reason": reason,
        "command": "wiki refine",
    }


def _priority(score: int) -> str:
    if score >= 50:
        return "high"
    if score >= 20:
        return "medium"
    return "low"


def scaffold_page(
    title: str,
    page_type: str = "concept",
    source: str = "triage:missing-link",
    force: bool = False,
    wiki_dir: Path | None = None,
) -> Path:
    """Create a schema-valid draft stub for a missing page."""
    wiki_dir = wiki_dir or WIKI_DIR
    existing = page_exists(title) if wiki_dir == WIKI_DIR else _page_exists_in(title, wiki_dir)
    if existing and not force:
        raise FileExistsError(f"Page already exists: {existing}")

    drafts_dir = wiki_dir / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    safe_title = title.replace("/", "-").replace("\\", "-").strip()
    draft_path = drafts_dir / f"{safe_title}.md"
    if draft_path.exists() and not force:
        raise FileExistsError(f"Draft already exists: {draft_path}")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if page_type == "entity":
        content = _entity_stub(title, source)
        metadata = {
            "title": title,
            "type": "entity",
            "entity_type": "unknown",
            "created": today,
            "source_refs": [source],
            "content_hash": hash_content(content),
        }
    else:
        content = _concept_stub(title, source)
        metadata = {
            "title": title,
            "type": "concept",
            "confidence": "LOW",
            "created": today,
            "source_refs": [source],
            "content_hash": hash_content(content),
        }
    write_page(draft_path, metadata, content)
    return draft_path


def _page_exists_in(title: str, wiki_dir: Path) -> Path | None:
    for subdir in ("concepts", "entities", "drafts"):
        page_dir = wiki_dir / subdir
        if not page_dir.exists():
            continue
        for page in page_dir.glob("*.md"):
            if page.stem.lower() == title.lower():
                return page
    return None


def _concept_stub(title: str, source: str) -> str:
    return f"""## Definition

> [!note] Inference: Scaffolded from `{source}`. Add cited facts before promotion.

## Key Properties

- TODO: Add citation-backed properties.

## How It Works

TODO: Add explanation with source citations.

## Relationships

- TODO: Link related concepts with typed wikilinks.

## Open Questions

- What source should ground `{title}`?

## Sources

- {source}
"""


def _entity_stub(title: str, source: str) -> str:
    return f"""## Overview

> [!note] Inference: Scaffolded from `{source}`. Add cited facts before promotion.

## Contributions

- TODO: Add citation-backed contributions.

## Relationships

- TODO: Link related concepts or entities.

## Sources

- {source}
"""


def draft_artifact(
    kind: str,
    topic: str,
    audience: str | None = None,
    wiki_dir: Path | None = None,
) -> dict[str, Any]:
    """Create a citation-preserving draft artifact from a context pack."""
    wiki_dir = wiki_dir or WIKI_DIR
    pack = build_context_pack(topic, wiki_dir=wiki_dir)
    content = _render_artifact(kind, topic, audience, pack)
    safe_topic = topic.replace("/", "-").replace("\\", "-").strip()
    output_path = (wiki_dir / "drafts" / f"{safe_topic} {kind}.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "topic": topic,
        "audience": audience,
        "path": _relative_path(output_path, wiki_dir),
        "context_pages": [page["title"] for page in pack["context"]["pages"]],
        "warnings": pack["warnings"],
        "content": content,
    }


def _render_artifact(kind: str, topic: str, audience: str | None, pack: dict[str, Any]) -> str:
    claims = pack["context"]["claims"]
    warning_lines = []
    for missing in pack["warnings"]["missing_pages"][:5]:
        warning_lines.append(f"- Missing page: [[{missing}]]")
    for stale in pack["warnings"]["stale_pages"][:5]:
        warning_lines.append(f"- Stale page: [[{stale}]]")
    warnings = "\n".join(warning_lines) if warning_lines else "- No substrate warnings."
    evidence = "\n".join(_claim_as_markdown(claim) for claim in claims[:10]) or "- No citation-backed claims found."
    sources = _sources_from_claims(claims)

    if kind == "case-study":
        return f"""# {topic} Case Study

Audience: {audience or "general"}

## Situation

{pack["context"]["summary"] or "TODO: Add situation from cited context."}

## Problem

TODO: Define the problem using cited evidence.

## Insight

TODO: Identify the key insight.

## Approach

TODO: Describe the approach.

## Design/Implementation Principles

{evidence}

## Evidence

{evidence}

## Risks and Tradeoffs

{warnings}

## Outcome Metrics

TODO: Add measurable outcomes.

## Open Questions

{warnings}

## Sources

{sources}
"""

    if kind == "playbook":
        return f"""# {topic} Playbook

Audience: {audience or "general"}

## When To Use

TODO: Define trigger conditions.

## Principles

{evidence}

## Steps

TODO: Add operational steps.

## Checks

{warnings}

## Sources

{sources}
"""

    if kind == "decision-memo":
        return f"""# {topic} Decision Memo

Audience: {audience or "general"}

## Decision

TODO: State the decision.

## Context

{pack["context"]["summary"] or "TODO: Add cited context."}

## Evidence

{evidence}

## Risks

{warnings}

## Recommendation

TODO: Add recommendation.

## Sources

{sources}
"""

    return f"""# {topic} Brief

Audience: {audience or "general"}

## Bottom Line

{pack["context"]["summary"] or "TODO: Add bottom line from cited context."}

## What We Know

{evidence}

## Gaps

{warnings}

## Recommended Next Actions

{_actions_as_markdown(pack.get("suggested_next_actions", []))}

## Sources

{sources}
"""


def _claim_as_markdown(claim: dict[str, Any]) -> str:
    source_refs = claim.get("source_refs", [])[:2]
    citations = " ".join(
        f"[source: {ref.get('source') or ref.get('file')}, §{ref.get('section', '?')}]"
        for ref in source_refs
    )
    text = textwrap.shorten(str(claim.get("text", "")), width=260, placeholder="…")
    return f"- {text} {citations}".rstrip()


def _sources_from_claims(claims: list[dict[str, Any]]) -> str:
    source_lines: list[str] = []
    seen: set[tuple[str, str]] = set()
    for claim in claims:
        for ref in claim.get("source_refs", []):
            key = (ref["source"], ref["section"])
            if key in seen:
                continue
            seen.add(key)
            source_lines.append(f"- [source: {ref['source']}, §{ref['section']}]")
    return "\n".join(source_lines) if source_lines else "- No sources found."


def _actions_as_markdown(actions: list[str]) -> str:
    if not actions:
        return "- No suggested actions."
    return "\n".join(f"- {action}" for action in actions)
