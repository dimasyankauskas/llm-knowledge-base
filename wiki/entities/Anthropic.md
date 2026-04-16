---
confidence: HIGH
content_hash: 22afba1e6f8a6452
created: '2026-04-15'
entity_type: organization
source_refs:
- '[source: ai-product-strategy-research-plan-google-2026-04-14T00-50-30.md, §Ecosystem
  Pioneers and Technical Implementations]'
tags:
- domain/ai
- entity/organization
- topic/cua
title: Anthropic
type: entity
---

## Overview

Anthropic is an AI safety company based in the San Francisco Bay Area that has pioneered Computer-Using Agent (CUA) capabilities with its Claude model family. The company introduced dedicated computer use tools in Claude Sonnet 4.5 and Opus 4.6, enabling autonomous desktop interaction through screenshot analysis and simulated mouse/keyboard control.

## Contributions

- **Claude Computer Use**: Introduced CUA capabilities allowing models to autonomously capture screenshots, interpret visual data, and control the mouse to click, drag, and input keyboard commands across desktop environments
- **Zero Data Retention (ZDR)**: Implemented for enterprise computer use, ensuring sensitive desktop data transmitted during the visual feedback loop is immediately discarded rather than stored
- **SWE-bench performance**: Claude models demonstrated strong performance on rigorous coding and agentic task benchmarks
- **Iterative feedback loop**: Architecture emphasizes continuous visual state assessment after each action to determine the next move

## Relationships

- [[Computer-Using Agents]]:implements — Anthropic implements the CUA paradigm with Claude computer use tools
- [[Zero-Trust AI Design]]:implements — ZDR policy is a zero-trust implementation for CUA security

## Sources

- [source: ai-product-strategy-research-plan-google-2026-04-14T00-50-30.md, §Ecosystem Pioneers and Technical Implementations]