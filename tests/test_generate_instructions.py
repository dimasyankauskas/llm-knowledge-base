"""Tests for CLAUDE.md generator from SCHEMA.yaml."""

import pytest
from pathlib import Path

from scripts.generate_instructions import generate_claude_md

SCHEMA_PATH = Path(__file__).parent.parent / "SCHEMA.yaml"


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
        lower = content.lower()
        assert "merge over create" in lower or "atomic notes" in lower

    def test_output_contains_section_rules(self):
        content = generate_claude_md(schema_path=SCHEMA_PATH)
        assert "facts_only" in content
        assert "inference_only" in content

    def test_output_contains_confidence_levels(self):
        content = generate_claude_md(schema_path=SCHEMA_PATH)
        assert "HIGH" in content
        assert "MEDIUM" in content
        assert "LOW" in content

    def test_output_contains_relation_types(self):
        content = generate_claude_md(schema_path=SCHEMA_PATH)
        assert "cites" in content
        assert "contradicts" in content

    def test_output_contains_contradiction_rules(self):
        content = generate_claude_md(schema_path=SCHEMA_PATH)
        assert "CONTRADICTION" in content
        assert "counter" in content.lower()

    def test_writes_to_file(self, tmp_path):
        out_path = tmp_path / "CLAUDE.md"
        generate_claude_md(schema_path=SCHEMA_PATH, output_path=out_path)
        assert out_path.exists()
        content = out_path.read_text(encoding="utf-8")
        assert "Wiki Curator" in content