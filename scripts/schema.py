"""Schema loader for LLM Knowledge Base v2.

Provides accessor functions for the SCHEMA.yaml system constitution.
"""

from pathlib import Path
from typing import Dict, List, Optional

import yaml

SCHEMA_PATH = Path(__file__).parent.parent / "SCHEMA.yaml"


def load_schema(path: Optional[Path] = None) -> dict:
    """Load and return the SCHEMA.yaml as a dictionary.

    Args:
        path: Optional override path to the schema file.

    Returns:
        Parsed schema dictionary.

    Raises:
        FileNotFoundError: If the schema file does not exist.
    """
    schema_path = path or SCHEMA_PATH
    with open(schema_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_page_type_config(schema: dict, page_type: str) -> dict:
    """Get configuration for a specific page type.

    Args:
        schema: The loaded schema dictionary.
        page_type: Name of the page type (e.g., 'concept', 'entity').

    Returns:
        Configuration dictionary for the page type.

    Raises:
        ValueError: If the page type does not exist in the schema.
    """
    page_types = schema.get("page_types", {})
    if page_type not in page_types:
        raise ValueError(
            f"Unknown page type: {page_type!r}. "
            f"Available types: {', '.join(page_types.keys())}"
        )
    return page_types[page_type]


def get_validation_rules(schema: dict) -> dict:
    """Get the validation rules section of the schema.

    Args:
        schema: The loaded schema dictionary.

    Returns:
        Dictionary of validation rule names to severity levels.
    """
    return schema.get("validation", {})


def get_confidence_levels(schema: dict) -> dict:
    """Get the confidence levels section of the schema.

    Args:
        schema: The loaded schema dictionary.

    Returns:
        Dictionary mapping confidence level names to their config.
    """
    return schema.get("confidence_levels", {})


def get_relation_types(schema: dict) -> List[str]:
    """Get the list of relation types.

    Args:
        schema: The loaded schema dictionary.

    Returns:
        List of relation type names.
    """
    return schema.get("relation_types", [])


def get_source_type_template(schema: dict, source_type: str) -> Optional[List[str]]:
    """Get the extraction template for a source type.

    Args:
        schema: The loaded schema dictionary.
        source_type: The source type key (e.g., 'paper', 'article').

    Returns:
        List of template field names, or None if source_type not found.
    """
    templates = schema.get("extraction", {}).get("source_type_templates", {})
    return templates.get(source_type)


def get_extraction_config(schema: dict) -> dict:
    """Get the extraction configuration section.

    Args:
        schema: The loaded schema dictionary.

    Returns:
        Dictionary of extraction configuration.
    """
    return schema.get("extraction", {})


def get_contradiction_config(schema: dict) -> dict:
    """Get the contradiction handling configuration.

    Args:
        schema: The loaded schema dictionary.

    Returns:
        Dictionary of contradiction config.
    """
    return schema.get("contradiction", {})


def get_all_page_types(schema: dict) -> List[str]:
    """Get a list of all page type names.

    Args:
        schema: The loaded schema dictionary.

    Returns:
        List of page type name strings.
    """
    return list(schema.get("page_types", {}).keys())


def get_required_frontmatter(schema: dict, page_type: str) -> List[str]:
    """Get required frontmatter fields for a page type.

    Args:
        schema: The loaded schema dictionary.
        page_type: Name of the page type.

    Returns:
        List of required frontmatter field names.
    """
    config = get_page_type_config(schema, page_type)
    return config.get("required_frontmatter", [])


def get_required_sections(schema: dict, page_type: str) -> List[str]:
    """Get required sections for a page type.

    Args:
        schema: The loaded schema dictionary.
        page_type: Name of the page type.

    Returns:
        List of required section names.
    """
    config = get_page_type_config(schema, page_type)
    return config.get("required_sections", [])


def get_section_rules(schema: dict, page_type: str) -> Dict[str, str]:
    """Get section rules for a page type.

    Args:
        schema: The loaded schema dictionary.
        page_type: Name of the page type.

    Returns:
        Dictionary mapping section names to their content rules.
    """
    config = get_page_type_config(schema, page_type)
    return config.get("section_rules", {})