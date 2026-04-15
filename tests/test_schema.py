"""Tests for SCHEMA.yaml loading and schema.py accessor functions."""

import pytest
from pathlib import Path

from scripts.schema import (
    load_schema,
    get_page_type_config,
    get_validation_rules,
    get_confidence_levels,
    get_relation_types,
    get_source_type_template,
    get_extraction_config,
    get_contradiction_config,
    get_all_page_types,
    get_required_frontmatter,
    get_required_sections,
    get_section_rules,
)


@pytest.fixture
def schema():
    """Load the schema once for all tests."""
    return load_schema()


def test_load_schema_returns_dict(schema):
    """Schema loads as a dict with version 2.0."""
    assert isinstance(schema, dict)
    assert schema["version"] == "2.0"


def test_schema_has_required_top_level_keys(schema):
    """Schema contains all required top-level sections."""
    required_keys = [
        "version",
        "page_types",
        "confidence_levels",
        "relation_types",
        "extraction",
        "validation",
        "contradiction",
    ]
    for key in required_keys:
        assert key in schema, f"Missing top-level key: {key}"


def test_get_page_type_config(schema):
    """Concept page type has expected structure and min_outlinks=2."""
    config = get_page_type_config(schema, "concept")
    assert "required_frontmatter" in config
    assert "required_sections" in config
    assert "section_rules" in config
    assert config["min_outlinks"] == 2
    assert "citation_format" in config


def test_get_page_type_config_entity(schema):
    """Entity page type has min_outlinks=1 and entity_type in frontmatter."""
    config = get_page_type_config(schema, "entity")
    assert config["min_outlinks"] == 1
    assert "entity_type" in config["required_frontmatter"]


def test_get_page_type_config_unknown_raises(schema):
    """Requesting an unknown page type raises ValueError."""
    with pytest.raises(ValueError):
        get_page_type_config(schema, "nonexistent_type")


def test_get_validation_rules(schema):
    """Validation rules contain expected entries with correct severities."""
    rules = get_validation_rules(schema)
    assert rules["broken_links"]["severity"] == "ERROR"
    assert "stale_page" in rules
    assert "unmarked_inference" in rules
    assert "missing_content_hash" in rules


def test_schema_page_types_have_section_rules(schema):
    """Concept page type has section_rules with expected entries."""
    concept = get_page_type_config(schema, "concept")
    rules = concept["section_rules"]
    assert "Definition" in rules
    assert rules["Definition"] == "facts_only"
    assert "How It Works" in rules
    assert rules["How It Works"] == "mixed"
    assert "Open Questions" in rules
    assert rules["Open Questions"] == "inference_only"
    assert "Key Properties" in rules
    assert rules["Key Properties"] == "facts_only"


def test_schema_relation_types(schema):
    """Relation types list contains expected entries and has length 7."""
    rels = get_relation_types(schema)
    assert "implements" in rels
    assert "contradicts" in rels
    assert "cites" in rels
    assert len(rels) == 7


def test_schema_extraction_config(schema):
    """Extraction config has expected values."""
    ext = get_extraction_config(schema)
    assert ext["merge_over_create"] is True
    assert ext["write_mode"] == "diff_proposal"
    assert "source_type_templates" in ext


def test_get_source_type_template(schema):
    """Source type templates return expected keys."""
    paper = get_source_type_template(schema, "paper")
    assert paper is not None
    assert isinstance(paper, list)
    article = get_source_type_template(schema, "article")
    assert article is not None
    unknown = get_source_type_template(schema, "nonexistent")
    assert unknown is None


def test_get_confidence_levels(schema):
    """Confidence levels contain HIGH, MEDIUM, LOW."""
    levels = get_confidence_levels(schema)
    assert "HIGH" in levels
    assert "MEDIUM" in levels
    assert "LOW" in levels
    for level_name, level_data in levels.items():
        assert "description" in level_data
        assert "color" in level_data


def test_get_contradiction_config(schema):
    """Contradiction config has expected structure."""
    config = get_contradiction_config(schema)
    assert config["callout_type"] == "warning"
    assert config["resolution_callout"] == "success"
    assert config["auto_downgrade_confidence"] == "LOW"
    assert config["require_counter_arguments"] is True


def test_get_all_page_types(schema):
    """All page types are returned."""
    types = get_all_page_types(schema)
    assert "concept" in types
    assert "entity" in types
    assert "index" in types
    assert "timeline" in types


def test_get_required_frontmatter(schema):
    """Required frontmatter for concept and entity types."""
    concept_fm = get_required_frontmatter(schema, "concept")
    assert isinstance(concept_fm, list)
    assert "content_hash" in concept_fm, "concept must require content_hash in frontmatter"
    assert "source_refs" in concept_fm, "concept must require source_refs in frontmatter"
    assert "type" in concept_fm, "concept must require type in frontmatter"

    entity_fm = get_required_frontmatter(schema, "entity")
    assert "entity_type" in entity_fm
    assert "content_hash" in entity_fm, "entity must require content_hash in frontmatter"


def test_get_required_sections(schema):
    """Required sections for concept type."""
    sections = get_required_sections(schema, "concept")
    assert isinstance(sections, list)
    assert len(sections) > 0


def test_get_section_rules(schema):
    """Section rules for concept type."""
    rules = get_section_rules(schema, "concept")
    assert isinstance(rules, dict)
    assert "Definition" in rules


def test_index_page_type_auto_generated(schema):
    """Index page type has auto_generated=True."""
    config = get_page_type_config(schema, "index")
    assert config.get("auto_generated") is True