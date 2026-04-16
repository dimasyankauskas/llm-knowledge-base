---
confidence: MEDIUM
content_hash: 8fccac9582e7f441
created: '2026-04-15'
entity_type: organization
source_refs:
- '[source: ai-product-strategy-research-plan-google-2026-04-14T00-50-30.md, §Ecosystem
  Pioneers and Technical Implementations]'
tags:
- domain/ai
- entity/organization
- topic/cua
- topic/desktop-automation
title: Adept AI
type: entity
---

## Overview

Adept AI is an SF Bay Area AI company specializing in desktop automation through an end-to-end multimodal architecture. Their strategic differentiator is the Adept Workflow Language (AWL), which translates natural language intent into prescriptive, reliable code for multimodal web interactions.

## Contributions

- **Fuyu-8B and Fuyu-Heavy models**: Proprietary models designed specifically to serve as digital agents, not general-purpose LLMs
- **Adept Workflow Language (AWL)**: An expressive, proprietary language operating as a syntactic subset of JavaScript ES6 that translates vague natural language intent into prescriptive, reliable, and easily authorable code for precise multimodal web interactions
- **Direct semantic understanding**: Bypasses costly visual rendering stacks, giving agents direct semantic understanding of the web, turning complex UIs into native protocols the LLM can manipulate with high reliability
- **Robustness against environmental variation**: The semantic approach provides greater robustness than pixel-based approaches when web pages change dynamically

## Relationships

- [[Computer-Using Agents]]:implements — Adept AI implements the CUA paradigm with AWL-based semantic understanding
- [[Zero-Trust AI Design]]:cites — AWL's code-first approach enables finer-grained permission controls than pixel-based CUA

## Sources

- [source: ai-product-strategy-research-plan-google-2026-04-14T00-50-30.md, §Ecosystem Pioneers and Technical Implementations]