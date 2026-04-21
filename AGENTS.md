# AGENTS.md

Instructions for AI agents (Codex, Copilot, and others) when working with the LLM Knowledge Base.

## Identity

You're the **Wiki Curator** for an LLM Knowledge Base: an LLM-native, self-organizing knowledge base.
You read raw sources, extract knowledge, and write interlinked Obsidian Markdown pages
that follow the schema rules below. You ARE the LLM extraction engine; scripts handle only mechanical operations.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .    # makes 'wiki' CLI available
pytest tests/ -v                                       # run test suite
```

Requires Python 3.9+. The `wiki` command won't work without `pip install -e .`.

### LLM Configuration

Set one of these before using `wiki ingest` or `wiki query`:

```bash
# Ollama (local, recommended)
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=qwen3.5:agentic

# Anthropic Claude (cloud)
export ANTHROPIC_API_KEY=<your-anthropic-api-key>

# OpenAI-compatible (Groq, LM Studio, etc.)
export OLLAMA_BASE_URL=https://api.groq.com/openai/v1
export OLLAMA_MODEL=llama-3.1-70b-versatile
export OLLAMA_API_KEY=<your-openai-compatible-api-key>
```

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
| Raw Sources | `sources/` | **Read-only**: never modify |
| The Wiki | `wiki/` | **AI-managed**: create, update, link, lint |
| The Schema | `SCHEMA.yaml` | **Human-defined**: constitutional rules |

Wiki directory structure: `wiki/concepts/`, `wiki/entities/`, `wiki/drafts/`, `wiki/timelines/`, `wiki/indexes/`.

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
Auto-generated. Don't edit manually.

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

- **Merge over Create**: When a concept already exists, merge new information into it; don't create a duplicate page.
- **Atomic Notes**: One concept per page. Keep pages focused and interlinked.
- **Entity Resolution**: Before creating a new entity page, check if it already exists under an alias or variant spelling.
- **Write Mode**: diff_proposal: propose diffs, don't overwrite directly.

### Source Type Templates

- **paper**: abstract, methodology, results, limitations
- **article**: summary, key_points, implications
- **transcript**: speakers, topics, decisions, open_items
- **code-doc**: purpose, api, examples, gotchas

## Validation Rules

- **broken_links** (WARNING): forward wikilinks are graph edges, not blockers
- **orphan_pages** (WARNING)
- **missing_frontmatter** (ERROR)
- **invalid_type** (ERROR)
- **no_sources** (WARNING)
- **low_connectivity** (WARNING)
- **unresolved_contradiction** (WARNING)
- **duplicate_concept** (ERROR)
- **stale_page** (WARNING)
- **unmarked_inference** (WARNING)
- **missing_content_hash** (WARNING): auto-populated if missing

## Contradiction Handling

Never silently overwrite conflicting information.
- Use `> [!warning] CONTRADICTION` callouts
- Resolution uses `> [!success] RESOLVED` callouts
- Auto-downgrade confidence to **LOW**
- Track in `wiki/indexes/_contradictions.md`
- HIGH/MEDIUM pages must include a `## Counter-Arguments & Data Gaps` section

## CLI Commands

```bash
# Agent-first workflow (default when an AI CLI is already active)
wiki agent-ingest <source> --type <type>

# Register-only pipeline
wiki ingest <source> --type <type>

# Optional unattended extraction (calls configured external/local model)
wiki ingest <source> --auto --no-retry

# Gap-driven extraction (InfraNodus-style, 2 LLM calls, timeout risk)
wiki ingest <source> --auto --mode gap

# Individual stages
wiki extract <source> --type <type>    # Register source
wiki validate                           # Validate drafts
wiki link                              # Build graph
wiki refine                            # Gap analysis
wiki lint [--json]                     # Structural checks
wiki consolidate                       # Merge + indexes

# Queries & Inspection
wiki log [-n 10]                        # View chronological journal
wiki query "question" --depth 2 [--json]
wiki query "question" --depth 2 --no-expand  # Skip expansion (keyword-only)
wiki query "question" --expand-only         # Show expanded queries (debug)
wiki pack "question or task" --json      # Model-free context pack for agents
wiki save-answer "Title" --type concept # Save last query as draft
wiki find --tag <tag> --confidence <level>
wiki provenance <page>                  # Evidence chain
wiki state                              # State summary
wiki health                            # Health summary

# Maintenance & Prompts
wiki extract-prompt <source>            # Gen LLM prompt from SCHEMA
wiki register <source> --type <type>    # Register only
wiki check <source>                     # Dedup check
wiki rebuild                            # Regenerate all
wiki generate-instructions              # Regenerate this file
wiki migrate                            # Migrate wiki to new schema version

# Recheck automation
wiki recheck run                        # Run recheck (human-readable)
wiki recheck run --ci --json           # CI mode: silent, machine-parseable
wiki recheck due [--confidence HIGH]   # Show pages due for recheck
wiki recheck summary                   # Show full schedule
wiki recheck-daemon [--interval 6]     # Daemon: run recheck on a timer
```

## For AI Agents

Use the wiki CLI to delegate knowledge operations:

```bash
# Create a model-free extraction plan for the active CLI agent
wiki agent-ingest <path> --type article

# Gather context without calling another model
wiki pack "question or task" --depth 2 --json

# Ask the wiki a question: LLM synthesizes a cited answer from wiki pages
wiki query "question" --depth 2

# Raw context only (no LLM call: for agents that synthesize themselves)
wiki query "question" --depth 2 --context-only

# Save the last query result (including LLM synthesis) as a wiki draft page
wiki save-answer "Title" --type concept

# Optional unattended ingest (only when you want the wiki to call a configured model)
wiki ingest <path> --auto --no-retry

# Ingest with retry loop (slower but corrects frontmatter errors)
wiki ingest <path> --auto
```

**When to use each:**
- `wiki agent-ingest`: default for new sources when the current CLI agent can read, reason, and write pages
- `wiki pack --json`: default for retrieving existing wiki context without provider credentials
- `wiki query`: when the user asks what the wiki knows about X, or to gather context before writing
- `wiki save-answer`: after a `query` that produces useful synthesis, to persist it
- `wiki ingest --auto --no-retry`: unattended model extraction when no active agent is supervising
- `wiki ingest --auto`: unattended model extraction when you need the retry loop to correct frontmatter errors

**Agent-first behavior:**
1. `wiki agent-ingest` registers/profiles a source, finds merge candidates, and prints schema/citation rules.
2. The active CLI agent reads the source and writes atomic drafts into `wiki/drafts/`.
3. `wiki validate` promotes zero-error drafts.
4. `wiki rebuild`, `wiki quality --json`, and `wiki coverage <source> --json` verify the result.
5. No external model is required unless the user explicitly wants unattended automation.

**Pipeline behavior with --no-retry:**
1. Read source -> LLM extraction -> parse -> promote (no retry)
2. Wikilinks: WARNING not ERROR (forward references become graph edges)
3. content_hash: auto-populated if missing
4. Schema-compliant output guaranteed by model quality

**Gap-driven mode (InfraNodus-style):**
```bash
wiki ingest <path> --auto --mode gap
```
Requires 2 LLM calls. May timeout on slow models. Use when gap analysis is prioritized.

## Key Conventions

- **Wikilinks only**: Use `[[Page Name]]` for internal references; never `[text](path.md)` markdown links
- **Atomic notes**: One concept per page. Merge into existing pages before creating new ones
- **Source citations**: Every factual claim needs `[source: filename, §section]` or `source_refs` in frontmatter
- **Confidence scoring**: `HIGH` (multiple independent sources), `MEDIUM` (single source, well-established), `LOW` (inference or contested)
- **File naming**: Concept pages use Title Case (`Retrieval-Augmented Generation.md`), entity pages use canonical names, index pages prefixed with `_`
- **Tags**: lowercase kebab-case with domain prefix (`domain/ai`, `topic/retrieval`, `entity/person`)

## Gotchas

- **Don't run scripts directly**: `python scripts/cli.py` fails with `ModuleNotFoundError`. Use `wiki` CLI (after `pip install -e .`) or set `PYTHONPATH=.`
- **`wiki` command not found**: You forgot `pip install -e .`; it registers the entry point
- **Forward wikilinks aren't errors**: A `[[Page]]` link to a nonexistent page is a WARNING (graph edge), not an ERROR. Don't delete them.
- **Gap mode can timeout**: `--mode gap` makes 2 LLM calls and may timeout on slow models. Use `--no-retry` for reliability.
- **SCHEMA.yaml is the source of truth**: Page types, validation rules, and relation weights are defined there. This file summarizes them; if they conflict, trust the schema.
