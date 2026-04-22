# Agent Quick Start

If you are an AI agent opening this repo, start here.

This project is a local, agent-native wiki for durable project memory. It is **not** a hosted chatbot and it does **not** rely on external model calls.

## Read Next

1. `AGENTS.md` — full operating instructions
2. `SCHEMA.yaml` — page rules and validation constitution
3. `README.md` — public overview and NotebookLM comparison
4. `ABOUT.md` — product explanation and practical use cases

## Core Workflow

- Use the active CLI agent for reading, reasoning, and writing.
- Use `wiki agent-ingest` to profile a source and get an extraction plan.
- Use `wiki pack --json` or `wiki query` to gather reusable context.
- Use `wiki validate`, `wiki link`, and `wiki lint` before promoting content.

## Why This Exists

NotebookLM is useful for hosted research notebooks. This repo is for knowledge that should live in your codebase, be versioned in git, and remain reusable by future CLI agents.
