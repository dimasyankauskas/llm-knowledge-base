# Antigravity Wiki v2 (Mission Wiki)

An LLM-native, self-organizing knowledge base inspired by Andrej Karpathy's "LLM Wiki" concept. This system uses a schema-driven architecture where an LLM acts as the "Wiki Curator," extracting and formatting knowledge, while Python scripts enforce structural integrity, typed relations, and provenance tracking.

## Architecture

The wiki is organized into three distinct layers where mutability decreases downwards:

1. **Raw Sources (`sources/`)**: Immutable PDF, text, and markdown files.
2. **The Wiki (`wiki/`)**: AI-managed Obsidian-flavored markdown pages linked as a knowledge graph.
3. **The Schema (`SCHEMA.yaml`)**: The human-defined constitutional rules governing page extraction and structural conventions.

## Features

- **Schema-Driven Extraction**: `SCHEMA.yaml` defines what an entity or concept looks like.
- **Typed Knowledge Graph**: Edges between pages specify the type of relationship (`implements`, `contradicts`, `cites`).
- **Provenance Tracking**: Every extracted fact traces back to the exact source document.
- **Continuous Linting**: 12 strict structural checks (e.g. `orphan_pages`, `missing_frontmatter`, `unmarked_inference`).
- **Chronological Journal**: Operations and changes are automatically appended to a chronological `log.md`.
- **Knowledge Compounding Loop**: Query the graph, then save the output directly back in as an integrated page.
- **Index-First Queries**: Fast, semantic-overlap scoring during context retrieval.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Quick Start
Here is the core iteration loop for expanding the knowledge base:

```bash
# 1. Ingest a new source document
wiki ingest sources/research-paper.pdf --type concept

# 2. Or generate a prompt template and paste into LLM manually
wiki extract-prompt my-paper.pdf --type concept
# Save LLM output in wiki/drafts/my-concept.md
wiki validate # Moves it out of draft if valid

# 3. Query the generated knowledge graph
wiki query "What is Agentic UX?"

# 4. Save your insight back into the wiki
wiki save-answer "Agentic UX" --type concept
```

For full system instructions, read [CLAUDE.md](./CLAUDE.md). This file acts as the AI Agent's instruction manual and is maintained automatically via `wiki generate-instructions`.
