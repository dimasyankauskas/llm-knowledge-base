"""Provenance sidecar management for Antigravity Wiki v2.

Tracks claim-level evidence and detects staleness when source files change.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import hash_file, read_provenance


def create_provenance(page: str, content_hash: str, sources: list[dict] | None = None) -> dict:
    """Create a new provenance record.

    Args:
        page: Wiki page title.
        content_hash: Hash of the page content.
        sources: Optional list of source dicts with 'file', 'content_hash',
                 'sections_used' keys.

    Returns:
        A new provenance dict.
    """
    return {
        "page": page,
        "content_hash": content_hash,
        "sources": list(sources) if sources else [],
        "claims": [],
        "derived_concepts": [],
    }


def add_claim(
    prov: dict,
    text: str,
    claim_type: str,
    sources: list[str],
    corroborated: bool = False,
) -> dict:
    """Add a claim to a provenance record.

    Args:
        prov: Provenance dict to update.
        text: Claim text.
        claim_type: 'fact' or 'inference'.
        sources: List of source filenames supporting this claim.
        corroborated: Whether the claim is independently corroborated.

    Returns:
        Updated provenance dict.
    """
    claim_number = len(prov["claims"]) + 1
    claim = {
        "id": f"claim-{claim_number}",
        "text": text,
        "type": claim_type,
        "sources": list(sources),
        "corroborated": corroborated,
        "last_verified": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    prov["claims"].append(claim)
    return prov


def add_source(
    prov: dict,
    file: str,
    content_hash: str,
    sections_used: list[str] | None = None,
) -> dict:
    """Add a source reference to a provenance record.

    Args:
        prov: Provenance dict to update.
        file: Source filename.
        content_hash: Hash of the source content at time of ingestion.
        sections_used: Sections of the source used; defaults to empty list.

    Returns:
        Updated provenance dict.
    """
    prov["sources"].append({
        "file": file,
        "content_hash": content_hash,
        "sections_used": list(sections_used) if sections_used else [],
    })
    return prov


def check_staleness(prov: dict, sources_dir: Path | None = None) -> list[str]:
    """Check if any source in the provenance record has changed.

    Compares stored content_hash with the actual file hash on disk.

    Args:
        prov: Provenance dict to check.
        sources_dir: Directory containing source files. Defaults to the
                      project's sources/ directory.

    Returns:
        List of source filenames that have changed (stale) or are missing.
    """
    if sources_dir is None:
        from scripts.utils import SOURCES_DIR
        sources_dir = SOURCES_DIR

    stale: list[str] = []
    for src in prov.get("sources", []):
        filepath = sources_dir / src["file"]
        if not filepath.exists():
            stale.append(src["file"])
            continue
        current_hash = hash_file(filepath)
        if current_hash != src["content_hash"]:
            stale.append(src["file"])
    return stale


def get_stale_pages(wiki_dir: Path, sources_dir: Path) -> list[str]:
    """Find all wiki pages whose sources have changed.

    Reads provenance sidecars for all concept and entity pages, checks
    each source's current hash against the stored hash.

    Args:
        wiki_dir: Root wiki directory containing concepts/ and entities/.
        sources_dir: Directory containing source files.

    Returns:
        List of page names (stems) whose sources are stale.
    """
    stale_pages: list[str] = []
    for subdir in ("concepts", "entities"):
        page_dir = wiki_dir / subdir
        if not page_dir.exists():
            continue
        for md_file in sorted(page_dir.glob("*.md")):
            prov = read_provenance(md_file)
            if prov is None:
                continue
            if check_staleness(prov, sources_dir):
                stale_pages.append(md_file.stem)
    return stale_pages


def get_claim_sources(prov: dict, claim_id: str) -> list[str]:
    """Get sources for a specific claim by its ID.

    Args:
        prov: Provenance dict.
        claim_id: The claim identifier (e.g. 'claim-1').

    Returns:
        List of source filenames for the claim, or empty list if not found.
    """
    for claim in prov.get("claims", []):
        if claim.get("id") == claim_id:
            return list(claim.get("sources", []))
    return []