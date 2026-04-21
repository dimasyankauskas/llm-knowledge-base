"""Provenance sidecar management for LLM Knowledge Base v2.

Tracks claim-level evidence and detects staleness when source files change.
"""

from __future__ import annotations

import sys
import re
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils import hash_file, read_page, read_provenance, write_provenance


SOURCE_REF_PATTERN = re.compile(r"\[source:\s*([^,\]]+),\s*§([^\]]+)\]")
SECTION_PATTERN = re.compile(r"^##\s+(.+)$")


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


def merge_provenance(existing: dict | None, incoming: dict | None, page: str, content_hash: str) -> dict:
    """Merge two provenance sidecars without duplicating sources or claims."""
    merged = create_provenance(page=page, content_hash=content_hash)

    source_keys: set[tuple[str, str]] = set()
    for prov in (existing or {}, incoming or {}):
        for source in prov.get("sources", []):
            key = (str(source.get("file", "")), str(source.get("content_hash", "")))
            if not key[0] or key in source_keys:
                continue
            source_keys.add(key)
            merged["sources"].append(source)

    claim_keys: set[tuple[str, tuple[str, ...]]] = set()
    for prov in (existing or {}, incoming or {}):
        for claim in prov.get("claims", []):
            sources = tuple(sorted(str(src) for src in claim.get("sources", [])))
            key = (str(claim.get("text", "")), sources)
            if not key[0] or key in claim_keys:
                continue
            claim_keys.add(key)
            new_claim = dict(claim)
            new_claim["id"] = f"claim-{len(merged['claims']) + 1}"
            merged["claims"].append(new_claim)

    derived: list[str] = []
    for prov in (existing or {}, incoming or {}):
        for concept in prov.get("derived_concepts", []):
            if concept not in derived:
                derived.append(concept)
    merged["derived_concepts"] = derived
    return merged


def extract_claims_from_page(page_path: Path, max_claims: int | None = None) -> list[dict]:
    """Extract cited claim lines from a page into provenance-ready records."""
    try:
        post = read_page(page_path)
    except Exception:
        return []

    claims: list[dict] = []
    confidence = post.metadata.get("confidence", "MEDIUM")
    current_section = ""

    for raw_line in post.content.splitlines():
        line = raw_line.strip()
        heading = SECTION_PATTERN.match(line)
        if heading:
            current_section = heading.group(1).strip()
            continue
        if not line or current_section == "Sources":
            continue

        refs = SOURCE_REF_PATTERN.findall(line)
        if not refs:
            continue

        text = re.sub(r"^[-*]\s+", "", line).strip()
        if text.startswith("[source:"):
            continue
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"\[source:\s*[^,\]]+,\s*§[^\]]+\]", "", text)
        text = re.sub(r"\s+", " ", text).strip(" .")
        if len(text) < 12:
            continue

        source_refs = [
            {"source": source.strip(), "section": section.strip()}
            for source, section in refs
        ]
        sources = sorted({ref["source"] for ref in source_refs})
        claims.append({
            "id": f"claim-{len(claims) + 1}",
            "text": text,
            "type": "fact",
            "confidence": confidence,
            "section": current_section,
            "sources": sources,
            "source_refs": source_refs,
            "corroborated": len(sources) > 1,
            "last_verified": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        })
        if max_claims is not None and len(claims) >= max_claims:
            break

    return claims


def refresh_page_claims(page_path: Path) -> dict | None:
    """Refresh a page sidecar with claims extracted from inline citations."""
    prov = read_provenance(page_path)
    if prov is None:
        return None
    prov = dict(prov)
    prov["claims"] = extract_claims_from_page(page_path)
    write_provenance(page_path, prov)
    return prov


def refresh_all_claims(wiki_dir: Path) -> int:
    """Refresh claim sidecars for all concept and entity pages."""
    refreshed = 0
    for subdir in ("concepts", "entities"):
        for page_path in sorted((wiki_dir / subdir).glob("*.md")):
            if refresh_page_claims(page_path) is not None:
                refreshed += 1
    return refreshed


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


def _resolve_source_file(filename: str, sources_dir: Path) -> Path | None:
    """Resolve a source filename to its actual path on disk.

    Tries in order:
    1. Direct path: sources_dir / filename (works for subdirectory-relative paths
       like 'article/paper.md')
    2. Subdirectory search: look for filename in any subdirectory of sources_dir
    3. Bare filename at top level of sources_dir

    Returns the Path if found, None otherwise.
    """
    # Try direct path first (handles 'article/paper.md' style)
    direct = sources_dir / filename
    if direct.exists():
        return direct

    # Try subdirectory search (handles bare 'paper.md' when file is in article/)
    for subdir in sorted(sources_dir.iterdir()):
        if subdir.is_dir():
            candidate = subdir / filename
            if candidate.exists():
                return candidate

    # Try top-level
    top = sources_dir / filename
    if top.exists():
        return top

    return None


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
        from utils import SOURCES_DIR
        sources_dir = SOURCES_DIR

    stale: list[str] = []
    for src in prov.get("sources", []):
        filename = src.get("file", "")
        filepath = _resolve_source_file(filename, sources_dir)
        if filepath is None:
            stale.append(filename)
            continue
        current_hash = hash_file(filepath)
        if current_hash != src.get("content_hash", ""):
            stale.append(filename)
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
