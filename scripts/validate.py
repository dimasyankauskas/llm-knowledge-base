"""
Antigravity Wiki v2 — Validate Stage

Stage 2 of the pipeline: validates draft pages against the schema and checks
provenance. Gates which pages go from wiki/drafts/ into wiki/concepts/ or
wiki/entities/.

Usage:
    # Validate all drafts
    python scripts/validate.py

    # Validate a specific draft
    python scripts/validate.py wiki/drafts/My_Concept.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

import frontmatter

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
    DRAFTS_DIR,
    ENTITIES_DIR,
    WIKI_DIR,
    extract_wikilinks,
    read_page,
    read_provenance,
)


# ── Data Classes ───────────────────────────────────────────────────────────────


class ValidationIssue:
    """A single validation issue."""

    def __init__(self, severity: str, code: str, page: str, message: str):
        self.severity = severity  # ERROR or WARNING
        self.code = code
        self.page = page
        self.message = message

    def __str__(self):
        icons = {"ERROR": "\u274c", "WARNING": "\u26a0\ufe0f"}
        icon = icons.get(self.severity, "?")
        return f"  {icon} [{self.code}] {self.page}: {self.message}"


class ValidationReport:
    """Collection of validation issues for a page."""

    def __init__(self, page_path: Path, page_name: str):
        self.page_path = page_path
        self.page_name = page_name
        self.issues: list[ValidationIssue] = []

    def add_error(self, code: str, message: str):
        self.issues.append(ValidationIssue("ERROR", code, self.page_name, message))

    def add_warning(self, code: str, message: str):
        self.issues.append(ValidationIssue("WARNING", code, self.page_name, message))

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "ERROR" for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "ERROR")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "WARNING")


# ── Section Parsing ──────────────────────────────────────────────────────────


def _parse_sections(content: str) -> dict[str, str]:
    """Parse markdown content into a dict of section_name -> section_body.

    Looks for ## headings (level 2). Returns a mapping from heading text
    to the body text under that heading (stripped, may be empty).
    """
    sections: dict[str, str] = {}
    current_heading: Optional[str] = None
    current_lines: list[str] = []

    for line in content.splitlines():
        heading_match = re.match(r"^##\s+(.+)", line)
        if heading_match:
            # Save the previous section
            if current_heading is not None:
                sections[current_heading] = "\n".join(current_lines).strip()
            current_heading = heading_match.group(1).strip()
            current_lines = []
        else:
            if current_heading is not None:
                current_lines.append(line)

    # Save the last section
    if current_heading is not None:
        sections[current_heading] = "\n".join(current_lines).strip()

    return sections


# ── Validation Functions ──────────────────────────────────────────────────────


def validate_frontmatter(page_path: Path, schema: dict) -> list[ValidationIssue]:
    """Check that frontmatter has all required fields for the page type.

    Reads the page, determines type from frontmatter, checks against schema
    required_frontmatter. Returns MISSING_FRONTMATTER errors for each missing
    field. Returns INVALID_TYPE error if page type not in schema.
    """
    issues: list[ValidationIssue] = []
    page_name = page_path.stem

    try:
        post = read_page(page_path)
    except Exception as exc:
        issues.append(ValidationIssue("ERROR", "PARSE_ERROR", page_name, str(exc)))
        return issues

    metadata = post.metadata or {}
    page_type = metadata.get("type", "")

    if not page_type:
        issues.append(
            ValidationIssue("ERROR", "MISSING_FRONTMATTER", page_name, "Missing required field: type")
        )
        return issues

    # Check if the page type is known
    all_types = get_all_page_types(schema)
    if page_type not in all_types:
        issues.append(
            ValidationIssue(
                "ERROR", "INVALID_TYPE", page_name,
                f"Unknown page type: {page_type!r}. Valid types: {', '.join(all_types)}"
            )
        )
        return issues

    # Check required frontmatter fields
    required_fields = get_required_frontmatter(schema, page_type)
    for field in required_fields:
        if field not in metadata or metadata[field] is None:
            issues.append(
                ValidationIssue(
                    "ERROR", "MISSING_FRONTMATTER", page_name,
                    f"Missing required frontmatter field: {field}"
                )
            )

    return issues


def validate_sections(page_path: Path, schema: dict) -> list[ValidationIssue]:
    """Check that all required sections exist and have content.

    Reads the page, checks that each required section (from schema) exists as
    a ## heading. Returns EMPTY_SECTION warning for sections that exist but
    have no content. Returns MISSING_SECTION warning for sections that don't
    exist.
    """
    issues: list[ValidationIssue] = []
    page_name = page_path.stem

    try:
        post = read_page(page_path)
    except Exception as exc:
        issues.append(ValidationIssue("ERROR", "PARSE_ERROR", page_name, str(exc)))
        return issues

    page_type = (post.metadata or {}).get("type", "")
    if not page_type:
        return issues  # Can't check sections without a type

    all_types = get_all_page_types(schema)
    if page_type not in all_types:
        return issues  # Can't check sections for unknown type

    required_sections = get_required_sections(schema, page_type)
    if not required_sections:
        return issues  # No required sections for this type

    sections = _parse_sections(post.content)

    for section_name in required_sections:
        if section_name not in sections:
            issues.append(
                ValidationIssue(
                    "WARNING", "MISSING_SECTION", page_name,
                    f"Missing required section: {section_name}"
                )
            )
        elif not sections[section_name]:
            issues.append(
                ValidationIssue(
                    "WARNING", "EMPTY_SECTION", page_name,
                    f"Empty required section: {section_name}"
                )
            )

    return issues


def validate_wikilinks(page_path: Path, all_page_names: set[str]) -> list[ValidationIssue]:
    """Check that all [[wikilinks]] resolve to existing pages.

    Uses utils.extract_wikilinks to find links, checks against
    all_page_names (case-insensitive). Returns BROKEN_LINK errors for
    each unresolvable link.
    """
    issues: list[ValidationIssue] = []
    page_name = page_path.stem

    try:
        text = page_path.read_text(encoding="utf-8")
    except Exception as exc:
        issues.append(ValidationIssue("ERROR", "READ_ERROR", page_name, str(exc)))
        return issues

    links = extract_wikilinks(text)

    # Build case-insensitive lookup set
    names_lower = {name.lower() for name in all_page_names}

    seen_links = set()  # Avoid duplicate warnings for same link
    for link_target in links:
        if link_target.lower() not in names_lower and link_target not in seen_links:
            issues.append(
                ValidationIssue(
                    "ERROR", "BROKEN_LINK", page_name,
                    f"Unresolvable wikilink: [[{link_target}]]"
                )
            )
            seen_links.add(link_target)

    return issues


def validate_provenance(page_path: Path) -> list[ValidationIssue]:
    """Check that a provenance sidecar exists and is valid.

    Returns MISSING_CONTENT_HASH error if no .provenance.json sidecar exists.
    Returns CORRUPT_PROVENANCE error if sidecar exists but can't be parsed.
    """
    issues: list[ValidationIssue] = []
    page_name = page_path.stem

    prov = read_provenance(page_path)

    if prov is None:
        issues.append(
            ValidationIssue(
                "ERROR", "MISSING_CONTENT_HASH", page_name,
                "No .provenance.json sidecar found"
            )
        )
    else:
        # Verify it has the minimum required structure
        if not isinstance(prov, dict):
            issues.append(
                ValidationIssue(
                    "ERROR", "CORRUPT_PROVENANCE", page_name,
                    "Provenance sidecar is not a valid JSON object"
                )
            )
        elif "page" not in prov or "content_hash" not in prov:
            issues.append(
                ValidationIssue(
                    "ERROR", "CORRUPT_PROVENANCE", page_name,
                    "Provenance sidecar missing required fields (page, content_hash)"
                )
            )

    return issues


def validate_fact_inference_separation(page_path: Path, schema: dict) -> list[ValidationIssue]:
    """Check that facts-only sections don't contain unmarked inferences.

    For each section marked as 'facts_only' in the schema section_rules:
    - Lines containing '> [!note] Inference:' are allowed (explicitly marked)
    - Lines containing '[source: ...]' citations are allowed (sourced facts)
    - Flag any paragraph that makes claims without [source: ...] citations
      as UNMARKED_INFERENCE

    Returns UNMARKED_INFERENCE warnings.
    """
    issues: list[ValidationIssue] = []
    page_name = page_path.stem

    try:
        post = read_page(page_path)
    except Exception as exc:
        issues.append(ValidationIssue("ERROR", "PARSE_ERROR", page_name, str(exc)))
        return issues

    page_type = (post.metadata or {}).get("type", "")
    if not page_type:
        return issues

    all_types = get_all_page_types(schema)
    if page_type not in all_types:
        return issues

    section_rules = get_section_rules(schema, page_type)
    if not section_rules:
        return issues

    # Find which sections are facts_only
    facts_only_sections = {
        name for name, rule in section_rules.items() if rule == "facts_only"
    }

    if not facts_only_sections:
        return issues

    sections = _parse_sections(post.content)

    # Pattern for explicitly marked inferences (allowed)
    inference_marker_pattern = re.compile(r"^>\s*\[!note\]\s*Inference:", re.MULTILINE)
    # Pattern for source citations (allowed)
    source_citation_pattern = re.compile(r"\[source:\s*[^\]]+\]")

    for section_name, rule in section_rules.items():
        if rule != "facts_only":
            continue

        if section_name not in sections:
            # Already caught by validate_sections
            continue

        section_body = sections[section_name]
        if not section_body.strip():
            continue

        # Split into paragraphs (blocks separated by blank lines)
        paragraphs = re.split(r"\n\s*\n", section_body)

        for para in paragraphs:
            para_stripped = para.strip()
            if not para_stripped:
                continue

            # Skip lines that are explicitly marked as inferences
            if inference_marker_pattern.search(para_stripped):
                continue

            # Skip lines that are just headings, list items with no claims,
            # or purely structural (like "---" separators)
            # We look at each line individually
            has_unmarked_claim = False
            for line in para_stripped.splitlines():
                line_stripped = line.strip()
                if not line_stripped:
                    continue

                # Skip headings, separators, blank callouts, pure links
                if line_stripped.startswith("#"):
                    continue
                if line_stripped.startswith("---"):
                    continue
                if line_stripped.startswith("> [!note] Inference:"):
                    continue
                # Skip list items that are just source references
                if re.match(r"^[-*]\s*\[source:", line_stripped):
                    continue

                # Skip lines that contain a source citation — they're sourced facts
                if source_citation_pattern.search(line_stripped):
                    continue

                # Skip lines that are just wikilinks or bullet-point links
                if re.match(r"^[-*]\s*\[\[", line_stripped):
                    continue

                # Skip callout lines (Obsidian-style)
                if line_stripped.startswith("> [!"):
                    continue

                # Skip bare list markers with no content
                if re.match(r"^[-*]\s*$", line_stripped):
                    continue

                # If the line has substantial text (more than just a few chars)
                # and doesn't have a source citation, flag it
                if len(line_stripped) > 10:
                    has_unmarked_claim = True
                    break

            if has_unmarked_claim:
                issues.append(
                    ValidationIssue(
                        "WARNING", "UNMARKED_INFERENCE", page_name,
                        f"Possible unmarked inference in facts_only section '{section_name}': "
                        f"claims without [source: ...] citation"
                    )
                )
                # One warning per section is enough
                break

    return issues


def validate_draft(
    draft_path: Path,
    schema: dict | None = None,
    wiki_dir: Path | None = None,
) -> ValidationReport:
    """Full validation of a draft page against the schema.

    Runs all checks: frontmatter, sections, wikilinks, provenance, fact/inference.
    Returns a ValidationReport with all issues found.
    """
    if schema is None:
        schema = load_schema()

    if wiki_dir is None:
        wiki_dir = WIKI_DIR

    page_name = draft_path.stem
    report = ValidationReport(draft_path, page_name)

    # 1. Frontmatter validation
    fm_issues = validate_frontmatter(draft_path, schema)
    report.issues.extend(fm_issues)

    # 2. Section validation
    section_issues = validate_sections(draft_path, schema)
    report.issues.extend(section_issues)

    # 3. Wikilink validation — collect all page names from wiki/
    all_page_names: set[str] = set()
    for md_file in wiki_dir.rglob("*.md"):
        # Skip draft pages themselves (they're not yet promoted)
        if "drafts" in str(md_file):
            continue
        all_page_names.add(md_file.stem)

    # Also include the current draft page name so self-references work
    all_page_names.add(page_name)

    link_issues = validate_wikilinks(draft_path, all_page_names)
    report.issues.extend(link_issues)

    # 4. Provenance validation
    prov_issues = validate_provenance(draft_path)
    report.issues.extend(prov_issues)

    # 5. Fact/inference separation
    fi_issues = validate_fact_inference_separation(draft_path, schema)
    report.issues.extend(fi_issues)

    return report


def promote_draft(
    draft_path: Path,
    schema: dict | None = None,
    wiki_dir: Path | None = None,
) -> Path | None:
    """Move a validated draft to the appropriate wiki directory.

    - Validates the draft first
    - If no errors, determines page type from frontmatter
    - Moves to wiki/concepts/ or wiki/entities/
    - Returns the new path, or None if validation failed
    """
    if wiki_dir is None:
        wiki_dir = WIKI_DIR

    report = validate_draft(draft_path, schema=schema, wiki_dir=wiki_dir)

    if report.has_errors:
        print(f"  Cannot promote {draft_path.name}: {report.error_count} error(s), "
              f"{report.warning_count} warning(s)")
        for issue in report.issues:
            print(f"    {issue}")
        return None

    # Determine destination directory from page type
    try:
        post = read_page(draft_path)
    except Exception:
        return None

    page_type = (post.metadata or {}).get("type", "")
    if page_type == "concept":
        dest_dir = wiki_dir / "concepts"
    elif page_type == "entity":
        dest_dir = wiki_dir / "entities"
    else:
        print(f"  Cannot promote {draft_path.name}: unknown type {page_type!r}")
        return None

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / draft_path.name

    # Move the draft file
    draft_path.rename(dest_path)

    # Also move the provenance sidecar if it exists
    prov_src = draft_path.with_suffix(draft_path.suffix + ".provenance.json")
    if prov_src.exists():
        prov_dest = dest_path.with_suffix(dest_path.suffix + ".provenance.json")
        prov_src.rename(prov_dest)

    print(f"  Promoted {draft_path.name} -> {dest_path}")
    return dest_path


def main():
    """CLI: python scripts/validate.py [draft_path]

    Without args: validate all drafts in wiki/drafts/
    With args: validate specific draft file
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Antigravity Wiki v2 — Validate Stage"
    )
    parser.add_argument(
        "draft_path",
        nargs="?",
        default=None,
        help="Path to a specific draft file to validate. "
             "If omitted, validates all drafts in wiki/drafts/.",
    )
    parser.add_argument(
        "--promote",
        action="store_true",
        help="Promote valid drafts (move to wiki/concepts/ or wiki/entities/).",
    )
    args = parser.parse_args()

    schema = load_schema()

    if args.draft_path:
        draft_path = Path(args.draft_path)
        if not draft_path.exists():
            print(f"  ERROR: File not found: {draft_path}")
            sys.exit(1)

        if args.promote:
            result = promote_draft(draft_path, schema=schema)
            if result is None:
                sys.exit(1)
        else:
            report = validate_draft(draft_path, schema=schema)
            print(f"\nValidation report for {draft_path.name}:")
            if report.issues:
                for issue in report.issues:
                    print(f"  {issue}")
            else:
                print("  No issues found.")
            print(f"\n  {report.error_count} error(s), {report.warning_count} warning(s)")
            if report.has_errors:
                sys.exit(1)
    else:
        # Validate all drafts
        drafts_dir = DRAFTS_DIR
        if not drafts_dir.exists():
            print(f"  No drafts directory found: {drafts_dir}")
            sys.exit(0)

        draft_files = sorted(drafts_dir.glob("*.md"))
        if not draft_files:
            print("  No drafts found.")
            sys.exit(0)

        total_errors = 0
        total_warnings = 0
        promoted = 0
        failed = 0

        for draft_file in draft_files:
            report = validate_draft(draft_file, schema=schema)

            if args.promote:
                if not report.has_errors:
                    new_path = promote_draft(draft_file, schema=schema)
                    if new_path:
                        promoted += 1
                else:
                    failed += 1
                    print(f"  SKIP {draft_file.name}: {report.error_count} error(s)")
            else:
                print(f"\n{draft_file.name}:")
                if report.issues:
                    for issue in report.issues:
                        print(f"  {issue}")
                else:
                    print("  OK — no issues found.")

            total_errors += report.error_count
            total_warnings += report.warning_count

        print(f"\n{'='*60}")
        if args.promote:
            print(f"  Promoted: {promoted}, Failed: {failed}")
        print(f"  Total: {total_errors} error(s), {total_warnings} warning(s)")
        print(f"{'='*60}\n")

        if total_errors > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()