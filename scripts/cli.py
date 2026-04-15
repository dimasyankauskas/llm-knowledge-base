"""
Antigravity Wiki v2 — Unified CLI

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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lint import LintIssue
from utils import WIKI_DIR, SOURCES_DIR, GRAPH_PATH, list_wiki_pages, read_provenance, read_page, page_exists
from schema import load_schema
from extract import register_source, check_dedup, classify_source_type
from validate import validate_draft, promote_draft
from link import build_typed_graph, verify_bidirectional_links, save_graph
from refine import generate_refinement_tasks
from lint import lint
from consolidate import find_duplicate_pages, generate_indexes, generate_timelines
from query import find_seed_pages, traverse_typed_graph, build_context
from state import generate_state, generate_health, save_state, save_health, load_state, load_health


def _lint_issues_to_dicts(issues: list[LintIssue]) -> list[dict]:
    """Convert LintIssue objects to dicts for generate_health compatibility."""
    return [
        {"severity": i.severity, "code": i.code, "page": i.page, "message": i.message}
        for i in issues
    ]


def cmd_ingest(args):
    """Full pipeline: extract → validate → link → lint → state."""
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
            page_type = "concept"  # default; frontmatter may say otherwise
            try:
                post = read_page(draft)
                page_type = post.metadata.get("type", "concept")
            except Exception:
                pass
            if promote_draft(draft, page_type):
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

    missing = verify_bidirectional_links(graph)
    if missing:
        print(f"Missing reverse links: {len(missing)}")
        for m in missing[:10]:
            print(f"  {m['source']} → {m['target']} ({m['type']})")
    else:
        print("All links bidirectional.")

    print(f"Graph: {len(graph.get('nodes', []))} nodes, {len(graph.get('edges', []))} edges")


def cmd_refine(args):
    """Run refinement analysis."""
    tasks = generate_refinement_tasks()
    if not tasks:
        print("No refinement tasks found.")
        return

    for task in sorted(tasks, key=lambda t: t.get("priority", 0), reverse=True):
        print(f"  [{task.get('priority', 0)}] {task['type']}: {task.get('page', task.get('description', ''))}")


def cmd_lint(args):
    """Run all 12 lint checks."""
    issues = lint()
    errors = sum(1 for i in issues if i.severity == "ERROR")
    warnings = sum(1 for i in issues if i.severity == "WARNING")
    if args.json:
        output = {
            "errors": errors,
            "warnings": warnings,
            "issues": [
                {"severity": i.severity, "rule": i.rule, "page": i.page, "message": i.message}
                for i in issues
            ],
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        for issue in issues:
            marker = "ERROR" if issue.severity == "ERROR" else "WARN"
            print(f"  [{marker}] {issue.page}: {issue.message} ({issue.code})")
        print(f"\n{errors} errors, {warnings} warnings")


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
    issues = lint()
    health = generate_health(lint_results=_lint_issues_to_dicts(issues))
    save_health(health)
    print(json.dumps(health, indent=2, ensure_ascii=False))


def cmd_query(args):
    """Graph traversal query."""
    pages = list_wiki_pages()
    if not pages:
        print("Wiki is empty. Ingest some sources first.")
        return

    seed = find_seed_pages(args.question, top_k=args.top_k)
    if not seed:
        print("No relevant pages found.")
        return

    graph = {}
    if GRAPH_PATH.exists():
        graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))

    traversed = traverse_typed_graph(seed, graph, args.depth)
    context = build_context(traversed)

    if args.json:
        output = {
            "question": args.question,
            "seed_pages": [p.stem for p in seed],
            "traversed_pages": [
                {"page": r["page"].stem, "score": r["score"], "path": r["path"]}
                for r in traversed
            ],
            "context_chars": len(context),
            "context": context,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(f"\nQuestion: {args.question}")
        print(f"Seed pages: {', '.join(p.stem for p in seed)}")
        print(f"Traversed: {len(traversed)} pages (depth={args.depth})")
        print(f"Context: {len(context):,} chars\n")
        print(context)


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


def build_parser():
    """Build the argparse parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="wiki",
        description="Antigravity Wiki v2 — LLM-native knowledge base engine",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ingest
    p_ingest = subparsers.add_parser("ingest", help="Full pipeline: extract → validate → link → lint → state")
    p_ingest.add_argument("source", help="Source file path")
    p_ingest.add_argument("--type", help="Source type (paper, article, transcript, code-doc)")
    p_ingest.set_defaults(func=cmd_ingest)

    # process (alias for ingest)
    p_process = subparsers.add_parser("process", help="Alias for ingest")
    p_process.add_argument("source", help="Source file path")
    p_process.add_argument("--type", help="Source type")
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
    p_query = subparsers.add_parser("query", help="Graph traversal query")
    p_query.add_argument("question", help="Question to find context for")
    p_query.add_argument("--depth", type=int, default=2, help="Traversal depth (default: 2)")
    p_query.add_argument("--top-k", type=int, default=5, help="Number of seed pages")
    p_query.add_argument("--json", action="store_true", help="Output as JSON")
    p_query.set_defaults(func=cmd_query)

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