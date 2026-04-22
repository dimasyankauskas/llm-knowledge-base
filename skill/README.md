# LLM Wiki — Skill for AI Agents

This folder contains the portable skill file (`SKILL.md`) for operating the LLM Wiki knowledge base from any AI agent.

The goal is simple: help agents use the system correctly on the first try.

## Quick Start for Any AI Agent

1. **Read `SKILL.md`** — contains the full operating instructions
2. **Read `AGENTS.md`** — contains detailed system architecture and rules
3. **Read `SCHEMA.yaml`** — contains the page constitution

## How to Use

Any AI agent that supports reading SKILL.md files can use this wiki:

```bash
# Create a model-free ingestion plan for the active agent
wiki agent-ingest /path/to/source.md --type article

# Retrieve agent-ready context without calling another model
wiki pack "What does the wiki know about X?" --json

# Query assembles graph-traversed context (no model calls)
wiki query "What does the wiki know about X?" --depth 2

# Save last query context as a draft page
wiki save-answer "Title" --type concept
```

## What Agents Should Remember

- The wiki is the memory layer, not the main reasoning engine.
- The active CLI agent should read sources, write drafts, and verify results.
- Use `wiki pack --json` for compact context handoff.
- Use `wiki query` when you want the graph-traversed context assembled for you.
- Use `wiki agent-ingest` when you want an extraction plan before writing.
- This repo intentionally does not rely on external model calls.

## NotebookLM Contrast

- NotebookLM is good for hosted research notebooks and guided summaries.
- This wiki is good when the output should live in your repo, be versioned in git, and remain editable by future CLI agents.
- If an agent already uses NotebookLM MCP, that can help with research, but it does not replace this repo’s durable file-based workflow.

## Agent Instruction Files

| File | Agent |
|------|-------|
| `AGENTS.md` | Codex, Copilot, others |
| `skill/SKILL.md` | Any agent (portable) |

## Skill Activation

In Claude Code: `/llm-wiki`
In other agents: Read `skill/SKILL.md` directly.

## Model Calls

This repository intentionally performs **no external model calls**. Use your active CLI agent for reasoning/writing; use the wiki for memory, validation, provenance, and retrieval context.

## Repository

https://github.com/dimasyankauskas/llm-knowledge-base
