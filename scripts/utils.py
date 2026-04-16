"""
Antigravity Wiki v2 — Shared Utilities
Provides common functions for file operations, frontmatter parsing,
wikilink extraction, typed relations, provenance sidecars, and graph management.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import frontmatter
import yaml

# ── Constants ──────────────────────────────────────────────────────────

WIKI_ROOT = Path(__file__).parent.parent
WIKI_DIR = WIKI_ROOT / "wiki"
SOURCES_DIR = WIKI_ROOT / "sources"
CONCEPTS_DIR = WIKI_DIR / "concepts"
ENTITIES_DIR = WIKI_DIR / "entities"
INDEXES_DIR = WIKI_DIR / "indexes"
TIMELINES_DIR = WIKI_DIR / "timelines"
MANIFEST_PATH = SOURCES_DIR / "manifest.json"
GRAPH_PATH = WIKI_DIR / "_graph.json"
SCHEMA_PATH = WIKI_ROOT / "SCHEMA.yaml"

# v2 additions
DRAFTS_DIR = WIKI_DIR / "drafts"
STATE_PATH = WIKI_DIR / "_state.json"
HEALTH_PATH = WIKI_DIR / "_health.json"
LOG_PATH = WIKI_DIR / "_log.md"

WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")

# Typed relation keywords (from SCHEMA.yaml relation_types)
_RELATION_KEYWORDS = [
    "implements",
    "extends",
    "contradicts",
    "cites",
    "prerequisite_of",
    "trades_off",
    "derived_from",
]

# Words pattern: used to scan text before each wikilink
_WORD_PATTERN = re.compile(r"\S+")


# ── File Hashing ───────────────────────────────────────────────────────

def hash_content(content: str) -> str:
    """SHA-256 hash of content for deduplication."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def hash_file(path: Path) -> str:
    """SHA-256 hash of file contents."""
    return hash_content(path.read_text(encoding="utf-8"))


# ── Manifest Operations ───────────────────────────────────────────────

def load_manifest() -> dict:
    """Load the source manifest."""
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"version": "1.0", "description": "Registry of ingested sources", "sources": []}


def save_manifest(manifest: dict) -> None:
    """Save the source manifest."""
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def is_source_ingested(content_hash: str) -> bool:
    """Check if a source with given hash has already been ingested."""
    manifest = load_manifest()
    return any(s.get("content_hash") == content_hash for s in manifest["sources"])


def register_source(
    filename: str,
    source_type: str,
    content_hash: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Register a source in the manifest."""
    manifest = load_manifest()
    entry = {
        "filename": filename,
        "source_type": source_type,
        "content_hash": content_hash,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "status": "ingested",
        "concepts_generated": [],
        "entities_generated": [],
    }
    if metadata:
        entry["metadata"] = metadata
    manifest["sources"].append(entry)
    save_manifest(manifest)


# ── Wiki Page Operations ──────────────────────────────────────────────

def list_wiki_pages() -> list[Path]:
    """List all .md files in the wiki directory."""
    return sorted(WIKI_DIR.rglob("*.md"))


def list_concept_pages() -> list[Path]:
    """List all concept pages."""
    return sorted(CONCEPTS_DIR.glob("*.md"))


def list_entity_pages() -> list[Path]:
    """List all entity pages."""
    return sorted(ENTITIES_DIR.glob("*.md"))


def page_exists(title: str) -> Path | None:
    """Check if a wiki page with the given title exists (case-insensitive)."""
    title_lower = title.lower()
    for page in list_wiki_pages():
        if page.stem.lower() == title_lower:
            return page
    return None


def read_page(path: Path) -> frontmatter.Post:
    """Read a wiki page and parse frontmatter."""
    return frontmatter.load(str(path))


def write_page(path: Path, metadata: dict, content: str) -> None:
    """Write a wiki page with frontmatter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(content, **metadata)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


# ── Wikilink Operations ──────────────────────────────────────────────

def extract_wikilinks(content: str) -> list[str]:
    """Extract all [[wikilink]] targets from content."""
    return WIKILINK_PATTERN.findall(content)


def find_all_wikilinks() -> dict[str, list[str]]:
    """Build a map of page -> [outgoing wikilinks] for the entire wiki."""
    links: dict[str, list[str]] = {}
    for page in list_wiki_pages():
        text = page.read_text(encoding="utf-8")
        targets = extract_wikilinks(text)
        links[page.stem] = targets
    return links


# ── Typed Relation Extraction (v2) ─────────────────────────────────────

def extract_typed_relations(content: str) -> list[dict]:
    """Parse wikilinks to extract typed relations.

    Detects relation types from two sources:
    1. Inline suffix: [[Target Page]]:relation_type (e.g. [[RAG]]:implements)
    2. Context prefix: relation keywords in the 1-3 words before the wikilink
       (e.g. "implements [[RAG]]")

    Relation keywords are defined in SCHEMA.yaml: implements, extends,
    contradicts, cites, prerequisite_of, trades_off, derived_from.
    Untyped links default to "neutral".
    """
    results: list[dict] = []
    keyword_set = set(_RELATION_KEYWORDS)

    # Pattern to match the :relation_type suffix after a wikilink
    _SUFFIX_PATTERN = re.compile(r":(" + "|".join(keyword_set) + r")\b")

    for match in WIKILINK_PATTERN.finditer(content):
        target = match.group(1)
        link_end = match.end()
        link_start = match.start()

        # 1. Check for inline suffix: [[Target]]:implements
        relation = "neutral"
        after_text = content[link_end:link_end + 30]
        suffix_match = _SUFFIX_PATTERN.match(after_text)
        if suffix_match:
            relation = suffix_match.group(1)
        else:
            # 2. Fallback: check 1-3 words before the wikilink
            context_start = max(0, link_start - 1)
            prefix = content[:context_start].rstrip()
            prefix_words = _WORD_PATTERN.findall(prefix)

            for word in reversed(prefix_words[-3:]):
                if word.lower() in keyword_set:
                    relation = word.lower()
                    break

        results.append({"target": target, "type": relation})

    return results


# ── Provenance Sidecar (v2) ────────────────────────────────────────────

def _provenance_path(page_path: Path) -> Path:
    """Derive the .provenance.json sidecar path for a page.

    E.g. wiki/concepts/RAG.md -> wiki/concepts/RAG.provenance.json
    """
    return page_path.with_suffix(page_path.suffix + ".provenance.json")


def read_provenance(page_path: Path) -> dict | None:
    """Read the .provenance.json sidecar file for a page.

    Returns None if the sidecar doesn't exist.
    """
    prov_path = _provenance_path(page_path)
    if prov_path.exists():
        return json.loads(prov_path.read_text(encoding="utf-8"))
    return None


def write_provenance(page_path: Path, data: dict) -> None:
    """Write the .provenance.json sidecar file for a page.

    Creates parent directories if needed.
    """
    prov_path = _provenance_path(page_path)
    prov_path.parent.mkdir(parents=True, exist_ok=True)
    prov_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ── Graph Operations ──────────────────────────────────────────────────

def build_graph_json() -> dict:
    """Build the machine-readable adjacency graph from wiki pages."""
    all_links = find_all_wikilinks()
    nodes = []
    edges = []

    # Build node list from all existing pages
    for page in list_wiki_pages():
        try:
            post = read_page(page)
            node = {
                "id": page.stem,
                "type": post.metadata.get("type", "unknown"),
                "path": str(page.relative_to(WIKI_ROOT)),
            }
            if "confidence" in post.metadata:
                node["confidence"] = post.metadata["confidence"]
            nodes.append(node)
        except Exception:
            nodes.append({
                "id": page.stem,
                "type": "unknown",
                "path": str(page.relative_to(WIKI_ROOT)),
            })

    # Build edge list from wikilinks
    page_names = {page.stem.lower(): page.stem for page in list_wiki_pages()}
    for source, targets in all_links.items():
        for target in targets:
            target_normalized = page_names.get(target.lower(), target)
            edges.append({"source": source, "target": target_normalized})

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }


def save_graph() -> dict:
    """Generate and save the graph JSON file."""
    graph = build_graph_json()
    GRAPH_PATH.write_text(
        json.dumps(graph, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return graph


# ── Formatting Helpers ────────────────────────────────────────────────

def today() -> str:
    """Return today's date as ISO string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def slugify(title: str) -> str:
    """Convert a title to a filename-safe slug (preserves spaces for Obsidian)."""
    # Remove filesystem-forbidden characters
    return re.sub(r'[\\/:*?"<>|]', "", title).strip()
