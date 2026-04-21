# LLM Knowledge Base

**An LLM-native knowledge base that compounds.**

Feed it raw sources — papers, articles, transcripts — and it extracts structured, interlinked concept pages. Every fact is cited. Every relationship is typed. The LLM is the extraction engine; Python scripts handle only what deterministic code can verify.

Built for engineers who think in systems, not in folders.

---

## Inspiration & Related Work

This project synthesizes ideas from several sources that shaped its design:

### [Andrej Karpathy — LLM Wiki (April 2026)](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

Karpathy's public gist introduced the core pattern: instead of retrieving from raw documents at query time (traditional RAG), an LLM incrementally builds and maintains a persistent wiki. The key insight is that **the wiki is a compounding artifact** — cross-references accumulate, contradictions get flagged, and synthesis improves with every source ingested. This project directly implements Karpathy's three-layer architecture (Sources → Wiki → Schema) and his ingest/query/lint loop.

### [InfraNodus — Knowledge Graph Text Analysis](https://infranodus.com)

InfraNodus visualizes any text as a knowledge graph, identifying gaps and structural weaknesses. The **gap-driven extraction mode** (`--mode gap`) in this project applies InfraNodus's insight — that knowing what you *don't* know is as valuable as knowing what you do — to the extraction pipeline. Two-pass extraction (gap analysis → targeted filling) is directly inspired by their research-oriented workflow.

### [Obsidian — Local PKM with Wikilinks](https://obsidian.md)

The file format and graph semantics (typed `[[wikilinks]]`, local markdown storage, vault-based architecture) are modeled after Obsidian. The decision to use plain-text, future-proof markdown files with YAML frontmatter is a deliberate choice to remain compatible with the Obsidian ecosystem.

### [LangChain + RAG — Retrieval-Augmented Generation](https://langchain.readthedocs.io)

The query pipeline (`wiki query`) uses graph-traversed context retrieval, a hybrid of vector similarity and structured graph traversal — inspired by LangChain's combining of RAG with knowledge graphs. Typed edges with per-type weights are analogous to LangChain's edge filtering in graph RAG.

---

## The Problem It Solves

Most knowledge bases are either **too loose** (chaotic notes, no structure, impossible to query) or **too rigid** (manual curation bottlenecks, no LLM synergy). LLM Knowledge Base closes the loop:

```
Sources → LLM Extraction → Typed Graph → Queries → New Synthesis → Sources
                                              ↑
                                    The compounding loop
```

The wiki doesn't just store knowledge — it creates the conditions for knowledge to grow.

---

## Architecture

Three layers, ordered by decreasing mutability:

```
┌─────────────────────────────────────────────────────────────────┐
│  SCHEMA.yaml           │  Constitution — defines what valid     │
│                        │  pages look like, typed relations,      │
│                        │  confidence rules, contradiction proto   │
├─────────────────────────────────────────────────────────────────┤
│  wiki/                 │  AI-managed workspace. Every page      │
│                        │  is a typed wikilink node with          │
│                        │  provenance sidecar                     │
├─────────────────────────────────────────────────────────────────┤
│  sources/              │  Read-only ground truth. Immutable.    │
│                        │  SHA-256 registered, never edited      │
└─────────────────────────────────────────────────────────────────┘
```

**Page types:** `concept`, `entity`, `timeline`

**Relation types:** `implements`, `extends`, `contradicts`, `cites`, `prerequisite_of`, `trades_off`, `derived_from`

**Confidence levels:** `HIGH` (multiple independent sources), `MEDIUM` (single source), `LOW` (inference or contested)

---

## How It Works

### Extraction Pipeline

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

### Query Loop

```bash
wiki query "What is the relationship between agentic AI and edge computing?" --depth 2
```

The query engine performs **two operations**:

1. **Graph traversal** — BFS from seed pages through typed edges, assembling a sourced context block
2. **LLM synthesis** — calls the configured LLM to produce a structured, cited answer from the assembled context

The LLM uses only the wiki pages as its source — no hallucination from training data. Every claim traces back to ingested documents.

```bash
# Raw context only (no LLM call, faster)
wiki query "What is agentic AI?" --depth 2 --context-only

# JSON output (includes synthesized answer)
wiki query "What is agentic AI?" --depth 2 --json
```

```bash
wiki save-answer "Agentic AI and Edge Computing" --type concept
```

The synthesized answer persists as a schema-compliant draft page. **This is the compounding loop** — every query can produce new knowledge that becomes part of the graph, making future queries richer.

```
Sources → Ingest → Wiki Pages → Query → LLM Synthesis → Save Answer → Wiki Pages
                                    ↑                                              |
                                    └──────────── The loop compounds ──────────────┘
```

---

## Setup

```bash
git clone https://github.com/yourhandle/llm-knowledge-base.git
cd llm-knowledge-base
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
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
> The CLI entry point is `wiki`. After `pip install -e .`, run `wiki ingest`, `wiki query`, etc. without the `python scripts/` prefix.

---

## Quick Start

```bash
# 1. Ingest a source — recommended: --no-retry (fast, reliable)
wiki ingest sources/my-paper.pdf --auto --no-retry

# 2. Ask what the wiki knows
wiki query "What does the wiki know about retrieval-augmented generation?"

# 3. Save useful synthesis back as a concept page
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

Most wikis treat `[[links]]` as navigation. LLM Knowledge Base treats them as **graph edges with semantics**:

```
[[Agentic AI]]:implements
[[Local AI]]:extends
[[UX Design Patterns]]:implements
```

The type determines graph traversal weight. A `cites` edge (weight 4) contributes more context than a `trades_off` edge (weight 1). This lets queries traverse the graph by semantic direction.

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

Every claim traces to its source file and section. Staleness detection compares `content_hash` against the live source — if the source changed, the page is flagged.

### Why confidence levels?

Knowledge quality is explicit, not implicit. `HIGH` pages (multiple independent sources) carry different weight in synthesis than `LOW` pages (single inference). When contradictions are detected, confidence auto-downgrades to `LOW` and the conflict is tracked in `_contradictions.md`.

---

## Multi-Wiki Architecture

Each knowledge domain gets its own wiki instance — a standalone clone of this repo with a customized `SCHEMA.yaml`. The schema is the constitution: change it, and the entire pipeline adapts. This means a research wiki can have different page types, confidence thresholds, and relation weights than a project-tracking wiki, while sharing the same extraction engine.

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
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# 5. Ingest your first source
wiki ingest sources/your-source.md --auto --no-retry
```

Each instance is independent: its own git history, its own sources, its own wiki graph. Cross-wiki linking is not supported — each wiki is a self-contained knowledge domain.

### Customizing SCHEMA.yaml

The schema controls everything the pipeline validates and extracts. Key customization points:

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
├── CLAUDE.md                # AI agent instructions (auto-generated from SCHEMA)
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
│   ├── _state.json          # Bootstrap: page inventory, health, contradictions
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

Provider detection is automatic. Set one environment variable and the right client is used.

| Provider | Env vars needed | SDK |
|----------|----------------|-----|
| Ollama | `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | `openai` |
| Anthropic direct | `ANTHROPIC_API_KEY` | `anthropic` |
| Groq | `OLLAMA_BASE_URL`, `OLLAMA_API_KEY`, `OLLAMA_MODEL` | `openai` |
| LM Studio | `OLLAMA_BASE_URL` (localhost), `OLLAMA_MODEL` | `openai` |
| OpenAI direct | `ANTHROPIC_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_API_KEY` | `openai` |

---

## Validation Rules

12 structural checks. ERROR means broken state — must fix before committing:

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

Forward wikilinks (links to pages that don't exist yet) are **warnings, not errors**. The link is registered as a graph edge — the target page can be created later.

---

## For AI Agents

The wiki is designed to be operated by an LLM agent, not manually. External agents can use it as a knowledge backend:

```bash
# Query with LLM synthesis (returns a structured, cited answer)
wiki query "What is the current state of agentic AI product strategy?" --depth 2

# Raw context only (no LLM call — useful for agents that synthesize themselves)
wiki query "What is agentic AI?" --depth 2 --context-only

# Persist a useful synthesized answer as a new wiki page
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
