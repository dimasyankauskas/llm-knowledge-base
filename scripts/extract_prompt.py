"""
Antigravity Wiki v2 — Extract Prompt Generator

Generates a structured LLM prompt from SCHEMA.yaml for creating
new wiki pages. Does NOT auto-generate content — produces a template
that an operator pastes into a chat session.

Usage:
    wiki extract-prompt <source> --type concept
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from schema import (
    get_required_frontmatter,
    get_required_sections,
    get_section_rules,
    load_schema,
)


def generate_extraction_prompt(
    source_name: str,
    page_type: str = "concept",
    schema: dict | None = None,
) -> str:
    """Generate a structured prompt for an LLM to create a wiki page.

    Reads required_frontmatter, required_sections, section_rules,
    and citation_format from SCHEMA.yaml.

    Returns a ready-to-paste markdown prompt.
    """
    if schema is None:
        schema = load_schema()

    required_fm = get_required_frontmatter(schema, page_type)
    required_sections = get_required_sections(schema, page_type)
    section_rules = get_section_rules(schema, page_type)

    # Get citation format
    page_config = schema.get("page_types", {}).get(page_type, {})
    citation_format = page_config.get("citation_format", "[source: {filename}, §{section}]")

    # Build section instructions
    section_lines: list[str] = []
    for section in required_sections:
        rule = section_rules.get(section, "mixed")
        if rule == "facts_only":
            guidance = "FACTS ONLY — every claim must have an inline citation"
        elif rule == "inference_only":
            guidance = "INFERENCE — mark speculative claims with > [!note] Inference:"
        elif rule == "required":
            guidance = "REQUIRED — list all source citations used"
        else:
            guidance = "MIXED — facts need citations, inferences need > [!note] Inference: markers"
        section_lines.append(f"## {section}\n   Rule: {guidance}")

    sections_block = "\n".join(section_lines)

    prompt = f"""---
You are a **Wiki Curator**. Read the source material and create a wiki page.

## Page Configuration

- **Page type**: `{page_type}`
- **Source file**: `{source_name}`
- **Citation format**: `{citation_format}`

## Required Frontmatter

```yaml
{chr(10).join(f'{field}: # FILL IN' for field in required_fm)}
```

## Required Sections (in order)

{sections_block}

## Rules

1. **Every factual claim** in a `facts_only` section MUST have an inline citation:
   `{citation_format.replace('{filename}', source_name)}`
2. **Inferences and speculation** must be explicitly marked:
   `> [!note] Inference: Your speculative claim here`
3. **Use wikilinks** `[[Page Name]]` to connect to existing concepts
4. **Typed relations** in Relationships section use format:
   `- [[Target Page]]:relation_type` where relation_type is one of:
   `implements`, `extends`, `contradicts`, `cites`, `prerequisite_of`, `trades_off`, `derived_from`
5. **Confidence levels**: HIGH (multiple sources agree), MEDIUM (single well-established source), LOW (inference/contested)
6. **content_hash**: Will be auto-generated — leave blank or set to `TBD`

## Output Format

Produce a complete markdown file with YAML frontmatter (delimited by `---`)
followed by all required sections populated from the source material.

Save the file to `wiki/drafts/` and run `wiki validate` to check and promote.
---"""

    return prompt


def main() -> None:
    """CLI: python scripts/extract_prompt.py <source> [--type concept]"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate structured LLM prompt for wiki page creation",
    )
    parser.add_argument("source", help="Source filename")
    parser.add_argument("--type", default="concept", help="Page type (default: concept)")

    args = parser.parse_args()
    schema = load_schema()
    prompt = generate_extraction_prompt(
        source_name=args.source,
        page_type=args.type,
        schema=schema,
    )
    print(prompt)


if __name__ == "__main__":
    main()
