"""
LLM Knowledge Base v2 — Consolidate Stage

Stage 6 of the pipeline: detect duplicates, merge pages, generate indexes
and timelines.

Usage:
    python scripts/consolidate.py
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import frontmatter

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    CONCEPTS_DIR,
    ENTITIES_DIR,
    INDEXES_DIR,
    TIMELINES_DIR,
    WIKI_DIR,
    extract_wikilinks,
    list_wiki_pages,
    read_page,
    write_page,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _normalize_name(name: str) -> str:
    """Normalize a name for comparison: lowercase, remove all non-alphanumeric."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _collect_pages(wiki_dir: Path) -> list[Path]:
    """Collect all concept and entity .md pages (skip indexes/timelines)."""
    pages: list[Path] = []
    for subdir in ("concepts", "entities"):
        d = wiki_dir / subdir
        if d.exists():
            pages.extend(sorted(d.glob("*.md")))
    return pages


def _read_all_pages(wiki_dir: Path) -> dict[str, dict]:
    """Read all concept/entity pages, returning {stem: {path, metadata, content}}."""
    result: dict[str, dict] = {}
    for page_path in _collect_pages(wiki_dir):
        try:
            post = read_page(page_path)
            result[page_path.stem] = {
                "path": page_path,
                "metadata": dict(post.metadata) if post.metadata else {},
                "content": post.content,
            }
        except Exception:
            continue
    return result


# ── find_duplicate_pages ────────────────────────────────────────────────────


def find_duplicate_pages(wiki_dir: Path | None = None) -> list[tuple[str, str, str]]:
    """Find pages that appear to describe the same concept.

    Checks: 1) Title similarity (case-insensitive, after removing special chars)
            2) Alias overlap (frontmatter aliases pointing to the same concept)

    Returns list of tuples: (page1, page2, reason)
    """
    if wiki_dir is None:
        wiki_dir = WIKI_DIR

    duplicates: list[tuple[str, str, str]] = []
    seen_pairs: set[frozenset[str]] = set()

    pages = _read_all_pages(wiki_dir)
    stems = list(pages.keys())

    # 1) Title similarity: normalize filenames and check for near-identical names
    norm_map: dict[str, str] = {}
    for stem in stems:
        norm = _normalize_name(stem)
        norm_map[stem] = norm

    for i, stem_a in enumerate(stems):
        for stem_b in stems[i + 1:]:
            pair_key = frozenset([stem_a, stem_b])
            if pair_key in seen_pairs:
                continue
            if norm_map[stem_a] == norm_map[stem_b]:
                duplicates.append((stem_a, stem_b, "title_similarity"))
                seen_pairs.add(pair_key)

    # 2) Alias overlap: check if any alias of one page matches
    #    the normalized title or an alias of another page
    for stem_a in stems:
        meta_a = pages[stem_a]["metadata"]
        aliases_a: list[str] = meta_a.get("aliases", [])
        if not isinstance(aliases_a, list):
            aliases_a = [str(aliases_a)]

        # Normalize all aliases for page A
        norm_aliases_a = {_normalize_name(a) for a in aliases_a}
        norm_aliases_a.add(norm_map[stem_a])  # Include the title itself

        for stem_b in stems:
            if stem_a == stem_b:
                continue
            pair_key = frozenset([stem_a, stem_b])
            if pair_key in seen_pairs:
                continue

            meta_b = pages[stem_b]["metadata"]
            aliases_b: list[str] = meta_b.get("aliases", [])
            if not isinstance(aliases_b, list):
                aliases_b = [str(aliases_b)]

            norm_aliases_b = {_normalize_name(a) for a in aliases_b}
            norm_aliases_b.add(norm_map[stem_b])

            # Check if any normalized alias overlaps
            if norm_aliases_a & norm_aliases_b:
                duplicates.append((stem_a, stem_b, "alias_overlap"))
                seen_pairs.add(pair_key)

    return duplicates


# ── generate_indexes ────────────────────────────────────────────────────────


def generate_indexes(wiki_dir: Path | None = None, schema: dict | None = None) -> None:
    """Regenerate all index pages.

    Creates:
    - wiki/indexes/_index.md — Master index of all wiki pages
    - wiki/indexes/_contradictions.md — Contradiction tracker (create if not exists)
    - wiki/indexes/by-topic.md — Pages grouped by topic tag
    - wiki/indexes/by-source.md — Pages grouped by source_refs
    - wiki/indexes/recently-updated.md — Pages modified in last 7 days

    Uses utils.write_page for frontmatter support.
    """
    if wiki_dir is None:
        wiki_dir = WIKI_DIR

    indexes_dir = wiki_dir / "indexes"
    indexes_dir.mkdir(parents=True, exist_ok=True)

    pages = _read_all_pages(wiki_dir)
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    # ── _index.md ──────────────────────────────────────────────────────────

    index_lines: list[str] = ["# Wiki Index\n"]
    index_lines.append("Master index of all wiki pages.\n")

    # Group by type
    by_type: dict[str, list[str]] = {}
    for stem, info in sorted(pages.items()):
        page_type = info["metadata"].get("type", "unknown")
        by_type.setdefault(page_type, []).append(stem)

    for page_type, stems in sorted(by_type.items()):
        index_lines.append(f"\n## {page_type.title()}s\n")
        for stem in stems:
            index_lines.append(f"- [[{stem}]]")
    index_lines.append("")

    write_page(
        indexes_dir / "_index.md",
        {"title": "Wiki Index", "type": "index", "created": today_str},
        "\n".join(index_lines),
    )

    # ── _contradictions.md ─────────────────────────────────────────────────

    contradictions_path = indexes_dir / "_contradictions.md"
    if not contradictions_path.exists():
        write_page(
            contradictions_path,
            {
                "title": "Contradiction Tracker",
                "type": "index",
                "created": today_str,
            },
            "# Contradiction Tracker\n\nTrack and resolve contradictions across wiki pages.\n\n"
            "> [!warning] CONTRADICTION entries are listed below.\n\n"
            "| Page | Callout | Status | Resolution |\n|------|---------|--------|------------|\n",
        )

    # ── by-topic.md ────────────────────────────────────────────────────────

    topic_lines: list[str] = ["# By Topic\n"]
    topic_lines.append("Pages grouped by their topic tags.\n")

    by_topic: dict[str, list[str]] = {}
    for stem, info in sorted(pages.items()):
        tags = info["metadata"].get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        if not tags:
            by_topic.setdefault("untagged", []).append(stem)
        else:
            for tag in tags:
                by_topic.setdefault(str(tag), []).append(stem)

    for topic, stems in sorted(by_topic.items()):
        topic_lines.append(f"\n## {topic}\n")
        for stem in stems:
            topic_lines.append(f"- [[{stem}]]")
    topic_lines.append("")

    write_page(
        indexes_dir / "by-topic.md",
        {"title": "By Topic", "type": "index", "created": today_str},
        "\n".join(topic_lines),
    )

    # ── by-source.md ────────────────────────────────────────────────────────

    source_lines: list[str] = ["# By Source\n"]
    source_lines.append("Pages grouped by their source references.\n")

    by_source: dict[str, list[str]] = {}
    for stem, info in sorted(pages.items()):
        source_refs = info["metadata"].get("source_refs", [])
        if isinstance(source_refs, str):
            source_refs = [source_refs]
        if not source_refs:
            by_source.setdefault("no-source", []).append(stem)
        else:
            for ref in source_refs:
                by_source.setdefault(str(ref), []).append(stem)

    for source, stems in sorted(by_source.items()):
        source_lines.append(f"\n## {source}\n")
        for stem in stems:
            source_lines.append(f"- [[{stem}]]")
    source_lines.append("")

    write_page(
        indexes_dir / "by-source.md",
        {"title": "By Source", "type": "index", "created": today_str},
        "\n".join(source_lines),
    )

    # ── recently-updated.md ────────────────────────────────────────────────

    recent_lines: list[str] = ["# Recently Updated\n"]
    recent_lines.append(f"Pages modified in the last 7 days (as of {today_str}).\n")

    seven_days_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    recent_pages: list[tuple[str, str]] = []  # (date, stem)
    for stem, info in pages.items():
        last_updated = info["metadata"].get("last_updated", info["metadata"].get("created", ""))
        if last_updated and str(last_updated) >= seven_days_ago:
            recent_pages.append((str(last_updated), stem))

    recent_pages.sort(reverse=True)

    for date, stem in recent_pages:
        recent_lines.append(f"- [[{stem}]] — {date}")

    if not recent_pages:
        recent_lines.append("\nNo pages updated in the last 7 days.")
    recent_lines.append("")

    write_page(
        indexes_dir / "recently-updated.md",
        {"title": "Recently Updated", "type": "index", "created": today_str},
        "\n".join(recent_lines),
    )


# ── generate_timelines ──────────────────────────────────────────────────────


def generate_timelines(wiki_dir: Path | None = None) -> None:
    """Generate timeline pages from concept pages with date information.

    Looks for concept pages with created/last_updated dates.
    Groups events by year-month.
    Only creates timeline if there are enough dated events (5+).
    """
    if wiki_dir is None:
        wiki_dir = WIKI_DIR

    timelines_dir = wiki_dir / "timelines"
    timelines_dir.mkdir(parents=True, exist_ok=True)

    pages = _read_all_pages(wiki_dir)

    # Collect dated events
    events: list[tuple[str, str, str]] = []  # (date, stem, title)
    for stem, info in pages.items():
        created = info["metadata"].get("created", "")
        if created:
            title = info["metadata"].get("title", stem)
            events.append((str(created), stem, title))

    if len(events) < 5:
        return  # Not enough events for a timeline

    events.sort()

    # Group by year-month
    by_month: dict[str, list[tuple[str, str, str]]] = {}
    for date_str, stem, title in events:
        # Extract year-month from date string (YYYY-MM-DD or YYYY-MM)
        ym = date_str[:7]  # "YYYY-MM"
        by_month.setdefault(ym, []).append((date_str, stem, title))

    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    lines: list[str] = ["# Wiki Timeline\n"]
    lines.append(f"Chronological listing of wiki concepts ({len(events)} events).\n")

    for ym in sorted(by_month.keys()):
        lines.append(f"\n## {ym}\n")
        for date_str, stem, title in by_month[ym]:
            lines.append(f"- {date_str}: [[{stem}]] — {title}")
    lines.append("")

    write_page(
        timelines_dir / "timeline.md",
        {
            "title": "Wiki Timeline",
            "type": "timeline",
            "created": today_str,
        },
        "\n".join(lines),
    )


# ── merge_pages ──────────────────────────────────────────────────────────────


def merge_pages(primary_name: str, secondary_name: str, wiki_dir: Path | None = None) -> bool:
    """Merge secondary page into primary page.

    1. Read both pages
    2. Combine content: keep primary content, add secondary's unique content
    3. Combine frontmatter: merge aliases, source_refs, tags
    4. Update all wikilinks in other pages that point to secondary -> point to primary
    5. Delete secondary page (both .md and .provenance.json)
    6. Return True if successful, False if either page doesn't exist
    """
    if wiki_dir is None:
        wiki_dir = WIKI_DIR

    # Find primary and secondary page paths
    primary_path: Optional[Path] = None
    secondary_path: Optional[Path] = None

    for subdir in ("concepts", "entities"):
        d = wiki_dir / subdir
        if not d.exists():
            continue
        for md_file in d.glob("*.md"):
            if md_file.stem == primary_name:
                primary_path = md_file
            if md_file.stem == secondary_name:
                secondary_path = md_file

    if primary_path is None or secondary_path is None:
        return False

    # 1. Read both pages
    primary_post = read_page(primary_path)
    secondary_post = read_page(secondary_path)

    primary_meta = dict(primary_post.metadata) if primary_post.metadata else {}
    secondary_meta = dict(secondary_post.metadata) if secondary_post.metadata else {}

    # 2. Combine content: keep primary content, append secondary's unique content
    combined_content_parts: list[str] = []
    primary_content = primary_post.content.strip()
    secondary_content = secondary_post.content.strip()

    if primary_content:
        combined_content_parts.append(primary_content)

    if secondary_content:
        # Add a section header for the merged content
        if secondary_content not in primary_content:
            combined_content_parts.append(
                f"\n\n## Merged from {secondary_name}\n\n{secondary_content}"
            )

    combined_content = "\n".join(combined_content_parts)

    # 3. Combine frontmatter
    # Merge aliases
    primary_aliases = primary_meta.get("aliases", [])
    if isinstance(primary_aliases, str):
        primary_aliases = [primary_aliases]
    secondary_aliases = secondary_meta.get("aliases", [])
    if isinstance(secondary_aliases, str):
        secondary_aliases = [secondary_aliases]

    # Add secondary name as alias of primary
    merged_aliases = list(primary_aliases)
    for alias in secondary_aliases:
        if alias not in merged_aliases:
            merged_aliases.append(alias)
    if secondary_meta.get("title", secondary_name) not in merged_aliases:
        merged_aliases.append(secondary_meta.get("title", secondary_name))
    if secondary_name not in merged_aliases:
        merged_aliases.append(secondary_name)

    # Merge source_refs
    primary_refs = primary_meta.get("source_refs", [])
    if isinstance(primary_refs, str):
        primary_refs = [primary_refs]
    secondary_refs = secondary_meta.get("source_refs", [])
    if isinstance(secondary_refs, str):
        secondary_refs = [secondary_refs]

    merged_refs = list(primary_refs)
    for ref in secondary_refs:
        if ref not in merged_refs:
            merged_refs.append(ref)

    # Merge tags
    primary_tags = primary_meta.get("tags", [])
    if isinstance(primary_tags, str):
        primary_tags = [primary_tags]
    secondary_tags = secondary_meta.get("tags", [])
    if isinstance(secondary_tags, str):
        secondary_tags = [secondary_tags]

    merged_tags = list(primary_tags)
    for tag in secondary_tags:
        if tag not in merged_tags:
            merged_tags.append(tag)

    # Build merged metadata, keeping primary's core fields
    merged_meta = dict(primary_meta)
    if merged_aliases:
        merged_meta["aliases"] = merged_aliases
    if merged_refs:
        merged_meta["source_refs"] = merged_refs
    if merged_tags:
        merged_meta["tags"] = merged_tags

    # Update last_updated
    merged_meta["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Write merged primary page
    write_page(primary_path, merged_meta, combined_content)

    # 4. Update wikilinks in all other pages
    all_pages = _collect_pages(wiki_dir)
    wikilink_pattern = re.compile(
        rf"\[\[{re.escape(secondary_name)}(?:\|[^\]]+)?\]\]"
    )

    for page_path in all_pages:
        # Skip primary and secondary pages
        if page_path.stem == primary_name or page_path.stem == secondary_name:
            continue

        try:
            text = page_path.read_text(encoding="utf-8")
        except Exception:
            continue

        # Replace [[Secondary]] and [[Secondary|Display]] with [[Primary]]
        # For [[Secondary|Display]] -> [[Primary|Display]]
        # For [[Secondary]] -> [[Primary]]
        def _replace_wikilink(match: re.Match) -> str:
            full = match.group(0)
            # Check if there's a display text (pipe)
            if "|" in full:
                display = full.split("|")[1].rstrip("]")
                return f"[[{primary_name}|{display}"
            else:
                return f"[[{primary_name}]]"

        new_text = wikilink_pattern.sub(_replace_wikilink, text)
        if new_text != text:
            page_path.write_text(new_text, encoding="utf-8")

    # 5. Delete secondary page and its provenance sidecar
    secondary_path.unlink(missing_ok=True)
    prov_path = secondary_path.with_suffix(secondary_path.suffix + ".provenance.json")
    prov_path.unlink(missing_ok=True)

    return True


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    """CLI: python scripts/consolidate.py

    Run consolidation: find duplicates, generate indexes, generate timelines.
    """
    wiki_dir = WIKI_DIR

    print("=== LLM Knowledge Base v2 — Consolidate Stage ===\n")

    # Find duplicates
    print("Finding duplicate pages...")
    duplicates = find_duplicate_pages(wiki_dir=wiki_dir)
    if duplicates:
        print(f"  Found {len(duplicates)} potential duplicate(s):")
        for page1, page2, reason in duplicates:
            print(f"    - {page1} <-> {page2} ({reason})")
    else:
        print("  No duplicates found.")

    # Generate indexes
    print("\nGenerating indexes...")
    generate_indexes(wiki_dir=wiki_dir)
    print("  Indexes generated.")

    # Generate timelines
    print("\nGenerating timelines...")
    generate_timelines(wiki_dir=wiki_dir)
    print("  Timelines generated.")

    print("\nDone.")


if __name__ == "__main__":
    main()