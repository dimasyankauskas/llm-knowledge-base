"""
LLM Knowledge Base v2 — CLAUDE.md Generator

Generates CLAUDE.md from SCHEMA.yaml so the agent's instructions
stay in sync with the schema automatically.

Usage:
    python scripts/generate_instructions.py
    wiki generate-instructions
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from schema import load_schema, get_page_type_config, get_validation_rules, get_confidence_levels, get_relation_types, get_extraction_config, get_contradiction_config, get_all_page_types, get_required_frontmatter, get_required_sections, get_section_rules  # type: ignore


def generate_claude_md(
    schema_path: Path | None = None,
    output_path: Path | None = None,
) -> str:
    """Generate CLAUDE.md content from SCHEMA.yaml.

    Args:
        schema_path: Path to SCHEMA.yaml (default: auto-detect)
        output_path: Path to write CLAUDE.md (default: None, just return string)

    Returns:
        The generated CLAUDE.md content as a string.
    """
    schema = load_schema(schema_path)
    project_root = schema_path.parent if schema_path else Path(__file__).parent.parent

    lines: list[str] = []

    # ── Header ──
    lines.append("# CLAUDE.md")
    lines.append("")
    lines.append("This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.")
    lines.append("")

    # ── Identity ──
    lines.append("## Identity")
    lines.append("")
    lines.append("You are the **Wiki Curator** for an LLM Knowledge Base — an LLM-native, self-organizing knowledge base.")
    lines.append("Your job is to read raw sources, extract knowledge, and write interlinked Obsidian Markdown pages")
    lines.append("that follow the schema rules below. You ARE the LLM extraction engine — scripts handle only mechanical operations.")
    lines.append("")

    # ── Bootstrap ──
    lines.append("## Bootstrap")
    lines.append("")
    lines.append("At the start of every session, read `wiki/_state.json` to get:")
    lines.append("- Schema version and page type inventory")
    lines.append("- Active pages with their types, confidence, and tags")
    lines.append("- Active contradictions needing resolution")
    lines.append("- Thin pages (fewer than 3 sections) needing expansion")
    lines.append("- Stale pages (source content has changed)")
    lines.append("")
    lines.append("Then read `wiki/_health.json` for lint status (errors, warnings).")
    lines.append("Resolve errors before any new content creation.")
    lines.append("")

    # ── Architecture ──
    lines.append("## Architecture")
    lines.append("")
    lines.append("Three-layer design where mutability decreases downward:")
    lines.append("")
    lines.append("| Layer | Location | Mutability |")
    lines.append("|-------|----------|------------|")
    lines.append("| Raw Sources | `sources/` | **Read-only** — never modify |")
    lines.append("| The Wiki | `wiki/` | AI-managed — create, update, link, lint |")
    lines.append("| The Schema | `SCHEMA.yaml` | Human-defined — constitutional rules |")
    lines.append("")
    lines.append("**`SCHEMA.yaml` is the constitution.** Read it before any wiki operation.")
    lines.append("")

    # ── Page Types ──
    lines.append("## Page Types")
    lines.append("")

    page_types = get_all_page_types(schema)
    for pt in page_types:
        config = get_page_type_config(schema, pt)
        lines.append(f"### {pt}")
        if config.get("auto_generated"):
            lines.append("Auto-generated. Do not edit manually.")
            lines.append("")
            continue

        fm_fields = get_required_frontmatter(schema, pt)
        sections = get_required_sections(schema, pt) if pt in ["concept", "entity"] else []
        rules = get_section_rules(schema, pt) if pt in ["concept"] else {}

        lines.append(f"**Required frontmatter:** {', '.join(fm_fields)}")
        if sections:
            lines.append(f"**Required sections:** {', '.join(sections)}")
        if rules:
            lines.append("**Section rules:**")
            for section, rule in rules.items():
                lines.append(f"- `{section}`: {rule}")
        if "min_outlinks" in config:
            lines.append(f"**Minimum outlinks:** {config['min_outlinks']}")
        if "citation_format" in config:
            lines.append(f"**Citation format:** `{config['citation_format']}`")
        lines.append("")

    # ── Confidence Levels ──
    lines.append("## Confidence Levels")
    lines.append("")

    levels = get_confidence_levels(schema)
    for level_name, level_data in levels.items():
        lines.append(f"- **{level_name}**: {level_data['description']} (color: {level_data['color']})")
    lines.append("")
    lines.append("Every factual claim must cite its confidence level in frontmatter.")
    lines.append("")

    # ── Relations ──
    lines.append("## Relation Types")
    lines.append("")
    lines.append("Use typed wikilinks to express relationships between concepts:")
    lines.append("")

    rels = get_relation_types(schema)
    weight_map = {
        "cites": 4, "contradicts": 3, "implements": 3, "extends": 2,
        "prerequisite_of": 2, "derived_from": 2, "trades_off": 1,
    }
    for rel in rels:
        w = weight_map.get(rel, 1)
        lines.append(f"- `[[Page]]:{rel}` (weight: {w})")
    lines.append("")
    lines.append("Syntax: `[[Target Page]]:relation_type` in content or `related_concepts: [[Page]]:type` in frontmatter.")
    lines.append("")

    # ── Extraction Rules ──
    lines.append("## Extraction Rules")
    lines.append("")

    ext_config = get_extraction_config(schema)
    if ext_config.get("merge_over_create"):
        lines.append("- **Merge over Create**: When a concept already exists, merge new information into it rather than creating a duplicate page.")
    if ext_config.get("atomic_notes"):
        lines.append("- **Atomic Notes**: One concept per page. Keep pages focused and interlinked.")
    if ext_config.get("entity_resolution"):
        lines.append("- **Entity Resolution**: Before creating a new entity page, check if it already exists under an alias or variant spelling.")
    if ext_config.get("write_mode"):
        lines.append(f"- **Write Mode**: {ext_config['write_mode']} — propose diffs, don't overwrite directly.")
    lines.append("")

    if "source_type_templates" in ext_config:
        lines.append("### Source Type Templates")
        lines.append("")
        for stype, sections in ext_config["source_type_templates"].items():
            lines.append(f"- **{stype}**: {', '.join(sections)}")
        lines.append("")

    # ── Validation Rules ──
    lines.append("## Validation Rules")
    lines.append("")

    rules = get_validation_rules(schema)
    for rule_name, rule_data in rules.items():
        severity = rule_data["severity"] if isinstance(rule_data, dict) else rule_data
        lines.append(f"- **{rule_name}** ({severity})")
    lines.append("")

    # ── Contradiction Handling ──
    lines.append("## Contradiction Handling")
    lines.append("")

    contr = get_contradiction_config(schema)
    lines.append("Never silently overwrite conflicting information.")
    lines.append(f"- Use `> [!{contr['callout_type']}] CONTRADICTION` callouts")
    lines.append(f"- Resolution uses `> [!{contr['resolution_callout']}] RESOLVED` callouts")
    lines.append(f"- Auto-downgrade confidence to **{contr['auto_downgrade_confidence']}**")
    lines.append(f"- Track in `wiki/indexes/{Path(contr['track_in']).name}`")
    if contr.get("require_counter_arguments"):
        lines.append("- HIGH/MEDIUM pages must include a `## Counter-Arguments & Data Gaps` section")
    lines.append("")

    # ── CLI Commands ──
    lines.append("## CLI Commands")
    lines.append("")
    lines.append("```bash")
    lines.append("# Full pipeline")
    lines.append("wiki ingest <source> --type <type>")
    lines.append("")
    lines.append("# Individual stages")
    lines.append("wiki extract <source> --type <type>    # Register source")
    lines.append("wiki validate                           # Validate drafts")
    lines.append("wiki link                               # Build graph")
    lines.append("wiki refine                             # Gap analysis")
    lines.append("wiki lint [--json]                      # Structural checks")
    lines.append("wiki consolidate                        # Merge + indexes")
    lines.append("")
    lines.append("# Queries & Inspection")
    lines.append("wiki log [-n 10]                        # View chronological journal")
    lines.append("wiki query \"question\" --depth 2 [--json]")
    lines.append("wiki save-answer \"Title\" --type concept # Save last query as draft")
    lines.append("wiki find --tag <tag> --confidence <level>")
    lines.append("wiki provenance <page>                  # Evidence chain")
    lines.append("wiki state                              # State summary")
    lines.append("wiki health                             # Health summary")
    lines.append("")
    lines.append("# Maintenance & Prompts")
    lines.append("wiki extract-prompt <source>            # Gen LLM prompt from SCHEMA")
    lines.append("wiki register <source> --type <type>    # Register only")
    lines.append("wiki check <source>                     # Dedup check")
    lines.append("wiki rebuild                            # Regenerate all")
    lines.append("wiki generate-instructions              # Regenerate this file")
    lines.append("```")
    lines.append("")

    # ── Key Conventions ──
    lines.append("## Key Conventions")
    lines.append("")
    lines.append("- **Wikilinks only**: Use `[[Page Name]]` for internal references, never `[text](path.md)` markdown links")
    lines.append("- **Atomic notes**: One concept per page. Merge into existing pages before creating new ones")
    lines.append("- **Source citations**: Every factual claim needs `[source: filename, §section]` or `source_refs` in frontmatter")
    lines.append("- **Confidence scoring**: `HIGH` (multiple independent sources), `MEDIUM` (single source, well-established), `LOW` (inference or contested)")
    lines.append("- **File naming**: Concept pages use Title Case (`Retrieval-Augmented Generation.md`), entity pages use canonical names, index pages prefixed with `_`")
    lines.append("- **Tags**: lowercase kebab-case with domain prefix (`domain/ai`, `topic/retrieval`, `entity/person`)")
    lines.append("")

    content = "\n".join(lines)

    if output_path:
        output_path.write_text(content, encoding="utf-8")

    return content


if __name__ == "__main__":
    output = Path(__file__).parent.parent / "CLAUDE.md"
    generate_claude_md(output_path=output)
    print(f"Generated: {output}")