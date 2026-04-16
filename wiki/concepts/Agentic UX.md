---
confidence: MEDIUM
content_hash: 0361f9f201f729b0
created: '2026-04-15'
source_refs:
- '[source: ai-product-strategy-research-plan-google-2026-04-14T00-50-30.md, §Designing
  Agentic UX]'
tags:
- domain/ai
- topic/ux
- topic/agents
title: Agentic UX
type: concept
---

## Definition

Agentic UX is the design paradigm for user interfaces of autonomous AI agent systems. It replaces the traditional command-response chat model with goal-oriented workflows where the user articulates a desired outcome and the system autonomously plans, executes, and reports. The design space shifts from visible screen elements to invisible behavioral logic.

[source: ai-product-strategy-research-plan-google-2026-04-14T00-50-30.md, §Designing Agentic UX]

## Key Properties

- **Goal-oriented input**: Users express outcomes, not step-by-step instructions
- **Asynchronous execution**: Agents operate in the background without requiring continuous human attention
- **Three-phase lifecycle**: Pre-Action (intent), In-Action (execution), Post-Action (audit)
- **Trust through transparency**: Every autonomous action must be observable, understandable, and reversible
- **Interruptibility over completion**: Users must be able to intervene at any point without breaking the system

[source: ai-product-strategy-research-plan-google-2026-04-14T00-50-30.md, §Designing Agentic UX]

## How It Works

The agentic UX lifecycle divides into three phases, each with distinct design patterns:

**Pre-Action patterns** establish intent and boundaries before execution:
- *Intent Preview*: The agent presents a high-level execution plan for human verification, serving as a decision point rather than notification
- *Autonomy Dial*: A control mechanism allowing users to throttle agent independence from full autonomy (low-risk tasks) to explicit approval for every action (high-risk scenarios)
- *Draft and Justification*: The agent presents a proposed action with a chain-of-thought rationale rather than executing directly — critical for regulated industries

**In-Action patterns** provide ambient context during background execution:
- *Layered Status System*: Four-tier attention management — ambient badge, on-demand progress panel, interrupting attention notification, and auto-dismissing summary
- *Explainable Rationale and Confidence Signals*: Continuous transparency into the agent's certainty levels and reasoning path

**Post-Action patterns** ensure safety and recovery:
- *Action Audit and Undo*: Comprehensive chronological log of all agent actions coupled with rollback mechanisms
- *Escalation Pathways*: Structured interfaces where the agent routes complex exceptions to a human operator with immediate comprehensive context

## Relationships

- [[Ambient AI]]:implements — Agentic UX implements ambient orchestration patterns
- [[Multi-Agent Orchestration]]:extends — Multi-agent systems extend the agentic UX lifecycle across specialized workers
- [[Zero-Trust AI Design]]:prerequisite_of — Zero-trust security is prerequisite for trustworthy agentic UX
- [[Computer-Using Agents]]:extends — CUAs extend agentic UX into native GUI manipulation
- [[Agentic KPI Framework]]:cites — KPI framework measures agentic UX effectiveness
- [[Edge-First Architecture]]:trades_off — Edge-first constraints trade off with agentic UX complexity
- [[LinkedIn Semantic Search]]:cites — LinkedIn's semantic search is an agentic UX pattern applied to recruiting

[source: ai-product-strategy-research-plan-google-2026-04-14T00-50-30.md, §Designing Agentic UX]

## Open Questions

- How should agentic UX handle situations where the user's intent is ambiguous but the agent must act?
- What is the optimal granularity for the Autonomy Dial — per-task, per-domain, or per-session?
- Can agentic UX patterns generalize to non-AI autonomous systems (IoT, robotics)?

## Counter-Arguments & Data Gaps

- Most claims in this page derive from a single deep-research source; independent corroboration is needed to upgrade confidence to HIGH
- The frameworks described are prescriptive patterns, not empirically validated design standards — real-world adoption data is sparse

## Sources

- [source: ai-product-strategy-research-plan-google-2026-04-14T00-50-30.md, §Designing Agentic UX]
- [source: ai-product-strategy-research-plan-google-2026-04-14T00-50-30.md, §Core UX Patterns for Agentic Systems]