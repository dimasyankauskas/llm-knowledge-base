"""LLM Knowledge Base v2 — LLM Response Parser

Parses LLM markdown output into structured frontmatter + content.
Handles YAML frontmatter extraction, content_hash injection, and wikilink validation.

Usage:
    pages = parse_multi_page_response(raw_text)
    frontmatter, content = parse_single_page(raw_text)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

import frontmatter

sys.path.insert(0, str(Path(__file__).parent))

from utils import hash_content, extract_wikilinks


def _count_yaml_keys(fm_text: str) -> int:
    """Count top-level YAML keys in a frontmatter block."""
    import yaml
    try:
        data = yaml.safe_load(fm_text)
        return len(data) if isinstance(data, dict) else 0
    except Exception:
        return 0


def _strip_code_fences(text: str) -> str:
    """Remove YAML/MD code fence wrappers.

    qwen3.5 sometimes outputs frontmatter wrapped in fenced code blocks:
        ```yaml
        ---
        title: ...
        ---
        ```
    This removes the wrapping fences so frontmatter.parse sees clean blocks.
    """
    # Remove opening ```yaml and closing ```
    cleaned = re.sub(r"```yaml\s*\n?", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    return cleaned


def parse_single_page(
    raw_markdown: str,
    page_type: str = "concept",
) -> tuple[dict, str]:
    """Parse a single LLM-generated wiki page.

    Args:
        raw_markdown: Raw markdown output from LLM (may include YAML frontmatter).
        page_type: Default page type if frontmatter doesn't specify.

    Returns:
        Tuple of (frontmatter_dict, content_str).

    Raises:
        ValueError: If YAML frontmatter is missing or content is empty.
    """
    import yaml

    raw_markdown = _strip_code_fences(raw_markdown).strip()
    if not raw_markdown:
        raise ValueError("Page content is empty")

    # Find all frontmatter blocks (---...--- pairs).
    # An LLM may output multiple consecutive frontmatter blocks (e.g. a partial
    # content_hash block followed by the full block). We want the most complete one.
    fm_blocks = list(re.finditer(r"^---\s*\n(.*?)\n---", raw_markdown, re.DOTALL | re.MULTILINE))

    if fm_blocks:
        # Pick the block with the most YAML keys (most complete frontmatter)
        best_block = max(
            fm_blocks,
            key=lambda m: _count_yaml_keys(m.group(1))
        )
        fm_text = best_block.group(1).strip()
        content_start = best_block.end()
        content = raw_markdown[content_start:].strip()
        try:
            metadata = yaml.safe_load(fm_text)
            if not isinstance(metadata, dict):
                metadata = {}
        except Exception:
            metadata = {}
    else:
        # No closed frontmatter block found.
        # Handle two sub-cases:
        # 1. Frontmatter opens with --- and closes with another --- later
        # 2. Frontmatter opens with --- and content starts with ## heading (no closing ---)
        metadata = {}
        content = raw_markdown
        if raw_markdown.startswith("---"):
            remainder = raw_markdown[2:]
            # Find closing --- (with newline before it)
            closing_match = re.search(r"\n---", remainder)
            # Find where content starts (## heading)
            content_heading = re.search(r"\n## ", remainder)
            # Use whichever comes first
            if closing_match and (not content_heading or closing_match.start() < content_heading.start()):
                fm_text = remainder[:closing_match.start()].strip()
                content = remainder[closing_match.end():].strip()
            elif content_heading:
                fm_text = remainder[:content_heading.start()].strip()
                content = remainder[content_heading.start():].strip()
            else:
                fm_text = remainder.strip()
                content = ""
            try:
                # Strip orphan YAML list items (e.g. leading "-\n" from abandoned blocks)
                cleaned_fm = re.sub(r"^\s*-\s*\n", "", fm_text, flags=re.MULTILINE).strip()
                data = yaml.safe_load(cleaned_fm)
                if isinstance(data, dict):
                    metadata = data
            except Exception:
                pass

    if not content:
        raise ValueError("Page content is empty")

    # Inject content_hash if TBD or missing
    content_hash = hash_content(content)
    existing = metadata.get("content_hash") or ""
    # Also catch common LLM placeholder variations
    placeholder_values = {"", "TBD", "tbd", "TODO", "FILL IN", "fill in", "null", "none"}
    if existing.strip().lower() in placeholder_values:
        metadata["content_hash"] = content_hash

    # Ensure type is set
    if not metadata.get("type"):
        metadata["type"] = page_type

    return dict(metadata), content


def _starts_frontmatter(text: str) -> bool:
    """Return True if text looks like the start of a YAML frontmatter block."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return False
    first = lines[0].lower()
    return (
        first.startswith("title:")
        or first.startswith("type:")
        or first.startswith("confidence:")
        or first.startswith("created:")
        or first.startswith("content_hash:")
        or first.startswith("source_refs:")
        or first.startswith("entity_type:")
    )


def split_pages(raw_text: str) -> list[str]:
    """Split a multi-page LLM response into individual page strings.

    Splits on "\n---\n". Key insight: the LLM outputs pages where each page
    either:
    (a) Has a body after frontmatter: ---\ntitle\n---\nbody
    (b) Has no body, just frontmatter: ---\ntitle\n---\n

    Even-index parts are page candidates.
    Odd-index parts are either: (a) body content, or (b) the start of the next
    page (when previous page had no body).

    A page can also contain multiple frontmatter blocks (e.g. an initial
    content_hash block followed by the full frontmatter). When an odd-index
    part begins with a frontmatter key (title:, confidence:, etc.), prepend
    it to the current page rather than starting a new page.

    Returns list of individual page markdown strings.
    """
    parts = raw_text.split("\n---\n")
    pages: list[str] = []
    current_page: list[str] = []

    for i, part in enumerate(parts):
        stripped = part.strip()

        if i % 2 == 0:
            # Even index: page opener or content
            if stripped.startswith("---"):
                # New page opener
                if current_page:
                    joined = "\n".join(current_page).strip()
                    if joined:
                        pages.append(joined)
                    current_page = []
                current_page.append(part)
            elif stripped and "---\n" in "\n".join(current_page):
                # current_page contains a bare "---" (from an earlier frontmatter block)
                # — could be the body OR the start of a new frontmatter
                if _starts_frontmatter(stripped):
                    # Frontmatter-looking content — prepend to current page (merge, not split)
                    joined = "\n".join(current_page).strip()
                    if joined:
                        pages.append(joined)
                    current_page = ["---\n" + part]
                else:
                    current_page.append(part)
            elif stripped:
                # Non-empty non---- content — body for current page
                current_page.append(part)
        else:
            # Odd index: body, blank separator, or page start
            if _starts_frontmatter(stripped):
                # Frontmatter-looking content — prepend to current page
                # (not a body and not a new page separator)
                if current_page:
                    current_page.append("---\n" + part)
                else:
                    current_page.append("---\n" + part)
            elif stripped.startswith("---"):
                # Next page opener
                if current_page:
                    joined = "\n".join(current_page).strip()
                    if joined:
                        pages.append(joined)
                    current_page = []
                current_page.append(part)
            elif stripped:
                # Non-empty body content
                current_page.append(part)
            # else: empty separator — skip

    # Last accumulated page
    joined = "\n".join(current_page).strip()
    if joined:
        pages.append(joined)

    if not pages:
        return [raw_text.strip()]

    return _merge_frontmatter_only_fragments(pages)


def _merge_frontmatter_only_fragments(pages: list[str]) -> list[str]:
    """Attach orphan frontmatter fragments to the next page body.

    Some models emit a tiny preliminary frontmatter block (often only
    ``content_hash`` and ``type``) followed by the real frontmatter block. The
    splitter can see that tiny block as its own page; for parsing we want one
    page so parse_single_page can choose the richest block.
    """
    merged: list[str] = []
    pending_fragments: list[str] = []

    for page in pages:
        if _is_frontmatter_only_fragment(page):
            pending_fragments.append(_ensure_closed_frontmatter(page))
            continue
        if pending_fragments:
            merged.append("\n\n".join(pending_fragments + [_ensure_closed_frontmatter(page)]))
            pending_fragments = []
        else:
            merged.append(page)

    if pending_fragments:
        merged.extend(pending_fragments)
    return merged


def _is_frontmatter_only_fragment(page: str) -> bool:
    stripped = page.strip()
    if not stripped.startswith("---"):
        return False
    if re.search(r"^#{1,6}\s+", stripped, flags=re.MULTILINE):
        return False
    return _starts_frontmatter(stripped.lstrip("-\n "))


def _ensure_closed_frontmatter(page: str) -> str:
    """Ensure a page fragment that starts with frontmatter has a closing marker."""
    stripped = page.strip()
    if not stripped.startswith("---"):
        return page
    if re.search(r"^---\s*$", stripped, flags=re.MULTILINE):
        # Opening marker counts too; require another marker after the first line.
        markers = list(re.finditer(r"^---\s*$", stripped, flags=re.MULTILINE))
        if len(markers) >= 2:
            return page

    heading = re.search(r"^#{1,6}\s+", page, flags=re.MULTILINE)
    if heading:
        return page[:heading.start()].rstrip() + "\n---\n\n" + page[heading.start():].lstrip()
    return page.rstrip() + "\n---"


def parse_multi_page_response(
    raw_text: str,
    page_type: str = "concept",
) -> list[tuple[dict, str]]:
    """Parse an LLM response that may contain multiple wiki pages.

    Args:
        raw_text: Raw text from LLM (may contain multiple pages separated by ---).
        page_type: Default page type for pages without frontmatter.

    Returns:
        List of (frontmatter_dict, content_str) tuples.
    """
    page_texts = split_pages(raw_text)
    results = []

    for page_text in page_texts:
        try:
            fm, content = parse_single_page(page_text, page_type)
            results.append((fm, content))
        except ValueError:
            # Skip pages that can't be parsed
            continue

    return results


def validate_page_wikilinks(
    content: str,
    existing_pages: set[str],
    pending_pages: Optional[set[str]] = None,
) -> list[str]:
    """Validate wikilinks in page content.

    Args:
        content: Page body content.
        existing_pages: Set of existing page stems (case-insensitive).
        pending_pages: Pages being created in this batch (also valid targets).

    Returns:
        List of broken link targets (empty if all valid).
    """
    links = extract_wikilinks(content)
    all_valid = existing_pages | (pending_pages or set())
    all_valid_lower = {l.lower() for l in all_valid}

    broken = []
    for link in links:
        if link.lower() not in all_valid_lower:
            broken.append(link)
    return broken


def extract_page_title(frontmatter: dict, content: str, default: str) -> str:
    """Extract page title from frontmatter or content."""
    if frontmatter.get("title"):
        return frontmatter["title"]

    # Try to extract from first H1 in content
    h1_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if h1_match:
        return h1_match.group(1).strip()

    return default


# ── CLI (for testing) ────────────────────────────────────────────────────────


def main() -> None:
    """CLI: python scripts/parse_llm_response.py

    Test parsing with sample inputs.
    """
    import argparse

    parser = argparse.ArgumentParser(description="Parse LLM response test")
    parser.add_argument("--text", help="Raw markdown text to parse")
    args = parser.parse_args()

    if args.text:
        try:
            pages = parse_multi_page_response(args.text)
            print(f"Parsed {len(pages)} page(s)")
            for i, (fm, content) in enumerate(pages):
                print(f"\n--- Page {i+1} ---")
                print(f"Title: {fm.get('title', 'N/A')}")
                print(f"Type: {fm.get('type', 'N/A')}")
                print(f"Content preview: {content[:200]}...")
        except Exception as e:
            print(f"Parse error: {e}", file=__import__("sys").stderr)


if __name__ == "__main__":
    main()
