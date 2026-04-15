"""
Antigravity Wiki v2 — Content Migration Script

Updates existing wiki pages to v2 format:
- Adds missing frontmatter fields (content_hash, source_refs, confidence)
- Creates .provenance.json sidecars for each page
- Creates wiki/drafts/ directory
- Creates wiki/_log.md with initial entry
- Generates initial _state.json and _health.json

Usage:
    python scripts/migrate.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    WIKI_DIR, SOURCES_DIR, hash_content, read_page, write_page,
    write_provenance, list_wiki_pages,
)
from schema import load_schema
from lint import lint
from state import generate_state, generate_health, save_state, save_health


def migrate_frontmatter(page_path: Path) -> bool:
    """Add missing frontmatter fields to a wiki page.

    Adds: content_hash, source_refs, confidence, created (if missing).
    Returns True if any changes were made.
    """
    try:
        post = read_page(page_path)
    except Exception:
        print(f"  SKIP: Cannot read {page_path.name}")
        return False

    metadata = dict(post.metadata)
    content = post.content
    changed = False

    # Add content_hash if missing
    if "content_hash" not in metadata:
        metadata["content_hash"] = hash_content(content)
        changed = True

    # Add source_refs if missing
    if "source_refs" not in metadata:
        # Try to extract source references from the content
        sources = []
        for line in content.split("\n"):
            if line.strip().startswith("- ") and "source:" in line.lower():
                sources.append(line.strip().lstrip("- ").strip())
        if not sources:
            sources = ["migrated-content"]
        metadata["source_refs"] = sources
        changed = True

    # Add confidence if missing
    if "confidence" not in metadata:
        # Infer confidence from content
        if "[!warning]" in content.lower() or "contradiction" in content.lower():
            metadata["confidence"] = "LOW"
        elif len(content) > 500:
            metadata["confidence"] = "MEDIUM"
        else:
            metadata["confidence"] = "MEDIUM"
        changed = True

    # Add created date if missing
    if "created" not in metadata:
        metadata["created"] = "2026-04-15"
        changed = True

    if changed:
        write_page(page_path, metadata, content)

    return changed


def create_provenance_sidecar(page_path: Path) -> bool:
    """Create a .provenance.json sidecar for a wiki page if one doesn't exist.

    Returns True if a new sidecar was created.
    """
    prov_path = page_path.with_suffix(".md.provenance.json")
    if prov_path.exists():
        return False

    try:
        post = read_page(page_path)
    except Exception:
        return False

    content = post.content
    metadata = post.metadata

    source_refs = metadata.get("source_refs", ["migrated-content"])
    # Convert source_refs to list of strings if they aren't already
    sources = []
    for s in source_refs:
        if isinstance(s, str):
            sources.append({"file": s, "sections": []})
        elif isinstance(s, dict):
            sources.append(s)

    created = metadata.get("created", "2026-04-15")
    if not isinstance(created, str):
        created = str(created)

    prov = {
        "page": page_path.stem,
        "content_hash": metadata.get("content_hash", hash_content(content)),
        "claims": [],
        "sources": sources,
        "last_verified": created,
    }

    write_provenance(page_path, prov)
    return True


def migrate():
    """Run the full migration from v1 to v2 format."""
    print("=" * 60)
    print("  Antigravity Wiki v2 — Content Migration")
    print("=" * 60)
    print()

    # Ensure wiki directory structure
    for d in ["concepts", "entities", "indexes", "timelines", "drafts"]:
        (WIKI_DIR / d).mkdir(parents=True, exist_ok=True)

    # Step 1: Migrate frontmatter
    print("Step 1: Migrating frontmatter...")
    pages = list_wiki_pages()
    migrated = 0
    for page in pages:
        if page.stem.startswith("_"):
            continue
        if migrate_frontmatter(page):
            migrated += 1
            print(f"  Updated: {page.stem}")
    print(f"  {migrated} pages updated\n")

    # Step 2: Create provenance sidecars
    print("Step 2: Creating provenance sidecars...")
    sidecars = 0
    for page in pages:
        if page.stem.startswith("_"):
            continue
        if create_provenance_sidecar(page):
            sidecars += 1
            print(f"  Created: {page.stem}.provenance.json")
    print(f"  {sidecars} sidecars created\n")

    # Step 3: Create wiki/_log.md
    print("Step 3: Creating wiki/_log.md...")
    log_path = WIKI_DIR / "_log.md"
    if not log_path.exists():
        log_path.write_text(
            "# Wiki Log\n\n"
            "## 2026-04-15 — v2 Migration\n\n"
            "- Migrated all wiki pages to v2 frontmatter format\n"
            "- Added provenance sidecars\n"
            "- Generated initial _state.json and _health.json\n",
            encoding="utf-8",
        )
        print("  Created: _log.md\n")
    else:
        print("  Already exists: _log.md\n")

    # Step 4: Run lint
    print("Step 4: Running lint...")
    issues = lint()
    errors = sum(1 for i in issues if i.severity == "ERROR")
    warnings = sum(1 for i in issues if i.severity == "WARNING")
    print(f"  {errors} errors, {warnings} warnings\n")

    # Step 5: Generate state and health
    print("Step 5: Generating _state.json and _health.json...")
    schema = load_schema()
    state = generate_state(schema=schema)
    save_state(state)

    issues_dicts = [
        {"severity": i.severity, "code": i.code, "page": i.page, "message": i.message}
        for i in issues
    ]
    health = generate_health(lint_results=issues_dicts)
    save_health(health)
    print("  Done.\n")

    print("=" * 60)
    print("  Migration complete!")
    print(f"  Pages migrated: {migrated}")
    print(f"  Sidecars created: {sidecars}")
    print(f"  Errors: {errors}, Warnings: {warnings}")
    print("=" * 60)


if __name__ == "__main__":
    migrate()