# About LLM Knowledge Base

LLM Knowledge Base is an agent-native wiki for durable project memory.

It is designed for people who already work inside capable AI CLIs such as Codex, Claude Code, Gemini CLI, or similar tools. In that workflow, the active CLI agent is the intelligence: it reads sources, reasons about them, and writes atomic wiki pages. The wiki provides the durable substrate around that intelligence: source registration, schema validation, provenance, typed graph links, context packs, quality scoring, and maintenance triage.

## Core Idea

Most AI work disappears into chat history. The next session has to rediscover the same facts, re-read the same documents, and rebuild the same mental model.

This project turns that work into reusable memory:

```text
source documents
  -> active CLI agent extracts atomic pages
  -> wiki validates schema and provenance
  -> graph/context packs become reusable agent memory
  -> future agents start with grounded project knowledge
```

## What Makes This Version Different

The earlier direction centered on LLM-powered ingestion. That can work, but it makes the system fragile: model choice, timeout behavior, malformed frontmatter, and large-document truncation can dominate product quality.

This version flips the default:

```text
CLI agent = reasoning and writing
Wiki = memory, schema, provenance, graph, quality rails
External model = optional unattended automation
```

The default command for new sources is:

```bash
wiki agent-ingest ./path/to/source.md --type article
```

It does not call another model. It gives the current agent a source profile, merge candidates, citation rules, required page sections, and validation commands.

## Who It Is For

- AI CLI users who want project memory that survives across sessions.
- Product strategists and researchers turning long documents into reusable concepts.
- Engineering teams that want agent-readable context packs instead of ad hoc notes.
- Agents that need grounded claims, source trails, graph relationships, and health status.

## Human Value

- Turns messy documents into clean, cited concept pages.
- Preserves source provenance so claims remain inspectable.
- Exposes gaps, stale pages, contradictions, and missing links.
- Produces reusable briefs, case studies, playbooks, and decision memos.
- Keeps private data local by default.

## Agent Value

- Provides fast model-free context via `wiki pack --json`.
- Gives canonical facts and citation-backed claims.
- Reduces repeated source reading and context-window waste.
- Makes the knowledge base health visible before the agent relies on it.
- Works from any CLI that can run shell commands and read/write files.

## Public Repo Policy

The repository is published data-free by default:

- `sources/` contains only scaffolding and an empty manifest.
- `wiki/` contains only empty runtime folders.
- generated state, graph, health, logs, and private wiki content are ignored.

Users bring their own sources locally. Those sources and generated wiki pages should not be committed unless they are intentionally public.

## Optional Model Automation

External/local models are still supported for unattended workflows:

```bash
wiki ingest ./path/to/source.md --auto
```

Use this when no active agent is supervising, or when you want a first-pass automated draft. For normal AI CLI work, prefer `wiki agent-ingest` plus direct agent extraction.
