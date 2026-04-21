"""LLM Knowledge Base v2 — Refine Stage.

Stage 4 of the pipeline: gap analysis, contradiction detection,
counter-argument generation hints, and staleness checking.
"""

from __future__ import annotations

import re
from pathlib import Path

import frontmatter

from scripts.provenance import get_stale_pages
from scripts.recheck_scheduler import (
    should_recheck_page,
    record_recheck_result,
    load_schedule,
)
from scripts.schema import load_schema, get_page_type_config
from scripts.utils import (
    WIKI_DIR,
    SOURCES_DIR,
    extract_wikilinks,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _list_pages(wiki_dir: Path) -> list[Path]:
    """List all .md files in wiki_dir (recursive)."""
    return sorted(wiki_dir.rglob("*.md"))


def _page_stems(wiki_dir: Path) -> set[str]:
    """Return a set of all page stems (lowercase) in wiki_dir."""
    return {p.stem.lower() for p in _list_pages(wiki_dir)}


def _page_exists_in(target: str, wiki_dir: Path) -> bool:
    """Check whether a page with the given title exists in wiki_dir."""
    return target.lower() in _page_stems(wiki_dir)


# ── Thin Pages ────────────────────────────────────────────────────────────────


def find_thin_pages(wiki_dir: Path | None = None, schema: dict | None = None) -> list[dict]:
    """Find pages with fewer than 2 content sections.

    A content section is a ## heading (not frontmatter).
    Returns list of dicts: [{"page": name, "section_count": int, "type": page_type}]
    """
    if wiki_dir is None:
        wiki_dir = WIKI_DIR

    thin: list[dict] = []
    for page_path in _list_pages(wiki_dir):
        post = frontmatter.load(str(page_path))
        content = post.content
        section_count = len(re.findall(r"^## ", content, re.MULTILINE))
        if section_count < 2:
            page_type = post.metadata.get("type", "unknown")
            thin.append({
                "page": page_path.stem,
                "section_count": section_count,
                "type": page_type,
            })
    return thin


# ── Contradictions ────────────────────────────────────────────────────────────


def find_contradictions(wiki_dir: Path | None = None) -> list[dict]:
    """Find pages with unresolved contradiction callouts.

    Detects ``> [!warning] CONTRADICTION`` followed by ``UNRESOLVED``
    in the same callout block.
    Returns list of dicts: [{"page": name, "callout_count": int}]
    """
    if wiki_dir is None:
        wiki_dir = WIKI_DIR

    results: list[dict] = []
    for page_path in _list_pages(wiki_dir):
        content = page_path.read_text(encoding="utf-8")

        # Strip frontmatter so we only scan the body
        _, body = _split_frontmatter(content)

        callout_count = 0
        # Find callout blocks: lines starting with "> " that follow
        # a "> [!warning] CONTRADICTION" opener.
        lines = body.split("\n")
        in_contradiction_callout = False
        callout_has_unresolved = False

        for line in lines:
            stripped = line.strip()
            if stripped == "> [!warning] CONTRADICTION":
                # Close previous callout if any
                if in_contradiction_callout and callout_has_unresolved:
                    callout_count += 1
                in_contradiction_callout = True
                callout_has_unresolved = False
                continue

            if in_contradiction_callout:
                if stripped.startswith("> "):
                    if "UNRESOLVED" in stripped:
                        callout_has_unresolved = True
                else:
                    # Callout block ended
                    if callout_has_unresolved:
                        callout_count += 1
                    in_contradiction_callout = False
                    callout_has_unresolved = False

        # Handle callout that extends to end of content
        if in_contradiction_callout and callout_has_unresolved:
            callout_count += 1

        if callout_count > 0:
            results.append({
                "page": page_path.stem,
                "callout_count": callout_count,
            })
    return results


def _split_frontmatter(content: str) -> tuple[str, str]:
    """Split a markdown file into (frontmatter_str, body_str).

    Returns ('', content) if no frontmatter is found.
    """
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            fm = content[3:end].strip()
            body = content[end + 3:].lstrip("\n")
            return fm, body
    return "", content


# ── Gap Pages ────────────────────────────────────────────────────────────────


def find_gap_pages(wiki_dir: Path | None = None) -> list[dict]:
    """Find wikilinks pointing to non-existent pages.

    These are concepts that are mentioned but don't have their own page yet.
    Returns list of dicts: [{"source": linking_page, "target": missing_page}]
    """
    if wiki_dir is None:
        wiki_dir = WIKI_DIR

    stems = _page_stems(wiki_dir)
    gaps: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for page_path in _list_pages(wiki_dir):
        text = page_path.read_text(encoding="utf-8")
        # Skip frontmatter when scanning for wikilinks
        _, body = _split_frontmatter(text)
        targets = extract_wikilinks(body)
        for target in targets:
            if target.lower() not in stems:
                key = (page_path.stem, target)
                if key not in seen:
                    seen.add(key)
                    gaps.append({
                        "source": page_path.stem,
                        "target": target,
                    })
    return gaps


# ── Staleness ─────────────────────────────────────────────────────────────────


def check_staleness_all(wiki_dir: Path | None = None, sources_dir: Path | None = None) -> list[str]:
    """Find all pages whose source references have changed.

    Delegates to provenance.get_stale_pages.
    Returns list of page names that are stale.
    """
    if wiki_dir is None:
        wiki_dir = WIKI_DIR
    if sources_dir is None:
        sources_dir = SOURCES_DIR

    return get_stale_pages(wiki_dir, sources_dir)


# ── Counter-Arguments ─────────────────────────────────────────────────────────


_COUNTER_SECTION_RE = re.compile(r"^## Counter[- ]Arguments", re.MULTILINE)


def find_pages_without_counter_args(wiki_dir: Path | None = None) -> list[dict]:
    """Find concept pages with HIGH or MEDIUM confidence that lack
    a '## Counter-Arguments' or '## Counter-Arguments & Data Gaps' section.

    Returns list of dicts: [{"page": name, "confidence": str}]
    """
    if wiki_dir is None:
        wiki_dir = WIKI_DIR

    results: list[dict] = []
    for page_path in _list_pages(wiki_dir):
        post = frontmatter.load(str(page_path))
        confidence = post.metadata.get("confidence", "")
        if confidence not in ("HIGH", "MEDIUM"):
            continue

        content = post.content
        if _COUNTER_SECTION_RE.search(content):
            continue

        results.append({
            "page": page_path.stem,
            "confidence": confidence,
        })
    return results


# ── Refinement Task Aggregation ──────────────────────────────────────────────


def generate_refinement_tasks(
    wiki_dir: Path | None = None,
    sources_dir: Path | None = None,
    schema: dict | None = None,
) -> list[dict]:
    """Aggregate all refinement tasks into a prioritized list.

    Runs all checks: thin pages, contradictions, gap pages, staleness,
    counter-arguments.
    Returns list of dicts, each with:
    - task_type: "thin_page" | "contradiction" | "gap" | "stale" | "missing_counter_args"
    - severity: "high" | "medium" | "low"
    - page: page name (or source for gaps)
    - details: dict with task specific info
    """
    if wiki_dir is None:
        wiki_dir = WIKI_DIR
    if sources_dir is None:
        sources_dir = SOURCES_DIR
    if schema is None:
        schema = load_schema()

    tasks: list[dict] = []

    # Contradictions — high severity
    for item in find_contradictions(wiki_dir):
        tasks.append({
            "task_type": "contradiction",
            "severity": "high",
            "page": item["page"],
            "details": {"callout_count": item["callout_count"]},
        })

    # Gap pages — high severity
    for item in find_gap_pages(wiki_dir):
        tasks.append({
            "task_type": "gap",
            "severity": "high",
            "page": item["source"],
            "details": {"target": item["target"]},
        })

    # Stale pages — backoff-aware, confidence-weighted
    # Load the recheck schedule once to avoid per-page disk reads
    recheck_sched = load_schedule()
    currently_stale = check_staleness_all(wiki_dir, sources_dir)
    stale_set = set(currently_stale)

    for page_name in currently_stale:
        # Always include currently-stale pages as tasks; severity is boosted
        # if the page is overdue for its next scheduled check
        entry = recheck_sched.get(page_name, {})
        overdue_h = 0.0
        if entry.get("next_check_after"):
            from datetime import datetime, timezone
            due_dt = datetime.fromisoformat(entry["next_check_after"])
            if due_dt.tzinfo is None:
                due_dt = due_dt.replace(tzinfo=timezone.utc)
            overdue_h = (datetime.now(timezone.utc) - due_dt).total_seconds() / 3600
            if overdue_h > 0:
                overdue_h = overdue_h
        tasks.append({
            "task_type": "stale",
            "severity": "high" if overdue_h > 0 else "medium",
            "page": page_name,
            "details": {
                "reason": "source_changed",
                "overdue_h": overdue_h,
                "backoff_applied": entry.get("current_interval_h", None),
            },
        })
        # Record this recheck result so interval resets
        confidence = entry.get("confidence", "MEDIUM")
        record_recheck_result(page_name, is_stale=True, confidence=confidence)

    # Add pages that are not currently stale but ARE due for their scheduled recheck.
    # These are pages whose backoff window has expired — they haven't been verified
    # since the window closed.
    for page_name, entry in recheck_sched.items():
        if page_name in stale_set:
            continue  # already covered above
        if not should_recheck_page(page_name, schedule=recheck_sched):
            continue  # still within backoff window
        tasks.append({
            "task_type": "scheduled_recheck",
            "severity": "low",
            "page": page_name,
            "details": {
                "reason": "backoff_expired",
                "interval_h": entry.get("current_interval_h", 24),
                "last_checked": entry.get("last_checked_at"),
            },
        })
        # Record a clean result so backoff applies
        confidence = entry.get("confidence", "MEDIUM")
        record_recheck_result(page_name, is_stale=False, confidence=confidence)

    # Thin pages — medium severity
    for item in find_thin_pages(wiki_dir, schema):
        tasks.append({
            "task_type": "thin_page",
            "severity": "medium",
            "page": item["page"],
            "details": {"section_count": item["section_count"], "type": item["type"]},
        })

    # Missing counter-arguments — low severity
    for item in find_pages_without_counter_args(wiki_dir):
        tasks.append({
            "task_type": "missing_counter_args",
            "severity": "low",
            "page": item["page"],
            "details": {"confidence": item["confidence"]},
        })

    return tasks


# ── CLI ───────────────────────────────────────────────────────────────────────


def main():
    """CLI: python scripts/refine.py

    Run all refinement checks and print results.
    """
    schema = load_schema()
    wiki_dir = WIKI_DIR
    sources_dir = SOURCES_DIR

    print("=== Refinement Report ===\n")

    thin = find_thin_pages(wiki_dir, schema)
    print(f"Thin pages (< 2 sections): {len(thin)}")
    for item in thin:
        print(f"  - {item['page']} ({item['type']}, {item['section_count']} sections)")

    contradictions = find_contradictions(wiki_dir)
    print(f"\nUnresolved contradictions: {len(contradictions)}")
    for item in contradictions:
        print(f"  - {item['page']} ({item['callout_count']} callouts)")

    gaps = find_gap_pages(wiki_dir)
    print(f"\nGap pages (broken wikilinks): {len(gaps)}")
    for item in gaps:
        print(f"  - {item['source']} -> {item['target']}")

    stale = check_staleness_all(wiki_dir, sources_dir)
    print(f"\nStale pages: {len(stale)}")
    for name in stale:
        print(f"  - {name}")

    no_counter = find_pages_without_counter_args(wiki_dir)
    print(f"\nPages missing counter-arguments: {len(no_counter)}")
    for item in no_counter:
        print(f"  - {item['page']} ({item['confidence']})")

    tasks = generate_refinement_tasks(wiki_dir, sources_dir, schema)
    print(f"\n=== Total refinement tasks: {len(tasks)} ===")
    by_severity = {"high": 0, "medium": 0, "low": 0}
    for t in tasks:
        by_severity[t["severity"]] += 1
    print(f"  High: {by_severity['high']}, Medium: {by_severity['medium']}, Low: {by_severity['low']}")


if __name__ == "__main__":
    main()
