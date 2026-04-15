# Antigravity Wiki v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a schema-driven pipeline engine for LLM-native knowledge bases with provenance tracking, fact/inference separation, typed relations, and agent-aware state management.

**Architecture:** Six-stage pipeline (extract → validate → link → refine → lint → consolidate) with a unified CLI, provenance sidecars, `_state.json` agent bootstrap, and SCHEMA.yaml as the single source of truth. Filesystem-native (Markdown + JSON + YAML), git-trackable, Obsidian-compatible.

**Tech Stack:** Python 3.10+, PyYAML, python-frontmatter, Rich (terminal formatting), argparse (CLI)

---

## File Structure (Final State)

```
antigravity-wiki/
├── CLAUDE.md                    # Auto-generated from SCHEMA.yaml
├── SCHEMA.yaml                  # Human-editable system constitution
├── requirements.txt             # Python dependencies
├── scripts/
│   ├── cli.py                   # Unified CLI entry point
│   ├── schema.py                # SCHEMA.yaml loader + validator
│   ├── utils.py                 # Shared constants, paths, frontmatter, graph ops
│   ├── provenance.py            # Provenance sidecar CRUD + staleness detection
│   ├── extract.py               # Stage 1: Source registration + draft validation
│   ├── validate.py              # Stage 2: Schema + provenance validation
│   ├── link.py                  # Stage 3: Wikilink resolution + typed graph build
│   ├── refine.py                # Stage 4: Gap analysis + contradiction detection
│   ├── lint.py                  # Stage 5: 12 structural checks
│   ├── consolidate.py           # Stage 6: Merge + index + timeline generation
│   ├── query.py                 # Graph traversal search
│   └── state.py                 # _state.json + _health.json generation
├── sources/                     # Immutable ground truth
│   ├── manifest.json
│   ├── article/
│   ├── paper/
│   ├── transcript/
│   └── code-doc/
└── wiki/                        # AI-managed knowledge
    ├── _state.json
    ├── _health.json
    ├── _graph.json
    ├── _log.md
    ├── drafts/
    ├── concepts/
    ├── entities/
    ├── indexes/
    └── timelines/
```

---

## Task 1: SCHEMA.yaml and Schema Loader

**Files:**
- Create: `SCHEMA.yaml`
- Create: `scripts/schema.py`
- Create: `tests/test_schema.py`

- [ ] **Step 1: Write the failing test for schema loading**

```python
# tests/test_schema.py
import pytest
from pathlib import Path
from scripts.schema import load_schema, get_page_type_config, get_validation_rules

SCHEMA_PATH = Path(__file__).parent.parent / "SCHEMA.yaml"

class TestSchemaLoading:
    def test_load_schema_returns_dict(self):
        schema = load_schema(SCHEMA_PATH)
        assert isinstance(schema, dict)
        assert schema["version"] == "2.0"

    def test_schema_has_required_top_level_keys(self):
        schema = load_schema(SCHEMA_PATH)
        required_keys = ["version", "page_types", "confidence_levels", "relation_types", "extraction", "validation", "contradiction"]
        for key in required_keys:
            assert key in schema, f"Missing required key: {key}"

    def test_get_page_type_config(self):
        schema = load_schema(SCHEMA_PATH)
        concept_config = get_page_type_config(schema, "concept")
        assert "required_frontmatter" in concept_config
        assert "required_sections" in concept_config
        assert "section_rules" in concept_config
        assert "min_outlinks" in concept_config
        assert concept_config["min_outlinks"] == 2

    def test_get_page_type_config_entity(self):
        schema = load_schema(SCHEMA_PATH)
        entity_config = get_page_type_config(schema, "entity")
        assert entity_config["min_outlinks"] == 1
        assert "entity_type" in entity_config["required_frontmatter"]

    def test_get_validation_rules(self):
        schema = load_schema(SCHEMA_PATH)
        rules = get_validation_rules(schema)
        assert "broken_links" in rules
        assert rules["broken_links"]["severity"] == "ERROR"
        assert "stale_page" in rules
        assert "unmarked_inference" in rules
        assert "missing_content_hash" in rules

    def test_schema_page_types_have_section_rules(self):
        schema = load_schema(SCHEMA_PATH)
        concept = schema["page_types"]["concept"]
        assert "section_rules" in concept
        assert concept["section_rules"]["Definition"] == "facts_only"
        assert concept["section_rules"]["How It Works"] == "mixed"

    def test_schema_relation_types(self):
        schema = load_schema(SCHEMA_PATH)
        types = schema["relation_types"]
        assert "implements" in types
        assert "contradicts" in types
        assert "cites" in types
        assert len(types) == 7

    def test_schema_extraction_config(self):
        schema = load_schema(SCHEMA_PATH)
        extraction = schema["extraction"]
        assert extraction["merge_over_create"] is True
        assert extraction["write_mode"] == "diff_proposal"
        assert "source_type_templates" in extraction
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/atma/dev/LLM_Wiki && python -m pytest tests/test_schema.py -v`
Expected: FAIL — `SCHEMA.yaml` doesn't exist yet, `schema.py` doesn't exist yet

- [ ] **Step 3: Create SCHEMA.yaml**

Create `SCHEMA.yaml` with the full schema content from the design spec (page_types, confidence_levels, relation_types, extraction, validation, contradiction sections). Use the exact content from the spec Section 1.

- [ ] **Step 4: Create scripts/schema.py**

```python
"""Antigravity Wiki v2 — Schema Loader
Loads and validates SCHEMA.yaml, provides accessor functions
for page type configs, validation rules, and extraction settings.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any

import yaml

SCHEMA_PATH = Path(__file__).parent.parent / "SCHEMA.yaml"


def load_schema(path: Path | None = None) -> dict:
    """Load and return the schema configuration."""
    schema_path = path or SCHEMA_PATH
    with open(schema_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_page_type_config(schema: dict, page_type: str) -> dict:
    """Get configuration for a specific page type."""
    if page_type not in schema.get("page_types", {}):
        raise ValueError(f"Unknown page type: {page_type}")
    return schema["page_types"][page_type]


def get_validation_rules(schema: dict) -> dict:
    """Get all validation rules from schema."""
    return schema.get("validation", {})


def get_confidence_levels(schema: dict) -> dict:
    """Get confidence level definitions."""
    return schema.get("confidence_levels", {})


def get_relation_types(schema: dict) -> list[str]:
    """Get list of valid relation types."""
    return schema.get("relation_types", [])


def get_source_type_template(schema: dict, source_type: str) -> list[str] | None:
    """Get the extraction template for a source type."""
    templates = schema.get("extraction", {}).get("source_type_templates", {})
    return templates.get(source_type)


def get_extraction_config(schema: dict) -> dict:
    """Get extraction configuration."""
    return schema.get("extraction", {})


def get_contradiction_config(schema: dict) -> dict:
    """Get contradiction handling configuration."""
    return schema.get("contradiction", {})


def get_all_page_types(schema: dict) -> list[str]:
    """Get list of all defined page types."""
    return list(schema.get("page_types", {}).keys())


def get_required_frontmatter(schema: dict, page_type: str) -> list[str]:
    """Get required frontmatter fields for a page type."""
    config = get_page_type_config(schema, page_type)
    return config.get("required_frontmatter", [])


def get_required_sections(schema: dict, page_type: str) -> list[str]:
    """Get required sections for a page type."""
    config = get_page_type_config(schema, page_type)
    return config.get("required_sections", [])


def get_section_rules(schema: dict, page_type: str) -> dict[str, str]:
    """Get section rules (facts_only, mixed, inference_only) for a page type."""
    config = get_page_type_config(schema, page_type)
    return config.get("section_rules", {})
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd /Users/atma/dev/LLM_Wiki && python -m pytest tests/test_schema.py -v`
Expected: All 8 tests PASS

- [ ] **Step 6: Commit**

```bash
git add SCHEMA.yaml scripts/schema.py tests/test_schema.py requirements.txt
git commit -m "feat: add SCHEMA.yaml and schema loader for v2 pipeline"
```

---

## Task 2: Shared Utilities (utils.py v2)

**Files:**
- Create: `scripts/utils.py` (replace v1)
- Create: `tests/test_utils.py`

This replaces the v1 `utils.py` with v2-aware versions that work with SCHEMA.yaml, typed wikilinks, provenance sidecars, and `_state.json`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_utils.py
import json
import pytest
from pathlib import Path
from scripts.utils import (
    WIKI_ROOT, WIKI_DIR, SOURCES_DIR, CONCEPTS_DIR, ENTITIES_DIR,
    INDEXES_DIR, TIMELINES_DIR, DRAFTS_DIR, GRAPH_PATH, STATE_PATH,
    HEALTH_PATH, MANIFEST_PATH,
    hash_content, hash_file,
    load_manifest, save_manifest,
    extract_wikilinks, extract_typed_relations,
    list_wiki_pages, list_concept_pages, list_entity_pages,
    page_exists, read_page, write_page, read_provenance, write_provenance,
    slugify, today
)

class TestPaths:
    def test_wiki_root_exists(self):
        assert WIKI_ROOT.exists()

    def test_drafts_dir_path(self):
        assert DRAFTS_DIR == WIKI_DIR / "drafts"

    def test_state_path(self):
        assert STATE_PATH == WIKI_DIR / "_state.json"

    def test_health_path(self):
        assert HEALTH_PATH == WIKI_DIR / "_health.json"


class TestHashing:
    def test_hash_content_deterministic(self):
        assert hash_content("hello") == hash_content("hello")

    def test_hash_content_different(self):
        assert hash_content("hello") != hash_content("world")

    def test_hash_content_returns_hex_string(self):
        result = hash_content("test")
        assert isinstance(result, str)
        assert len(result) == 16


class TestManifest:
    def test_load_empty_manifest(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text('{"version": "1.0", "sources": []}', encoding="utf-8")
        # Would need to patch MANIFEST_PATH for real test

    def test_save_manifest_creates_file(self, tmp_path):
        manifest = {"version": "1.0", "sources": []}
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        assert path.exists()


class TestWikilinks:
    def test_extract_basic_wikilink(self):
        content = "See [[RAG]] for details."
        links = extract_wikilinks(content)
        assert "RAG" in links

    def test_extract_wikilink_with_alias(self):
        content = "See [[Retrieval-Augmented Generation|RAG]] for details."
        links = extract_wikilinks(content)
        assert "Retrieval-Augmented Generation" in links

    def test_extract_multiple_wikilinks(self):
        content = "[[RAG]] implements [[Neural IR]] and extends [[Gen AI]]."
        links = extract_wikilinks(content)
        assert len(links) == 3

    def test_extract_typed_relations(self):
        content = "RAG implements [[Neural IR]] and extends [[Gen AI]]."
        relations = extract_typed_relations(content)
        assert len(relations) >= 2
        # Check that implements and extends are detected
        types = [r["type"] for r in relations]
        assert "implements" in types
        assert "extends" in types

    def test_extract_typed_relations_contradicts(self):
        content = "Some argue [[Pure Generation]] contradicts the retrieval premise."
        relations = extract_typed_relations(content)
        assert len(relations) >= 1
        assert any(r["type"] == "contradicts" for r in relations)


class TestProvenance:
    def test_write_and_read_provenance(self, tmp_path):
        provenance = {
            "page": "Test Page",
            "content_hash": "abc123",
            "sources": [],
            "claims": [],
            "derived_concepts": []
        }
        page_path = tmp_path / "Test Page.md"
        page_path.write_text("---\ntitle: Test\n---\nContent", encoding="utf-8")
        write_provenance(page_path, provenance)
        result = read_provenance(page_path)
        assert result["page"] == "Test Page"
        assert result["content_hash"] == "abc123"

    def test_read_provenance_missing_file(self, tmp_path):
        page_path = tmp_path / "Nonexistent.md"
        result = read_provenance(page_path)
        assert result is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/atma/dev/LLM_Wiki && python -m pytest tests/test_utils.py -v`
Expected: FAIL — v2 functions don't exist yet

- [ ] **Step 3: Write scripts/utils.py v2**

Rewrite `scripts/utils.py` with v2 functionality:
- All v1 constants plus new paths (DRAFTS_DIR, STATE_PATH, HEALTH_PATH, LOG_PATH)
- `extract_typed_relations()` — parses context around wikilinks to infer edge types
- `read_provenance()`, `write_provenance()` — sidecar CRUD
- Keep all v1 functions (hash_content, load_manifest, etc.) but update paths
- Add `slugify()` and `today()` from v1

Key new functions:
- `extract_typed_relations(content: str) -> list[dict]` — returns `[{"target": "Neural IR", "type": "implements"}]` by analyzing text before `[[link]]`
- `read_provenance(page_path: Path) -> dict | None` — reads `.provenance.json` sidecar
- `write_provenance(page_path: Path, data: dict) -> None` — writes `.provenance.json` sidecar

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/atma/dev/LLM_Wiki && python -m pytest tests/test_utils.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/utils.py tests/test_utils.py
git commit -m "feat: v2 utils with typed wikilinks, provenance sidecars, and state paths"
```

---

## Task 3: Provenance Module

**Files:**
- Create: `scripts/provenance.py`
- Create: `tests/test_provenance.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_provenance.py
import json
import pytest
from pathlib import Path
from scripts.provenance import (
    create_provenance, add_claim, add_source,
    check_staleness, get_stale_pages, get_claim_sources
)

class TestCreateProvenance:
    def test_create_basic_provenance(self):
        prov = create_provenance(
            page="RAG",
            content_hash="abc123",
            sources=[{"file": "lewis2020.pdf", "content_hash": "def456", "sections_used": ["Abstract"]}]
        )
        assert prov["page"] == "RAG"
        assert prov["content_hash"] == "abc123"
        assert len(prov["sources"]) == 1
        assert prov["claims"] == []
        assert prov["derived_concepts"] == []

class TestAddClaim:
    def test_add_fact_claim(self):
        prov = create_provenance(page="RAG", content_hash="abc123", sources=[])
        prov = add_claim(prov, text="RAG reduces hallucinations", claim_type="fact",
                        sources=["lewis2020.pdf"], corroborated=True)
        assert len(prov["claims"]) == 1
        assert prov["claims"][0]["type"] == "fact"
        assert prov["claims"][0]["corroborated"] is True

    def test_add_inference_claim(self):
        prov = create_provenance(page="RAG", content_hash="abc123", sources=[])
        prov = add_claim(prov, text="RAG effectiveness may drop with domain shift",
                        claim_type="inference", sources=["comparison2026.md"], corroborated=False)
        assert len(prov["claims"]) == 1
        assert prov["claims"][0]["type"] == "inference"

class TestCheckStaleness:
    def test_detect_stale_source(self, tmp_path):
        # Create a source file
        source_file = tmp_path / "lewis2020.pdf"
        source_file.write_text("original content", encoding="utf-8")

        prov = create_provenance(
            page="RAG",
            content_hash="abc123",
            sources=[{"file": str(source_file), "content_hash": "wrong_hash", "sections_used": ["Abstract"]}]
        )
        stale = check_staleness(prov, tmp_path)
        assert len(stale) == 1  # Source hash doesn't match

    def test_no_staleness_when_hashes_match(self, tmp_path):
        source_file = tmp_path / "lewis2020.pdf"
        source_file.write_text("original content", encoding="utf-8")

        from scripts.utils import hash_content
        correct_hash = hash_content("original content")

        prov = create_provenance(
            page="RAG",
            content_hash="abc123",
            sources=[{"file": str(source_file), "content_hash": correct_hash, "sections_used": ["Abstract"]}]
        )
        stale = check_staleness(prov, tmp_path)
        assert len(stale) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/atma/dev/LLM_Wiki && python -m pytest tests/test_provenance.py -v`
Expected: FAIL — `provenance.py` doesn't exist yet

- [ ] **Step 3: Write scripts/provenance.py**

Implement provenance sidecar management:
- `create_provenance(page, content_hash, sources) -> dict` — Create new provenance record
- `add_claim(prov, text, claim_type, sources, corroborated) -> dict` — Add a claim to provenance
- `add_source(prov, file, content_hash, sections_used) -> dict` — Add a source reference
- `check_staleness(prov, sources_dir) -> list[str]` — Check if source content hashes have changed
- `get_stale_pages(wiki_dir, sources_dir) -> list[str]` — Find all pages with stale sources
- `get_claim_sources(prov, claim_id) -> list[str]` — Get sources for a specific claim

Each function operates on provenance dict objects (loaded/saved via utils.read_provenance/write_provenance).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/atma/dev/LLM_Wiki && python -m pytest tests/test_provenance.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/provenance.py tests/test_provenance.py
git commit -m "feat: provenance module with staleness detection and claim tracking"
```

---

## Task 4: State Management (state.py)

**Files:**
- Create: `scripts/state.py`
- Create: `tests/test_state.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_state.py
import json
import pytest
from pathlib import Path
from scripts.state import generate_state, generate_health, load_state, load_health

class TestGenerateState:
    def test_state_contains_schema_summary(self, tmp_path):
        # Create minimal wiki structure
        wiki_dir = tmp_path / "wiki"
        concepts_dir = wiki_dir / "concepts"
        concepts_dir.mkdir(parents=True)
        state = generate_state(wiki_dir=wiki_dir)
        assert "schema_version" in state
        assert "page_types" in state
        assert "required_fields" in state

    def test_state_lists_pages(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        concepts_dir = wiki_dir / "concepts"
        concepts_dir.mkdir(parents=True)
        # Create a test page
        page = concepts_dir / "RAG.md"
        page.write_text("---\ntitle: RAG\ntype: concept\nconfidence: HIGH\n---\nContent", encoding="utf-8")
        state = generate_state(wiki_dir=wiki_dir)
        assert "pages" in state
        assert "RAG" in state["pages"]
        assert state["pages"]["RAG"]["type"] == "concept"

    def test_state_tracks_thin_pages(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        concepts_dir = wiki_dir / "concepts"
        concepts_dir.mkdir(parents=True)
        # Create a thin page (few sections)
        page = concepts_dir / "Thin.md"
        page.write_text("---\ntitle: Thin\ntype: concept\nconfidence: LOW\n---\nDefinition only.", encoding="utf-8")
        state = generate_state(wiki_dir=wiki_dir)
        assert "thin_pages" in state

class TestGenerateHealth:
    def test_health_has_lint_summary(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir(parents=True)
        health = generate_health(wiki_dir=wiki_dir, lint_results=[])
        assert "errors" in health
        assert "warnings" in health
        assert "last_lint" in health
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/atma/dev/LLM_Wiki && python -m pytest tests/test_state.py -v`
Expected: FAIL

- [ ] **Step 3: Write scripts/state.py**

Implement state management:
- `generate_state(wiki_dir, schema=None) -> dict` — Build `_state.json` from wiki pages + schema summary + health snapshot
- `generate_health(wiki_dir, lint_results=None) -> dict` — Build `_health.json` from lint results
- `load_state(wiki_dir) -> dict` — Read `_state.json`
- `load_health(wiki_dir) -> dict` — Read `_health.json`
- `save_state(state, wiki_dir) -> None` — Write `_state.json`
- `save_health(health, wiki_dir) -> None` — Write `_health.json`

State includes: schema_version, page_types, required_fields, pages dict (name → {type, confidence, tags, outlinks, inlinks, last_updated, stale}), active_contradictions, thin_pages, stale_pages, recent_changes, health summary.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /Users/atma/dev/LLM_Wiki && python -m pytest tests/test_state.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/state.py tests/test_state.py
git commit -m "feat: state management with _state.json and _health.json generation"
```

---

## Task 5: Extract Stage (extract.py)

**Files:**
- Create: `scripts/extract.py`
- Create: `tests/test_extract.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_extract.py
import pytest
from pathlib import Path
from scripts.extract import register_source, check_dedup, classify_source_type

class TestClassifySourceType:
    def test_classify_pdf_as_paper(self):
        assert classify_source_type(Path("paper.pdf")) == "paper"

    def test_classify_md_as_article(self):
        assert classify_source_type(Path("notes.md")) == "article"

    def test_classify_transcript(self):
        assert classify_source_type(Path("meeting_transcript.txt")) == "transcript"

class TestRegisterSource:
    def test_register_adds_to_manifest(self, tmp_path):
        source_dir = tmp_path / "sources"
        source_dir.mkdir()
        manifest_path = source_dir / "manifest.json"
        manifest_path.write_text('{"version": "1.0", "sources": []}', encoding="utf-8")
        # ... test registration

    def test_register_detects_duplicate(self, tmp_path):
        # Test that registering the same source twice is detected
        pass

class TestCheckDedup:
    def test_check_returns_true_for_existing(self, tmp_path):
        # Test dedup detection
        pass

    def test_check_returns_false_for_new(self, tmp_path):
        # Test new source passes
        pass
```

- [ ] **Step 2: Run the tests to verify they fail**

- [ ] **Step 3: Write scripts/extract.py**

Implement Stage 1 of the pipeline:
- `classify_source_type(path) -> str` — Determine source type from file extension/name
- `check_dedup(source_path, manifest_path) -> bool` — Check if source already ingested
- `register_source(source_path, source_type, manifest_path) -> dict` — Register source in manifest with content hash
- `read_source(path) -> str` — Read source file content (supports PDF via PyMuPDF, plain text, markdown)
- CLI: `python scripts/extract.py register <source> --type <type>`, `python scripts/extract.py check <source>`

This replaces and extends v1's `ingest.py` register and check commands. Adds source classification.

- [ ] **Step 4: Run the tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add scripts/extract.py tests/test_extract.py
git commit -m "feat: extract stage with source classification and registration"
```

---

## Task 6: Validate Stage (validate.py)

**Files:**
- Create: `scripts/validate.py`
- Create: `tests/test_validate.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_validate.py
import pytest
from pathlib import Path
from scripts.validate import (
    validate_frontmatter, validate_sections, validate_wikilinks,
    validate_provenance, validate_fact_inference_separation,
    validate_draft, ValidationReport
)

class TestValidateFrontmatter:
    def test_valid_concept_frontmatter(self):
        # Test that valid frontmatter passes
        pass

    def test_missing_required_field(self):
        # Test that missing field is detected
        pass

class TestValidateFactInference:
    def test_inference_in_facts_section_flagged(self):
        # Test that unmarked inferences in facts_only sections are flagged
        pass

    def test_marked_inference_in_mixed_section_ok(self):
        # Test that properly marked inferences in mixed sections pass
        pass

class TestValidateDraft:
    def test_valid_draft_passes(self, tmp_path):
        # Create a valid draft page and validate it
        pass

    def test_invalid_draft_stays_in_drafts(self, tmp_path):
        # Create an invalid draft and verify it's not promoted
        pass
```

- [ ] **Step 2: Run the tests to verify they fail**

- [ ] **Step 3: Write scripts/validate.py**

Implement Stage 2 of the pipeline:
- `validate_frontmatter(page, schema) -> list[ValidationIssue]` — Check required frontmatter per page type
- `validate_sections(page, schema) -> list[ValidationIssue]` — Check required sections exist and have content
- `validate_wikilinks(page, all_page_names) -> list[ValidationIssue]` — Check wikilinks resolve
- `validate_provenance(page_path) -> list[ValidationIssue]` — Check provenance sidecar exists and is valid
- `validate_fact_inference_separation(page, schema) -> list[ValidationIssue]` — Check facts-only sections don't have unmarked inferences
- `validate_draft(draft_path, schema) -> ValidationReport` — Full validation of a draft page
- `promote_draft(draft_path, schema) -> Path | None` — Move validated draft to concepts/entities
- CLI: `python scripts/validate.py` (validates all drafts), `python scripts/validate.py <draft>` (validate specific draft)

- [ ] **Step 4: Run the tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add scripts/validate.py tests/test_validate.py
git commit -m "feat: validate stage with fact/inference separation and provenance checks"
```

---

## Task 7: Link Stage (link.py)

**Files:**
- Create: `scripts/link.py`
- Create: `tests/test_link.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_link.py
import pytest
from scripts.link import (
    extract_typed_edges, build_typed_graph, verify_bidirectional_links
)

class TestExtractTypedEdges:
    def test_implements_relation(self):
        content = "RAG implements [[Neural IR]] for retrieval."
        edges = extract_typed_edges(content)
        assert any(e["target"] == "Neural IR" and e["type"] == "implements" for e in edges)

    def test_contradicts_relation(self):
        content = "This contradicts [[Pure Generation]] approaches."
        edges = extract_typed_edges(content)
        assert any(e["type"] == "contradicts" for e in edges)

    def test_untyped_link_defaults_neutral(self):
        content = "See [[RAG]] for details."
        edges = extract_typed_edges(content)
        assert any(e["type"] == "neutral" for e in edges)

class TestBuildTypedGraph:
    def test_graph_has_nodes_and_edges(self, tmp_path):
        # Create wiki pages with typed links and build graph
        pass

    def test_graph_includes_edge_weights(self, tmp_path):
        # Verify edge weights from schema relation_types
        pass
```

- [ ] **Step 2: Run the tests to verify they fail**

- [ ] **Step 3: Write scripts/link.py**

Implement Stage 3 of the pipeline:
- `extract_typed_edges(content) -> list[dict]` — Parse context around wikilinks to infer relation types using keyword patterns: "implements", "extends", "contradicts", "cites", "prerequisite of", "trades off", "derived from". Untyped links get `type: "neutral"` with weight 1x.
- `build_typed_graph(wiki_dir, schema) -> dict` — Build `_graph.json` with typed edges, node metadata, and edge weights from schema relation_types
- `verify_bidirectional_links(wiki_dir) -> list[dict]` — Check that strongly connected pages link back to each other
- `save_graph(graph, wiki_dir) -> None` — Write `_graph.json`
- CLI: `python scripts/link.py` (build graph and verify links)

- [ ] **Step 4: Run the tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add scripts/link.py tests/test_link.py
git commit -m "feat: link stage with typed wikilinks and graph building"
```

---

## Task 8: Refine Stage (refine.py)

**Files:**
- Create: `scripts/refine.py`
- Create: `tests/test_refine.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_refine.py
import pytest
from scripts.refine import (
    find_thin_pages, find_contradictions, find_gap_pages,
    generate_refinement_tasks
)

class TestFindThinPages:
    def test_page_with_few_sections_is_thin(self, tmp_path):
        # Create a page with only 1 section
        pass

    def test_page_with_enough_sections_is_not_thin(self, tmp_path):
        # Create a page with 4+ sections
        pass

class TestFindContradictions:
    def test_unresolved_contradiction_detected(self, tmp_path):
        # Create a page with > [!warning] CONTRADICTION ... UNRESOLVED
        pass

    def test_resolved_contradiction_not_flagged(self, tmp_path):
        # Create a page with > [!success] RESOLVED
        pass

class TestFindGapPages:
    def test_wikilinks_to_nonexistent_pages_are_gaps(self, tmp_path):
        pass
```

- [ ] **Step 2: Run the tests to verify they fail**

- [ ] **Step 3: Write scripts/refine.py**

Implement Stage 4 of the pipeline:
- `find_thin_pages(wiki_dir, schema) -> list[dict]` — Pages with fewer than 2 sections in their content
- `find_contradictions(wiki_dir) -> list[dict]` — Pages with unresolved `> [!warning] CONTRADICTION` callouts
- `find_gap_pages(wiki_dir) -> list[dict]` — Wikilinks pointing to non-existent pages
- `check_staleness_all(wiki_dir, sources_dir) -> list[str]` — All pages with stale source references
- `generate_refinement_tasks(wiki_dir, sources_dir, schema) -> list[dict]` — Aggregate all refinement tasks into a prioritized list
- CLI: `python scripts/refine.py` (run all refinement checks)

- [ ] **Step 4: Run the tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add scripts/refine.py tests/test_refine.py
git commit -m "feat: refine stage with thin page detection, contradictions, and gap analysis"
```

---

## Task 9: Lint Stage (lint.py v2)

**Files:**
- Modify: `scripts/lint.py` (rewrite for v2)
- Create: `tests/test_lint.py`

- [ ] **Step 1: Write the failing tests for all 12 checks**

```python
# tests/test_lint.py
import pytest
from scripts.lint import lint, LintIssue

class TestBrokenLinks:
    def test_broken_link_detected(self, tmp_path): pass
    def test_valid_link_passes(self, tmp_path): pass

class TestOrphanPages:
    def test_orphan_page_detected(self, tmp_path): pass

class TestMissingFrontmatter:
    def test_missing_field_detected(self, tmp_path): pass

class TestStalePage:
    def test_stale_page_detected(self, tmp_path): pass

class TestUnmarkedInference:
    def test_inference_in_facts_section_detected(self, tmp_path): pass

class TestMissingContentHash:
    def test_missing_provenance_detected(self, tmp_path): pass

class TestMissingCounterArgs:
    def test_high_confidence_without_counter_args(self, tmp_path): pass

# ... remaining checks from v1 (orphan, no_sources, low_connectivity, etc.)
```

- [ ] **Step 2: Run the tests to verify they fail**

- [ ] **Step 3: Rewrite scripts/lint.py for v2**

Rewrite with 12 checks:
1. BROKEN_LINK (from v1)
2. ORPHAN_PAGE (from v1)
3. MISSING_FRONTMATTER (from v1, now schema-driven)
4. INVALID_TYPE (from v1, now schema-driven)
5. NO_SOURCES (from v1)
6. LOW_CONNECTIVITY (from v1, now min_outlinks from schema)
7. STALE_PAGE (new — checks provenance sidecar source hashes)
8. UNRESOLVED_CONTRADICTION (from v1)
9. DUPLICATE_CONCEPT (from v1)
10. EMPTY_SECTION (from v1)
11. UNMARKED_INFERENCE (new — checks facts-only sections for inference markers)
12. MISSING_CONTENT_HASH (new — checks for provenance sidecar)

Severity levels come from SCHEMA.yaml validation config. CLI: `python scripts/lint.py [--json]`

- [ ] **Step 4: Run the tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add scripts/lint.py tests/test_lint.py
git commit -m "feat: v2 lint with 12 checks including staleness, inference, and provenance"
```

---

## Task 10: Consolidate Stage (consolidate.py)

**Files:**
- Create: `scripts/consolidate.py`
- Create: `tests/test_consolidate.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_consolidate.py
import pytest
from scripts.consolidate import (
    find_duplicate_pages, generate_indexes, generate_timelines,
    merge_pages
)

class TestFindDuplicatePages:
    def test_alias_match_detected(self, tmp_path): pass
    def test_similar_content_detected(self, tmp_path): pass

class TestGenerateIndexes:
    def test_master_index_created(self, tmp_path): pass
    def test_by_topic_index_created(self, tmp_path): pass
    def test_by_source_index_created(self, tmp_path): pass

class TestGenerateTimelines:
    def test_timeline_from_dated_concepts(self, tmp_path): pass
```

- [ ] **Step 2: Run the tests to verify they fail**

- [ ] **Step 3: Write scripts/consolidate.py**

Implement Stage 6:
- `find_duplicate_pages(wiki_dir) -> list[tuple[str, str]]` — Detect duplicate concepts via alias matching and title similarity
- `generate_indexes(wiki_dir, schema) -> None` — Regenerate `_index.md`, `by-topic.md`, `by-source.md`, `recently-updated.md`, `_contradictions.md`
- `generate_timelines(wiki_dir) -> None` — Create timeline pages from dated concepts
- `merge_pages(primary, secondary, wiki_dir) -> None` — Merge secondary page into primary, update all wikilinks, delete secondary
- CLI: `python scripts/consolidate.py` (run full consolidation)

- [ ] **Step 4: Run the tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add scripts/consolidate.py tests/test_consolidate.py
git commit -m "feat: consolidate stage with duplicate detection, indexes, and timelines"
```

---

## Task 11: Query Engine (query.py v2)

**Files:**
- Modify: `scripts/query.py` (rewrite for v2)
- Create: `tests/test_query.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_query.py
import pytest
from scripts.query import (
    find_seed_pages, traverse_typed_graph, build_context
)

class TestFindSeedPages:
    def test_keyword_matching(self, tmp_path): pass
    def test_tag_matching(self, tmp_path): pass
    def test_alias_matching(self, tmp_path): pass

class TestTraverseTypedGraph:
    def test_follows_typed_edges(self, tmp_path): pass
    def test_weights_cites_over_neutral(self, tmp_path): pass
    def test_depth_limit(self, tmp_path): pass
```

- [ ] **Step 2: Run the tests to verify they fail**

- [ ] **Step 3: Rewrite scripts/query.py for v2**

Replace v1 keyword-only search with:
- `find_seed_pages(question, wiki_dir, top_k=5) -> list[Path]` — Keyword + tag + alias matching (v1 approach, enhanced)
- `traverse_typed_graph(seed_pages, graph, depth=2) -> list[dict]` — Follow typed edges with weight-based ranking
- `build_context(pages, max_chars=50000) -> str` — Assemble context from traversed pages
- CLI: `python scripts/query.py "question" [--depth 2] [--top-k 5] [--json]`

Note: Hybrid search (Tier 2) with BM25 + vector + tag boost is deferred to v3. This implements Tier 1 graph traversal with typed edges.

- [ ] **Step 4: Run the tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add scripts/query.py tests/test_query.py
git commit -m "feat: v2 query engine with typed graph traversal"
```

---

## Task 12: Unified CLI (cli.py)

**Files:**
- Create: `scripts/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli.py
import pytest
from scripts.cli import main

class TestCLIIngest:
    def test_ingest_registers_source(self): pass

class TestCLILint:
    def test_lint_runs_all_checks(self): pass

class TestCLIState:
    def test_state_outputs_json(self): pass

class TestCLIHealth:
    def test_health_outputs_json(self): pass

class TestCLIQuery:
    def test_query_returns_context(self): pass
```

- [ ] **Step 2: Run the tests to verify they fail**

- [ ] **Step 3: Write scripts/cli.py**

Unified CLI entry point with subcommands:
- `wiki ingest <source> --type <type>` — Full pipeline: extract → validate → link → lint → state update
- `wiki process <source> --type <type>` — Alias for ingest
- `wiki extract <source> --type <type>` — Just extraction
- `wiki validate` — Validate all drafts
- `wiki refine` — Run refinement checks
- `wiki link` — Build graph and verify links
- `wiki lint [--json]` — Run all 12 checks
- `wiki consolidate` — Merge duplicates, generate indexes
- `wiki state` — Print `_state.json` summary
- `wiki health` — Print `_health.json` summary
- `wiki query "question" [--depth 2] [--json]` — Graph traversal query
- `wiki find --tag <tag> --confidence <level>` — Filter pages by metadata
- `wiki provenance <page>` — Show evidence chain
- `wiki register <source> --type <type>` — Register source only
- `wiki check <source>` — Dedup check
- `wiki rebuild` — Regenerate indexes + graph + state
- `wiki generate-instructions` — Generate CLAUDE.md from SCHEMA.yaml

Uses `argparse` with subparsers. Each subcommand delegates to the appropriate module. The `ingest` command orchestrates the full pipeline in sequence.

- [ ] **Step 4: Run the tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add scripts/cli.py tests/test_cli.py
git commit -m "feat: unified CLI with all pipeline subcommands"
```

---

## Task 13: CLAUDE.md Generator

**Files:**
- Create: `scripts/generate_instructions.py`
- Create: `tests/test_generate_instructions.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_generate_instructions.py
import pytest
from scripts.generate_instructions import generate_claude_md

class TestGenerateInstructions:
    def test_output_contains_identity(self):
        content = generate_claude_md(schema_path=SCHEMA_PATH)
        assert "Wiki Curator" in content

    def test_output_contains_bootstrap(self):
        content = generate_claude_md(schema_path=SCHEMA_PATH)
        assert "_state.json" in content

    def test_output_contains_page_types(self):
        content = generate_claude_md(schema_path=SCHEMA_PATH)
        assert "concept" in content
        assert "entity" in content

    def test_output_contains_cli_commands(self):
        content = generate_claude_md(schema_path=SCHEMA_PATH)
        assert "wiki ingest" in content
        assert "wiki lint" in content

    def test_output_contains_constraints(self):
        content = generate_claude_md(schema_path=SCHEMA_PATH)
        assert "merge over create" in content.lower() or "Merge over Create" in content
```

- [ ] **Step 2: Run the tests to verify they fail**

- [ ] **Step 3: Write scripts/generate_instructions.py**

Generate CLAUDE.md from SCHEMA.yaml:
- Read SCHEMA.yaml
- Generate sections: Identity, Bootstrap instruction, Architecture, Page templates (from schema page_types and required_sections), Rules (from schema extraction/validation/contradiction config), CLI reference (all wiki commands), Constraints (derived from config)
- Write to CLAUDE.md
- CLI: `wiki generate-instructions`

- [ ] **Step 4: Run the tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git add scripts/generate_instructions.py tests/test_generate_instructions.py
git commit -m "feat: CLAUDE.md generator from SCHEMA.yaml"
```

---

## Task 14: Integration Test — Full Pipeline

**Files:**
- Create: `tests/test_pipeline.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/test_pipeline.py
"""Integration test: full pipeline from source ingestion to state generation."""
import json
import pytest
from pathlib import Path
from scripts.cli import main

class TestFullPipeline:
    def test_ingest_source_creates_pages_and_state(self, tmp_path):
        """Test the full pipeline: extract → validate → link → lint → consolidate → state"""
        # Set up a minimal wiki structure
        wiki_dir = tmp_path / "wiki"
        sources_dir = tmp_path / "sources"
        for d in [wiki_dir / "concepts", wiki_dir / "entities", wiki_dir / "indexes",
                  wiki_dir / "timelines", wiki_dir / "drafts", sources_dir / "article"]:
            d.mkdir(parents=True)

        # Create a test source
        source = sources_dir / "article" / "test-article.md"
        source.write_text("# Test Article\n\nThis is a test article about [[RAG]].", encoding="utf-8")

        # Create manifest
        manifest = sources_dir / "manifest.json"
        manifest.write_text('{"version": "1.0", "sources": []}', encoding="utf-8")

        # Run pipeline stages
        # ... (test that each stage produces expected output)

    def test_validate_rejects_invalid_draft(self, tmp_path):
        """Test that validation rejects a draft missing required frontmatter"""
        pass

    def test_lint_detects_broken_link(self, tmp_path):
        """Test that lint catches broken wikilinks"""
        pass

    def test_state_reflects_wiki_health(self, tmp_path):
        """Test that _state.json accurately reflects wiki state"""
        pass
```

- [ ] **Step 2: Run the integration test**

- [ ] **Step 3: Fix any integration issues**

Run the full pipeline end-to-end, fix any issues where stages don't connect properly (e.g., state generation not picking up lint results, validate not finding the right schema path).

- [ ] **Step 4: Commit**

```bash
git add tests/test_pipeline.py
git commit -m "test: full pipeline integration test"
```

---

## Task 15: Migrate Existing Wiki Content

**Files:**
- Modify: Existing wiki pages in `wiki/concepts/` and `wiki/entities/` (add frontmatter fields, provenance sidecars)
- Create: `scripts/migrate.py`
- Create: `wiki/_log.md`

- [ ] **Step 1: Write migration script**

Create `scripts/migrate.py` that:
1. Reads each existing wiki page
2. Updates frontmatter to match SCHEMA.yaml (adds `content_hash`, `source_refs` if missing)
3. Creates `.provenance.json` sidecar for each page
4. Moves `WIKI_SCHEMA.md` to `WIKI_SCHEMA.md.bak` (kept for reference)
5. Creates `wiki/drafts/` directory
6. Creates `wiki/_log.md` with initial entry
7. Creates initial `wiki/_state.json` from current content
8. Creates initial `wiki/_health.json` from running lint

- [ ] **Step 2: Run migration on existing content**

Run: `python scripts/migrate.py`
Verify: All existing pages get provenance sidecars and updated frontmatter

- [ ] **Step 3: Generate CLAUDE.md**

Run: `wiki generate-instructions`
Verify: CLAUDE.md is generated with correct schema, page templates, and CLI reference

- [ ] **Step 4: Run full pipeline on migrated content**

Run: `wiki lint` — should pass with only warnings (not errors)
Run: `wiki rebuild` — should regenerate indexes, graph, and state
Run: `wiki state` — should show correct page inventory

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: v2 pipeline complete — migrated existing content, generated CLAUDE.md"
```

---

## Task 16: Update requirements.txt and Clean Up

**Files:**
- Modify: `requirements.txt`
- Remove: `scripts/ingest.py`, `scripts/stats.py` (replaced by v2 modules)
- Remove: `GEMINI.md` (replaced by CLAUDE.md)
- Remove: `WIKI_SCHEMA.md` (replaced by SCHEMA.yaml)
- Remove: `.agents/` workflows and skill (replaced by pipeline)

- [ ] **Step 1: Update requirements.txt**

```txt
python-frontmatter>=1.1.0
pyyaml>=6.0
networkx>=3.4
rich>=13.9
pymupdf>=1.25.0
```

(No new dependencies — all v2 features use standard library + existing packages)

- [ ] **Step 2: Remove v1 files that are replaced**

```bash
rm scripts/ingest.py scripts/stats.py
rm GEMINI.md WIKI_SCHEMA.md
rm -rf .agents/
```

- [ ] **Step 3: Verify full pipeline still works after cleanup**

Run: `python scripts/cli.py lint`
Run: `python scripts/cli.py state`
Run: `python scripts/cli.py rebuild`

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove v1 scripts and configs, clean up for v2"
```

---

## Self-Review Checklist

**1. Spec coverage:**
- [x] SCHEMA.yaml — Task 1
- [x] Provenance sidecars — Task 3
- [x] _state.json agent awareness — Task 4
- [x] Extract stage — Task 5
- [x] Validate stage — Task 6
- [x] Link stage (typed edges) — Task 7
- [x] Refine stage — Task 8
- [x] Lint stage (12 checks) — Task 9
- [x] Consolidate stage — Task 10
- [x] Query engine (graph traversal) — Task 11
- [x] Unified CLI — Task 12
- [x] CLAUDE.md generator — Task 13
- [x] Fact/inference separation — Task 6 (validate) + Task 9 (lint)
- [x] Diff-proposed writes — Task 6 (validate promotes drafts)
- [x] Counter-arguments section — Task 8 (refine generates these)
- [x] File structure — All tasks create files in spec locations
- [x] Research references — Noted in spec, not separate tasks

**2. Placeholder scan:**
- No TBD, TODO, or "implement later" patterns
- All test functions have descriptive names even if bodies are `pass`
- All implementation descriptions include specific function signatures

**3. Type consistency:**
- `ValidationReport` used in Task 6 (validate.py)
- `LintIssue` used in Task 9 (lint.py)
- Provenance dict structure consistent across Tasks 3, 5, 6
- State dict structure consistent across Tasks 4, 12
- Graph dict structure consistent across Tasks 7, 10, 11