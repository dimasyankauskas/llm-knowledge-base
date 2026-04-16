# Active Sprint

## Current Focus
- Wiki operational with 13 pages (10 concepts, 3 entities) from 2 article sources
- **0 errors**, 22 warnings (20× UNMARKED_INFERENCE in facts_only sections, 2× NO_SOURCES false positives on index pages)
- Graph: 13 nodes, 42 typed edges — all connections bidirectional

## Immediate Priorities
- [ ] Add inline `[source: ...]` citations to Definition and Key Properties sections across all 10 concept pages to clear UNMARKED_INFERENCE warnings
- [ ] Fix NO_SOURCES false positive on `by-topic.md` and `recently-updated.md` (either prefix with `_` or add index-type skip in `check_sources()`)
- [ ] Deduplicate edges in graph builder (Ambient AI → Agentic UX appears twice in `_state.json`)
- [ ] Ingest additional sources to grow the knowledge graph beyond 13 nodes

## Backlog
- [ ] Semantic/embedding search to replace keyword-only query engine (needed at 50+ pages)
- [ ] `wiki extract-prompt` command to generate structured LLM prompts for page creation
- [ ] Consolidate `build_graph_json()` (utils.py) and `build_typed_graph()` (link.py) into single graph builder

---

# Strategic Constraints

- **Schema supremacy**: All structural decisions live in `SCHEMA.yaml`. Scripts read from it. Never hardcode page type rules in Python.
- **LLM = extraction engine, scripts = mechanical validators**: Zero LLM API calls in any script.
- **Obsidian-native**: All wiki pages are Obsidian-flavored Markdown. Wikilinks only.
- **Provenance-first**: Every page must have a `.provenance.json` sidecar. Content hashes track staleness.
- **200 tests passing**: No code changes without `pytest` verification.

---

# Open Questions

- At what page count does keyword-only search become unusable? Is 50 the real threshold or can tag-based scoring extend it?
- Should the ingestion workflow include an LLM extraction step, or keep the strict LLM-outside / scripts-inside separation?
- Would a `wiki diff` command for reviewing proposed page changes (instead of direct writes) improve the contradiction detection workflow?
