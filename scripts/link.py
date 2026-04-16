"""
Antigravity Wiki v2 — Link Stage

Stage 3 of the pipeline: resolve wikilinks, build typed graph,
verify bidirectional links.

Usage:
    python scripts/link.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import frontmatter

sys.path.insert(0, str(Path(__file__).parent))

from schema import load_schema, get_relation_types
from utils import (
    CONCEPTS_DIR,
    ENTITIES_DIR,
    WIKI_DIR,
    extract_wikilinks,
    extract_typed_relations,
    list_wiki_pages,
    read_page,
)


# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_EDGE_WEIGHTS: dict[str, int] = {
    "cites": 4,
    "contradicts": 3,
    "implements": 3,
    "extends": 2,
    "prerequisite_of": 2,
    "trades_off": 1,
    "derived_from": 2,
    "neutral": 1,
}

# Pattern for frontmatter related_concepts entries like "[[Neural IR]]:implements"
_FRONTMATTER_TYPED_PATTERN = re.compile(
    r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]:(\w+)"
)


# ── extract_typed_edges ──────────────────────────────────────────────────────


def extract_typed_edges(
    content: str,
    page_name: str,
    relation_types: list[str] | None = None,
    metadata: dict | None = None,
) -> list[dict]:
    """Parse content to extract typed edges from wikilinks.

    Uses utils.extract_typed_relations to find relations.
    Also checks frontmatter 'related_concepts' list for explicit type
    annotations like:
      - "[[Neural IR]]:implements"

    Returns list of dicts: [{"source": page_name, "target": str, "type": str}]
    - typed edges from context analysis (implements, extends, contradicts, etc.)
    - explicit edges from frontmatter related_concepts
    - untyped edges default to "neutral"
    """
    edges: list[dict] = []

    # 1. Context-based typed relations from the body text
    typed_relations = extract_typed_relations(content)
    seen_targets: set[str] = set()

    for rel in typed_relations:
        edge = {
            "source": page_name,
            "target": rel["target"],
            "type": rel["type"],
        }
        edges.append(edge)
        seen_targets.add(rel["target"])

    # 2. Explicit typed edges from frontmatter related_concepts
    if metadata and "related_concepts" in metadata:
        for entry in metadata["related_concepts"]:
            match = _FRONTMATTER_TYPED_PATTERN.search(str(entry))
            if match:
                target = match.group(1)
                rel_type = match.group(2)
                # Frontmatter explicit types override context-detected types
                # Remove any existing edge for this target (from context)
                edges = [
                    e for e in edges
                    if not (e["target"] == target and e["source"] == page_name)
                ]
                edges.append({
                    "source": page_name,
                    "target": target,
                    "type": rel_type,
                })
                seen_targets.add(target)

    return edges


# ── build_typed_graph ────────────────────────────────────────────────────────


def build_typed_graph(
    wiki_dir: Path | None = None,
    schema: dict | None = None,
) -> dict:
    """Build _graph.json with typed edges from all wiki pages.

    For each page in wiki/concepts/ and wiki/entities/:
    - Read the page content
    - Extract typed edges using extract_typed_edges
    - Add node with type, path, confidence metadata

    Build edge list with source, target, type, and weight.
    Weights come from schema relation_types (or defaults).
    Default weights: cites=4, contradicts=3, implements=3, extends=2,
    prerequisite_of=2, trades_off=1, derived_from=2, neutral=1

    Returns dict: {
        "generated_at": ISO timestamp,
        "node_count": int,
        "edge_count": int,
        "nodes": [{"id", "type", "path", "confidence"}],
        "edges": [{"source", "target", "type", "weight"}]
    }
    """
    if wiki_dir is None:
        wiki_dir = WIKI_DIR
    if schema is None:
        try:
            schema = load_schema()
        except FileNotFoundError:
            schema = {}

    # Load relation types and weights from schema (if available)
    relation_type_list = get_relation_types(schema) if schema else []
    edge_weights = dict(DEFAULT_EDGE_WEIGHTS)

    # Gather pages from concepts/ and entities/
    concepts_dir = wiki_dir / "concepts"
    entities_dir = wiki_dir / "entities"

    page_paths: list[Path] = []
    if concepts_dir.exists():
        page_paths.extend(sorted(concepts_dir.glob("*.md")))
    if entities_dir.exists():
        page_paths.extend(sorted(entities_dir.glob("*.md")))

    # Build a lookup: lowercase-normalized name -> actual page stem
    # Wikilinks may use spaces (e.g. "Neural IR") but page stems use
    # underscores (e.g. "Neural_IR"). Normalize both to lowercase with
    # spaces replaced by underscores for matching.
    page_name_map: dict[str, str] = {}
    for page_path in page_paths:
        stem = page_path.stem
        normalized = stem.lower().replace(" ", "_")
        page_name_map[normalized] = stem

    def _resolve_target(target: str) -> str:
        """Resolve a wikilink target to its canonical page stem."""
        normalized = target.lower().replace(" ", "_")
        return page_name_map.get(normalized, target)

    nodes: list[dict] = []
    edges: list[dict] = []
    seen_edges: set[tuple[str, str, str]] = set()  # (source, target, type) dedup

    for page_path in page_paths:
        page_name = page_path.stem

        # Skip index pages (names starting with _)
        if page_name.startswith("_"):
            continue

        try:
            post = read_page(page_path)
        except Exception:
            continue

        metadata = dict(post.metadata) if post.metadata else {}
        content = post.content

        # Build node
        node: dict[str, Any] = {
            "id": page_name,
            "type": metadata.get("type", "unknown"),
            "path": str(page_path.relative_to(wiki_dir)),
        }
        if "confidence" in metadata:
            node["confidence"] = metadata["confidence"]
        nodes.append(node)

        # Extract typed edges
        page_edges = extract_typed_edges(
            content, page_name, relation_types=relation_type_list, metadata=metadata,
        )

        for edge in page_edges:
            resolved_target = _resolve_target(edge["target"])
            # Case-normalize dedup key to prevent duplicates from
            # body text vs frontmatter extraction with different casing
            edge_key = (edge["source"].lower(), resolved_target.lower(), edge["type"].lower())
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                weight = edge_weights.get(edge["type"], 1)
                edges.append({
                    "source": edge["source"],
                    "target": resolved_target,
                    "type": edge["type"],
                    "weight": weight,
                })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }


# ── verify_bidirectional_links ───────────────────────────────────────────────


def verify_bidirectional_links(
    wiki_dir: Path | None = None,
) -> list[dict]:
    """Check that strongly connected pages link back to each other.

    For each pair of pages where A->B has a typed relation
    (not "neutral"), check if B->A also exists.

    Returns list of dicts: [{"source": str, "target": str, "type": str, "has_reverse": bool}]
    Only includes pairs where has_reverse is False (missing reverse link).
    """
    if wiki_dir is None:
        wiki_dir = WIKI_DIR

    # Build a map of all typed edges (non-neutral) per page
    concepts_dir = wiki_dir / "concepts"
    entities_dir = wiki_dir / "entities"

    page_paths: list[Path] = []
    if concepts_dir.exists():
        page_paths.extend(sorted(concepts_dir.glob("*.md")))
    if entities_dir.exists():
        page_paths.extend(sorted(entities_dir.glob("*.md")))

    # Build a lookup: lowercase-normalized name -> actual page stem
    page_name_map: dict[str, str] = {}
    for page_path in page_paths:
        stem = page_path.stem
        normalized = stem.lower().replace(" ", "_")
        page_name_map[normalized] = stem

    def _resolve_target(target: str) -> str:
        """Resolve a wikilink target to its canonical page stem."""
        normalized = target.lower().replace(" ", "_")
        return page_name_map.get(normalized, target)

    # Collect all edges per page (typed and neutral) for reverse lookup,
    # and separately collect typed (non-neutral) edges for the check
    all_outgoing: dict[str, set[str]] = {}   # page -> set of targets (any type)
    typed_outgoing: dict[str, list[dict]] = {}  # page -> list of {target, type}

    for page_path in page_paths:
        page_name = page_path.stem
        if page_name.startswith("_"):
            continue

        try:
            post = read_page(page_path)
        except Exception:
            continue

        metadata = dict(post.metadata) if post.metadata else {}
        content = post.content
        edges = extract_typed_edges(content, page_name, metadata=metadata)

        all_targets: set[str] = set()
        typed_edges: list[dict] = []
        for e in edges:
            resolved = _resolve_target(e["target"])
            all_targets.add(resolved)
            if e["type"] != "neutral":
                typed_edges.append({
                    "source": e["source"],
                    "target": resolved,
                    "type": e["type"],
                })

        all_outgoing[page_name] = all_targets
        typed_outgoing[page_name] = typed_edges

    # Check each typed edge for a reverse (any link back counts)
    issues: list[dict] = []
    for source, edge_list in typed_outgoing.items():
        for edge in edge_list:
            target = edge["target"]
            edge_type = edge["type"]
            # Check if target links back to source (any type, even neutral)
            has_reverse = source in all_outgoing.get(target, set())
            if not has_reverse:
                issues.append({
                    "source": source,
                    "target": target,
                    "type": edge_type,
                    "has_reverse": False,
                })

    return issues


# ── save_graph ───────────────────────────────────────────────────────────────


def save_graph(graph: dict, wiki_dir: Path | None = None) -> None:
    """Write _graph.json to disk."""
    if wiki_dir is None:
        wiki_dir = WIKI_DIR
    graph_path = wiki_dir / "_graph.json"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(
        json.dumps(graph, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ── CLI ──────────────────────────────────────────────────────────────────────


def main() -> None:
    """CLI: python scripts/link.py
    Build graph and verify links for the current wiki.
    """
    print("Building typed graph...")
    graph = build_typed_graph()
    save_graph(graph)
    print(f"  Nodes: {graph['node_count']}")
    print(f"  Edges: {graph['edge_count']}")

    print("\nVerifying bidirectional links...")
    issues = verify_bidirectional_links()
    if issues:
        print(f"  Missing reverse links: {len(issues)}")
        for issue in issues:
            print(f"    {issue['source']} -> {issue['target']} ({issue['type']})")
    else:
        print("  All typed links are bidirectional.")

    print("\nDone.")


if __name__ == "__main__":
    main()