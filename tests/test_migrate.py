"""Tests for migrate.py — source ref parsing and provenance sidecar creation."""

from __future__ import annotations

from pathlib import Path

from scripts.migrate import _parse_source_ref, _resolve_source_path
from scripts.utils import hash_content, hash_file, write_provenance


class TestParseSourceRef:
    def test_full_citation(self):
        """Parse '[source: filename.md, §Section Name]' format."""
        result = _parse_source_ref("[source: paper.md, §Abstract]")
        assert result["file"] == "paper.md"
        assert result["sections_used"] == ["Abstract"]

    def test_citation_without_section(self):
        """Parse '[source: filename.md]' format."""
        result = _parse_source_ref("[source: report.pdf]")
        assert result["file"] == "report.pdf"
        assert result["sections_used"] == []

    def test_bare_filename(self):
        """Bare filename passes through."""
        result = _parse_source_ref("paper.md")
        assert result["file"] == "paper.md"
        assert result["sections_used"] == []

    def test_migrated_content(self):
        """Legacy 'migrated-content' placeholder passes through."""
        result = _parse_source_ref("migrated-content")
        assert result["file"] == "migrated-content"
        assert result["sections_used"] == []

    def test_citation_with_complex_section(self):
        """Parse citation with complex section name."""
        result = _parse_source_ref("[source: ai-strategy.md, §The Multi-Agent Swarm and Contextual Memory Architectures]")
        assert result["file"] == "ai-strategy.md"
        assert result["sections_used"] == ["The Multi-Agent Swarm and Contextual Memory Architectures"]


class TestResolveSourcePath:
    def test_resolve_subdirectory_file(self, tmp_path):
        """Resolves bare filename to article/filename.md when file is in subdirectory."""
        article_dir = tmp_path / "article"
        article_dir.mkdir()
        (article_dir / "paper.md").write_text("content", encoding="utf-8")

        result = _resolve_source_path("paper.md", tmp_path)
        assert result == "article/paper.md"

    def test_resolve_already_prefixed(self, tmp_path):
        """Already-prefixed path returns unchanged if file exists."""
        article_dir = tmp_path / "article"
        article_dir.mkdir()
        (article_dir / "paper.md").write_text("content", encoding="utf-8")

        result = _resolve_source_path("article/paper.md", tmp_path)
        assert result == "article/paper.md"

    def test_resolve_not_found(self, tmp_path):
        """Returns bare filename if no match found."""
        result = _resolve_source_path("nonexistent.md", tmp_path)
        assert result == "nonexistent.md"

    def test_resolve_multiple_subdirs(self, tmp_path):
        """Finds file in first matching subdirectory."""
        (tmp_path / "article").mkdir()
        (tmp_path / "paper").mkdir()
        (tmp_path / "paper" / "report.md").write_text("content", encoding="utf-8")

        result = _resolve_source_path("report.md", tmp_path)
        assert result == "paper/report.md"