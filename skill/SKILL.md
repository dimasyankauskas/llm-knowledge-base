---
name: llm-wiki
description: Use when you need to add sources to a knowledge wiki, query what the wiki knows, or build a knowledge graph from documents. Works with any AI agent that reads SKILL.md files.
user-invocable: true
---

# LLM Wiki Skill

Add documents to a knowledge wiki, query the knowledge graph, and build structured interlinked concept pages. Works with plain language or automated pipelines.

## What This Skill Does

1. **Plan ingestion**: profile a source and get a concrete extraction plan for the active CLI agent
2. **Query**: ask a question and get graph-traversed context excerpts (for the active agent to synthesize)
3. **Link**: pages become typed graph nodes with relationship edges

## For Humans (Plain Language)

```bash
# Plan document ingestion for the active CLI agent
wiki agent-ingest /path/to/source.pdf --type article

# Ask the wiki a question — returns context only
wiki query "What does the wiki know about RAG?" --context-only

# Save the last query context as a concept draft page
wiki save-answer "RAG at Scale" --type concept
```

## For AI Agents (Automated)

### Ingestion Pipeline

```bash
# Step 1: Build an agent-first extraction plan
wiki agent-ingest /path/to/source.pdf --type article

# The pipeline:
# Source → Agent Plan → Agent Drafts → Validate → Promote → Link → Lint

# Forward wikilinks are warnings not errors — they're graph edges
# content_hash is auto-populated if missing
```

### Query Pipeline

```bash
# Skip expansion (keyword-only, fast)
wiki query "What is agentic UX?" --depth 2 --no-expand

# Show expanded queries (debug)
wiki query "What is agentic UX?" --expand-only

# Raw context only
wiki query "What is agentic UX?" --depth 2 --context-only

# Options:
# --depth N       : how many hops from seed pages (default: 2)
# --top-k N      : number of seed pages (default: 5)
# --json         : structured JSON output (context + traversal metadata)
# --context-only  : raw context output (same as default output)
```

The query pipeline: seed pages → BFS traversal → context assembly → print context.

### Validation

```bash
# Check wiki health
wiki health

# Lint rules (WARNING = acceptable, ERROR = must fix):
# BROKEN_LINK          : wikilink to nonexistent page (WARNING)
# MISSING_FRONTMATTER  : required field absent (ERROR)
# INVALID_TYPE         : type not in schema (ERROR)
# LOW_CONNECTIVITY     : fewer than 2 connections (WARNING)
# STALE_PAGE           : source changed since last hash (WARNING)
```

## Repository Structure

```
llm-wiki/
├── SCHEMA.yaml           # Page constitution
├── AGENTS.md             # Full agent instructions
├── skill/
│   └── SKILL.md         # This file — portable skill for any AI agent
├── scripts/
│   ├── cli.py           # wiki CLI entry point
│   ├── validate.py       # Draft validation
│   ├── lint.py          # Structural checks
│   ├── link.py          # Graph builder
│   ├── query.py         # Graph-traversal query (context-first)
│   └── ingest_folder.sh # Example: batch register a folder of sources
├── sources/              # Read-only source documents
└── wiki/                # Extracted knowledge base
    ├── concepts/        # Concept pages
    ├── drafts/           # Staging area
    └── timelines/        # Auto-generated timelines
```

## Page Types

| Type | Frontmatter | Sections |
|------|-------------|----------|
| `concept` | title, type, confidence, created, source_refs, content_hash | Definition, Key Properties, How It Works, Relationships, Open Questions, Sources |
| `entity` | title, type, entity_type, created, source_refs, content_hash | Overview, Contributions, Relationships, Sources |

## Typed Relationships

Use `[[Page]]:relation_type` in content or `related_concepts` in frontmatter:

```
implements    (weight: 3)
extends       (weight: 2)
contradicts   (weight: 3)
cites         (weight: 4)
prerequisite_of (weight: 2)
trades_off    (weight: 1)
derived_from  (weight: 2)
```

## Confidence Levels

```
HIGH   : Multiple independent sources agree (green)
MEDIUM : Single source, well-established (yellow)
LOW    : Inference or contested (red)
```

## Schema

All rules live in `SCHEMA.yaml` at repo root. It's the constitution for all pages. Read it before modifying wiki structure.
