---
name: llm-wiki
description: Use when you need to add sources to a knowledge wiki, query what the wiki knows, or build a knowledge graph from documents. Works with any AI agent that reads SKILL.md files.
user-invocable: true
---

# LLM Wiki Skill

Add documents to a knowledge wiki, query the knowledge graph, and build structured interlinked concept pages — using plain language or automated pipelines.

## What This Skill Does

1. **Ingest** — drop a source (PDF, article, transcript) → get structured wiki pages
2. **Query** — ask questions against the knowledge graph
3. **Link** — pages become typed graph nodes with relationship edges

## For Humans (Plain Language)

```bash
# Ingest a document (fast mode — recommended)
wiki ingest --auto --no-retry /path/to/source.pdf --type concept

# Ingest with automatic retry (slower but self-corrects)
wiki ingest --auto /path/to/source.pdf --type concept

# Gap-driven ingestion (analyzes what's missing first)
wiki ingest --auto --mode gap /path/to/source.pdf --type concept

# Query the wiki
wiki query "What does the wiki know about RAG?"

# Save a useful answer
wiki save-answer "RAG at Scale" --type concept
```

## For AI Agents (Automated)

### LLM Setup

The wiki works with Ollama (local) or Anthropic Claude (cloud):

```bash
# Ollama — local, private, fast
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=qwen3.5:agentic

# Anthropic Claude — cloud
export ANTHROPIC_API_KEY=sk-ant-...
```

### Ingestion Pipeline

```bash
# Step 1: Ingest (recommended: --no-retry for trust-first extraction)
wiki ingest --auto --no-retry /path/to/source.pdf --type concept

# The pipeline:
# Source → LLM Extract → Parse → Validate → Promote → Link → Lint

# Forward wikilinks are warnings not errors — they're graph edges
# content_hash is auto-populated if missing
```

### Query Pipeline

```bash
# Query with graph traversal (BFS through typed edges)
wiki query "What is agentic UX?" --depth 2

# Options:
# --depth N   : how many hops from seed pages (default: 2)
# --top-k N  : number of seed pages (default: 5)
# --json     : structured JSON output
```

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
├── CLAUDE.md             # Full agent instructions
├── skill/
│   └── SKILL.md         # This file — portable skill for any AI agent
├── scripts/
│   ├── cli.py           # wiki CLI entry point
│   ├── auto_ingest.py   # Full ingestion pipeline
│   ├── llm_client.py    # Anthropic + Ollama abstraction
│   ├── validate.py       # Draft validation
│   ├── lint.py          # Structural checks
│   ├── link.py          # Graph builder
│   └── query.py         # Graph-traversal query
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

## Gap-Driven Extraction (InfraNodus Mode)

```bash
wiki ingest --auto --mode gap /path/to/source.pdf --type concept
```

Two-pass extraction:
1. Analyze existing wiki for structural gaps
2. Extract specifically to fill those gaps

Requires 2 LLM calls — slower but useful for systematic coverage.

## Schema

All rules live in `SCHEMA.yaml` at repo root — the constitution for all pages. Read it before modifying wiki structure.
