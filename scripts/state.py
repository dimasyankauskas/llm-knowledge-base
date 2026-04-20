"""State management for LLM Knowledge Base v2.

Generates _state.json and _health.json for agent awareness.
These are the key files the agent reads at session start.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).parent))

from provenance import get_stale_pages
from schema import load_schema, get_all_page_types, get_required_frontmatter
from utils import (
    CONCEPTS_DIR,
    ENTITIES_DIR,
    HEALTH_PATH,
    SOURCES_DIR,
    STATE_PATH,
    WIKI_DIR,
    extract_wikilinks,
    list_concept_pages,
    list_entity_pages,
    read_page,
    today,
)


# ── Constants ────────────────────────────────────────────────────────────────

_CONTRADICTION_PATTERN = re.compile(
    r">\s*\[!warning\]\s*CONTRADICTION", re.IGNORECASE
)
_SECTION_PATTERN = re.compile(r"^##\s+", re.MULTILINE)

# ── Core Generation ─────────────────────────────────────────────────────────


def generate_state(
    wiki_dir: Path | None = None,
    schema: dict | None = None,
) -> dict:
    """Build _state.json from wiki pages + schema summary + health snapshot.

    Returns a dict with:
    - schema_version: str
    - last_updated: ISO timestamp
    - page_types: list[str] (from schema)
    - required_fields: dict[str, list[str]] (page_type -> required_frontmatter)
    - pages: dict (page_name -> {type, confidence, tags, outlinks, inlinks,
                last_updated, stale})
    - active_contradictions: list[str]
    - thin_pages: list[str]
    - stale_pages: list[str]
    - recent_changes: list[dict] (page, change, date)
    - health: dict (errors, warnings, orphans, broken_links, last_lint)

    Reads all .md files in wiki/concepts/ and wiki/entities/, parses frontmatter,
    counts inlinks/outlinks, checks for contradictions, identifies thin pages.
    """
    if wiki_dir is None:
        wiki_dir = WIKI_DIR
    if schema is None:
        schema = load_schema()

    # Schema summary
    schema_version = str(schema.get("version", "2.0"))
    page_types = get_all_page_types(schema)
    required_fields: dict[str, list[str]] = {}
    for pt in page_types:
        try:
            required_fields[pt] = get_required_frontmatter(schema, pt)
        except ValueError:
            required_fields[pt] = []

    # Collect pages
    pages: dict[str, dict[str, Any]] = {}
    all_outlinks: dict[str, list[str]] = {}  # page_name -> list of targets
    active_contradictions: list[str] = []
    thin_pages: list[str] = []

    # Scan concept and entity directories
    concepts_dir = wiki_dir / "concepts"
    entities_dir = wiki_dir / "entities"

    page_dirs = []
    if concepts_dir.exists():
        page_dirs.append(concepts_dir)
    if entities_dir.exists():
        page_dirs.append(entities_dir)

    for page_dir in page_dirs:
        for md_file in sorted(page_dir.glob("*.md")):
            try:
                post = read_page(md_file)
            except Exception:
                continue

            page_name = md_file.stem
            meta = post.metadata
            content = post.content

            # Determine page type from frontmatter or directory
            page_type = meta.get("type", page_dir.name.rstrip("s"))
            confidence = meta.get("confidence", "")
            tags = meta.get("tags", [])
            last_updated = meta.get("last_updated", meta.get("created", ""))
            if not isinstance(last_updated, str):
                last_updated = str(last_updated)

            # Outlinks
            outlinks = extract_wikilinks(content)
            all_outlinks[page_name] = outlinks

            # Detect contradictions
            if _CONTRADICTION_PATTERN.search(content):
                active_contradictions.append(page_name)

            # Detect thin pages (fewer than 2 sections)
            section_count = len(_SECTION_PATTERN.findall(content))
            if section_count < 2:
                thin_pages.append(page_name)

            pages[page_name] = {
                "type": page_type,
                "confidence": confidence,
                "tags": tags,
                "outlinks": outlinks,
                "inlinks": [],  # filled in below
                "last_updated": last_updated,
                "stale": False,  # filled in below
            }

    # Compute inlinks from outlinks
    page_names_lower = {name.lower(): name for name in pages}
    for source, targets in all_outlinks.items():
        for target in targets:
            # Normalize target name (case-insensitive match)
            normalized = page_names_lower.get(target.lower(), target)
            if normalized in pages:
                pages[normalized]["inlinks"].append(source)

    # Stale pages from provenance
    sources_dir = wiki_dir.parent / "sources"
    try:
        stale_page_list = get_stale_pages(wiki_dir, sources_dir)
    except Exception:
        stale_page_list = []

    for page_name in stale_page_list:
        if page_name in pages:
            pages[page_name]["stale"] = True

    # Deduplicate inlinks
    for page_name, page_data in pages.items():
        page_data["inlinks"] = sorted(set(page_data["inlinks"]))

    # Recent changes — sort by last_updated, take last 10
    recent_changes = sorted(
        [
            {
                "page": name,
                "change": "updated",
                "date": data["last_updated"],
            }
            for name, data in pages.items()
            if data["last_updated"]
        ],
        key=lambda x: x["date"],
        reverse=True,
    )[:10]

    # Load health snapshot if available
    health: dict[str, Any] = {}
    health_path = wiki_dir / "_health.json"
    if health_path.exists():
        try:
            health = json.loads(health_path.read_text(encoding="utf-8"))
        except Exception:
            health = {}

    state = {
        "schema_version": schema_version,
        "last_updated": today(),
        "page_types": page_types,
        "required_fields": required_fields,
        "pages": pages,
        "active_contradictions": active_contradictions,
        "thin_pages": thin_pages,
        "stale_pages": stale_page_list,
        "recent_changes": recent_changes,
        "health": health,
    }

    return state


def generate_health(
    wiki_dir: Path | None = None,
    lint_results: list | None = None,
) -> dict:
    """Build _health.json from lint results.

    Returns a dict with:
    - errors: int
    - warnings: int
    - orphans: int
    - broken_links: int
    - last_lint: ISO timestamp
    - issues: list[dict] (code, page, message, severity) -- only ERROR and WARNING
    """
    if lint_results is None:
        lint_results = []

    errors = 0
    warnings = 0
    orphans = 0
    broken_links = 0
    issues: list[dict] = []

    for result in lint_results:
        severity = result.get("severity", "WARNING")
        code = result.get("code", "unknown")

        if severity == "ERROR":
            errors += 1
        elif severity == "WARNING":
            warnings += 1

        # Count specific categories
        if code == "orphan_pages":
            orphans += 1
        if code == "broken_links":
            broken_links += 1

        # Only include ERROR and WARNING in issues
        if severity in ("ERROR", "WARNING"):
            issues.append({
                "code": code,
                "page": result.get("page", ""),
                "message": result.get("message", ""),
                "severity": severity,
            })

    return {
        "errors": errors,
        "warnings": warnings,
        "orphans": orphans,
        "broken_links": broken_links,
        "last_lint": datetime.now(timezone.utc).isoformat(),
        "issues": issues,
    }


# ── Loaders ─────────────────────────────────────────────────────────────────


def load_state(wiki_dir: Path | None = None) -> dict:
    """Read _state.json from disk. Returns empty dict if not found."""
    if wiki_dir is None:
        wiki_dir = WIKI_DIR
    state_path = wiki_dir / "_state.json"
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def load_health(wiki_dir: Path | None = None) -> dict:
    """Read _health.json from disk. Returns empty dict if not found."""
    if wiki_dir is None:
        wiki_dir = WIKI_DIR
    health_path = wiki_dir / "_health.json"
    if health_path.exists():
        try:
            return json.loads(health_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


# ── Savers ───────────────────────────────────────────────────────────────────

# Max pages to include in _state.json before truncation
_MAX_PAGES_IN_STATE = 50


def _compact_state(state: dict) -> dict:
    """Create a compact version of state for agent bootstrap.

    When page count exceeds _MAX_PAGES_IN_STATE, the pages dict is
    replaced with a summary (count by type) plus only the pages that
    need attention (stale, thin, contradictory). The full data is
    saved to _state_full.json for programmatic access.
    """
    pages = state.get("pages", {})
    if len(pages) <= _MAX_PAGES_IN_STATE:
        return state

    # Keep only pages that need attention + a random sample of healthy ones
    attention_pages = {}
    healthy_pages = {}
    for name, data in pages.items():
        is_attention = (
            data.get("stale", False)
            or name in state.get("thin_pages", [])
            or name in state.get("active_contradictions", [])
        )
        if is_attention:
            attention_pages[name] = data
        else:
            healthy_pages[name] = data

    # Keep all attention pages + sample of healthy ones to stay under limit
    healthy_budget = _MAX_PAGES_IN_STATE - len(attention_pages)
    if healthy_budget > 0:
        # Take the most recently updated healthy pages
        sorted_healthy = sorted(
            healthy_pages.items(),
            key=lambda x: x[1].get("last_updated", ""),
            reverse=True,
        )
        for name, data in sorted_healthy[:healthy_budget]:
            attention_pages[name] = data

    compact = dict(state)
    compact["pages"] = attention_pages
    compact["pages_truncated"] = True
    compact["total_page_count"] = len(pages)
    return compact


def save_state(state: dict, wiki_dir: Path | None = None) -> None:
    """Write _state.json and _state_full.json to disk.

    _state_full.json: complete state for programmatic access (scripts, CLI)
    _state.json: compact state for agent bootstrap (capped at 50 pages)
    """
    if wiki_dir is None:
        wiki_dir = WIKI_DIR
    state_path = wiki_dir / "_state.json"
    full_path = wiki_dir / "_state_full.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)

    # Save full state first
    full_path.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Save compact state for agent bootstrap
    compact = _compact_state(state)
    state_path.write_text(
        json.dumps(compact, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def save_health(health: dict, wiki_dir: Path | None = None) -> None:
    """Write _health.json to disk. Creates parent dirs if needed."""
    if wiki_dir is None:
        wiki_dir = WIKI_DIR
    health_path = wiki_dir / "_health.json"
    health_path.parent.mkdir(parents=True, exist_ok=True)
    health_path.write_text(
        json.dumps(health, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )