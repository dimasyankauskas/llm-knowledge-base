# LLM Knowledge Base

**A knowledge base that compounds.** Drop in raw sources — papers, articles, transcripts — and get structured, interlinked concept pages with cited facts and typed relationships. Your active CLI agent can handle extraction; the wiki provides durable memory, schema rails, provenance, graph retrieval, and quality checks.

---

## Why This Exists

Traditional RAG retrieves from raw documents every time you ask a question. Nothing builds up. Each query re-derives knowledge from scratch, and the LLM has no memory of what it already processed.

This project takes a different approach, inspired by [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f): knowledge gets compiled once into a persistent wiki, and queries traverse the pre-built graph. In a CLI-first workflow, the active agent is the extraction engine. Optional external models are automation helpers for unattended ingestion. Every source you add makes the whole wiki smarter. Contradictions get flagged. Connections accumulate. The compounding loop — source → agent extraction → wiki pages → context packs → better agent work — means each session can build durable knowledge instead of another disposable chat transcript.

Additional influences: [InfraNodus](https://infranodus.com) for gap-driven extraction, [Obsidian](https://obsidian.md) for the wikilink + local markdown format, and [LangChain](https://langchain.readthedocs.io) for graph-traversed retrieval patterns.

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

`wiki agent-ingest` does not call another model. It gives the current CLI agent a source profile, merge candidates, schema contract, citation format, and exact validation commands. Use `wiki ingest --auto` only when you want unattended model-powered extraction.

### Query Pipeline

```bash
wiki query "What's the relationship between agentic AI and edge computing?" --depth 2
```

Two operations run in sequence:

1. **Graph traversal** — BFS from seed pages through typed edges, assembling a sourced context block (up to 50K chars)
2. **LLM synthesis** — the configured LLM produces a structured, cited answer using only wiki pages as source material

Every claim in the synthesized answer traces back to an ingested document. No hallucination from training data.

```bash
# Raw context only (skip LLM call, faster)
wiki query "What is agentic AI?" --depth 2 --context-only

# JSON output (includes synthesized answer)
wiki query "What is agentic AI?" --depth 2 --json
```

### The Compounding Loop

```bash
wiki save-answer "Agentic AI and Edge Computing" --type concept
```

The synthesized answer persists as a schema-compliant draft page. This closes the loop — every query can produce new knowledge that becomes part of the graph.

```
Sources → Ingest → Wiki Pages → Query → LLM Synthesis → Save Answer → Wiki Pages
                                    ↑                                              |
                                    └──────────── The loop compounds ──────────────┘
```

---

## New Version: Agent-First by Default

This version is intentionally **model-optional**.

If you are already working inside Codex, Claude Code, Gemini CLI, or another strong AI CLI, do not make the wiki call a second model by default. Use the active agent to read and write; use the wiki for durable memory, validation, provenance, graph context, and quality checks.

See `ABOUT.md` for the product philosophy and public-repo policy.

## Setup

```bash
git clone https://github.com/dimasyankauskas/llm-knowledge-base.git
cd llm-knowledge-base
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### Optional LLM Configuration

Provider credentials are not required for the agent-first workflow (`agent-ingest`, `pack`, `triage`, `scaffold`, `validate`, `rebuild`, `quality`, `coverage`). Configure a model only for unattended commands such as `wiki ingest --auto` or `wiki query` without `--context-only`.

#### Ollama (local, recommended for privacy)

```bash
# Install: https://ollama.com
ollama pull qwen3.5:agentic

export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=qwen3.5:agentic
```

#### Anthropic Claude (cloud)

```bash
export ANTHROPIC_API_KEY=<your-anthropic-api-key>
```

#### OpenAI-compatible (Groq, LM Studio, Perplexity, etc.)

```bash
export OLLAMA_BASE_URL=https://api.groq.com/openai/v1
export OLLAMA_MODEL=llama-3.1-70b-versatile
export OLLAMA_API_KEY=<your-openai-compatible-api-key>
```

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
| `wiki ingest <source> --auto --no-retry` | Optional unattended model extraction |
| `wiki ingest <source> --auto` | Optional extraction with retry correction |
| `wiki ingest <source> --auto --mode gap` | Gap-driven extraction (2 LLM calls) |
| `wiki query "question" --depth 2` | Graph-traversed query with LLM synthesis |
| `wiki query "question" --depth 2 --no-expand` | Skip expansion (keyword-only) |
| `wiki query "question" --expand-only` | Show expanded queries (debug) |
| `wiki query "question" --context-only` | Raw context output (no LLM call) |
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

# 5. Ingest your first source
wiki ingest sources/your-source.md --auto --no-retry
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
├── CLAUDE.md                # AI agent instructions
├── requirements.txt
├── pyproject.toml
│
├── scripts/
│   ├── cli.py               # Unified CLI entry point (wiki command)
│   ├── auto_ingest.py       # Full ingestion pipeline
│   ├── llm_client.py        # LLM provider abstraction (Anthropic + Ollama)
│   ├── extract.py           # Source registration + SHA-256 dedup
│   ├── validate.py          # Draft validation + promotion
│   ├── link.py              # Typed graph builder
│   ├── lint.py              # 12 structural checks
│   ├── consolidate.py       # Duplicate merge + index generation
│   ├── query.py             # Graph traversal + LLM synthesis
│   ├── refine.py            # Gap analysis + contradiction detection
│   ├── provenance.py        # Sidecar CRUD + staleness detection
│   ├── state.py             # _state.json generator
│   ├── schema.py            # SCHEMA.yaml accessor functions
│   └── utils.py             # Paths, hashing, wikilink parsing
│
├── sources/                  # Read-only source documents
│   ├── manifest.json         # SHA-256 registry
│   ├── article/
│   ├── paper/
│   ├── transcript/
│   └── code-doc/
│
├── wiki/                     # AI-managed knowledge base
│   ├── _state.json          # Page inventory, health, contradictions
│   ├── concepts/            # Extracted concept pages
│   ├── drafts/              # Staging: must pass validation to promote
│   └── timelines/           # Auto-generated from dated events
│
└── tests/                   # 14 test modules, 200+ tests
```

---

## LLM Provider Configuration

```python
# scripts/llm_client.py — provider detection order:
1. OLLAMA_BASE_URL env var  →  OpenAI-compatible (Ollama, LM Studio, Groq, etc.)
2. ANTHROPIC_BASE_URL env var  →  OpenAI-compatible (routes through ANTHROPIC_BASE_URL)
3. else  →  Anthropic direct (requires ANTHROPIC_API_KEY)
```

Provider detection is automatic. Set one environment variable and the right client kicks in.

| Provider | Env vars needed | SDK |
|----------|----------------|-----|
| Ollama | `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | `openai` |
| Anthropic direct | `ANTHROPIC_API_KEY` | `anthropic` |
| Groq | `OLLAMA_BASE_URL`, `OLLAMA_API_KEY`, `OLLAMA_MODEL` | `openai` |
| LM Studio | `OLLAMA_BASE_URL` (localhost), `OLLAMA_MODEL` | `openai` |
| OpenAI direct | `ANTHROPIC_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_API_KEY` | `openai` |

---

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

The wiki is designed for LLM agent operation, not manual curation. External agents can use it as a knowledge backend:

```bash
# Query with LLM synthesis — returns a structured, cited answer
wiki query "What's the current state of agentic AI product strategy?" --depth 2

# Skip expansion (keyword-only, fast)
wiki query "What is agentic AI?" --depth 2 --no-expand

# Show expanded queries (debug)
wiki query "What is agentic AI?" --expand-only

# Raw context only (for agents that synthesize themselves)
wiki query "What is agentic AI?" --depth 2 --context-only

# Agent-ready context pack (model-free JSON)
wiki pack "What is agentic AI?" --depth 2 --json

# Agent-first source processing plan (model-free)
wiki agent-ingest ./sources/articles/source.md --json

# Prioritized maintenance queue
wiki triage --json

# Create schema-valid drafts from graph gaps or existing context
wiki scaffold "Product Strategy" --type concept
wiki draft brief --topic "Agentic UX Strategy" --json

# Persist a synthesized answer as a new wiki page
wiki save-answer "Agentic AI Product Strategy — 2026 Synthesis" --type concept
```

For agents and CLIs that already have their own model, prefer `wiki agent-ingest` for new sources and `wiki pack --json` for existing knowledge. These commands return source metadata, merge candidates, relevant pages, citation-backed claims, graph relationships, health status, stale pages, missing pages, contradictions, and suggested next actions without requiring any provider credentials.

The `wiki query` command:
1. Scores all pages by keyword overlap with the query
2. BFS traversal from seed pages through typed edges
3. Assembles a context block (max 50K chars)
4. Calls the configured LLM to synthesize a structured answer with citations
5. Saves the answer to `_last_query.json` for `save-answer` to persist

The compounding loop: ingest → query → synthesize → save → the wiki grows richer with every cycle.

---

## Dependencies

```
python-frontmatter>=1.1.0    # YAML frontmatter parsing
pyyaml>=6.0                  # SCHEMA.yaml loading
rich>=13.9                   # Terminal formatting
pymupdf>=1.25.0              # PDF reading

# Optional (choose one or both):
openai>=1.0                  # Ollama + OpenAI-compatible APIs
anthropic>=0.96              # Anthropic Claude direct
```

```bash
# Core only
pip install -r requirements.txt

# With Ollama support
pip install -r requirements.txt openai

# With Anthropic support
pip install -r requirements.txt anthropic
```

---

## Test Suite

```bash
python -m pytest tests/ -v
```

14 test modules covering every pipeline stage: schema loading, frontmatter validation, wikilink parsing, provenance tracking, graph building, lint checks, query traversal, CLI commands, and full pipeline integration.
