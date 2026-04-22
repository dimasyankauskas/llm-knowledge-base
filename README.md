# LLM Knowledge Base

**Durable memory for AI agents and the people who work with them.**

LLM Knowledge Base turns source documents into a local, schema-checked Markdown wiki: cited concept pages, typed relationships, provenance, health checks, and agent-ready context packs. It is built for CLI-first work. Codex, Claude Code, Gemini CLI, or any other capable agent does the reasoning and writing; the wiki supplies the memory layer, validation rails, and graph retrieval.

This is not another chat history export. It is a project memory substrate you can inspect, version, query, and hand to the next agent without asking it to rediscover the same facts.

---

## Why This Exists

Most AI work evaporates. You upload the same PDFs, paste the same notes, explain the same context, and the next session starts cold.

Traditional RAG helps retrieve raw chunks, but it does not automatically build a durable understanding of a domain. Every question can become a fresh re-read.

This project takes a different path, inspired by [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f): compile knowledge once into a persistent wiki, then let future agents query the graph. Contradictions get flagged. Thin pages become visible. Provenance stays attached. Each useful answer can be saved back into the wiki, so the system gets better instead of merely longer.

Additional influences: [InfraNodus](https://infranodus.com) for gap-driven extraction, [Obsidian](https://obsidian.md) for the wikilink + local markdown format, and [LangChain](https://langchain.readthedocs.io) for graph-traversed retrieval patterns.

## What It Is

- **A local Markdown knowledge base** for sources, concepts, entities, timelines, and indexes.
- **A validation system** that enforces frontmatter, required sections, citations, confidence levels, and graph connectivity.
- **An agent context backend** that returns model-free JSON packs with relevant pages, claims, relationships, health status, and next actions.
- **A provenance layer** that tracks which source files support which claims.
- **A clean public template**: no bundled private data, no committed generated wiki content, no checked-in virtual environment.

## What It Is Not

- Not a hosted SaaS.
- Not a vector database wrapper.
- Not a replacement for a capable agent.
- Not a black-box ingestion pipeline that hides source quality.
- Not a place to commit private corpora unless you intentionally want those sources public.

## Who It Helps

- **AI CLI users** who want project memory that survives across sessions.
- **Researchers and product strategists** turning long documents into reusable concepts.
- **Engineering teams** that want grounded context packs instead of ad hoc notes.
- **Agents** that need cited facts, graph relationships, stale-page warnings, and missing-page cues before acting.

---

## Architecture

Three layers, ordered by decreasing mutability:

```
┌─────────────────────────────────────────────────────────────────┐
│  SCHEMA.yaml           │  Constitution — page types, relations,  │
│                        │  confidence rules, validation            │
├─────────────────────────────────────────────────────────────────┤
│  wiki/                 │  AI-managed workspace. Every page is a   │
│                        │  typed wikilink node with provenance     │
├─────────────────────────────────────────────────────────────────┤
│  sources/              │  Read-only ground truth. SHA-256         │
│                        │  registered, never edited               │
└─────────────────────────────────────────────────────────────────┘
```

**Page types:** `concept`, `entity`, `timeline`

**Relation types:** `implements`, `extends`, `contradicts`, `cites`, `prerequisite_of`, `trades_off`, `derived_from`

**Confidence levels:** `HIGH` (multiple independent sources), `MEDIUM` (single source), `LOW` (inference or contested)

---

## How It Works

### Agent-First Ingest Pipeline

```
wiki agent-ingest <source>
        │
        ▼
┌─────────────┐    ┌──────────────┐    ┌────────────┐    ┌──────────┐
│  REGISTER   │───▶│ ACTIVE AGENT │───▶│  VALIDATE  │───▶│   LINK   │
│  source     │    │  writes      │    │  promote   │    │  graph   │
│  SHA-256    │    │  draft pages │    │  if zero   │    │  edges   │
│  manifest   │    │  with schema │    │  errors    │    │  from    │
│             │    │  frontmatter │    │            │    │  wikilinks
└─────────────┘    └──────────────┘    └────────────┘    └──────────┘
                                                              │
                                                              ▼
                                                      ┌────────────┐
                                                      │   LINT     │
                                                      │  12 checks │
                                                      │  0 errors  │
                                                      │  → publish │
                                                      └────────────┘
```

`wiki agent-ingest` gives the current CLI agent a source profile, merge candidates, schema contract, citation format, and exact validation commands.

### Query Pipeline

```bash
wiki query "What's the relationship between agentic AI and edge computing?" --depth 2
```

Two operations run in sequence:

1. **Graph traversal** — BFS from seed pages through typed edges, assembling a sourced context block (up to 50K chars)
2. **Context output** — the wiki prints the assembled context (or returns it as JSON) for the active agent to use

```bash
# Raw context only
wiki query "What is agentic AI?" --depth 2 --context-only

# JSON output (context + traversal metadata)
wiki query "What is agentic AI?" --depth 2 --json
```

### The Compounding Loop

```bash
wiki save-answer "Agentic AI and Edge Computing" --type concept
```

The last query context persists as a schema-compliant draft page you can refine and promote. This closes the loop — useful work-products become durable wiki memory.

---

## New Version: Agent-First by Default

This version is intentionally **model-free**.

If you are already working inside Codex, Claude Code, Gemini CLI, or another strong AI CLI, use the active agent to read and write. Use the wiki for durable memory, validation, provenance, graph context, and quality checks.

See `ABOUT.md` for the product philosophy and public-repo policy.

## Setup

```bash
git clone https://github.com/dimasyankauskas/llm-knowledge-base.git
cd llm-knowledge-base
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

This repository intentionally performs **no external model calls**. Use your active CLI agent for reading, reasoning, and writing.

> [!note]
> The CLI entry point is `wiki`. After `pip install -e .`, run `wiki ingest`, `wiki query`, etc. directly.

---

## Quick Start

```bash
# 1. Create a model-free ingestion plan for the active CLI agent
wiki agent-ingest sources/articles/my-source.md --type article

# 2. The active agent writes atomic pages into wiki/drafts/
#    Then validate and promote clean drafts
wiki validate
wiki rebuild

# 3. Ask for model-free context any future agent can use
wiki pack "What does the wiki know about retrieval-augmented generation?" --json

# 4. Inspect the graph
wiki state        # page inventory, contradictions, thin pages
wiki health      # lint errors and warnings
```

### Full CLI Reference

| Command | Description |
|---------|-------------|
| `wiki agent-ingest <source>` | Model-free ingestion plan for the active CLI agent |
| `wiki ingest <source>` | Register source + rebuild graph + health |
| `wiki query "question" --depth 2` | Graph-traversed query (context-first; no model calls) |
| `wiki query "question" --depth 2 --no-expand` | Skip expansion (keyword-only) |
| `wiki query "question" --expand-only` | Show expanded queries (debug) |
| `wiki query "question" --context-only` | Raw context output (same as default output) |
| `wiki pack "task or question" --json` | Agent-ready context pack with pages, claims, health, warnings, and next actions |
| `wiki triage --json` | Prioritized maintenance queue for stale pages, missing pages, contradictions, and errors |
| `wiki scaffold "Missing Page"` | Create a schema-valid draft stub for a missing page |
| `wiki draft case-study --topic "Topic"` | Assemble a cited draft artifact from existing wiki context |
| `wiki save-answer "Title" --type concept` | Persist last query as draft |
| `wiki validate` | Promote zero-error drafts |
| `wiki link` | Build typed relationship graph |
| `wiki lint` | 12 structural checks |
| `wiki consolidate` | Merge duplicates, regenerate indexes |
| `wiki find --tag domain/ai --confidence HIGH` | Filter by metadata |
| `wiki provenance <page>` | Evidence chain for a page |

---

## Key Design Decisions

### Why typed wikilinks?

Most wikis treat `[[links]]` as navigation. This project treats them as **graph edges with semantics**:

```
[[Agentic AI]]:implements
[[Local AI]]:extends
[[UX Design Patterns]]:implements
```

The type determines traversal weight. A `cites` edge (weight 4) contributes more context than a `trades_off` edge (weight 1). Queries follow semantic direction, not just proximity.

### Why schema-first?

`SCHEMA.yaml` is the constitution. Every script reads it — page types, required fields, validation rules, relation weights, confidence definitions. Change the schema, the entire pipeline adapts. No hardcoded assumptions.

### Why provenance sidecars?

```json
{
  "page": "Agentic AI",
  "content_hash": "e6f4cba0f587fe02",
  "sources": [
    {
      "file": "example-research-report.md",
      "content_hash": "abc123",
      "sections_used": ["The Paradigm Shift to Agentic Autonomy"]
    }
  ],
  "claims": [
    {
      "id": "claim-1",
      "text": "Agentic AI executes multi-step workflows without continuous human input",
      "type": "fact",
      "sources": ["example-research-report.md"],
      "corroborated": true,
      "last_verified": "2026-04-20"
    }
  ]
}
```

Every claim traces to its source file and section. Staleness detection compares `content_hash` against the live source — if the source changed, the page gets flagged.

### Why confidence levels?

Knowledge quality is explicit, not implicit. `HIGH` pages (multiple independent sources) carry different weight in synthesis than `LOW` pages (single inference). When contradictions surface, confidence auto-downgrades to `LOW` and the conflict gets tracked in `_contradictions.md`.

---

## Multi-Wiki Architecture

Each knowledge domain gets its own wiki instance — a standalone clone with a customized `SCHEMA.yaml`. The schema is the constitution: change it, and the entire pipeline adapts. A research wiki can have different page types, confidence thresholds, and relation weights than a project-tracking wiki, while sharing the same extraction engine.

```
wikis/
├── _template/          # Base template — clone this for new instances
│   ├── SCHEMA.yaml     # Default schema (customize per domain)
│   ├── scripts/        # Shared extraction engine
│   ├── sources/        # Domain-specific raw sources
│   └── wiki/           # Domain-specific extracted knowledge
│
├── example-project/    # Example: project-specific wiki
├── research/           # Example: academic research wiki
└── notes/              # Example: personal notes wiki
```

### Creating a New Wiki Instance

```bash
# 1. Copy the template
cp -r wikis/_template wikis/<name>

# 2. Initialize as its own repo
cd wikis/<name> && rm -rf .git && git init && git add -A && git commit -m "init: <name> wiki"

# 3. Customize SCHEMA.yaml for your domain
#    — Add/remove page types, relation types, confidence levels
#    — Adjust validation rules, section requirements, citation formats

# 4. Set up Python environment
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && pip install -e .

# 5. Plan your first agent-led ingest
wiki agent-ingest sources/articles/your-source.md --type article
```

Each instance is independent: its own git history, its own sources, its own wiki graph. Cross-wiki linking isn't supported — each wiki is a self-contained knowledge domain.

### Customizing SCHEMA.yaml

| Section | What it controls |
|---------|-----------------|
| `page_types` | Define domain-specific page types (e.g., `project`, `decision`, `meeting`) |
| `confidence_levels` | Adjust thresholds or add levels (e.g., `VERIFIED` for audited claims) |
| `relation_types` | Add domain-specific edges (e.g., `blocks`, `depends_on`, `supersedes`) |
| `validation` | Tune severity levels, adjust `min_outlinks`, set `threshold_days` |
| `extraction.source_type_templates` | Define section templates for new source types |

---

## Repository Structure

```
llm-knowledge-base/
├── SCHEMA.yaml              # Page schema (constitution)
├── requirements.txt
├── pyproject.toml
│
├── scripts/
│   ├── cli.py               # Unified CLI entry point (wiki command)
│   ├── extract.py           # Source registration + SHA-256 dedup
│   ├── ingest_folder.sh     # Example: batch register a folder of sources
│   ├── validate.py          # Draft validation + promotion
│   ├── link.py              # Typed graph builder
│   ├── lint.py              # 12 structural checks
│   ├── consolidate.py       # Duplicate merge + index generation
│   ├── query.py             # Graph traversal + source/page context assembly
│   ├── refine.py            # Gap analysis + contradiction detection
│   ├── provenance.py        # Sidecar CRUD + staleness detection
│   ├── state.py             # _state.json generator
│   ├── schema.py            # SCHEMA.yaml accessor functions
│   └── utils.py             # Paths, hashing, wikilink parsing
│
├── sources/                  # Read-only source documents
│   ├── manifest.json         # SHA-256 registry (generated locally; do not commit)
│   ├── articles/
│   ├── papers/
│   ├── transcripts/
│   └── code-docs/
│
├── wiki/                     # AI-managed knowledge base
│   ├── _state.json          # Generated locally; ignored by git
│   ├── concepts/            # Extracted concept pages
│   ├── drafts/              # Staging: must pass validation to promote
│   └── timelines/           # Auto-generated from dated events
│
└── tests/                   # 14 test modules, 200+ tests
```

## Validation Rules

12 structural checks. ERROR means broken state — fix before committing:

| Check | Severity | Description |
|-------|----------|-------------|
| `missing_frontmatter` | ERROR | Required field absent |
| `invalid_type` | ERROR | `type` not in schema |
| `duplicate_concept` | ERROR | Two pages with same title |
| `broken_links` | WARNING | `[[Page]]` to nonexistent page |
| `orphan_pages` | WARNING | No inlinks and no outlinks |
| `no_sources` | WARNING | `source_refs` empty |
| `low_connectivity` | WARNING | Fewer than `min_outlinks` connections |
| `stale_page` | WARNING | Source content changed since last hash |
| `unresolved_contradiction` | WARNING | `CONTRADICTION` callout without resolution |
| `unmarked_inference` | WARNING | `facts_only` section has unsourced claim |
| `missing_content_hash` | WARNING | No hash in frontmatter |
| `missing_counter_args` | WARNING | HIGH/MEDIUM page without counter-arguments section |

Forward wikilinks (links to pages that don't exist yet) are **warnings, not errors**. The link registers as a graph edge — the target page can be created later.

---

## For AI Agents

The wiki is designed for agent operation, not hand-maintained note gardening. The important commands do not require provider credentials:

```bash
# Agent-first source processing plan (model-free)
wiki agent-ingest ./sources/articles/source.md --json

# Agent-ready context pack (model-free JSON)
wiki pack "What is agentic AI?" --depth 2 --json

# Prioritized maintenance queue
wiki triage --json

# Create schema-valid drafts from graph gaps or existing context
wiki scaffold "Product Strategy" --type concept
wiki draft brief --topic "Agentic UX Strategy" --json

# Persist last query context as a new draft page
wiki save-answer "Agentic AI Product Strategy — 2026 Synthesis" --type concept
```

For agents and CLIs that already have their own model, prefer `wiki agent-ingest` for new sources and `wiki pack --json` for existing knowledge. These commands return source metadata, merge candidates, relevant pages, citation-backed claims, graph relationships, health status, stale pages, missing pages, contradictions, and suggested next actions without requiring any provider credentials.

Use `wiki query` when you want graph-traversed context assembled for the active agent:

```bash
wiki query "What is agentic AI?" --depth 2 --context-only
wiki query "What is agentic AI?" --expand-only
```

The `wiki query` command:
1. Scores all pages by keyword overlap with the query
2. BFS traversal from seed pages through typed edges
3. Assembles a context block (max 50K chars)
4. Saves the context to `_last_query.json` for `save-answer` to persist

The compounding loop: ingest → query → save → the wiki grows richer with every cycle.

---

## Dependencies

```
python-frontmatter>=1.1.0    # YAML frontmatter parsing
pyyaml>=6.0                  # SCHEMA.yaml loading
rich>=13.9                   # Terminal formatting
pymupdf>=1.25.0              # PDF reading
```

```bash
pip install -r requirements.txt
```

---

## Test Suite

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

Tests cover every pipeline stage: schema loading, frontmatter validation, wikilink parsing, provenance tracking, graph building, lint checks, query traversal, CLI commands, and pipeline integration.
