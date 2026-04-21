# LLM Knowledge Base

**A knowledge base that compounds.** Drop in raw sources — papers, articles, transcripts — and get structured, interlinked concept pages with cited facts and typed relationships. The LLM handles extraction; Python scripts handle verification.

---

## Why This Exists

Traditional RAG retrieves from raw documents every time you ask a question. Nothing builds up. Each query re-derives knowledge from scratch, and the LLM has no memory of what it already processed.

This project takes a different approach, inspired by [Karpathy's LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f): the LLM compiles knowledge once at ingest time, writes it into a persistent wiki, and queries traverse the pre-built graph. Every source you add makes the whole wiki smarter. Contradictions get flagged. Connections accumulate. The compounding loop — ingest → query → synthesize → save — means each answer can become a new page.

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

### Ingest Pipeline

```
wiki ingest <source> --auto --no-retry
        │
        ▼
┌─────────────┐    ┌──────────────┐    ┌────────────┐    ┌──────────┐
│  REGISTER   │───▶│   EXTRACT    │───▶│  VALIDATE  │───▶│   LINK   │
│  source     │    │  LLM writes  │    │  promote   │    │  graph   │
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

## Setup

```bash
git clone https://github.com/dimasyankauskas/llm-knowledge-base.git
cd llm-knowledge-base
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### LLM Configuration

The system works with any provider that speaks OpenAI-compatible API or Anthropic. Pick one:

#### Ollama (local, recommended for privacy)

```bash
# Install: https://ollama.com
ollama pull qwen3.5:agentic

export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=qwen3.5:agentic
```

#### Anthropic Claude (cloud)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

#### OpenAI-compatible (Groq, LM Studio, Perplexity, etc.)

```bash
export OLLAMA_BASE_URL=https://api.groq.com/openai/v1
export OLLAMA_MODEL=llama-3.1-70b-versatile
export OLLAMA_API_KEY=gsk_...
```

> [!note]
> The CLI entry point is `wiki`. After `pip install -e .`, run `wiki ingest`, `wiki query`, etc. directly.

---

## Quick Start

```bash
# 1. Ingest a source (fast mode — recommended)
wiki ingest sources/my-paper.pdf --auto --no-retry

# 2. Ask a question — LLM synthesizes a cited answer
wiki query "What does the wiki know about retrieval-augmented generation?"

# 3. Save the synthesized answer as a new concept page
wiki save-answer "RAG at Scale" --type concept

# 4. Inspect the graph
wiki state        # page inventory, contradictions, thin pages
wiki health      # lint errors and warnings
```

### Full CLI Reference

| Command | Description |
|---------|-------------|
| `wiki ingest <source> --auto --no-retry` | Fast extraction (recommended) |
| `wiki ingest <source> --auto` | Extraction with retry correction |
| `wiki ingest <source> --auto --mode gap` | Gap-driven extraction (2 LLM calls) |
| `wiki query "question" --depth 2` | Graph-traversed query with LLM synthesis |
| `wiki query "question" --context-only` | Raw context output (no LLM call) |
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
      "file": "ai-product-strategy-research-plan-google-2026-04-20T03-58-24.md",
      "content_hash": "abc123",
      "sections_used": ["The Paradigm Shift to Agentic Autonomy"]
    }
  ],
  "claims": [
    {
      "id": "claim-1",
      "text": "Agentic AI executes multi-step workflows without continuous human input",
      "type": "fact",
      "sources": ["ai-product-strategy-research-plan-google-2026-04-20T03-58-24.md"],
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
├── mission400/         # Example: project-specific wiki
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

# Raw context only (for agents that synthesize themselves)
wiki query "What is agentic AI?" --depth 2 --context-only

# Persist a synthesized answer as a new wiki page
wiki save-answer "Agentic AI Product Strategy — 2026 Synthesis" --type concept
```

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