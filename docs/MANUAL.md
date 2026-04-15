# Antigravity Wiki v2 — Manual

## What It Is

Antigravity Wiki is an LLM-native, self-organizing knowledge base. The LLM (you, the agent) is the extraction engine — it reads raw sources, extracts knowledge, and writes interlinked Obsidian Markdown pages. Python scripts handle only deterministic operations: registration, indexing, graph-building, validation, and linting. There are no LLM API calls in any script.

The system is **schema-driven**: a single `SCHEMA.yaml` file defines page types, required fields, relation types, validation rules, confidence scoring, and contradiction handling. Every script reads from this schema, so changes to the schema automatically propagate through the entire pipeline.

---

## Architecture

Three layers, ordered by decreasing mutability:

```
┌─────────────────────────────────┐
│  The Schema (SCHEMA.yaml)        │  Human-defined — constitutional rules
│  Read by every script and agent   │
├─────────────────────────────────┤
│  The Wiki (wiki/)                │  AI-managed — create, update, link, lint
│  concepts/ entities/ indexes/     │
├─────────────────────────────────┤
│  Raw Sources (sources/)          │  Read-only — never modify
│  manifest.json + source files     │
└─────────────────────────────────┘
```

**Raw Sources** are immutable ground truth. Never edit them after ingestion.

**The Wiki** is your workspace. Create pages, update content, add links, resolve contradictions. All pages are Obsidian-flavored Markdown with YAML frontmatter.

**The Schema** is the constitution. It defines what a valid page looks like, how relations work, what confidence levels mean, and how contradictions are handled. Read it before any wiki operation.

---

## Directory Structure

```
antigravity-wiki/
├── SCHEMA.yaml                  # Human-editable system constitution
├── CLAUDE.md                    # Auto-generated agent instructions
├── requirements.txt             # Python dependencies
├── sources/                     # IMMUTABLE — raw source documents
│   ├── manifest.json            #   Registry with SHA-256 hashes
│   ├── article/                 #   .md, .txt source files
│   ├── paper/                   #   .pdf academic papers
│   ├── transcript/              #   Meeting/chat transcripts
│   └── code-doc/                #   Code documentation
├── wiki/                        # AI-MANAGED — knowledge base
│   ├── _state.json              #   Agent bootstrap: pages, health, contradictions
│   ├── _health.json             #   Lint results: errors, warnings, issues
│   ├── _graph.json              #   Typed adjacency graph (auto-generated)
│   ├── _log.md                  #   Activity log
│   ├── drafts/                  #   Staging area — pages must pass validation
│   ├── concepts/                #   Concept pages + provenance sidecars
│   ├── entities/                #   Entity pages + provenance sidecars
│   ├── indexes/                 #   Auto-generated index pages (prefixed _)
│   └── timelines/               #   Auto-generated timeline pages
├── scripts/                     # Pipeline engine
│   ├── cli.py                   #   Unified CLI entry point
│   ├── schema.py                #   Schema loader + 12 accessor functions
│   ├── utils.py                 #   Constants, paths, frontmatter, wikilinks
│   ├── provenance.py            #   Sidecar CRUD + staleness detection
│   ├── state.py                 #   _state.json + _health.json generation
│   ├── extract.py               #   Stage 1: source registration
│   ├── validate.py              #   Stage 2: draft validation + promotion
│   ├── link.py                  #   Stage 3: typed graph building
│   ├── refine.py                #   Stage 4: gap + contradiction analysis
│   ├── lint.py                  #   Stage 5: 12 structural checks
│   ├── consolidate.py           #   Stage 6: merge, indexes, timelines
│   ├── query.py                 #   Graph-traversal context builder
│   ├── migrate.py               #   v1 → v2 migration
│   └── generate_instructions.py #   CLAUDE.md generator
└── tests/                       # 200 tests across 12 test modules
```

---

## The Six-Stage Pipeline

```
Source ──► Extract ──► Validate ──► Link ──► Refine ──► Lint ──► Consolidate
              │            │          │         │         │          │
         register      promote    graph    gaps &      12      indexes &
         + dedup       drafts     build   contra-   checks    timelines
                                           dicts
```

### Stage 1: Extract

Register a source file and add it to the manifest.

```bash
wiki extract <source> --type <type>
wiki register <source> --type <type>    # alias
wiki check <source>                      # dedup check
```

- **Auto-classification**: If `--type` is omitted, the system guesses from file extension:
  - `.pdf` → `paper`
  - `.md`, `.txt`, `.json`, `.yaml`, `.csv` → `article`
  - `.py`, `.js`, `.ts`, `.go`, `.rs`, `.java` → `code-doc`
  - Files with "transcript" keywords → `transcript`
- **Dedup**: SHA-256 hash of file content checked against `sources/manifest.json`
- **Registration**: Source is copied to `sources/<type>/` and added to manifest

### Stage 2: Validate

Validate draft pages against the schema and promote valid ones.

```bash
wiki validate
```

Five validation checks run on each draft:

1. **Frontmatter** — all required fields present? correct `type` value?
2. **Sections** — all required sections present? any empty sections?
3. **Wikilinks** — do all `[[Page]]` links point to existing pages?
4. **Provenance** — does a `.provenance.json` sidecar exist? valid `content_hash`?
5. **Fact/Inference separation** — do `facts_only` sections contain unmarked inferences (claims without `[source: ...]` citations)?

If a draft has **zero errors**, it is promoted from `wiki/drafts/` to `wiki/concepts/` or `wiki/entities/` based on its `type` frontmatter field. Its provenance sidecar moves with it.

### Stage 3: Link

Build the typed knowledge graph from wikilinks.

```bash
wiki link
```

- Scans all concept and entity pages
- Extracts typed edges from two sources:
  - **Context-based**: `[[Neural IR]]:implements` in page body
  - **Frontmatter-based**: `related_concepts: [[Page]]:type` in YAML
- Each edge gets a weight from `DEFAULT_EDGE_WEIGHTS` (see Relation Types below)
- Verifies bidirectional links (warns if `A → B` exists but `B → A` is missing)
- Writes `wiki/_graph.json`

### Stage 4: Refine

Identify pages that need human/agent attention.

```bash
wiki refine
```

Generates a prioritized task list from five detection modes:

| Detection | Severity | What It Finds |
|-----------|----------|---------------|
| Contradictions | high | Unresolved `> [!warning] CONTRADICTION` callouts |
| Gap pages | high | Wikilinks to pages that don't exist yet |
| Stale pages | medium | Source files have changed since last ingestion |
| Thin pages | medium | Pages with fewer than 2 `##` sections |
| Missing counter-args | low | HIGH/MEDIUM pages without `## Counter-Arguments & Data Gaps` |

### Stage 5: Lint

Run 12 structural checks on the entire wiki.

```bash
wiki lint
wiki lint --json
```

| # | Check | Code | Severity | Description |
|---|-------|------|----------|-------------|
| 1 | Broken links | `BROKEN_LINK` | ERROR | `[[Page]]` links to nonexistent page |
| 2 | Orphan pages | `ORPHAN_PAGE` | WARNING | No inlinks and no outlinks |
| 3 | Missing frontmatter | `MISSING_FRONTMATTER` | ERROR | Required field absent |
| 4 | Invalid type | `INVALID_TYPE` | ERROR | `type` not in schema |
| 5 | No sources | `NO_SOURCES` | WARNING | `source_refs` empty or missing |
| 6 | Low connectivity | `LOW_CONNECTIVITY` | WARNING | Fewer outgoing links than `min_outlinks` |
| 7 | Stale pages | `STALE_PAGE` | WARNING | Source file content has changed |
| 8 | Unresolved contradictions | `UNRESOLVED_CONTRADICTION` | WARNING | `CONTRACTION` callout without resolution |
| 9 | Empty sections | `EMPTY_SECTION` | WARNING | Required section has no content |
| 10 | Duplicate concepts | `DUPLICATE_CONCEPT` | ERROR | Two pages with same title or overlapping aliases |
| 11 | Unmarked inference | `UNMARKED_INFERENCE` | WARNING | `facts_only` section contains unsourced claims |
| 12 | Missing content hash | `MISSING_CONTENT_HASH` | ERROR | No `content_hash` in frontmatter |

**Exit behavior**: The linter prints a summary. Any ERROR means the wiki is in a broken state — fix before committing.

### Stage 6: Consolidate

Merge duplicates and regenerate indexes.

```bash
wiki consolidate
```

Three operations:

1. **Duplicate detection** — finds page pairs with title similarity or alias overlap
2. **Index generation** — creates 5 auto-generated index pages:
   - `_index.md` — master alphabetical listing
   - `_contradictions.md` — tracks unresolved contradictions
   - `by-topic.md` — pages grouped by tag
   - `by-source.md` — pages grouped by source file
   - `recently-updated.md` — 10 most recently changed pages
3. **Timeline generation** — creates a timeline page if 5+ dated events exist

---

## Full-Pipeline Command

The `ingest` command runs the entire pipeline end-to-end:

```bash
wiki ingest <source> --type <type>
```

This executes: extract → link → lint → state. Use it when adding a new source and you want everything updated in one step.

---

## Inspection Commands

### Query the Wiki

Search the knowledge graph by natural language question:

```bash
wiki query "What is Agentic RAG?" --depth 2
wiki query "RAG effectiveness" --depth 2 --json
```

**How it works**:
1. **Seed finding** — scores all pages against the question using title words (+10/word), aliases (+8), tag words (+3/word), and content keywords (+1/word)
2. **Graph traversal** — BFS from seed pages, following typed edges with weighted scoring. Edge weights decay by depth: `score = node_score * weight / (depth + 1)`
3. **Context assembly** — formats relevant pages into a single text block (max 50K chars)

Options:
- `--depth N` — how many hops from seeds (default: 2)
- `--top-k N` — number of seed pages (default: 5)
- `--json` — structured JSON output

### Find Pages by Metadata

```bash
wiki find --tag domain/ai
wiki find --confidence HIGH
wiki find --tag topic/retrieval --confidence MEDIUM
```

### Show Provenance

View the evidence chain for a specific page:

```bash
wiki provenance "RAG"
```

Outputs the full `.provenance.json` sidecar — claims, sources, staleness status.

### System State

```bash
wiki state       # Print _state.json (pages, contradictions, thin pages, health)
wiki health      # Print _health.json (errors, warnings, lint issues)
```

---

## Page Types

### Concept Pages

Location: `wiki/concepts/`

Required frontmatter fields:

```yaml
---
title: Page Title
type: concept
confidence: HIGH | MEDIUM | LOW
created: 2026-04-15
source_refs:
  - source-file.md
content_hash: a1b2c3d4e5f6g7h8
tags:
  - domain/ai
  - topic/retrieval
aliases:
  - RAG
related_concepts:
  - "[[Neural IR]]:implements"
---
```

Required sections with their rules:

| Section | Rule | Meaning |
|---------|------|---------|
| Definition | `facts_only` | Only verifiable claims with `[source: ...]` citations |
| Key Properties | `facts_only` | Only verifiable claims with citations |
| How It Works | `mixed` | Both facts and inferences allowed |
| Relationships | `facts_only` | Typed wikilinks: `[[Page]]:relation_type` |
| Open Questions | `inference_only` | Speculation, hypotheses, unknowns |
| Sources | `required` | Must exist, must list source references |

**Minimum outlinks**: 2 (a concept page should connect to at least 2 other pages)

### Entity Pages

Location: `wiki/entities/`

Required frontmatter fields: same as concept, plus `entity_type` (e.g., `company`, `person`, `technology`).

Required sections: Overview, Contributions, Relationships, Sources.

**Minimum outlinks**: 1

### Index Pages

Location: `wiki/indexes/`

Auto-generated. Never hand-edit. Prefixed with `_` (e.g., `_index.md`, `_contradictions.md`).

### Timeline Pages

Location: `wiki/timelines/`

Auto-generated when 5+ dated events exist. Groups events by year-month.

---

## Typed Relations

Use typed wikilinks to express semantic relationships between concepts:

```
[[Target Page]]:relation_type
```

Seven relation types with their graph traversal weights:

| Relation | Weight | Meaning |
|----------|--------|---------|
| `:cites` | 4 | Direct citation from source material |
| `:contradicts` | 3 | Conflicting claims |
| `:implements` | 3 | One concept implements another |
| `:extends` | 2 | Builds upon a base concept |
| `:prerequisite_of` | 2 | Must understand A before B |
| `:derived_from` | 2 | Concept evolved from another |
| `:trades_off` | 1 | Competing approaches |

**Untyped links** (`[[Page]]` without a colon suffix) default to weight 1.

Two ways to add typed edges:

1. **Inline in content**: `Neural IR [[RAG]]:implements a retrieval layer.`
2. **In frontmatter**: `related_concepts: ["[[Neural IR]]:implements"]`

---

## Confidence Scoring

Every concept and entity page must declare a confidence level:

| Level | Color | Criteria |
|-------|-------|----------|
| **HIGH** | Green | Multiple independent sources agree |
| **MEDIUM** | Yellow | Single source, well-established claim |
| **LOW** | Red | Inference, single mention, or contested claim |

Confidence affects:
- How the page appears in `_state.json`
- Whether a `## Counter-Arguments & Data Gaps` section is required (HIGH and MEDIUM pages must have one)
- Auto-downgrade: when a contradiction is detected, confidence drops to LOW

---

## Contradiction Handling

Never silently overwrite conflicting information. Follow this protocol:

1. **Mark the contradiction** with a callout:
   ```markdown
   > [!warning] CONTRADICTION
   > Source A claims X, but Source B claims Y.
   ```

2. **Auto-downgrade confidence** to `LOW`.

3. **Add counter-arguments** — HIGH/MEDIUM pages must include a `## Counter-Arguments & Data Gaps` section.

4. **Track in `wiki/indexes/_contradictions.md`** — the consolidate stage maintains this index automatically.

5. **Resolve** with a success callout when evidence settles the matter:
   ```markdown
   > [!success] RESOLVED
   > Source C confirms X. Downgraded claim Y has been updated.
   ```

---

## Provenance Sidecars

Every wiki page has a companion `.provenance.json` file that tracks evidence and staleness:

```
wiki/concepts/RAG.md                    → wiki/concepts/RAG.md.provenance.json
wiki/entities/Anthropic.md              → wiki/entities/Anthropic.md.md.provenance.json
```

Sidecar structure:

```json
{
  "page": "RAG",
  "content_hash": "a1b2c3d4e5f6g7h8",
  "sources": [
    {
      "file": "source-file.md",
      "content_hash": "x1y2z3",
      "sections_used": ["abstract", "results"]
    }
  ],
  "claims": [
    {
      "id": "claim-1",
      "text": "RAG combines retrieval and generation",
      "type": "fact",
      "sources": ["source-file.md"],
      "corroborated": true,
      "last_verified": "2026-04-15"
    }
  ],
  "last_verified": "2026-04-15"
}
```

**Staleness detection**: On each lint run, the system compares the `content_hash` in each provenance source against the actual file in `sources/`. If the hash differs, the page is flagged as stale.

---

## Agent Bootstrap

At the start of every session, read `wiki/_state.json` to get:

- **Schema summary** — version, page types, required fields
- **Page inventory** — every page with its type, confidence, tags, outlinks, inlinks
- **Active contradictions** — pages with unresolved `CONTRADICTION` callouts
- **Thin pages** — pages with fewer than 2 sections that need expansion
- **Stale pages** — pages whose source content has changed since last verification

Then read `wiki/_health.json` for lint status. **Resolve all ERROR-level issues before creating new content.**

---

## File Naming Conventions

| Type | Pattern | Example |
|------|---------|---------|
| Concept | Title Case | `Retrieval-Augmented Generation.md` |
| Entity | Canonical name | `Anthropic.md` |
| Index | Underscore prefix | `_index.md`, `_contradictions.md` |
| Tags | lowercase kebab-case with domain prefix | `domain/ai`, `topic/retrieval`, `entity/company` |
| Provenance | Page name + `.provenance.json` | `RAG.md.provenance.json` |

---

## Citation Format

Factual claims must include inline source citations:

```markdown
RAG combines retrieval and generation [source: lewis2020rag, §abstract].
```

The citation format is defined in `SCHEMA.yaml` under `page_types.concept.citation_format`:

```
[source: {filename}, §{section}]
```

---

## Complete CLI Reference

```
wiki ingest <source> --type <type>         Full pipeline: extract → validate → link → lint → state
wiki process <source> --type <type>         Alias for ingest
wiki extract <source> --type <type>         Register source only (no pipeline)
wiki validate                                Validate all drafts; promote valid ones
wiki link                                    Build typed graph; verify bidirectional links
wiki refine                                  Run gap/contradiction/staleness analysis
wiki lint [--json]                           12 structural checks (ERROR = must fix)
wiki consolidate                             Merge duplicates; generate indexes + timelines
wiki state                                   Print _state.json summary
wiki health                                  Print _health.json summary
wiki query "question" [--depth N] [--top-k N] [--json]
                                             Graph-traversal context builder
wiki find --tag <tag> [--confidence <level>]  Filter pages by metadata
wiki provenance <page>                       Show evidence chain for a page
wiki register <source> --type <type>          Register source only (same as extract)
wiki check <source>                          Dedup check — is source already ingested?
wiki rebuild                                 Regenerate: indexes + graph + state + health
wiki generate-instructions                   Regenerate CLAUDE.md from SCHEMA.yaml
```

Running `wiki` with no arguments prints help.

---

## Source Type Templates

When ingesting a source, use the `--type` flag to specify its category. Each type has an expected content structure:

| Type | Expected Sections |
|------|-------------------|
| `paper` | abstract, methodology, results, limitations |
| `article` | summary, key_points, implications |
| `transcript` | speakers, topics, decisions, open_items |
| `code-doc` | purpose, api, examples, gotchas |

These templates guide what the agent should extract but are not enforced by validation.

---

## Ingestion Workflow (Step by Step)

1. **Check for duplicates**:
   ```bash
   wiki check sources/paper/new-research.pdf
   ```
   If "Already ingested", stop here.

2. **Read the source document yourself** (you are the LLM, not a script). Extract concepts, entities, and relationships.

3. **Write wiki pages** in `wiki/drafts/` following the schema:
   - Create concept pages with all required frontmatter and sections
   - Create entity pages for organizations, people, technologies
   - Use typed wikilinks: `[[Page]]:implements`
   - Add `[source: ...]` citations for factual claims
   - Set confidence level based on evidence strength

4. **Register the source**:
   ```bash
   wiki register sources/paper/new-research.pdf --type paper
   ```

5. **Validate and promote drafts**:
   ```bash
   wiki validate
   ```
   Fix any errors reported. Only zero-error drafts get promoted.

6. **Build the graph**:
   ```bash
   wiki link
   ```

7. **Run the linter**:
   ```bash
   wiki lint
   ```
   Fix all ERROR-level issues. Warnings are acceptable but should be addressed eventually.

8. **Regenerate state**:
   ```bash
   wiki rebuild
   ```

---

## Migration from v1

If upgrading from v1:

```bash
python scripts/migrate.py
```

This script:
1. Adds missing frontmatter fields (`content_hash`, `source_refs`, `confidence`, `created`) to all existing pages
2. Creates `.provenance.json` sidecars for each page
3. Creates `wiki/_log.md` with a migration entry
4. Runs lint and generates `_state.json` + `_health.json`
5. Creates the `wiki/drafts/` directory

After migration, run `wiki generate-instructions` to create the v2 CLAUDE.md.

---

## Regenerating CLAUDE.md

The `CLAUDE.md` file is auto-generated from `SCHEMA.yaml`. Regenerate it whenever the schema changes:

```bash
wiki generate-instructions
```

This reads `SCHEMA.yaml` and produces `CLAUDE.md` with all current page types, rules, commands, and conventions. Never hand-edit `CLAUDE.md` — your changes will be overwritten.

---

## Troubleshooting

### Lint reports BROKEN_LINK errors

You have wikilinks `[[Page]]` that point to pages that don't exist yet. Either:
- Create the missing pages
- Or remove the wikilinks from the source page

### Lint reports STALE_PAGE warnings

Source files in `sources/` have been modified since their content was hashed into the wiki. The wiki pages referencing those sources may be out of date. Re-read the updated sources and update the wiki pages.

### Lint reports UNMARKED_INFERENCE warnings

A `facts_only` section (like Definition or Key Properties) contains claims without `[source: ...]` citations. Either add citations or move the claim to a `mixed` or `inference_only` section.

### Lint reports MISSING_CONTENT_HASH errors

The `content_hash` frontmatter field is missing. This usually means the page was created without going through the ingestion workflow. Run `wiki generate-instructions` to regenerate CLAUDE.md, then manually add the hash or re-run migration.

### Validation rejects my draft

Check the validation report for the specific errors. Common causes:
- Missing required frontmatter field (e.g., `confidence`, `source_refs`)
- Missing required section (e.g., `## Open Questions`)
- Broken wikilinks in the draft content

### Query returns no results

The query engine uses keyword matching, not semantic search. Try:
- Using exact words from page titles
- Including words from tags or aliases
- Increasing `--top-k` to find more seed pages
- Increasing `--depth` to traverse further in the graph

---

## Dependencies

```
python-frontmatter>=1.1.0    # YAML frontmatter parsing
pyyaml>=6.0                  # SCHEMA.yaml loading
networkx>=3.4                # Graph operations (available but not required)
rich>=13.9                   # Terminal formatting
pymupdf>=1.25.0              # PDF reading for paper sources
```

Activate the virtual environment before running commands:

```bash
source .venv/bin/activate
```

---

## Test Suite

```bash
# Run all 200 tests
python -m pytest tests/ -v

# Run a specific module
python -m pytest tests/test_lint.py -v

# Run a single test
python -m pytest tests/test_query.py::TestFindSeedPages::test_find_seed_pages_alias_match -v
```

12 test modules covering every pipeline stage:

| Module | Tests | Coverage |
|--------|-------|----------|
| test_schema.py | 17 | Schema loading + accessor functions |
| test_utils.py | 14 | Paths, hashing, wikilinks, provenance I/O |
| test_provenance.py | 14 | Claim tracking, staleness detection |
| test_state.py | 19 | _state.json + _health.json generation |
| test_extract.py | 20 | Source classification, dedup, registration |
| test_validate.py | 19 | Frontmatter, sections, wikilinks, fact/inference |
| test_link.py | 10 | Typed edge extraction, graph building |
| test_refine.py | 12 | Thin pages, contradictions, gaps, staleness |
| test_lint.py | 20 | All 12 lint checks |
| test_consolidate.py | 12 | Duplicates, indexes, timelines, merge |
| test_query.py | 9 | Seed finding, graph traversal, context building |
| test_cli.py | 17 | All CLI subcommands |
| test_generate_instructions.py | 10 | CLAUDE.md generation |
| test_pipeline.py | 7 | Full pipeline integration |