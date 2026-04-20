# LLM Wiki — Skill for AI Agents

This folder contains the portable skill file (`SKILL.md`) for operating the LLM Wiki knowledge base from any AI agent.

## Quick Start for Any AI Agent

1. **Read `SKILL.md`** — contains the full operating instructions
2. **Read `CLAUDE.md`** — contains detailed system architecture
3. **Read `SCHEMA.yaml`** — contains the page constitution

## How to Use

Any AI agent that supports reading SKILL.md files can use this wiki:

```bash
# Ingest a document
wiki ingest --auto --no-retry /path/to/source.pdf --type concept

# Query the wiki
wiki query "What does the wiki know about X?" --depth 2

# Save useful synthesis
wiki save-answer "Title" --type concept
```

## Skill Activation

In Claude Code: `/wiki-ingest`
In other agents: Read `skill/SKILL.md` directly.

## LLM Setup

```bash
# Ollama (local, recommended)
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=qwen3.5:agentic

# Anthropic Claude (cloud)
export ANTHROPIC_API_KEY=sk-ant-...
```

## Repository

https://github.com/dimasyankauskas/llm-knowledge-base
