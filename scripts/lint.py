"""
Antigravity Wiki v2 — Structural Linter

Validates wiki integrity with 12 schema-driven checks:
  1. BROKEN_LINK — ERROR
  2. ORPHAN_PAGE — WARNING
  3. MISSING_FRONTMATTER — ERROR
  4. INVALID_TYPE — ERROR
  5. NO_SOURCES — WARNING
  6. LOW_CONNECTIVITY — WARNING
  7. STALE_PAGE — WARNING
  8. UNRESOLVED_CONTRADICTION — WARNING
  9. DUPLICATE_CONCEPT — ERROR
 10. EMPTY_SECTION — WARNING
 11. UNMARKED_INFERENCE — WARNING
 12. MISSING_CONTENT_HASH — ERROR

Usage:
    python scripts/lint.py [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from schema import (
    get_all_page_types,
    get_required_frontmatter,
    get_required_sections,
    get_section_rules,
    load_schema,
)
from utils import (
    CONCEPTS_DIR,
    ENTITIES_DIR,
    SOURCES_DIR,
    WIKI_DIR,
    extract_wikilinks,
    find_all_wikilinks,
    hash_file,
    list_wiki_pages,
    read_page,
    read_provenance,
)


# ── Data Structures ───────────────────────────────────────────────────────


class LintIssue:
    """A single lint issue."""

    def __init__(self, severity: str, code: str, page: str, message: str):
        self.severity = severity  # ERROR, WARNING, or INFO
        self.code = code
        self.page = page
        self.message = message

    def __str__(self):
        icons = {"ERROR": "\u274c", "WARNING": "\u26a0\ufe0f", "INFO": "\u2139\ufe0f"}
        icon = icons.get(self.severity, "?")
        return f"  {icon} [{self.code}] {self.page}: {self.message}"


# ── Helpers ───────────────────────────────────────────────────────────────


def _parse_sections(content: str) -> dict[str, str]:
    """Parse markdown content into section_name -> section_body (## headings)."""
    sections: dict[str, str] = {}
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in content.splitlines():
        heading_match = re.match(r"^##\s+(.+)", line)
        if heading_match:
            if current_heading is not None:
                sections[current_heading] = "\n".join(current_lines).strip()
            current_heading = heading_match.group(1).strip()
            current_lines = []
        else:
            if current_heading is not None:
                current_lines.append(line)

    if current_heading is not None:
        sections[current_heading] = "\n".join(current_lines).strip()

    return sections


def _is_index_page(page: Path) -> bool:
    """Check if a page is an index page (stem starts with _)."""
    return page.stem.startswith("_")


def _collect_pages(wiki_dir: Path) -> list[Path]:
    """Collect all markdown pages from the wiki directory."""
    pages: list[Path] = []
    for subdir in ("concepts", "entities", "indexes", "timelines"):
        d = wiki_dir / subdir
        if d.exists():
            pages.extend(sorted(d.glob("*.md")))
    # Also pick up any stray .md at top level
    for f in sorted(wiki_dir.glob("*.md")):
        if f.name != "_graph.json" and f.suffix == ".md":
            pages.append(f)
    return pages


def _get_severity(schema: dict, rule_name: str) -> str:
    """Look up severity for a rule from the schema's validation section."""
    validation = schema.get("validation", {})
    rule = validation.get(rule_name, {})
    if isinstance(rule, dict):
        return rule.get("severity", "WARNING")
    return "WARNING"


# ── Lint Checks ──────────────────────────────────────────────────────────


def check_broken_links(pages: list[Path], all_page_names: set[str]) -> list[LintIssue]:
    """Check [[wikilinks]] that point to non-existent pages.

    Uses utils.extract_wikilinks, compares against all_page_names (case-insensitive).
    Returns BROKEN_LINK errors.
    """
    issues: list[LintIssue] = []
    names_lower = {name.lower() for name in all_page_names}

    for page in pages:
        try:
            text = page.read_text(encoding="utf-8")
        except Exception:
            continue
        links = extract_wikilinks(text)
        seen = set()
        for link in links:
            if link.lower() not in names_lower and link not in seen:
                issues.append(LintIssue(
                    "ERROR", "BROKEN_LINK", page.stem,
                    f"Links to [[{link}]] which does not exist",
                ))
                seen.add(link)
    return issues


def check_orphan_pages(pages: list[Path]) -> list[LintIssue]:
    """Find pages with 0 inlinks AND 0 outlinks.

    Skip index pages (names starting with _).
    Returns ORPHAN_PAGE warnings.
    """
    issues: list[LintIssue] = []

    # Build link maps
    outlinks: dict[str, list[str]] = {}
    inlinks: dict[str, int] = {}
    existing_names: dict[str, str] = {}  # lower -> actual stem

    for page in pages:
        name = page.stem
        existing_names[name.lower()] = name
        inlinks[name] = 0
        try:
            text = page.read_text(encoding="utf-8")
            targets = extract_wikilinks(text)
            outlinks[name] = targets
        except Exception:
            outlinks[name] = []

    # Count inlinks
    for source, targets in outlinks.items():
        for target in targets:
            canonical = existing_names.get(target.lower())
            if canonical and canonical in inlinks:
                inlinks[canonical] += 1

    for page in pages:
        name = page.stem
        if _is_index_page(page):
            continue
        out_count = len(outlinks.get(name, []))
        in_count = inlinks.get(name, 0)
        if out_count == 0 and in_count == 0:
            issues.append(LintIssue(
                "WARNING", "ORPHAN_PAGE", name,
                "Page has 0 inlinks and 0 outlinks — isolated node",
            ))
    return issues


def check_frontmatter(pages: list[Path], schema: dict) -> list[LintIssue]:
    """Check required frontmatter fields per page type from schema.

    Skip index pages. Check each page_type has its required_frontmatter fields.
    Returns MISSING_FRONTMATTER errors and INVALID_TYPE errors.
    """
    issues: list[LintIssue] = []
    all_types = get_all_page_types(schema)

    for page in pages:
        if _is_index_page(page):
            continue

        try:
            post = read_page(page)
        except Exception as exc:
            issues.append(LintIssue(
                "ERROR", "MISSING_FRONTMATTER", page.stem,
                f"Failed to parse frontmatter: {exc}",
            ))
            continue

        metadata = post.metadata or {}
        page_type = metadata.get("type", "")

        if not page_type:
            issues.append(LintIssue(
                "ERROR", "MISSING_FRONTMATTER", page.stem,
                "Missing required field: type",
            ))
            continue

        if page_type not in all_types:
            issues.append(LintIssue(
                "ERROR", "INVALID_TYPE", page.stem,
                f"Unknown page type: {page_type!r}. Valid types: {', '.join(all_types)}",
            ))
            continue

        required_fields = get_required_frontmatter(schema, page_type)
        for field in required_fields:
            if field not in metadata or metadata[field] is None:
                issues.append(LintIssue(
                    "ERROR", "MISSING_FRONTMATTER", page.stem,
                    f"Missing required field: {field}",
                ))

    return issues


def check_sources(pages: list[Path]) -> list[LintIssue]:
    """Check for pages without source citations.

    Skip index pages. Check for [source: text] in content or source_refs in frontmatter.
    Returns NO_SOURCES warnings.
    """
    issues: list[LintIssue] = []

    for page in pages:
        if _is_index_page(page):
            continue

        try:
            text = page.read_text(encoding="utf-8")
        except Exception:
            continue

        has_source_in_content = bool(re.search(r"\[source:\s*[^\]]+\]", text, re.IGNORECASE))

        has_source_refs = False
        try:
            post = read_page(page)
            src_refs = (post.metadata or {}).get("source_refs")
            if src_refs and (isinstance(src_refs, list) and len(src_refs) > 0):
                has_source_refs = True
            elif src_refs and isinstance(src_refs, str) and src_refs.strip():
                has_source_refs = True
        except Exception:
            pass

        if not has_source_in_content and not has_source_refs:
            issues.append(LintIssue(
                "WARNING", "NO_SOURCES", page.stem,
                "Page contains no source citations",
            ))

    return issues


def check_low_connectivity(pages: list[Path], schema: dict) -> list[LintIssue]:
    """Check for concept pages with fewer than min_outlinks outgoing links.

    Skip index pages. Read min_outlinks from schema page_type config.
    Returns LOW_CONNECTIVITY warnings.
    """
    issues: list[LintIssue] = []

    # Get min_outlinks from schema, with fallback
    concept_config = schema.get("page_types", {}).get("concept", {})
    min_outlinks = concept_config.get("min_outlinks", 2)

    # Also check the validation section
    validation_config = schema.get("validation", {}).get("low_connectivity", {})
    if isinstance(validation_config, dict):
        min_outlinks = validation_config.get("min_outlinks", min_outlinks)

    for page in pages:
        if _is_index_page(page):
            continue

        try:
            post = read_page(page)
        except Exception:
            continue

        page_type = (post.metadata or {}).get("type", "")
        if page_type != "concept":
            continue

        text = page.read_text(encoding="utf-8")
        links = extract_wikilinks(text)
        if len(links) < min_outlinks:
            issues.append(LintIssue(
                "WARNING", "LOW_CONNECTIVITY", page.stem,
                f"Concept page has only {len(links)} outgoing links (minimum: {min_outlinks})",
            ))

    return issues


def check_staleness(pages: list[Path], sources_dir: Path | None = None) -> list[LintIssue]:
    """Check for pages whose source content hashes have changed.

    Read provenance sidecars, compare source hashes against current files.
    Returns STALE_PAGE warnings.
    """
    issues: list[LintIssue] = []

    if sources_dir is None:
        sources_dir = SOURCES_DIR

    for page in pages:
        if _is_index_page(page):
            continue

        prov = read_provenance(page)
        if prov is None:
            continue

        stale_sources: list[str] = []
        for src in prov.get("sources", []):
            src_file = src.get("file", "")
            src_hash = src.get("content_hash", "")
            filepath = sources_dir / src_file
            if not filepath.exists():
                stale_sources.append(src_file)
                continue
            current_hash = hash_file(filepath)
            if current_hash != src_hash:
                stale_sources.append(src_file)

        if stale_sources:
            issues.append(LintIssue(
                "WARNING", "STALE_PAGE", page.stem,
                f"Source content changed: {', '.join(stale_sources)}",
            ))

    return issues


def check_contradictions(pages: list[Path]) -> list[LintIssue]:
    """Check for unresolved contradiction callouts.

    Returns UNRESOLVED_CONTRADICTION warnings.
    """
    issues: list[LintIssue] = []

    for page in pages:
        try:
            text = page.read_text(encoding="utf-8")
        except Exception:
            continue

        if "> [!warning] CONTRADICTION" in text and "Status:** UNRESOLVED" in text:
            issues.append(LintIssue(
                "WARNING", "UNRESOLVED_CONTRADICTION", page.stem,
                "Contains unresolved contradiction(s)",
            ))

    return issues


def check_empty_sections(pages: list[Path]) -> list[LintIssue]:
    """Check for required sections that exist but have no content.

    Returns EMPTY_SECTION warnings.
    """
    issues: list[LintIssue] = []

    for page in pages:
        if _is_index_page(page):
            continue

        try:
            text = page.read_text(encoding="utf-8")
        except Exception:
            continue

        # Check for placeholder markers
        if "*To be documented*" in text or "*To be expanded*" in text:
            issues.append(LintIssue(
                "WARNING", "EMPTY_SECTION", page.stem,
                "Contains placeholder content that needs expansion",
            ))
            continue

        # Also check for sections that exist with ## heading but empty body
        try:
            post = read_page(page)
        except Exception:
            continue

        sections = _parse_sections(post.content)
        for name, body in sections.items():
            if not body.strip():
                issues.append(LintIssue(
                    "WARNING", "EMPTY_SECTION", page.stem,
                    f"Empty required section: {name}",
                ))
                break  # One warning per page is enough

    return issues


def check_duplicate_concepts(pages: list[Path]) -> list[LintIssue]:
    """Check for pages that appear to describe the same concept.

    Compare page titles (case-insensitive, after removing special chars).
    Also check aliases in frontmatter for overlap.
    Returns DUPLICATE_CONCEPT errors.
    """
    issues: list[LintIssue] = []

    def _normalize(name: str) -> str:
        """Normalize a name for comparison: lowercase, strip special chars."""
        return re.sub(r"[^a-z0-9]", "", name.lower())

    # Build a map: normalized_name -> list of (page, original_stem)
    name_map: dict[str, list[tuple[Path, str]]] = {}
    alias_map: dict[str, list[tuple[Path, str]]] = {}

    for page in pages:
        if _is_index_page(page):
            continue
        stem = page.stem
        norm = _normalize(stem)
        name_map.setdefault(norm, []).append((page, stem))

        # Check aliases in frontmatter
        try:
            post = read_page(page)
            aliases = (post.metadata or {}).get("aliases", [])
            if isinstance(aliases, list):
                for alias in aliases:
                    alias_norm = _normalize(str(alias))
                    alias_map.setdefault(alias_norm, []).append((page, stem))
        except Exception:
            pass

    # Find duplicates by normalized name
    seen_dup_stems: set[str] = set()
    for norm, entries in name_map.items():
        if len(entries) > 1:
            stems = [e[1] for e in entries]
            for stem in stems:
                if stem not in seen_dup_stems:
                    seen_dup_stems.add(stem)
                    others = [s for s in stems if s != stem]
                    issues.append(LintIssue(
                        "ERROR", "DUPLICATE_CONCEPT", stem,
                        f"Possible duplicate of: {', '.join(others)}",
                    ))

    # Find duplicates by alias overlap
    for norm, entries in alias_map.items():
        if len(entries) > 1:
            stems = list({e[1] for e in entries})
            if len(stems) > 1:
                for stem in stems:
                    if stem not in seen_dup_stems:
                        seen_dup_stems.add(stem)
                        others = [s for s in stems if s != stem]
                        issues.append(LintIssue(
                            "ERROR", "DUPLICATE_CONCEPT", stem,
                            f"Alias overlaps with: {', '.join(others)}",
                        ))

    return issues


def check_unmarked_inference(pages: list[Path], schema: dict) -> list[LintIssue]:
    """Check that facts-only sections don't contain unmarked inferences.

    For each section marked as 'facts_only' in schema section_rules:
    - Lines making claims without [source: ...] are potential unmarked inferences
    - Lines with > [!note] Inference: are properly marked and OK
    Returns UNMARKED_INFERENCE warnings.
    """
    issues: list[LintIssue] = []

    inference_marker_pattern = re.compile(r"^>\s*\[!note\]\s*Inference:", re.MULTILINE)
    source_citation_pattern = re.compile(r"\[source:\s*[^\]]+\]")

    for page in pages:
        if _is_index_page(page):
            continue

        try:
            post = read_page(page)
        except Exception:
            continue

        page_type = (post.metadata or {}).get("type", "")
        if not page_type:
            continue

        all_types = get_all_page_types(schema)
        if page_type not in all_types:
            continue

        section_rules = get_section_rules(schema, page_type)
        if not section_rules:
            continue

        facts_only_sections = {
            name for name, rule in section_rules.items() if rule == "facts_only"
        }
        if not facts_only_sections:
            continue

        sections = _parse_sections(post.content)

        for section_name, rule in section_rules.items():
            if rule != "facts_only":
                continue
            if section_name not in sections:
                continue

            section_body = sections[section_name]
            if not section_body.strip():
                continue

            # Check paragraphs for unmarked inferences
            paragraphs = re.split(r"\n\s*\n", section_body)
            for para in paragraphs:
                para_stripped = para.strip()
                if not para_stripped:
                    continue

                # Skip explicitly marked inferences
                if inference_marker_pattern.search(para_stripped):
                    continue

                has_unmarked_claim = False
                for line in para_stripped.splitlines():
                    line_stripped = line.strip()
                    if not line_stripped:
                        continue

                    # Skip headings, separators, callouts, list links
                    if line_stripped.startswith("#"):
                        continue
                    if line_stripped.startswith("---"):
                        continue
                    if line_stripped.startswith("> [!note] Inference:"):
                        continue
                    if line_stripped.startswith("> [!"):
                        continue
                    if re.match(r"^[-*]\s*\[source:", line_stripped):
                        continue
                    if source_citation_pattern.search(line_stripped):
                        continue
                    if re.match(r"^[-*]\s*\[\[", line_stripped):
                        continue
                    if re.match(r"^[-*]\s*$", line_stripped):
                        continue

                    # Flag substantial lines without citations
                    if len(line_stripped) > 10:
                        has_unmarked_claim = True
                        break

                if has_unmarked_claim:
                    issues.append(LintIssue(
                        "WARNING", "UNMARKED_INFERENCE", page.stem,
                        f"Possible unmarked inference in facts_only section "
                        f"'{section_name}': claims without [source: ...] citation",
                    ))
                    break  # One warning per section is enough

    return issues


def check_missing_content_hash(pages: list[Path]) -> list[LintIssue]:
    """Check that each concept/entity page has a provenance sidecar.

    Returns MISSING_CONTENT_HASH errors for pages without .provenance.json.
    """
    issues: list[LintIssue] = []

    for page in pages:
        if _is_index_page(page):
            continue

        # Only check concept and entity pages
        try:
            post = read_page(page)
            page_type = (post.metadata or {}).get("type", "")
            if page_type not in ("concept", "entity"):
                continue
        except Exception:
            continue

        prov = read_provenance(page)
        if prov is None:
            issues.append(LintIssue(
                "ERROR", "MISSING_CONTENT_HASH", page.stem,
                "No .provenance.json sidecar found",
            ))

    return issues


# ── Main Linter ──────────────────────────────────────────────────────────


def lint(
    wiki_dir: Path | None = None,
    sources_dir: Path | None = None,
    schema: dict | None = None,
    verbose: bool = True,
) -> list[LintIssue]:
    """Run all lint checks and return issues.

    If verbose, print formatted output to console.
    """
    if wiki_dir is None:
        wiki_dir = WIKI_DIR
    if sources_dir is None:
        sources_dir = SOURCES_DIR
    if schema is None:
        try:
            schema = load_schema()
        except FileNotFoundError:
            schema = {}

    pages = _collect_pages(wiki_dir)

    if not pages:
        if verbose:
            print("  \u2139\ufe0f  No wiki pages found. Nothing to lint.")
        return []

    if verbose:
        print(f"\n{'='*60}")
        print("  \U0001f50d Antigravity Wiki v2 \u2014 Structural Lint")
        print(f"{'='*60}")
        print(f"  Scanning {len(pages)} pages...\n")

    all_issues: list[LintIssue] = []

    # Build page name set for broken link check
    all_page_names = {p.stem for p in pages}

    # Run all 12 checks
    check_runs = [
        ("Broken Links", lambda: check_broken_links(pages, all_page_names)),
        ("Orphan Pages", lambda: check_orphan_pages(pages)),
        ("Frontmatter", lambda: check_frontmatter(pages, schema)),
        ("Source Citations", lambda: check_sources(pages)),
        ("Connectivity", lambda: check_low_connectivity(pages, schema)),
        ("Staleness", lambda: check_staleness(pages, sources_dir=sources_dir)),
        ("Contradictions", lambda: check_contradictions(pages)),
        ("Empty Sections", lambda: check_empty_sections(pages)),
        ("Duplicate Concepts", lambda: check_duplicate_concepts(pages)),
        ("Unmarked Inference", lambda: check_unmarked_inference(pages, schema)),
        ("Missing Content Hash", lambda: check_missing_content_hash(pages)),
    ]

    for name, check_fn in check_runs:
        check_issues = check_fn()
        all_issues.extend(check_issues)
        if verbose and check_issues:
            print(f"  --- {name} ---")
            for issue in check_issues:
                print(str(issue))
            print()

    # Summary
    errors = sum(1 for i in all_issues if i.severity == "ERROR")
    warnings = sum(1 for i in all_issues if i.severity == "WARNING")
    infos = sum(1 for i in all_issues if i.severity == "INFO")

    if verbose:
        print(f"{'='*60}")
        if errors > 0:
            print(f"  \u274c FAILED \u2014 {errors} errors, {warnings} warnings, {infos} info")
        elif warnings > 0:
            print(f"  \u26a0\ufe0f  PASSED with warnings \u2014 {warnings} warnings, {infos} info")
        else:
            print(f"  \u2705 CLEAN \u2014 No issues found")
        print(f"{'='*60}\n")

    return all_issues


# ── CLI ──────────────────────────────────────────────────────────────────


def main():
    """CLI: python scripts/lint.py [--json]

    Run all 12 lint checks. Exit with 1 if any ERRORs found.
    """
    parser = argparse.ArgumentParser(
        description="Antigravity Wiki v2 \u2014 Structural Linter",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args()

    issues = lint(verbose=not args.json)

    if args.json:
        output = [
            {"severity": i.severity, "code": i.code, "page": i.page, "message": i.message}
            for i in issues
        ]
        print(json.dumps(output, indent=2))

    errors = sum(1 for i in issues if i.severity == "ERROR")
    sys.exit(1 if errors > 0 else 0)


if __name__ == "__main__":
    main()