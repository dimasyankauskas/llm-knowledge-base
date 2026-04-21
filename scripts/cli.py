"""
LLM Knowledge Base v2 — Unified CLI

Single entry point for all pipeline operations.

Usage:
    wiki ingest <source> --type <type>
    wiki lint [--json]
    wiki query "question" [--depth 2] [--json]
    wiki state
    wiki health
    ...
"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lint import LintIssue
from utils import WIKI_DIR, SOURCES_DIR, GRAPH_PATH, list_wiki_pages, read_provenance, read_page, page_exists
from schema import load_schema
from extract import register_source, check_dedup, classify_source_type
from validate import validate_draft, promote_draft
from link import build_typed_graph, verify_bidirectional_links, save_graph
from refine import generate_refinement_tasks
from recheck_scheduler import (
    get_pages_due_for_recheck,
    print_schedule_summary,
    record_recheck_result,
    load_schedule,
    should_recheck_page,
)
from lint import lint
from consolidate import find_duplicate_pages, generate_indexes, generate_timelines
from query import find_seed_pages, traverse_typed_graph, build_context
from state import generate_state, generate_health, save_state, save_health, load_state, load_health
from log import append_log
from auto_ingest import auto_ingest as run_auto_ingest
from substrate import (
    build_agent_ingest_plan,
    build_context_pack,
    build_triage,
    draft_artifact,
    render_agent_ingest_plan,
    scaffold_page,
)
from quality import page_quality, source_coverage

DEFAULT_PAGE_TYPE = "concept"


def _lint_issues_to_dicts(issues: list[LintIssue]) -> list[dict]:
    """Convert LintIssue objects to dicts for generate_health compatibility."""
    return [
        {"severity": i.severity, "code": i.code, "page": i.page, "message": i.message}
        for i in issues
    ]


def cmd_ingest(args):
    """Full pipeline: extract → validate → link → lint → state.

    With --auto: run LLM-powered auto-ingest instead.
    """
    if getattr(args, "auto", False):
        cmd_auto_ingest(args)
        return

    source = Path(args.source)
    source_type = args.type or classify_source_type(source)

    # Extract
    dest = register_source(source, source_type=source_type)
    print(f"Registered: {dest}")

    # Link
    schema = load_schema()
    graph = build_typed_graph(schema=schema)
    save_graph(graph)

    # Lint
    issues = lint()
    errors = sum(1 for i in issues if i.severity == "ERROR")
    warnings = sum(1 for i in issues if i.severity == "WARNING")
    print(f"Lint: {errors} errors, {warnings} warnings")

    # State
    state = generate_state()
    save_state(state)
    health = generate_health(lint_results=_lint_issues_to_dicts(issues))
    save_health(health)

    # Log
    append_log("ingest", f"Source: {source.name}", {
        "Type": source_type,
        "Destination": str(dest),
        "Graph": f"{graph.get('node_count', 0)} nodes, {graph.get('edge_count', 0)} edges",
        "Lint": f"{errors} errors, {warnings} warnings",
    })


def cmd_auto_ingest(args):
    """LLM-powered auto-ingest: read source → generate page → validate → promote."""
    source = Path(args.source)
    page_type = args.type or DEFAULT_PAGE_TYPE
    retry_on_error = not (args.no_retry or args.fast)
    extraction_mode = getattr(args, "mode", "standard")

    print(f"\n{'='*60}")
    print(f"  Auto-ingest: {source.name}")
    if extraction_mode == "gap":
        print(f"  Mode: gap-driven (InfraNodus-style)")
    print(f"{'='*60}\n")

    promoted = run_auto_ingest(
        source_path=source,
        page_type=page_type,
        verbose=True,
        retry_on_error=retry_on_error,
        extraction_mode=extraction_mode,
    )

    # Post-auto-ingest: rebuild graph + lint + state
    schema = load_schema()
    graph = build_typed_graph(schema=schema)
    save_graph(graph)

    issues = lint()
    errors = sum(1 for i in issues if i.severity == "ERROR")
    warnings = sum(1 for i in issues if i.severity == "WARNING")
    print(f"\nLint: {errors} errors, {warnings} warnings")

    state = generate_state()
    save_state(state)
    health = generate_health(lint_results=_lint_issues_to_dicts(issues))
    save_health(health)

    print(f"\n{'='*60}")
    print(f"  Promoted: {len(promoted)} page(s)")
    print(f"{'='*60}")


def cmd_extract(args):
    """Register a source file."""
    source = Path(args.source)
    source_type = args.type or classify_source_type(source)
    dest = register_source(source, source_type=source_type)
    print(f"Registered: {dest}")


def cmd_validate(args):
    """Validate all draft pages."""
    schema = load_schema()
    drafts_dir = WIKI_DIR / "drafts"
    if not drafts_dir.exists():
        print("No drafts directory.")
        return

    promoted = 0
    errors = 0
    for draft in sorted(drafts_dir.glob("*.md")):
        report = validate_draft(draft, schema)
        if not report.has_errors:
            if promote_draft(draft, schema=schema):
                promoted += 1
        else:
            errors += report.error_count
            for issue in report.issues:
                if issue.severity == "ERROR":
                    print(f"  ERROR: {draft.stem}: {issue.message}")

    print(f"Validated: {promoted} promoted, {errors} errors")


def cmd_link(args):
    """Build typed graph and verify bidirectional links."""
    schema = load_schema()
    graph = build_typed_graph(schema=schema)
    save_graph(graph)

    missing = verify_bidirectional_links()
    if missing:
        print(f"Missing reverse links: {len(missing)}")
        for m in missing[:10]:
            print(f"  {m['source']} → {m['target']} ({m['type']})")
    else:
        print("All links bidirectional.")

    print(f"Graph: {len(graph.get('nodes', []))} nodes, {len(graph.get('edges', []))} edges")


def cmd_refine(args):
    """Run refinement analysis with backoff-aware stale detection."""
    tasks = generate_refinement_tasks()
    if not tasks:
        print("No refinement tasks found.")
        return

    # Sort by severity then by overdue amount
    severity_order = {"high": 0, "medium": 1, "low": 2}
    for task in sorted(
        tasks,
        key=lambda t: (
            severity_order.get(t.get("severity", "low"), 3),
            -(t.get("details", {}).get("overdue_h", 0.0)),
        ),
        reverse=False,
    ):
        page = task.get("page", "")
        sev = task.get("severity", "?")
        ttype = task.get("task_type", "")
        details = task.get("details", {})
        extra = ""
        if ttype == "stale" and details.get("overdue_h", 0) > 0:
            extra = f" (overdue {details['overdue_h']:.1f}h)"
        elif ttype == "stale" and details.get("backoff_applied"):
            extra = f" [interval={details['backoff_applied']:.1f}h]"
        elif ttype == "scheduled_recheck":
            extra = f" (backoff expired, was {details.get('interval_h', 24):.1f}h interval)"
        print(f"  [{sev.upper():>6}] {ttype}: {page}{extra}")


def cmd_lint(args):
    """Run all 12 lint checks."""
    if args.json:
        # Ensure machine-readable output: suppress lint's rich console output.
        with redirect_stdout(StringIO()):
            issues = lint()
    else:
        issues = lint()
    errors = sum(1 for i in issues if i.severity == "ERROR")
    warnings = sum(1 for i in issues if i.severity == "WARNING")
    if args.json:
        output = {
            "errors": errors,
            "warnings": warnings,
            "issues": [
                {"severity": i.severity, "code": i.code, "page": i.page, "message": i.message}
                for i in issues
            ],
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        for issue in issues:
            marker = "ERROR" if issue.severity == "ERROR" else "WARN"
            print(f"  [{marker}] {issue.page}: {issue.message} ({issue.code})")
        print(f"\n{errors} errors, {warnings} warnings")

    # Log
    codes = {}
    for i in issues:
        codes[i.code] = codes.get(i.code, 0) + 1
    code_summary = ", ".join(f"{v}× {k}" for k, v in sorted(codes.items())) if codes else "clean"
    append_log("lint", f"{errors} errors, {warnings} warnings", {
        "Breakdown": code_summary,
    })


def cmd_consolidate(args):
    """Merge duplicates, generate indexes, generate timelines."""
    schema = load_schema()

    dupes = find_duplicate_pages()
    if dupes:
        print(f"Duplicate pairs: {len(dupes)}")
        for primary, secondary, reason in dupes:
            print(f"  {primary} <-> {secondary} ({reason})")

    generate_indexes(schema=schema)
    print("Indexes generated.")

    generate_timelines()
    print("Timelines generated.")


def cmd_state(args):
    """Print _state.json summary."""
    state = generate_state()
    save_state(state)
    print(json.dumps(state, indent=2, ensure_ascii=False))


def cmd_health(args):
    """Print _health.json summary."""
    # Ensure machine-readable output: suppress lint's rich console output.
    with redirect_stdout(StringIO()):
        issues = lint()
    health = generate_health(lint_results=_lint_issues_to_dicts(issues))
    save_health(health)
    print(json.dumps(health, indent=2, ensure_ascii=False))


def cmd_query(args):
    """Graph traversal query with LLM synthesis."""
    from query import synthesize_answer, expand_query, index_boost

    pages = list_wiki_pages()
    if not pages:
        print("Wiki is empty. Ingest some sources first.")
        return

    # Query expansion
    if getattr(args, "expand_only", False):
        queries = expand_query(args.question)
        print(f"Original: {args.question}")
        print("Expanded queries:")
        for i, q in enumerate(queries, 1):
            marker = " (original)" if q == args.question else ""
            print(f"  {i}. {q}{marker}")
        return

    if getattr(args, "no_expand", False):
        queries = [args.question]
    else:
        queries = expand_query(args.question)

    seed = find_seed_pages(queries, top_k=args.top_k)
    if not seed:
        # Fallback: try index-only search
        boosts = index_boost(args.question)
        if boosts:
            print(f"No keyword matches found. Index suggests: {', '.join(boosts.keys())}")
            print("Try: wiki query with different terms, or wiki ingest new sources.")
        else:
            print("No relevant wiki pages found.")
            print("Try: wiki query with different terms, or wiki ingest new sources.")
        return

    graph = {}
    if GRAPH_PATH.exists():
        graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))

    traversed = traverse_typed_graph(seed, graph, args.depth)
    context = build_context(traversed)

    # LLM synthesis (unless --json or --context-only)
    answer = None
    if not getattr(args, "json", False) and not getattr(args, "context_only", False):
        print(f"\n🔍 Question: {args.question}")
        if len(queries) > 1:
            print(f"📝 Expanded: {', '.join(queries[1:])}")
        print(f"📄 Seed pages: {', '.join(p.stem for p in seed)}")
        print(f"🔗 Traversed: {len(traversed)} pages (depth={args.depth})")
        print(f"📝 Context: {len(context):,} chars")
        print(f"🧠 Synthesizing answer...\n")
        try:
            answer = synthesize_answer(args.question, context)
            print(answer)
        except Exception as e:
            print(f"⚠️  LLM synthesis failed: {e}")
            print("Falling back to raw context:\n")
            print(context)

    if getattr(args, "json", False):
        output = {
            "question": args.question,
            "expanded_queries": queries if len(queries) > 1 else None,
            "seed_pages": [p.stem for p in seed],
            "traversed_pages": [
                {"page": r["page"].stem, "score": r["score"], "path": r["path"]}
                for r in traversed
            ],
            "context_chars": len(context),
            "context": context,
            "answer": answer,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))

    if getattr(args, "context_only", False):
        print(context)

    # Save last query for save-answer command
    last_query = {
        "question": args.question,
        "expanded_queries": queries if len(queries) > 1 else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "seed_pages": [p.stem for p in seed],
        "traversed_pages": [{"page": r["page"].stem, "score": r["score"]} for r in traversed],
        "context": context,
        "answer": answer,
    }
    (WIKI_DIR / "_last_query.json").write_text(
        json.dumps(last_query, indent=2, ensure_ascii=False), encoding="utf-8",
    )

    # Log
    append_log("query", f'"{args.question}"', {
        "Seeds": ", ".join(p.stem for p in seed),
        "Expanded": len(queries) > 1,
        "Traversed": f"{len(traversed)} pages",
        "Context": f"{len(context):,} chars",
        "Synthesized": "yes" if answer else "no",
    })


def cmd_pack(args):
    """Build an agent-readable context pack without LLM synthesis."""
    pack = build_context_pack(args.query, depth=args.depth, top_k=args.top_k)
    if args.json:
        print(json.dumps(pack, indent=2, ensure_ascii=False))
        return

    health = pack["wiki"]["health"]
    print(f"Query: {pack['query']}")
    print(f"Health: {health['status']} ({health['errors']} errors, {health['warnings']} warnings)")
    print(f"Pages: {len(pack['context']['pages'])}")
    for page in pack["context"]["pages"][:10]:
        stale = " stale" if page.get("stale") else ""
        print(f"  - {page['title']} [{page['type']}, {page['confidence']}]{stale}")
    if pack["warnings"]["missing_pages"]:
        print("\nMissing pages:")
        for page in pack["warnings"]["missing_pages"][:10]:
            print(f"  - {page}")
    if pack["suggested_next_actions"]:
        print("\nSuggested next actions:")
        for action in pack["suggested_next_actions"][:10]:
            print(f"  - {action}")


def cmd_agent_ingest(args):
    """Create a model-free ingestion plan for the active CLI agent."""
    source = Path(args.source)
    source_type = args.type or classify_source_type(source)
    registered_path = None
    if not args.no_register:
        registered_path = register_source(source, source_type=source_type)

    plan = build_agent_ingest_plan(
        source,
        source_type=source_type,
        max_candidates=args.max_candidates,
    )
    if registered_path:
        plan["registered_source"] = str(registered_path)

    if args.json:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return

    if registered_path:
        print(f"Registered source: {registered_path}\n")
    print(render_agent_ingest_plan(plan))


def cmd_triage(args):
    """Build a prioritized maintenance queue."""
    triage = build_triage()
    if args.json:
        print(json.dumps(triage, indent=2, ensure_ascii=False))
        return

    counts = triage["counts"]
    print(f"Status: {triage['status']}")
    print(
        "Counts: "
        f"{counts['errors']} errors, {counts['warnings']} warnings, "
        f"{counts['stale_pages']} stale, {counts['missing_pages']} missing, "
        f"{counts['contradictions']} contradictions"
    )
    if not triage["items"]:
        print("No triage items.")
        return
    print("\nTop items:")
    for item in triage["items"][:15]:
        print(f"  [{item['priority']}] {item['type']}: {item['title']}")
        print(f"      {item['reason']}")
        print(f"      {item['command']}")


def cmd_scaffold(args):
    """Create a schema-valid draft stub for a missing page."""
    try:
        draft_path = scaffold_page(
            args.title,
            page_type=args.type,
            source=args.source,
            force=args.force,
        )
    except FileExistsError as exc:
        print(str(exc))
        return
    print(f"Draft scaffolded: {draft_path}")


def cmd_draft(args):
    """Create an extractive work-product draft from wiki context."""
    artifact = draft_artifact(args.kind, args.topic, audience=args.audience)
    if args.json:
        print(json.dumps(artifact, indent=2, ensure_ascii=False))
        return
    print(f"Draft created: {artifact['path']}")
    if artifact["warnings"]["missing_pages"] or artifact["warnings"]["stale_pages"]:
        print("Warnings:")
        for page in artifact["warnings"]["missing_pages"][:5]:
            print(f"  - Missing page: {page}")
        for page in artifact["warnings"]["stale_pages"][:5]:
            print(f"  - Stale page: {page}")


def cmd_quality(args):
    """Score wiki/page usefulness for agents and humans."""
    report = page_quality(args.page)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return
    print(f"Quality: {report['score']}/100 ({report['scope']})")
    lint_report = report["lint"]
    print(f"Lint: {lint_report['errors']} errors, {lint_report['warnings']} warnings")
    for page in report["pages"][:10]:
        stale = " stale" if page["stale_sources"] else ""
        print(
            f"  - {page['title']}: {page['score']}/100, "
            f"{page['claims']} claims, {page['citations']} citations{stale}"
        )


def cmd_coverage(args):
    """Report how much of a source is represented in the wiki."""
    report = source_coverage(args.source)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return
    sections = report["sections"]
    print(f"Coverage: {report['score']}/100 for {report['source']}")
    print(
        f"Sections: {sections['coverage_ratio']:.0%} covered "
        f"({sections['total'] - len(sections['uncovered'])}/{sections['total']})"
    )
    print(f"Claims: {report['claims']}; Pages: {len(report['pages'])}")
    if sections["uncovered"]:
        print("Uncovered sections:")
        for section in sections["uncovered"][:10]:
            print(f"  - {section}")


def cmd_find(args):
    """Filter pages by metadata (tag, confidence)."""
    pages = list_wiki_pages()

    results = []
    for page in pages:
        if page.stem.startswith("_"):
            continue
        try:
            post = read_page(page)
        except Exception:
            continue

        match = True
        if args.tag:
            tags = post.metadata.get("tags", [])
            if args.tag not in tags:
                match = False
        if args.confidence:
            if post.metadata.get("confidence", "") != args.confidence:
                match = False

        if match:
            results.append({
                "page": page.stem,
                "type": post.metadata.get("type", "?"),
                "confidence": post.metadata.get("confidence", "?"),
                "tags": post.metadata.get("tags", []),
            })

    for r in results:
        tag_str = ", ".join(r["tags"][:3]) if r["tags"] else "-"
        print(f"  {r['page']} [{r['type']}] confidence={r['confidence']} tags={tag_str}")
    print(f"\n{len(results)} pages found")


def cmd_provenance(args):
    """Show evidence chain for a page."""
    page_path = page_exists(args.page)
    if not page_path:
        # Try as stem
        for p in list_wiki_pages():
            if p.stem.lower() == args.page.lower():
                page_path = p
                break

    if not page_path:
        print(f"Page not found: {args.page}")
        return

    prov = read_provenance(page_path)
    if not prov:
        print(f"No provenance for: {args.page}")
        return

    print(json.dumps(prov, indent=2, ensure_ascii=False))


def cmd_register(args):
    """Register a source file (extract only)."""
    source = Path(args.source)
    source_type = args.type or classify_source_type(source)
    dest = register_source(source, source_type=source_type)
    print(f"Registered: {dest}")


def cmd_check(args):
    """Check if a source is already ingested."""
    source = Path(args.source)
    exists = check_dedup(source)
    if exists:
        print(f"Already ingested: {source.name}")
    else:
        print(f"New source: {source.name}")


def cmd_rebuild(args):
    """Regenerate indexes + graph + state + health."""
    schema = load_schema()

    generate_indexes(schema=schema)
    print("Indexes regenerated.")

    graph = build_typed_graph(schema=schema)
    save_graph(graph)
    print(f"Graph: {len(graph.get('nodes', []))} nodes, {len(graph.get('edges', []))} edges")

    state = generate_state()
    save_state(state)
    print("State regenerated.")

    issues = lint()
    health = generate_health(lint_results=_lint_issues_to_dicts(issues))
    save_health(health)
    print(f"Health: {health['errors']} errors, {health['warnings']} warnings")

    # Log
    append_log("rebuild", "Full rebuild", {
        "Graph": f"{graph.get('node_count', 0)} nodes, {graph.get('edge_count', 0)} edges",
        "Health": f"{health.get('errors', 0)} errors, {health.get('warnings', 0)} warnings",
    })


def cmd_generate_instructions(args):
    """Generate CLAUDE.md from SCHEMA.yaml."""
    try:
        from generate_instructions import generate_claude_md
    except ImportError:
        print("generate_instructions module not found. Implement Task 13 first.")
        return

    content = generate_claude_md()
    claude_md_path = Path(__file__).parent.parent / "CLAUDE.md"
    claude_md_path.write_text(content, encoding="utf-8")
    print(f"Generated: {claude_md_path}")


def cmd_log(args):
    """Print recent log entries."""
    from utils import LOG_PATH
    if not LOG_PATH.exists():
        print("No log yet. Run some commands first.")
        return
    text = LOG_PATH.read_text(encoding="utf-8")
    # Split into entries (each starts with ## [)
    entries = text.split("\n## [")
    header = entries[0]  # noqa: F841
    body_entries = entries[1:]  # each is a log entry without the leading "## ["
    if not body_entries:
        print("Log is empty.")
        return
    # Show last N entries
    n = args.n
    for entry in body_entries[-n:]:
        print(f"## [{entry.rstrip()}")


def cmd_save_answer(args):
    """Save last query result as a draft wiki page."""
    last_query_path = WIKI_DIR / "_last_query.json"
    if not last_query_path.exists():
        print("No query to save. Run `wiki query` first.")
        return

    lq = json.loads(last_query_path.read_text(encoding="utf-8"))
    title = args.title
    page_type = args.type or "concept"
    confidence = args.confidence or "LOW"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    traversed_stems = [p["page"] for p in lq.get("traversed_pages", [])]
    source_refs = [f"[source: wiki query, §{stem}]" for stem in traversed_stems[:5]]

    # Use LLM-synthesized answer if available, otherwise fall back to context
    answer = lq.get("answer", "")

    lines = []
    lines.append(f"## Definition\n")
    lines.append(f"Synthesized answer to: *{lq.get('question', '')}*\n")
    if answer:
        lines.append(f"## Synthesis\n")
        lines.append(f"{answer}\n")
    else:
        lines.append(f"## How It Works\n")
        context = lq.get("context", "")
        if len(context) > 2000:
            context = context[:2000] + "\n\n*[Context truncated — see full query output]*"
        lines.append(f"{context}\n")
    lines.append(f"## Relationships\n")
    for stem in traversed_stems:
        lines.append(f"- [[{stem}]]")
    lines.append("")
    lines.append(f"## Open Questions\n")
    lines.append(f"- Original query: {lq.get('question', '')}\n")
    lines.append(f"## Sources\n")
    for ref in source_refs:
        lines.append(f"- {ref}")
    lines.append("")

    content = "\n".join(lines)

    # Build frontmatter
    import frontmatter
    post = frontmatter.Post(content)
    post.metadata["title"] = title
    post.metadata["type"] = page_type
    post.metadata["confidence"] = confidence
    post.metadata["created"] = today
    post.metadata["source_refs"] = source_refs
    from utils import hash_content
    post.metadata["content_hash"] = hash_content(content)

    drafts_dir = WIKI_DIR / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    draft_path = drafts_dir / f"{title}.md"
    draft_path.write_text(frontmatter.dumps(post), encoding="utf-8")

    print(f"Draft saved: {draft_path}")
    print(f"Edit it, then run `wiki validate` to promote.")

    append_log("save-answer", f'Draft: "{title}"', {
        "Question": lq.get("question", ""),
        "Pages referenced": ", ".join(traversed_stems[:5]),
    })


def cmd_recheck(args):
    """Show recheck schedule summary (default action for 'wiki recheck')."""
    print_schedule_summary()


def cmd_recheck_due(args):
    """Show pages that are due for rechecking."""
    confidence = getattr(args, "confidence", None)
    limit = getattr(args, "limit", None)
    due = get_pages_due_for_recheck(confidence_filter=confidence, limit=limit)
    if not due:
        print("No pages are currently due for rechecking.")
        return
    print(f"\nPages due for recheck ({len(due)}):\n")
    for item in due:
        stale_mark = " [CURRENTLY STALE]" if item["is_currently_stale"] else ""
        print(
            f"  {item['page_name']} [{item['confidence']}] "
            f"overdue={item['overdue_by_h']:.1f}h "
            f"interval={item['interval_h']:.1f}h{stale_mark}"
        )


def cmd_recheck_summary(args):
    """Show the full recheck schedule."""
    print_schedule_summary()


def cmd_recheck_run(args):
    """Run backoff-aware recheck on tracked pages (updates schedule)."""
    import frontmatter
    from utils import WIKI_DIR, SOURCES_DIR, list_concept_pages, list_entity_pages

    specific_page = getattr(args, "page", None)
    schedule = load_schedule()
    pages_to_check: list[tuple[str, str]] = []

    if specific_page:
        pages_to_check = [(specific_page, schedule.get(specific_page, {}).get("confidence", "MEDIUM"))]
    else:
        # Collect all tracked pages
        for page_path in list_concept_pages() + list_entity_pages():
            pages_to_check.append((page_path.stem, schedule.get(page_path.stem, {}).get("confidence", "MEDIUM")))

    from provenance import get_stale_pages
    try:
        stale_now = set(get_stale_pages(WIKI_DIR, SOURCES_DIR))
    except Exception:
        stale_now = set()

    results_stale = []
    results_clean = []
    results_skip = []

    for page_name, confidence in pages_to_check:
        if not should_recheck_page(page_name, confidence, schedule):
            results_skip.append(page_name)
            continue
        is_stale = page_name in stale_now
        entry = record_recheck_result(page_name, is_stale=is_stale, confidence=confidence)
        if is_stale:
            results_stale.append((page_name, entry["current_interval_h"]))
        else:
            results_clean.append((page_name, entry["current_interval_h"], entry["next_check_after"]))

    if args.json:
        import json as _json
        output = {
            "rechecked": len(results_stale) + len(results_clean),
            "stale": [{"page": p, "interval_h": i} for p, i in results_stale],
            "clean": [{"page": p, "interval_h": i, "next_check": n} for p, i, n in results_clean],
            "skipped": len(results_skip),
        }
        print(_json.dumps(output, indent=2, ensure_ascii=False))
        return

    if results_stale:
        print("\nStale pages (interval reset to minimum):")
        if not args.ci:
            for page_name, interval in results_stale:
                print(f"  STALE  {page_name} → interval reset to {interval:.1f}h")
        else:
            print(f"  {len(results_stale)} stale page(s)")
    if results_clean:
        print("\nClean pages (backoff applied):")
        if not args.ci:
            for page_name, interval, next_check in results_clean:
                print(f"  CLEAN  {page_name} → interval now {interval:.1f}h, next after {next_check}")
        else:
            print(f"  {len(results_clean)} clean page(s)")
    if results_skip:
        if args.ci:
            print(f"Skipped: {len(results_skip)} page(s)")
        else:
            print(f"\nSkipped (within backoff window): {len(results_skip)} pages")

    if not args.ci:
        print(f"\nTotal: {len(results_stale)} stale, {len(results_clean)} clean, {len(results_skip)} skipped")


def cmd_extract_prompt(args):
    """Generate a structured LLM prompt for creating a wiki page."""
    from extract_prompt import generate_extraction_prompt
    schema = load_schema()
    prompt = generate_extraction_prompt(
        source_name=args.source,
        page_type=args.type or "concept",
        schema=schema,
    )
    print(prompt)


def build_parser():
    """Build the argparse parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="wiki",
        description="LLM-native knowledge base engine",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ingest
    p_ingest = subparsers.add_parser("ingest", help="Full pipeline: extract → validate → link → lint → state")
    p_ingest.add_argument("source", help="Source file path")
    p_ingest.add_argument("--type", help="Source type (paper, article, transcript, code-doc)")
    p_ingest.add_argument("--auto", action="store_true", help="Run LLM-powered auto-ingest (no manual collaboration required)")
    p_ingest.add_argument("--no-retry", action="store_true", help="Skip retry loop on validation errors (trust first-pass output)")
    p_ingest.add_argument("--fast", action="store_true", help="Alias for --no-retry (fast extraction without correction)")
    p_ingest.add_argument("--mode", default="standard", choices=["standard", "gap"], help="Extraction mode: standard (full summary) or gap (fill gaps only)")
    p_ingest.set_defaults(func=cmd_ingest)

    # process (alias for ingest)
    p_process = subparsers.add_parser("process", help="Alias for ingest")
    p_process.add_argument("source", help="Source file path")
    p_process.add_argument("--type", help="Source type")
    p_process.add_argument("--auto", action="store_true", help="Run LLM-powered auto-ingest")
    p_process.set_defaults(func=cmd_ingest)

    # extract
    p_extract = subparsers.add_parser("extract", help="Register source only")
    p_extract.add_argument("source", help="Source file path")
    p_extract.add_argument("--type", help="Source type")
    p_extract.set_defaults(func=cmd_extract)

    # validate
    p_validate = subparsers.add_parser("validate", help="Validate all drafts")
    p_validate.set_defaults(func=cmd_validate)

    # link
    p_link = subparsers.add_parser("link", help="Build typed graph")
    p_link.set_defaults(func=cmd_link)

    # refine
    p_refine = subparsers.add_parser("refine", help="Run refinement analysis")
    p_refine.set_defaults(func=cmd_refine)

    # lint
    p_lint = subparsers.add_parser("lint", help="Run all 12 structural checks")
    p_lint.add_argument("--json", action="store_true", help="Output as JSON")
    p_lint.set_defaults(func=cmd_lint)

    # consolidate
    p_consolidate = subparsers.add_parser("consolidate", help="Merge duplicates, generate indexes")
    p_consolidate.set_defaults(func=cmd_consolidate)

    # state
    p_state = subparsers.add_parser("state", help="Print _state.json summary")
    p_state.set_defaults(func=cmd_state)

    # health
    p_health = subparsers.add_parser("health", help="Print _health.json summary")
    p_health.set_defaults(func=cmd_health)

    # query
    p_query = subparsers.add_parser("query", help="Graph traversal query with LLM synthesis")
    p_query.add_argument("question", help="Question to find context for")
    p_query.add_argument("--depth", type=int, default=2, help="Traversal depth (default: 2)")
    p_query.add_argument("--top-k", type=int, default=5, help="Number of seed pages")
    p_query.add_argument("--json", action="store_true", help="Output as JSON")
    p_query.add_argument("--context-only", action="store_true", help="Output raw context without LLM synthesis")
    p_query.add_argument("--no-expand", action="store_true", help="Skip query expansion (keyword-only)")
    p_query.add_argument("--expand-only", action="store_true", help="Show expanded queries without running pipeline")
    p_query.set_defaults(func=cmd_query)

    # pack
    p_pack = subparsers.add_parser("pack", help="Build an agent-readable context pack")
    p_pack.add_argument("query", help="Question or task to gather context for")
    p_pack.add_argument("--depth", type=int, default=2, help="Traversal depth (default: 2)")
    p_pack.add_argument("--top-k", type=int, default=5, help="Number of seed pages")
    p_pack.add_argument("--json", action="store_true", help="Output as JSON")
    p_pack.set_defaults(func=cmd_pack)

    # agent-ingest
    p_agent_ingest = subparsers.add_parser(
        "agent-ingest",
        help="Create a model-free ingestion plan for the active CLI agent",
    )
    p_agent_ingest.add_argument("source", help="Source file path")
    p_agent_ingest.add_argument("--type", help="Source type")
    p_agent_ingest.add_argument("--json", action="store_true", help="Output as JSON")
    p_agent_ingest.add_argument("--no-register", action="store_true", help="Do not register/copy the source")
    p_agent_ingest.add_argument("--max-candidates", type=int, default=5, help="Merge candidates to include")
    p_agent_ingest.set_defaults(func=cmd_agent_ingest)

    # triage
    p_triage = subparsers.add_parser("triage", help="Show prioritized wiki maintenance queue")
    p_triage.add_argument("--json", action="store_true", help="Output as JSON")
    p_triage.set_defaults(func=cmd_triage)

    # scaffold
    p_scaffold = subparsers.add_parser("scaffold", help="Create a schema-valid draft stub")
    p_scaffold.add_argument("title", help="Page title to scaffold")
    p_scaffold.add_argument("--type", default="concept", choices=["concept", "entity"], help="Page type")
    p_scaffold.add_argument("--source", default="triage:missing-link", help="Reason/source for scaffold")
    p_scaffold.add_argument("--force", action="store_true", help="Overwrite an existing draft")
    p_scaffold.set_defaults(func=cmd_scaffold)

    # draft
    p_draft = subparsers.add_parser("draft", help="Create a cited work-product draft")
    p_draft.add_argument("kind", choices=["brief", "case-study", "playbook", "decision-memo"], help="Draft type")
    p_draft.add_argument("--topic", required=True, help="Topic to draft from wiki context")
    p_draft.add_argument("--audience", help="Target audience")
    p_draft.add_argument("--json", action="store_true", help="Output as JSON")
    p_draft.set_defaults(func=cmd_draft)

    # quality
    p_quality = subparsers.add_parser("quality", help="Score wiki/page usefulness")
    p_quality.add_argument("page", nargs="?", help="Optional page title/stem")
    p_quality.add_argument("--json", action="store_true", help="Output as JSON")
    p_quality.set_defaults(func=cmd_quality)

    # coverage
    p_coverage = subparsers.add_parser("coverage", help="Report source coverage")
    p_coverage.add_argument("source", help="Source filename/path")
    p_coverage.add_argument("--json", action="store_true", help="Output as JSON")
    p_coverage.set_defaults(func=cmd_coverage)

    # find
    p_find = subparsers.add_parser("find", help="Filter pages by metadata")
    p_find.add_argument("--tag", help="Filter by tag")
    p_find.add_argument("--confidence", help="Filter by confidence (HIGH, MEDIUM, LOW)")
    p_find.set_defaults(func=cmd_find)

    # provenance
    p_prov = subparsers.add_parser("provenance", help="Show evidence chain for a page")
    p_prov.add_argument("page", help="Page name or stem")
    p_prov.set_defaults(func=cmd_provenance)

    # register
    p_reg = subparsers.add_parser("register", help="Register source only")
    p_reg.add_argument("source", help="Source file path")
    p_reg.add_argument("--type", help="Source type")
    p_reg.set_defaults(func=cmd_register)

    # check
    p_check = subparsers.add_parser("check", help="Check if source is already ingested")
    p_check.add_argument("source", help="Source file path")
    p_check.set_defaults(func=cmd_check)

    # rebuild
    p_rebuild = subparsers.add_parser("rebuild", help="Regenerate indexes + graph + state")
    p_rebuild.set_defaults(func=cmd_rebuild)

    # generate-instructions
    p_gen = subparsers.add_parser("generate-instructions", help="Generate CLAUDE.md from SCHEMA.yaml")
    p_gen.set_defaults(func=cmd_generate_instructions)

    # log
    p_log = subparsers.add_parser("log", help="Show recent log entries")
    p_log.add_argument("-n", type=int, default=10, help="Number of entries (default: 10)")
    p_log.set_defaults(func=cmd_log)

    # save-answer
    p_save = subparsers.add_parser("save-answer", help="Save last query as draft page")
    p_save.add_argument("title", help="Page title for the draft")
    p_save.add_argument("--type", default="concept", help="Page type (default: concept)")
    p_save.add_argument("--confidence", default="LOW", help="Confidence level (default: LOW)")
    p_save.set_defaults(func=cmd_save_answer)

    # extract-prompt
    p_ep = subparsers.add_parser("extract-prompt", help="Generate LLM prompt for page creation")
    p_ep.add_argument("source", help="Source filename")
    p_ep.add_argument("--type", default="concept", help="Page type (default: concept)")
    p_ep.set_defaults(func=cmd_extract_prompt)

    # recheck — smart recheck scheduling
    p_recheck = subparsers.add_parser("recheck", help="Smart recheck scheduler management")
    p_recheck_sub = p_recheck.add_subparsers(dest="recheck_action", help="Recheck action")

    p_r_due = p_recheck_sub.add_parser("due", help="Show pages due for recheck")
    p_r_due.add_argument("--confidence", help="Filter by confidence (HIGH, MEDIUM, LOW)")
    p_r_due.add_argument("--limit", type=int, help="Limit to N pages")
    p_r_due.set_defaults(func=cmd_recheck_due)

    p_r_summary = p_recheck_sub.add_parser("summary", help="Show full recheck schedule")
    p_r_summary.set_defaults(func=cmd_recheck_summary)

    p_r_run = p_recheck_sub.add_parser("run", help="Run backoff-aware recheck on all tracked pages")
    p_r_run.add_argument("--page", help="Recheck a specific page only")
    p_r_run.add_argument("--ci", action="store_true", help="CI mode: suppress per-page progress output")
    p_r_run.add_argument("--json", action="store_true", help="Output results as machine-parseable JSON")
    p_r_run.set_defaults(func=cmd_recheck_run)

    p_recheck.set_defaults(func=cmd_recheck)

    return parser


def main(argv: list[str] | None = None):
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
