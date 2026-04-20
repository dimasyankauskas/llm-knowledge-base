"""LLM Knowledge Base v2 — Auto-Ingest Orchestration

Drops a source file → gets a fully integrated, validated, linked wiki page.
No manual LLM collaboration required.

Pipeline:
  1. Read source content (reuse: extract.py:read_source())
  2. Build LLM prompt (reuse: extract_prompt.py:generate_extraction_prompt())
  3. Call LLM with retry + backoff
  4. Parse response into frontmatter + content
  5. Write draft + provenance sidecar
  6. Validate (reuse: validate.py:validate_draft())
  7. On validation errors: retry LLM with correction prompt (max 2 retries)
  8. On success: promote (reuse: validate.py:promote_draft())
  9. Update state + health
  10. Log operation to _log.md

Usage:
    from auto_ingest import auto_ingest
    promoted = auto_ingest(Path("sources/article.md"), page_type="concept")
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import frontmatter

sys.path.insert(0, str(Path(__file__).parent))

from extract import read_source, classify_source_type, register_source
from extract_prompt import generate_extraction_prompt
from llm_client import completion_with_retry, count_tokens
from parse_llm_response import parse_multi_page_response, validate_page_wikilinks, extract_page_title
from provenance import create_provenance
from utils import write_provenance
from schema import load_schema
from validate import validate_draft, promote_draft
from state import generate_state, generate_health, save_state, save_health
from utils import (
    DRAFTS_DIR,
    WIKI_DIR,
    SOURCES_DIR,
    CONCEPTS_DIR,
    ENTITIES_DIR,
    list_wiki_pages,
    hash_content,
    extract_wikilinks,
    page_exists,
)
from log import append_log

# ── Constants ────────────────────────────────────────────────────────────────

MAX_RETRIES_PER_DRAFT = 2
DEFAULT_PAGE_TYPE = "concept"

GAP_SYSTEM_PROMPT = """You are a **Wiki Gap Analyst**.
Your job is to read a new source and identify EXACTLY what NEW knowledge it brings
that is NOT covered by the existing wiki.

Focus on:
1. NEW concepts the source introduces that don't exist in the wiki
2. NEW relationships between existing concepts
3. NEW evidence or data that extends existing concepts
4. CONTRADICTIONS with existing wiki content
5. OPEN QUESTIONS the source raises that aren't answered

Do NOT summarize the source. Do NOT create a comprehensive page.
Only identify the specific gaps this source fills.
"""


# ── Core Functions ──────────────────────────────────────────────────────────


def _build_gap_analysis_prompt(
    source_name: str,
    existing_context: str,
    source_text: str,
) -> str:
    """Build prompt for gap analysis."""
    return f"""---
SOURCE: {source_name}

EXISTING WIKI CONCEPTS:
{existing_context}

{GAP_SYSTEM_PROMPT}

Analyze the source material and identify specific gaps it fills.
Be precise — don't say "covers many topics." Name the specific new concepts,
relationships, evidence, contradictions, or questions.

---
SOURCE MATERIAL:
{source_text}
"""


def _build_gap_extraction_prompt(
    source_name: str,
    page_type: str,
    schema: dict,
    existing_context: str,
    gap_output: str,
    source_text: str,
) -> str:
    """Build prompt for gap-driven extraction."""
    required_fm = schema.get("page_types", {}).get(page_type, {}).get(
        "required_frontmatter", []
    )
    citation_format = schema.get("page_types", {}, {}).get(
        page_type, {}
    ).get("citation_format", "[source: {filename}, §{section}]"
    )

    fm_block = "\n".join(f"{f}: # FILL IN" for f in required_fm)
    created_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    return f"""---
You are a **Wiki Curator**. You have identified gaps this source fills.
Your job: create pages that ONLY fill these gaps — don't summarize everything.

## Identified Gaps
{gap_output}

## Existing Wiki Concepts
{existing_context}

## Page Configuration
- Source: {source_name}
- Page type: {page_type}
- Citation format: {citation_format}

## Required Frontmatter
```yaml
{fm_block}
created: {created_date}
```

## Rules
1. FACTS ONLY sections need inline citations: {citation_format.format(filename=source_name, section='section')}
2. Inferences marked with: > [!note] Inference: ...
3. Use wikilinks [[Page Name]] for connections
4. Confidence: HIGH (multiple sources), MEDIUM (single source), LOW (inference)
5. Do NOT repeat content already in the wiki

## Output
Produce a complete markdown file with YAML frontmatter followed by sections.
Focus ONLY on the gaps identified above.

---
SOURCE MATERIAL:
{source_text}
"""


def _get_existing_concepts() -> list[str]:
    """Get list of existing concept page titles."""
    titles = []
    for md_file in CONCEPTS_DIR.rglob("*.md"):
        titles.append(md_file.stem)
    return titles


def _build_existing_context() -> str:
    """Build context string of existing wiki concepts."""
    existing = _get_existing_concepts()
    if not existing:
        return "No existing concept pages yet."
    return "\n".join(f"  - {t}" for t in sorted(existing))


def _build_correction_prompt(
    page_title: str,
    errors: list[str],
    context: Optional[str] = None,
) -> str:
    """Build a correction prompt from validation errors."""
    error_list = "\n".join(f"  - {err}" for err in errors)
    prompt = f"""The following errors were found in the wiki page for "{page_title}".
Please fix them and output the corrected page in markdown format.

## Errors

{error_list}

## Instructions

1. Fix all listed errors
2. Keep all valid content that doesn't have errors
3. Output the complete corrected page with YAML frontmatter
4. Follow the SCHEMA rules (facts_only sections need citations, inferences need > [!note] Inference: markers)
"""
    if context:
        prompt += f"\n\n## Context\n\n{context[:2000]}\n\n(Truncated — see original source for full content)"
    return prompt


def _write_draft(
    title: str,
    frontmatter_dict: dict,
    content: str,
    source_path: Path,
    source_content_hash: str,
) -> tuple[Path, Path]:
    """Write a draft file and its provenance sidecar.

    Returns (draft_path, provenance_path).
    """
    drafts_dir = DRAFTS_DIR
    drafts_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize title for filename
    safe_title = title.replace("/", "-").replace("\\", "-").strip()
    draft_path = drafts_dir / f"{safe_title}.md"

    # Check if draft already exists
    counter = 1
    while draft_path.exists():
        draft_path = drafts_dir / f"{safe_title}_{counter}.md"
        counter += 1

    # Build frontmatter Post
    post = frontmatter.Post(content)
    for key, value in frontmatter_dict.items():
        post.metadata[key] = value

    # Write draft
    draft_path.write_text(frontmatter.dumps(post), encoding="utf-8")

    # Create and write provenance
    content_hash = hash_content(content)
    prov = create_provenance(
        page=safe_title,
        content_hash=content_hash,
        sources=[{
            "file": str(source_path.relative_to(SOURCES_DIR)) if source_path.is_relative_to(SOURCES_DIR) else source_path.name,
            "content_hash": source_content_hash,
            "sections_used": [],
        }],
    )
    prov_path = draft_path.with_suffix(draft_path.suffix + ".provenance.json")
    write_provenance(draft_path, prov)

    return draft_path, prov_path


def auto_ingest(
    source_path: Path,
    page_type: str = DEFAULT_PAGE_TYPE,
    system_prompt: Optional[str] = None,
    verbose: bool = True,
    retry_on_error: bool = True,
    extraction_mode: str = "standard",
) -> list[Path]:
    """Run the full auto-ingest pipeline on a source file.

    Args:
        source_path: Path to source file (.pdf, .md, .txt, etc.)
        page_type: Default page type ("concept" or "entity")
        system_prompt: Optional system prompt override
        verbose: Print progress messages
        retry_on_error: If False, skip retry loop on validation errors.
        extraction_mode: "standard" (full summary) or "gap" (fill gaps only).

    Returns:
        List of promoted page paths (may be empty if all failed).
    """
    schema = load_schema()

    # ── Step 1: Read source ──────────────────────────────────────────────────
    if verbose:
        print(f"  Reading source: {source_path}")

    try:
        source_text = read_source(source_path)
    except Exception as e:
        print(f"  ERROR reading source: {e}")
        return []

    source_type = classify_source_type(source_path)
    source_content_hash = hash_content(source_text)

    # Truncate source if very long (LLM context limits)
    MAX_SOURCE_CHARS = 100_000
    if len(source_text) > MAX_SOURCE_CHARS:
        if verbose:
            print(f"  Truncating source from {len(source_text):,} to {MAX_SOURCE_CHARS:,} chars")
        source_text = source_text[:MAX_SOURCE_CHARS]

    # ── Step 2: Build LLM prompt ─────────────────────────────────────────────
    if extraction_mode == "gap":
        # Gap-driven mode: first analyze gaps, then extract to fill them
        existing_context = _build_existing_context()

        if verbose:
            print(f"  Mode: gap-driven (analyzing gaps first)...")

        # Step 2a: Gap analysis
        gap_prompt = _build_gap_analysis_prompt(source_path.name, existing_context, source_text)
        try:
            gap_output = completion_with_retry(
                prompt=gap_prompt,
                system_prompt=system_prompt,
                max_tokens=4096,
            )
        except Exception as e:
            print(f"  ERROR: Gap analysis failed: {e}")
            return []

        if verbose:
            print(f"  Gap analysis: {len(gap_output):,} chars")

        # Step 2b: Extraction prompt for filling gaps
        full_prompt = _build_gap_extraction_prompt(
            source_path.name,
            page_type,
            schema,
            existing_context,
            gap_output,
            source_text,
        )
    else:
        # Standard mode: full summary extraction
        prompt = generate_extraction_prompt(
            source_name=source_path.name,
            page_type=page_type,
            schema=schema,
        )
        full_prompt = f"""{prompt}

## Source Material

Read the following source material and create the wiki page(s) described above.

---

{source_text}
"""

    # ── Step 3: Call LLM ─────────────────────────────────────────────────────
    if verbose:
        print(f"  Calling LLM (source: {source_path.name}, type: {source_type})...")

    try:
        llm_output = completion_with_retry(
            prompt=full_prompt,
            system_prompt=system_prompt,
            max_tokens=8192,
        )
    except Exception as e:
        print(f"  ERROR: LLM call failed: {e}")
        return []

    if verbose:
        token_est = count_tokens(full_prompt + llm_output)
        print(f"  LLM output: ~{token_est} tokens, {len(llm_output):,} chars")

    # ── Step 4: Parse response ───────────────────────────────────────────────
    if verbose:
        print("  Parsing LLM response...")

    try:
        pages = parse_multi_page_response(llm_output, page_type=page_type)
    except Exception as e:
        print(f"  ERROR parsing LLM response: {e}")
        return []

    if not pages:
        print("  ERROR: No valid pages found in LLM response")
        return []

    if verbose:
        print(f"  Detected {len(pages)} page(s) in LLM response")

    # ── Step 5–7: Write drafts, validate, retry, promote ──────────────────
    promoted_paths: list[Path] = []
    pending_titles = set()

    for i, (fm, content) in enumerate(pages):
        title = extract_page_title(fm, content, f"{source_path.stem}_{i+1}")
        page_type_from_fm = fm.get("type", page_type)
        if verbose:
            print(f"\n  Processing page {i+1}/{len(pages)}: {title}")

        # Write draft
        try:
            draft_path, prov_path = _write_draft(
                title=title,
                frontmatter_dict=fm,
                content=content,
                source_path=source_path,
                source_content_hash=source_content_hash,
            )
            if verbose:
                print(f"    Draft written: {draft_path.name}")
        except Exception as e:
            print(f"    ERROR writing draft: {e}")
            continue

        # Validate
        report = validate_draft(draft_path, schema=schema, wiki_dir=WIKI_DIR)

        if report.has_errors and retry_on_error:
            # Retry with correction prompt — but NOT for wikilink errors (those are warnings)
            error_msgs = [
                f"[{iss.code}] {iss.message}"
                for iss in report.issues
                if iss.severity == "ERROR" and iss.code != "BROKEN_LINK"
            ]
            retry_count = 0

            while report.has_errors and retry_count < MAX_RETRIES_PER_DRAFT:
                retry_count += 1
                if verbose:
                    print(f"    Retry {retry_count}/{MAX_RETRIES_PER_DRAFT} — {len(error_msgs)} error(s)")

                # Build correction prompt
                correction_prompt = _build_correction_prompt(title, error_msgs, source_text[:5000])
                try:
                    llm_retry = completion_with_retry(
                        prompt=correction_prompt,
                        system_prompt=system_prompt,
                        max_tokens=4096,
                    )
                except Exception as e:
                    if verbose:
                        print(f"    Retry {retry_count} failed: {e}")
                    break

                # Parse retry output
                retry_pages = parse_multi_page_response(llm_retry, page_type=page_type)
                if retry_pages:
                    # Use the first parsed page from retry
                    fm_retry, content_retry = retry_pages[0]
                    # Overwrite draft with corrected content
                    title_retry = extract_page_title(fm_retry, content_retry, title)
                    fm = fm_retry
                    content = content_retry

                    # Re-write corrected draft
                    draft_path, prov_path = _write_draft(
                        title=title_retry,
                        frontmatter_dict=fm_retry,
                        content=content_retry,
                        source_path=source_path,
                        source_content_hash=source_content_hash,
                    )

                    report = validate_draft(draft_path, schema=schema, wiki_dir=WIKI_DIR)
                    error_msgs = [f"[{iss.code}] {iss.message}" for iss in report.issues if iss.severity == "ERROR"]
                else:
                    break

            if report.has_errors:
                if verbose:
                    for iss in report.issues:
                        if iss.severity == "ERROR":
                            print(f"    ERROR: {iss.message}")
                continue  # Skip this page

        # Promote
        new_path = promote_draft(draft_path, schema=schema, wiki_dir=WIKI_DIR)
        if new_path:
            promoted_paths.append(new_path)
            pending_titles.add(new_path.stem)
            if verbose:
                print(f"    Promoted: {new_path.name}")
        else:
            if verbose:
                print(f"    Skipped: promotion returned None")

    # ── Step 8: Update state + health ───────────────────────────────────────
    if verbose:
        print("\n  Updating state and health...")

    state = generate_state()
    save_state(state)
    health = generate_health()
    save_health(health)

    # ── Step 9: Log operation ────────────────────────────────────────────────
    append_log(
        "auto-ingest",
        f"Source: {source_path.name}, Pages: {len(promoted_paths)}/{len(pages)}",
        {
            "Source type": source_type,
            "Pages generated": len(pages),
            "Pages promoted": len(promoted_paths),
            "Page titles": ", ".join(p.stem for p in promoted_paths),
        },
    )

    if verbose:
        print(f"\n  Done: {len(promoted_paths)} page(s) promoted")

    return promoted_paths


# ── CLI ──────────────────────────────────────────────────────────────────────


def main() -> None:
    """CLI: python scripts/auto_ingest.py <source> [--type concept]"""
    import argparse

    parser = argparse.ArgumentParser(description="LLM Knowledge Base v2 — Auto-Ingest")
    parser.add_argument("source", help="Source file path")
    parser.add_argument("--type", default="concept", help="Page type (default: concept)")
    parser.add_argument("--system", default=None, help="System prompt override")

    args = parser.parse_args()

    source_path = Path(args.source)
    if not source_path.exists():
        print(f"ERROR: Source file not found: {source_path}")
        sys.exit(1)

    print(f"\nAuto-ingest: {source_path.name}")
    print(f"{'='*60}")

    promoted = auto_ingest(
        source_path=source_path,
        page_type=args.type,
        system_prompt=args.system,
        verbose=True,
    )

    print(f"{'='*60}")
    print(f"Promoted: {len(promoted)} page(s)")
    if promoted:
        for p in promoted:
            print(f"  - {p.name}")


if __name__ == "__main__":
    main()