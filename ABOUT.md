# About LLM Knowledge Base

LLM Knowledge Base is a local, agent-native wiki for durable project memory.

It is built for a simple reality: capable AI agents already know how to read, reason, and write. The missing layer is memory you can trust after the chat ends. This project gives agents and humans a shared substrate: source registration, schema validation, provenance, typed graph links, context packs, quality scoring, and maintenance triage.

## The Problem

Most AI work disappears into the session that produced it. The next agent has to re-read the same sources, rebuild the same context, and rediscover the same trade-offs. That is expensive in tokens, time, and attention.

Raw RAG helps retrieve text. It does not, by itself, turn a messy domain into a maintained body of knowledge.

## The Product

LLM Knowledge Base compiles source documents into an inspectable Markdown wiki:

```text
source documents
  -> active CLI agent extracts atomic pages
  -> wiki validates schema, citations, and graph links
  -> context packs become reusable agent memory
  -> future agents start from grounded project knowledge
```

The default workflow is deliberately agent-first:

```bash
wiki agent-ingest ./path/to/source.md --type article
```

That command does not call another model. It profiles the source, registers its hash, finds merge candidates, shows required sections, and gives the active CLI agent the exact validation path.

## What Makes This Version Different

The earlier direction centered on model-powered ingestion. That can work for unattended automation, but it makes the wrong thing central: model choice, timeout behavior, malformed frontmatter, and truncation can dominate the user experience.

This version changes the center of gravity:

```text
CLI agent = reasoning and writing
Wiki = memory, schema, provenance, graph, quality rails
External model = optional automation
```

If you already have Codex, Claude Code, Gemini CLI, or another capable agent in the loop, the wiki should not compete with it. It should make that agent better.

## Human Value

- Turn long documents into clean, cited concept pages.
- Keep source trails attached to the claims they support.
- See gaps, stale pages, contradictions, thin pages, and missing links.
- Produce reusable briefs, playbooks, case studies, and decision memos.
- Keep private source data local by default.

## Agent Value

- Retrieve fast, model-free context with `wiki pack --json`.
- Start from canonical facts instead of re-reading every source.
- See wiki health before relying on the knowledge base.
- Use typed relationships to understand why concepts belong together.
- Work from any CLI that can run shell commands and read/write files.

## What It Is Not

- Not a hosted product.
- Not a vector database wrapper.
- Not a second agent pretending to be smarter than the active agent.
- Not a black box. The output is Markdown, JSON, YAML, and git-friendly files.

## Public Repo Policy

The repository is published as a clean template:

- `sources/` contains only scaffolding and an empty manifest.
- `wiki/` contains only empty runtime folders.
- Generated state, graph, health, logs, and private wiki content are ignored.
- `.venv/` is ignored and not part of the public repo.

Users bring their own sources locally. Commit source files and generated wiki pages only when those documents are intentionally public.

## Model Calls

This repository intentionally performs **no external model calls**. The active CLI agent is the extraction/synthesis engine; the wiki is the memory + validation substrate.
