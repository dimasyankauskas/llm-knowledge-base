---
name: llm-wiki
description: Use when you need to turn source documents into durable project memory, query what the wiki knows, or hand off grounded context between CLI agents. Works with any AI agent that reads SKILL.md files.
user-invocable: true
---

# LLM Wiki Skill

Turn source documents into durable project memory: schema-checked Markdown pages, typed links, provenance, health checks, and agent-ready context packs.

This skill is **agent-first** and **model-free**. The active CLI agent should do the reading, reasoning, and writing. The wiki provides the memory layer, validation rails, and graph context.

## When to Use This Skill

- You want to convert PDFs, docs, transcripts, or notes into a reusable knowledge base.
- You want a later CLI agent to inherit grounded context without rebuilding it from scratch.
- You want citations, provenance, and graph relationships instead of free-form notes.
- You want a public-friendly, git-versioned wiki rather than a hosted notebook surface.

## What This Skill Does

1. **Plan ingestion**: profile a source and give the active CLI agent a concrete extraction plan
2. **Query**: gather graph-traversed context excerpts for the active agent to synthesize
3. **Link**: turn pages into typed graph nodes with semantic edges
4. **Validate**: enforce schema, sections, citations, and connectivity
5. **Maintain**: surface stale pages, contradictions, thin pages, and missing links

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

### Core Operating Rule

- Use the active CLI agent for reasoning and writing.
- Use `wiki` for durable memory, validation, provenance, graph traversal, and health checks.
- Do not treat this wiki as a second chatbot.

### Ingestion Pipeline

```bash
# Step 1: Build an agent-first extraction plan
wiki agent-ingest /path/to/source.pdf --type article

# The pipeline:
# Source → Agent Plan → Agent Drafts → Validate → Promote → Link → Lint

# Forward wikilinks are warnings not errors — they're graph edges
# content_hash is auto-populated if missing
```

Recommended workflow:

1. Register and profile the source with `wiki agent-ingest`
2. Read the source and write atomic drafts into `wiki/drafts/`
3. Run `wiki validate`
4. Run `wiki link`
5. Run `wiki lint`
6. Promote only clean content

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

Use `wiki pack --json` when you need compact, agent-readable context without depending on provider credentials.

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

### NotebookLM vs This Wiki

- NotebookLM is a managed notebook for reading, asking questions, and summarizing inside the product.
- This wiki is for durable project memory that lives in files, git, and CLI workflows.
- If an agent can already talk to NotebookLM through MCP, that is fine for research.
- Use this wiki when you want the output to remain in your repo, stay inspectable, and be reusable by future agents.

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
