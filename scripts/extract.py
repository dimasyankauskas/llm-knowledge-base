"""
LLM Knowledge Base v2 — Extract Stage

Source registration and classification. Stage 1 of the pipeline.
Replaces v1 ingest.py with cleaner v2 conventions.

Usage:
    # Register a source after the agent has created wiki pages
    python scripts/extract.py register <source_file> --type article

    # Check if a source has already been ingested
    python scripts/extract.py check <source_file>

    # Regenerate indexes, graph, and state from current wiki pages
    python scripts/extract.py rebuild
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from utils import (
    CONCEPTS_DIR,
    ENTITIES_DIR,
    INDEXES_DIR,
    SOURCES_DIR,
    WIKI_DIR,
    hash_content,
    hash_file,
    is_source_ingested,
    list_concept_pages,
    list_entity_pages,
    load_manifest,
    page_exists,
    save_graph,
    slugify,
    today,
    write_page,
)

import state as state_mod


# ── Source Classification ────────────────────────────────────────────────

# Extensions that map to specific source types
_CODE_EXTENSIONS = {".py", ".js", ".ts", ".go", ".rs", ".java"}
_TEXT_EXTENSIONS = {".md", ".txt", ".json", ".yaml", ".yml", ".csv"}


def classify_source_type(path: Path) -> str:
    """Determine source type from file extension and name patterns.

    Priority order:
    - filenames with 'transcript' -> 'transcript'
    - .pdf -> 'paper'
    - .py, .js, .ts, .go, .rs, .java -> 'code-doc'
    - .md, .txt -> 'article' (default for text)
    - everything else -> 'article'

    Returns one of: 'paper', 'article', 'transcript', 'code-doc'
    """
    name_lower = path.name.lower()

    # Transcript check has highest priority (even .pdf transcripts)
    if "transcript" in name_lower:
        return "transcript"

    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return "paper"
    if suffix in _CODE_EXTENSIONS:
        return "code-doc"
    # Default: article covers .md, .txt, and anything else
    return "article"


# ── Source Reading ───────────────────────────────────────────────────────


def read_source(path: Path) -> str:
    """Read a source file and return its text content.

    - .md, .txt, .json, .yaml, .yml, .csv -> read as text
    - .pdf -> use PyMuPDF (fitz) to extract text
    - other -> try to read as text, fail gracefully
    """
    suffix = path.suffix.lower()

    if suffix in _TEXT_EXTENSIONS:
        return path.read_text(encoding="utf-8")
    elif suffix == ".pdf":
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise RuntimeError(
                "PyMuPDF not installed. Install with: pip install pymupdf"
            )
        doc = fitz.open(str(path))
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    else:
        # Try reading as text for unknown extensions
        try:
            return path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            raise RuntimeError(f"Cannot read file {path}: {exc}") from exc


# ── Dedup Check ──────────────────────────────────────────────────────────


def check_dedup(source_path: Path, manifest_path: Path | None = None) -> bool:
    """Check if a source has already been ingested by comparing content hash.

    Returns True if already ingested (duplicate), False if new.

    Args:
        source_path: Path to the source file to check.
        manifest_path: Optional path to manifest.json. If None, uses the
                       default MANIFEST_PATH from utils.
    """
    content_hash = hash_file(source_path)

    if manifest_path is not None:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return any(
            s.get("content_hash") == content_hash for s in manifest.get("sources", [])
        )

    return is_source_ingested(content_hash)


# ── Source Registration ──────────────────────────────────────────────────


def register_source(
    source_path: Path,
    source_type: str,
    manifest_path: Path | None = None,
    metadata: dict | None = None,
) -> dict | None:
    """Register a source in the manifest after the agent has created wiki pages.

    - Copy source to sources/<type>/ if not already there
    - Compute content hash
    - Check for duplicates (skip if already registered)
    - Add entry to manifest with filename, source_type, content_hash,
      ingested_at, status, concepts_generated, entities_generated
    - Returns the manifest entry dict, or None if duplicate detected.
    """
    # Read source and compute hash
    text = read_source(source_path)
    content_hash = hash_content(text)

    # Load manifest (from custom path or default)
    if manifest_path is not None:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = load_manifest()

    # Check for duplicates
    if any(s.get("content_hash") == content_hash for s in manifest.get("sources", [])):
        return None

    # Copy source to sources/<type>/ if not already there
    sources_dir = manifest_path.parent if manifest_path else SOURCES_DIR
    if not str(source_path.resolve()).startswith(str(sources_dir.resolve())):
        dest = sources_dir / source_type / source_path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, dest)
        source_path = dest

    # Build manifest entry
    entry = {
        "filename": source_path.name,
        "source_type": source_type,
        "content_hash": content_hash,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "status": "ingested",
        "concepts_generated": [],
        "entities_generated": [],
    }
    if metadata:
        entry["metadata"] = metadata

    # Save manifest
    manifest["sources"].append(entry)
    if manifest_path is not None:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    else:
        from utils import save_manifest
        save_manifest(manifest)

    return entry


# ── Index Generation ────────────────────────────────────────────────────


def regenerate_indexes() -> None:
    """Regenerate all index pages."""
    concepts = list_concept_pages()
    entities = list_entity_pages()

    master_content = f"""# Wiki Index

> Auto-generated on {today()}. Do not edit manually.

## Statistics

- **Concepts:** {len(concepts)}
- **Entities:** {len(entities)}
- **Total Pages:** {len(concepts) + len(entities)}

## Concepts

{chr(10).join(f"- [[{p.stem}]]" for p in concepts)}

## Entities

{chr(10).join(f"- [[{p.stem}]]" for p in entities)}
"""

    write_page(
        INDEXES_DIR / "_index.md",
        {
            "title": "Wiki Index",
            "type": "index",
            "created": today(),
            "last_updated": today(),
        },
        master_content,
    )

    # Contradictions tracker
    contradictions_path = INDEXES_DIR / "_contradictions.md"
    if not contradictions_path.exists():
        write_page(
            contradictions_path,
            {
                "title": "Contradictions Tracker",
                "type": "index",
                "created": today(),
                "last_updated": today(),
            },
            f"""# Contradictions Tracker

> Auto-generated on {today()}. Tracks unresolved contradictions across the wiki.

## Unresolved Contradictions

*No contradictions detected yet.*
""",
        )

    print(f"  Indexes regenerated ({len(concepts)} concepts, {len(entities)} entities)")


# ── CLI Commands ─────────────────────────────────────────────────────────


def cmd_register(args):
    """CLI command: python scripts/extract.py register <source> --type <type>"""
    path = Path(args.source)
    if not path.exists():
        print(f"  ERROR: File not found: {args.source}")
        sys.exit(1)

    # Auto-classify if type not explicitly specified
    source_type = getattr(args, "source_type", None) or classify_source_type(path)

    entry = register_source(path, source_type)

    if entry is None:
        print(f"  WARNING: Source already registered (duplicate)")
    else:
        print(f"  OK: Source registered: {entry['filename']} (hash: {entry['content_hash']})")


def cmd_check(args):
    """CLI command: python scripts/extract.py check <source>"""
    path = Path(args.source)
    if not path.exists():
        print(f"  ERROR: File not found: {args.source}")
        sys.exit(1)

    if check_dedup(path):
        content_hash = hash_file(path)
        print(f"  DUPLICATE: Already ingested (hash: {content_hash})")
        sys.exit(1)
    else:
        content_hash = hash_file(path)
        print(f"  NEW: Not yet ingested (hash: {content_hash})")


def cmd_rebuild(args):
    """CLI command: python scripts/extract.py rebuild

    Regenerates indexes and graph from current wiki pages.
    Also regenerates _state.json.
    """
    print(f"\n{'='*60}")
    print(f"  Rebuilding indexes, graph, and state...")
    print(f"{'='*60}\n")

    regenerate_indexes()
    graph = save_graph()

    # Regenerate _state.json
    state = state_mod.generate_state()
    state_mod.save_state(state)

    print(f"  Graph: {graph['node_count']} nodes, {graph['edge_count']} edges")
    print(f"  State: {len(state.get('pages', {}))} pages tracked")
    print(f"  OK: Rebuild complete\n")


def main():
    """CLI entry point with subcommands: register, check, rebuild"""
    parser = argparse.ArgumentParser(
        description="LLM Knowledge Base v2 — Extract Stage (source registration)",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # register
    reg = subparsers.add_parser(
        "register",
        help="Register a source after agent creates wiki pages",
    )
    reg.add_argument("source", help="Path to source file")
    reg.add_argument(
        "--type",
        dest="source_type",
        default=None,
        choices=["article", "paper", "transcript", "code-doc"],
        help="Source type (auto-detected if omitted)",
    )

    # rebuild
    subparsers.add_parser("rebuild", help="Regenerate indexes, graph, and state")

    # check
    chk = subparsers.add_parser("check", help="Check if a source is already ingested")
    chk.add_argument("source", help="Path to source file")

    args = parser.parse_args()

    if args.command == "register":
        cmd_register(args)
    elif args.command == "rebuild":
        cmd_rebuild(args)
    elif args.command == "check":
        cmd_check(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()