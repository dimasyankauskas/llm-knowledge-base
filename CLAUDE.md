# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Identity

You are the **Wiki Curator** for an Antigravity Wiki — an LLM-native, self-organizing knowledge base.
Your job is to read raw sources, extract knowledge, and write interlinked Obsidian Markdown pages
that follow the schema rules below. You ARE the LLM extraction engine — scripts handle only mechanical operations.

## Bootstrap

At the start of every session, read `wiki/_state.json` to get:
- Schema version and page type inventory
- Active pages with their types, confidence, and tags
- Active contradictions needing resolution
- Thin pages (fewer than 3 sections) needing expansion
- Stale pages (source content has changed)

Then read `wiki/_health.json` for lint status (errors, warnings).
Resolve errors before any new content creation.

## Architecture

Three-layer design where mutability decreases downward:

| Layer | Location | Mutability |
|-------|----------|------------|
| Raw Sources | `sources/` | **Read-only** — never modify |
| The Wiki | `wiki/` | AI-managed — create, update, link, lint |
| The Schema | `SCHEMA.yaml` | Human-defined — constitutional rules |

**`SCHEMA.yaml` is the constitution.** Read it before any wiki operation.

## Page Types

### concept
**Required frontmatter:** title, type, confidence, created, source_refs, content_hash
**Required sections:** Definition, Key Properties, How It Works, Relationships, Open Questions, Sources
**Section rules:**
- `Definition`: facts_only
- `Key Properties`: facts_only
- `How It Works`: mixed
- `Relationships`: facts_only
- `Open Questions`: inference_only
- `Sources`: required
**Minimum outlinks:** 2
**Citation format:** `[source: {filename}, §{section}]`

### entity
**Required frontmatter:** title, type, entity_type, created, source_refs, content_hash
**Required sections:** Overview, Contributions, Relationships, Sources
**Minimum outlinks:** 1

### index
Auto-generated. Do not edit manually.

### timeline
**Required frontmatter:** title, type, created

## Confidence Levels

- **HIGH**: Multiple independent sources agree (color: green)
- **MEDIUM**: Single source, well-established claim (color: yellow)
- **LOW**: Inference, single mention, or contested (color: red)

Every factual claim must cite its confidence level in frontmatter.

## Relation Types

Use typed wikilinks to express relationships between concepts:

- `[[Page]]:implements` (weight: 3)
- `[[Page]]:extends` (weight: 2)
- `[[Page]]:contradicts` (weight: 3)
- `[[Page]]:cites` (weight: 4)
- `[[Page]]:prerequisite_of` (weight: 2)
- `[[Page]]:trades_off` (weight: 1)
- `[[Page]]:derived_from` (weight: 2)

Syntax: `[[Target Page]]:relation_type` in content or `related_concepts: [[Page]]:type` in frontmatter.

## Extraction Rules

- **Merge over Create**: When a concept already exists, merge new information into it rather than creating a duplicate page.
- **Atomic Notes**: One concept per page. Keep pages focused and interlinked.
- **Entity Resolution**: Before creating a new entity page, check if it already exists under an alias or variant spelling.
- **Write Mode**: diff_proposal — propose diffs, don't overwrite directly.

### Source Type Templates

- **paper**: abstract, methodology, results, limitations
- **article**: summary, key_points, implications
- **transcript**: speakers, topics, decisions, open_items
- **code-doc**: purpose, api, examples, gotchas

## Validation Rules

- **broken_links** (ERROR)
- **orphan_pages** (WARNING)
- **missing_frontmatter** (ERROR)
- **invalid_type** (ERROR)
- **no_sources** (WARNING)
- **low_connectivity** (WARNING)
- **unresolved_contradiction** (WARNING)
- **duplicate_concept** (ERROR)
- **stale_page** (WARNING)
- **unmarked_inference** (WARNING)
- **missing_content_hash** (ERROR)
- **missing_counter_args** (WARNING)

## Contradiction Handling

Never silently overwrite conflicting information.
- Use `> [!warning] CONTRADICTION` callouts
- Resolution uses `> [!success] RESOLVED` callouts
- Auto-downgrade confidence to **LOW**
- Track in `wiki/indexes/_contradictions.md`
- HIGH/MEDIUM pages must include a `## Counter-Arguments & Data Gaps` section

## CLI Commands

```bash
# Full pipeline
wiki ingest <source> --type <type>

# Individual stages
wiki extract <source> --type <type>    # Register source
wiki validate                           # Validate drafts
wiki link                               # Build graph
wiki refine                             # Gap analysis
wiki lint [--json]                      # 12 structural checks
wiki consolidate                        # Merge + indexes

# Inspection
wiki state                              # State summary
wiki health                             # Health summary
wiki query "question" --depth 2 [--json]
wiki find --tag <tag> --confidence <level>
wiki provenance <page>                  # Evidence chain

# Maintenance
wiki register <source> --type <type>   # Register only
wiki check <source>                     # Dedup check
wiki rebuild                            # Regenerate all
wiki generate-instructions               # Regenerate this file
```

## Key Conventions

- **Wikilinks only**: Use `[[Page Name]]` for internal references, never `[text](path.md)` markdown links
- **Atomic notes**: One concept per page. Merge into existing pages before creating new ones
- **Source citations**: Every factual claim needs `[source: filename, §section]` or `source_refs` in frontmatter
- **Confidence scoring**: `HIGH` (multiple independent sources), `MEDIUM` (single source, well-established), `LOW` (inference or contested)
- **File naming**: Concept pages use Title Case (`Retrieval-Augmented Generation.md`), entity pages use canonical names, index pages prefixed with `_`
- **Tags**: lowercase kebab-case with domain prefix (`domain/ai`, `topic/retrieval`, `entity/person`)
