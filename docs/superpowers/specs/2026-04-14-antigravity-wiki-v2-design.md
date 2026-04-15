# Antigravity Wiki v2 — Design Specification

**Date:** 2026-04-14  
**Author:** Dimas Yankauskas (Kedarnatha Das), BuildFutures.ai  
**Status:** Design approved, pending implementation planning  
**Replaces:** Antigravity Wiki v1 (current `main` branch)

---

## Problem Statement

Antigravity Wiki v1 validates the LLM Wiki pattern (Karpathy, 2026) — an LLM-native, self-organizing knowledge base where the agent is the extraction engine and scripts handle mechanical operations. However, v1 has hard limits:

1. **No provenance** — Claims cannot be traced to sources; there's no way to detect when a source changes and wiki pages become stale
2. **No fact/inference separation** — The agent can present inferences as facts, causing epistemic drift
3. **No draft staging** — Pages are written directly to the live wiki; errors propagate immediately
4. **No iterative refinement** — The `consolidate` workflow exists but there's no automated gap analysis or contradiction detection loop
5. **Keyword-only search** — The query engine uses simple keyword matching, no graph-aware traversal or hybrid search
6. **Hardcoded schema** — Page types, validation rules, and lint checks are baked into scripts; no way to configure for different domains
7. **No agent awareness** — Each session starts from scratch; the agent must explore the entire wiki to understand its state

Research into Karpathy's LLM Wiki pattern and 20+ community implementations (sage-wiki, Palinode, llm-wiki-agent, llm-knowledge-base, and others) validates these gaps and provides tested solutions.

---

## Design Goals

- **Reusable framework** — A clean-slate system that any domain can configure via SCHEMA.yaml
- **Epistemic integrity** — Every claim traceable to sources, facts separated from inferences, contradictions surfaced not buried
- **Agent awareness** — Any Claude Code session boots into full wiki awareness in one file read (~20KB)
- **CLI-first** — No server, no database, no API; the agent operates through CLI commands
- **Filesystem-native** — Markdown + JSON + YAML, git-trackable, Obsidian-compatible
- **Schema-driven** — SCHEMA.yaml is the single source of truth for all behavior

---

## Architecture

### Three-Layer Design (Preserved from v1)

| Layer | Location | Mutability | Access |
|-------|----------|------------|--------|
| **Raw Sources** | `sources/` | Read-only | Agent reads, never writes |
| **The Wiki** | `wiki/` | Agent-managed | Agent creates, updates, links, lints |
| **The Schema** | `SCHEMA.yaml` | Human-defined | Agent reads, never modifies |

### Pipeline Architecture (New in v2)

Knowledge flows through six configurable stages, each with a clear contract:

```
source → extract → validate → link → refine → lint → consolidate
              │          │        │                  │
              ▼          ▼        ▼                  ▼
         draft pages  validated  typed edges    refinement tasks
         + provenance  pages    + graph JSON    + gap analysis
```

Each stage is independently runnable for debugging, but the standard agent workflow uses the unified CLI: `wiki ingest <source> --type article`.

---

## Component Design

### 1. SCHEMA.yaml — Configurable Constitution

A structured YAML config that defines all wiki behavior. Replaces v1's hand-written `WIKI_SCHEMA.md`.

```yaml
version: "2.0"

page_types:
  concept:
    required_frontmatter: [title, type, confidence, created, source_refs, content_hash]
    required_sections: [Definition, "Key Properties", "How It Works", Relationships, "Open Questions", Sources]
    section_rules:
      Definition: facts_only
      "Key Properties": facts_only
      "How It Works": mixed
      Relationships: facts_only
      "Open Questions": inference_only
      Sources: required
    min_outlinks: 2
    citation_format: "[source: {filename}, §{section}]"

  entity:
    required_frontmatter: [title, type, entity_type, created, source_refs, content_hash]
    required_sections: [Overview, Contributions, Relationships, Sources]
    min_outlinks: 1

  index:
    auto_generated: true

  timeline:
    required_frontmatter: [title, type, created]

confidence_levels:
  HIGH: { description: "Multiple independent sources agree", color: green }
  MEDIUM: { description: "Single source, well-established claim", color: yellow }
  LOW: { description: "Inference, single mention, or contested", color: red }

relation_types:
  - implements
  - extends
  - contradicts
  - cites
  - prerequisite_of
  - trades_off
  - derived_from

extraction:
  merge_over_create: true
  atomic_notes: true
  entity_resolution: true
  write_mode: diff_proposal
  source_type_templates:
    paper: [abstract, methodology, results, limitations]
    article: [summary, key_points, implications]
    transcript: [speakers, topics, decisions, open_items]
    code-doc: [purpose, api, examples, gotchas]

validation:
  broken_links: { severity: ERROR }
  orphan_pages: { severity: WARNING }
  missing_frontmatter: { severity: ERROR }
  no_sources: { severity: WARNING }
  low_connectivity: { severity: WARNING, min_outlinks: 2 }
  unresolved_contradiction: { severity: WARNING }
  duplicate_concept: { severity: ERROR }
  stale_page: { severity: WARNING, threshold_days: 30 }
  unmarked_inference: { severity: WARNING }
  missing_content_hash: { severity: ERROR }
  missing_counter_args: { severity: WARNING }

contradiction:
  callout_type: warning
  resolution_callout: success
  auto_downgrade_confidence: LOW
  track_in: "wiki/indexes/_contradictions.md"
  require_counter_arguments: true
```

**Key differences from v1:**
- Machine-readable — pipeline stages validate against this directly
- `section_rules` enforce fact/inference separation
- `relation_types` define typed edges for the graph
- `source_type_templates` classify before extracting
- `write_mode: diff_proposal` gates writes through validation
- New validation rules: `stale_page`, `unmarked_inference`, `missing_content_hash`, `missing_counter_args`

### 2. Agent Awareness — `_state.json`

The agent reads exactly one file at session start to rebuild full wiki awareness:

```json
{
  "schema_version": "2.0",
  "last_updated": "2026-04-14T18:00:00Z",
  "page_types": ["concept", "entity", "index", "timeline"],
  "required_fields": {
    "concept": ["title", "type", "confidence", "created", "source_refs", "content_hash"],
    "entity": ["title", "type", "entity_type", "created", "source_refs", "content_hash"]
  },
  "pages": {
    "Retrieval-Augmented Generation": {
      "type": "concept",
      "confidence": "HIGH",
      "tags": ["domain/ai", "topic/retrieval"],
      "outlinks": 5,
      "inlinks": 3,
      "last_updated": "2026-04-14",
      "stale": false
    }
  },
  "active_contradictions": ["RAG Effectiveness"],
  "thin_pages": ["Knowledge Distillation"],
  "stale_pages": [],
  "recent_changes": [
    {"page": "RAG", "change": "updated", "date": "2026-04-14"},
    {"page": "Agentic RAG", "change": "created", "date": "2026-04-14"}
  ],
  "health": {
    "errors": 0,
    "warnings": 2,
    "orphans": 1,
    "broken_links": 0,
    "last_lint": "2026-04-14T18:00:00Z"
  }
}
```

Regenerated after every pipeline run. Contains schema summary + page inventory + health status + active contradictions + thin pages + recent changes. Total size: ~10-20KB for a wiki with 100-200 pages.

### 3. Provenance Sidecars

Every concept and entity page has a `.provenance.json` sidecar:

```
wiki/concepts/Retrieval-Augmented Generation.md
wiki/concepts/Retrieval-Augmented Generation.provenance.json
```

Provenance structure:

```json
{
  "page": "Retrieval-Augmented Generation",
  "content_hash": "a3f2b1c8",
  "sources": [
    {
      "file": "lewis2020_rag.pdf",
      "content_hash": "8e4d2f1a",
      "sections_used": ["Abstract", "Results"]
    }
  ],
  "claims": [
    {
      "id": "claim-1",
      "text": "RAG combines retrieval and generation to reduce hallucinations",
      "type": "fact",
      "sources": ["lewis2020_rag.pdf"],
      "corroborated": true,
      "last_verified": "2026-04-14"
    },
    {
      "id": "claim-2",
      "text": "RAG effectiveness drops with domain shift",
      "type": "inference",
      "sources": ["agentic_rag_comparison2026.md"],
      "corroborated": false,
      "last_verified": "2026-04-14"
    }
  ],
  "derived_concepts": ["Agentic RAG", "Knowledge Distillation"]
}
```

**Staleness detection:** Pipeline hashes every source file and compares against stored `content_hash`. If a source hash changed, every page citing it gets `stale: true` in frontmatter and `_state.json`.

### 4. Pipeline Stages

#### Stage 1: Extract

```
Input:  Source file in sources/
Output: Draft pages in wiki/drafts/ + provenance sidecars
        Source registered in manifest with content hash
```

- Agent reads source and extracts concepts, entities, relationships
- Agent classifies source type (paper, article, transcript, code-doc) using schema templates
- Agent writes draft pages to `wiki/drafts/`
- Pipeline validates draft structure against schema before promotion

#### Stage 2: Validate

```
Input:  Draft pages + source files + schema
Output: Validated pages in wiki/concepts/ or wiki/entities/
        .provenance.json sidecars with content hashes
        Staleness flags for changed sources
```

Checks:
- All frontmatter fields per schema
- Facts-only sections contain no unmarked inferences
- Minimum outlink count met
- All wikilinks resolve or flagged as `BROKEN_LINK`
- Content hashes match sources; flag stale pages
- No duplicate concepts

Failed validation = draft stays in `wiki/drafts/` with error report.

#### Stage 3: Link

```
Input:  All wiki pages
Output: _graph.json with typed edges
        Updated pages with resolved wikilinks
        Bidirectional link verification
```

Typed wikilinks in markdown:

```markdown
The [[RAG]] pattern implements [[Neural Information Retrieval]]
and extends [[Generative Pre-training]].
```

Graph stores typed edges:

```json
{
  "edges": [
    {"source": "RAG", "target": "Neural Information Retrieval", "type": "implements"},
    {"source": "RAG", "target": "Generative Pre-training", "type": "extends"}
  ]
}
```

#### Stage 4: Refine

```
Input:  Full wiki state + _state.json + _health.json
Output: Refinement tasks (thin pages, contradictions, gaps)
        Counter-argument sections for strong claims
        Staleness checks on all provenance
```

- **Thin pages** — Pages with fewer than 2 sections get flagged for re-extraction
- **Contradictions** — Pages with conflicting claims on the same topic
- **Counter-arguments** — High-confidence pages get `## Counter-Arguments & Data Gaps` sections
- **Stale checks** — Source content hashes compared against stored hashes
- **Gap analysis** — Wikilinks pointing to non-existent pages

#### Stage 5: Lint

12 structural checks (v1's 8 + 4 new):

| Check | Severity | Description |
|-------|----------|-------------|
| BROKEN_LINK | ERROR | Wikilink points to non-existent page |
| ORPHAN_PAGE | WARNING | Page has 0 inlinks AND 0 outlinks |
| MISSING_FRONTMATTER | ERROR | Required frontmatter fields missing |
| INVALID_TYPE | ERROR | Page type not in schema |
| NO_SOURCES | WARNING | Page contains no source citations |
| LOW_CONNECTIVITY | WARNING | Concept page has fewer than 2 outgoing links |
| STALE_PAGE | WARNING | Source content hash changed, page needs re-extraction |
| UNRESOLVED_CONTRADICTION | WARNING | Open contradiction callouts exist |
| DUPLICATE_CONCEPT | ERROR | Two pages describe the same concept |
| EMPTY_SECTION | WARNING | Required section exists but has no content |
| UNMARKED_INFERENCE | WARNING | Inference in facts-only section without callout |
| MISSING_CONTENT_HASH | ERROR | Page has no provenance sidecar |

#### Stage 6: Consolidate

```
Input:  Full wiki state + graph metrics
Output: Merged pages, generated indexes, timelines
        Updated _state.json
```

- **Duplicate detection** — High content overlap or alias matches
- **Index generation** — `_index.md`, `by-topic.md`, `by-source.md`, `recently-updated.md`
- **Timeline generation** — From milestone-dated concepts
- **Merger** — Updating all wikilinks, deleting redirects, re-validating graph

### 5. Search Architecture

**Tier 1: Graph traversal** (wikis < 50K tokens)
- Seed pages found by keyword + tag + alias matching
- Expand via typed edges (depth configurable)
- Rank by edge type weight: cites(4x), contradicts(3x), implements(3x), extends(2x)

**Tier 2: Hybrid search** (wikis 50K-200K tokens)
- Reciprocal Rank Fusion combining:
  - BM25 full-text search (SQLite FTS5)
  - Vector search (embedding cosine similarity)
  - Tag boost (matching wiki tags)
  - Graph expansion (4-signal scorer from typed edges)

**Tier 3: RAG overflow** (wikis > 200K tokens)
- Wiki as L1 cache for stable core knowledge
- Raw sources searched via vector similarity for dynamic/overflow content
- Architecture supports this; implementation deferred to v3

### 6. Unified CLI

```bash
# Full pipeline
wiki ingest <source> --type article       # extract → validate → link → lint
wiki process <source> --type paper        # alias for ingest

# Individual stages
wiki extract <source> --type article     # just extraction
wiki validate                             # validate drafts against schema
wiki refine                               # iterative refinement pass
wiki link                                 # resolve wikilinks, build graph
wiki lint                                 # structural integrity check
wiki consolidate                          # merge duplicates, gen indexes

# Search & awareness
wiki state                                # current snapshot (_state.json)
wiki health                               # lint status summary
wiki query "RAG effectiveness" --depth 2  # graph traversal query
wiki query "RAG" --mode hybrid            # hybrid RRF search
wiki find --tag domain/ai --confidence LOW # filter by metadata
wiki provenance "RAG.md"                  # show evidence chain

# Source management
wiki register <source> --type article     # register in manifest
wiki check <source>                       # dedup check
wiki rebuild                              # regenerate indexes + graph

# Schema management
wiki generate-instructions                # generate CLAUDE.md from SCHEMA.yaml
```

### 7. CLAUDE.md Generation

The agent instructions file is generated from SCHEMA.yaml:

```bash
wiki generate-instructions   # reads SCHEMA.yaml, writes CLAUDE.md
```

Generated CLAUDE.md contains:
1. **Identity** — "You are the Wiki Curator agent"
2. **Bootstrap instruction** — "Read `wiki/_state.json` before any wiki operation"
3. **Architecture** — Three-layer design, access levels
4. **Rules** — Derived from schema: merge over create, cite everything, separate facts from inferences, propose diffs, lint after changes
5. **Page templates** — Generated from `page_types` and `required_sections`
6. **CLI reference** — All `wiki` commands with examples
7. **Constraints** — Derived from `extraction`, `validation`, and `contradiction` config

### 8. File Structure

```
antigravity-wiki/
├── CLAUDE.md                    # Agent instructions (auto-generated from schema)
├── SCHEMA.yaml                  # System constitution (human-editable)
├── requirements.txt             # Python dependencies
│
├── sources/                     # Layer 1: Immutable ground truth
│   ├── manifest.json            # Source registry with content hashes
│   ├── article/
│   ├── paper/
│   ├── transcript/
│   └── code-doc/
│
├── wiki/                        # Layer 2: AI-managed knowledge
│   ├── _state.json              # Agent bootstrap: inventory + health + schema summary
│   ├── _health.json             # Last lint results summary
│   ├── _graph.json              # Typed adjacency graph
│   ├── _log.md                  # Append-only operation log
│   │
│   ├── drafts/                  # Staging area before validation
│   │
│   ├── concepts/                # Concept pages + provenance sidecars
│   │   ├── *.md
│   │   └── *.provenance.json
│   │
│   ├── entities/                # Entity pages + provenance sidecars
│   │   ├── *.md
│   │   └── *.provenance.json
│   │
│   ├── indexes/                 # Auto-generated navigation pages
│   │   ├── _index.md
│   │   ├── _contradictions.md
│   │   ├── by-topic.md
│   │   ├── by-source.md
│   │   └── recently-updated.md
│   │
│   └── timelines/               # Chronological evolution pages
│
└── scripts/                     # Layer 3: Mechanical tools
    ├── cli.py                   # Unified CLI entry point
    ├── extract.py               # Source classification + draft validation
    ├── validate.py              # Schema + provenance validation
    ├── refine.py                # Gap analysis + contradiction detection
    ├── link.py                  # Wikilink resolution + graph build
    ├── lint.py                  # Structural integrity (12 checks)
    ├── consolidate.py           # Merge + index + timeline generation
    ├── query.py                 # Graph traversal + hybrid search
    ├── provenance.py            # Evidence chain + staleness detection
    └── utils.py                 # Shared constants, frontmatter, graph ops
```

### 9. Typed Wikilinks

v1 used flat `[[wikilinks]]`. v2 introduces typed relations:

**Markdown syntax:**

```markdown
RAG implements [[Neural Information Retrieval]] and extends [[Generative Pre-training]].
Some argue [[Pure Generation]] contradicts the retrieval premise.
```

**Relation types (from SCHEMA.yaml):**

| Type | Meaning | Weight (for search) |
|------|---------|-------------------|
| `implements` | A uses/builds on B | 3x |
| `extends` | A is an extension of B | 2x |
| `contradicts` | A conflicts with B | 3x |
| `cites` | A references B | 4x |
| `prerequisite_of` | A must be understood before B | 2x |
| `trades_off` | A and B are alternatives | 1x |
| `derived_from` | A is derived from B | 2x |

**How typing works:**
- Agent marks relations in page content using context: "X implements Y", "X contradicts Y"
- `link` stage parses context around wikilinks to infer edge types from surrounding text
- When context is ambiguous, the agent can explicitly mark the relation in frontmatter `related_concepts` list: `- "[[Neural IR]]:implements"`
- Graph stores typed edges in `_graph.json` with both explicit and inferred relations
- Search and traversal use edge weights for relevance scoring
- Untyped wikilinks default to weight 1x (neutral) — they still connect pages but don't carry semantic weight

### 10. Fact/Inference Separation

Every concept page must clearly distinguish:

- **Facts** — Claims directly supported by sources, marked with `[source: filename, §section]`
- **Inferences** — Synthesis, connections, or conclusions drawn by the agent, marked with `> [!note] Inference: ...`
- **Open Questions** — Explicitly flagged unknowns in the `Open Questions` section

The `validate` stage checks that facts-only sections (Definition, Key Properties, Relationships) contain no unmarked inferences. The `lint` stage flags `UNMARKED_INFERENCE` warnings.

### 11. Diff-Proposed Writes

v1 had the agent directly editing wiki pages. v2 gates writes:

1. Agent writes draft pages to `wiki/drafts/`
2. `validate` stage checks them against the schema
3. For updates to existing pages, the agent proposes a diff (what to add/change/remove)
4. Diff is reviewed (by human or auto-verified if: no contradictions introduced, all new claims have sources, confidence not downgraded without reason)
5. Only then does the page get updated in `wiki/concepts/` or `wiki/entities/`

Auto-verification criteria:
- No new contradictions introduced
- All new claims have source citations
- Confidence not downgraded without explicit `CONTRADICTION` callout
- No unmarked inferences in facts-only sections

### 12. Counter-Arguments Section

Inspired by @localwolfpackai's divergence check, every concept page with `confidence: HIGH` or `confidence: MEDIUM` must include a `## Counter-Arguments & Data Gaps` section.

The `refine` stage generates these by:
- Searching for `contradicts` relations in the graph
- Identifying opposing viewpoints from other sources
- Flagging areas where evidence is thin

If no counter-arguments exist, the section reads: `No significant counter-arguments identified. [source: ...]`

---

## Research References

| Source | Key Insight | How It Shapes v2 |
|--------|-------------|------------------|
| [Karpathy's LLM Wiki Gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) | Three-layer architecture, schema is 80% of outcome, lint weekly | Core pattern, SCHEMA.yaml as config |
| [sage-wiki](https://github.com/xoai/sage-wiki) | 5-pass pipeline, typed relations, 4-signal graph scorer, provenance CLI | Pipeline stages, typed edges, provenance command |
| [Palinode](https://github.com/Paul-Kyle/palinode) | Proposition-level provenance, content-hash staleness, git blame any fact | Provenance sidecars, content-hash staleness detection |
| [llm-wiki-agent](https://github.com/SamurAIGPT/llm-wiki-agent) | Contradiction detection at ingest time, Louvain community detection | Refine stage contradiction detection |
| [llm-knowledge-base](https://louiswang524.github.io/blog/llm-knowledge-base) | Reflect stage between compile and query, 9-skill system | Refine stage as deliberate reflection pass |
| laphilosophia critique | Separate facts from inferences, propose diffs, make ingest idempotent | Fact/inference separation, diff-proposed writes |
| @localwolfpackai | Counter-arguments section, search for sophisticated critique | Counter-Arguments & Data Gaps section |
| Steph Ango | Separate vaults for human vs LLM content | Draft staging area (`wiki/drafts/`) |
| @bluewater8008 | Classify before extracting, every task produces two outputs | source_type_templates, two-output rule |
| Proudfrog guide | Content-hash staleness, weekly lint, schema invests an hour | Content-hash staleness detection in validate/lint |

---

## What v2 Does NOT Include (v3 Considerations)

- **Vector search / embedding pipeline** — Architecture supports it; implementation deferred
- **Multi-user access control** — No merge resolution or concurrent editing protocol
- **Web UI** — CLI-first; Obsidian for human viewing
- **MCP server** — CLI is the interface; MCP could wrap it in v3
- **Real-time data** — Wiki reflects knowledge at last ingest; not suitable for rapidly changing data
- **Multi-agent coordination** — Single agent model; multi-agent wiki access is unsolved in the community

---

## Migration from v1

v2 is a clean-slate design. The v1 codebase (`scripts/ingest.py`, `lint.py`, `query.py`, `stats.py`, `utils.py`) is replaced by the new pipeline architecture. However:

- Existing wiki content (`wiki/concepts/`, `wiki/entities/`) can be migrated by adding provenance sidecars and updating frontmatter to match SCHEMA.yaml
- The `sources/` directory and `manifest.json` are preserved as-is
- `WIKI_SCHEMA.md` is replaced by `SCHEMA.yaml` (machine-readable)
- `GEMINI.md` is replaced by auto-generated `CLAUDE.md`