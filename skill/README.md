# LLM Wiki — Skill for AI Agents

This folder contains the portable skill file (`SKILL.md`) for operating the LLM Wiki knowledge base from any AI agent.

## Quick Start for Any AI Agent

1. **Read `SKILL.md`** — contains the full operating instructions
2. **Read `CLAUDE.md`** — contains detailed system architecture
3. **Read `SCHEMA.yaml`** — contains the page constitution

## How to Use

Any AI agent that supports reading SKILL.md files can use this wiki:

```bash
# Create a model-free ingestion plan for the active agent
wiki agent-ingest /path/to/source.md --type article

# Retrieve agent-ready context without calling another model
wiki pack "What does the wiki know about X?" --json

# Optional: query with synthesis if an LLM provider is configured
wiki query "What does the wiki know about X?" --depth 2

# Save useful synthesis
wiki save-answer "Title" --type concept
```

## Agent Instruction Files

| File | Agent |
|------|-------|
| `CLAUDE.md` | Claude Code |
| `GEMINI.md` | Gemini CLI |
| `AGENTS.md` | Codex, Copilot, others |
| `skill/SKILL.md` | Any agent (portable) |

## Skill Activation

In Claude Code: `/llm-wiki`
In other agents: Read `skill/SKILL.md` directly.

## LLM Setup

LLM credentials are optional. The default agent-first workflow uses the current CLI agent plus model-free wiki commands such as `agent-ingest`, `pack`, `triage`, `validate`, `rebuild`, `quality`, and `coverage`.

Configure a provider only for unattended `wiki ingest --auto` or `wiki query` synthesis.

```bash
export OLLAMA_BASE_URL=http://localhost:11434
export OLLAMA_MODEL=qwen3.5:agentic
```

## Repository

https://github.com/dimasyankauskas/llm-knowledge-base
