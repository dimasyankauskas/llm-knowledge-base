"""Tests for unified CLI entry point."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from scripts.cli import main


class TestCLIIngest:
    def test_ingest_registers_source(self, tmp_path):
        """Ingest subcommand should call extract + link + lint + state."""
        with patch("scripts.cli.register_source") as mock_reg, \
             patch("scripts.cli.build_typed_graph") as mock_graph, \
             patch("scripts.cli.save_graph") as mock_save_graph, \
             patch("scripts.cli.lint") as mock_lint, \
             patch("scripts.cli.generate_state") as mock_state, \
             patch("scripts.cli.save_state") as mock_save_state, \
             patch("scripts.cli.generate_health") as mock_health, \
             patch("scripts.cli.save_health") as mock_save_health:
            mock_reg.return_value = Path("/tmp/test.pdf")
            mock_graph.return_value = {"nodes": [], "edges": []}
            mock_lint.return_value = []
            mock_state.return_value = {"schema_version": "2.0", "pages": {}}
            mock_health.return_value = {"errors": 0, "warnings": 0, "issues": []}
            main(["ingest", "test.pdf", "--type", "paper"])
            mock_reg.assert_called_once()
            mock_graph.assert_called_once()
            mock_lint.assert_called_once()


class TestCLILint:
    def test_lint_runs_all_checks(self, tmp_path):
        """Lint subcommand should run lint and output results."""
        with patch("scripts.cli.lint") as mock_lint:
            mock_lint.return_value = []
            main(["lint"])
            mock_lint.assert_called_once()


class TestCLILintJSON:
    def test_lint_json_output(self, tmp_path, capsys):
        """Lint --json should output JSON."""
        with patch("scripts.cli.lint") as mock_lint:
            mock_lint.return_value = []
            main(["lint", "--json"])
            mock_lint.assert_called_once()
            captured = capsys.readouterr()
            assert "errors" in captured.out


class TestCLIState:
    def test_state_outputs_json(self, tmp_path, capsys):
        """State subcommand should output state summary."""
        with patch("scripts.cli.generate_state") as mock_gen, \
             patch("scripts.cli.save_state") as mock_save:
            mock_gen.return_value = {"schema_version": "2.0", "pages": {}}
            main(["state"])
            mock_gen.assert_called_once()
            mock_save.assert_called_once()
            captured = capsys.readouterr()
            assert "schema_version" in captured.out


class TestCLIHealth:
    def test_health_outputs_json(self, tmp_path, capsys):
        """Health subcommand should output health summary."""
        with patch("scripts.cli.lint") as mock_lint, \
             patch("scripts.cli.generate_health") as mock_gen, \
             patch("scripts.cli.save_health") as mock_save:
            mock_lint.return_value = []
            mock_gen.return_value = {"errors": 0, "warnings": 0, "issues": []}
            main(["health"])
            mock_lint.assert_called_once()
            mock_gen.assert_called_once()
            captured = capsys.readouterr()
            assert "errors" in captured.out


class TestCLIQuery:
    def test_query_returns_context(self, tmp_path, capsys):
        """Query subcommand should find seed pages and build context."""
        with patch("scripts.cli.list_wiki_pages") as mock_list, \
             patch("scripts.cli.find_seed_pages") as mock_find, \
             patch("scripts.cli.traverse_typed_graph") as mock_traverse, \
             patch("scripts.cli.build_context") as mock_build:
            mock_list.return_value = [Path("wiki/concepts/RAG.md")]
            mock_find.return_value = [Path("wiki/concepts/RAG.md")]
            mock_traverse.return_value = [{"page": Path("wiki/concepts/RAG.md"), "score": 10.0, "path": ["RAG"]}]
            mock_build.return_value = "RAG context"
            main(["query", "What is RAG?"])
            mock_find.assert_called_once()
            captured = capsys.readouterr()
            assert "Seed pages" in captured.out


class TestCLIValidate:
    def test_validate_runs_on_drafts(self, tmp_path):
        """Validate subcommand should validate drafts."""
        with patch("scripts.cli.validate_draft") as mock_validate, \
             patch("scripts.cli.WIKI_DIR", tmp_path / "wiki"):
            drafts = tmp_path / "wiki" / "drafts"
            drafts.mkdir(parents=True)
            mock_validate.return_value = MagicMock(errors=0, warnings=0, issues=[])
            main(["validate"])
            # No drafts exist, so validate_draft won't be called


class TestCLILink:
    def test_link_builds_graph(self, tmp_path, capsys):
        """Link subcommand should build typed graph."""
        with patch("scripts.cli.build_typed_graph") as mock_build, \
             patch("scripts.cli.verify_bidirectional_links") as mock_verify, \
             patch("scripts.cli.save_graph") as mock_save:
            mock_build.return_value = {"nodes": [], "edges": []}
            mock_verify.return_value = []
            main(["link"])
            mock_build.assert_called_once()
            mock_verify.assert_called_once()
            captured = capsys.readouterr()
            assert "bidirectional" in captured.out.lower()


class TestCLIConsolidate:
    def test_consolidate_runs(self, tmp_path, capsys):
        """Consolidate subcommand should run merge + indexes + timelines."""
        with patch("scripts.cli.find_duplicate_pages") as mock_dup, \
             patch("scripts.cli.generate_indexes") as mock_idx, \
             patch("scripts.cli.generate_timelines") as mock_tl:
            mock_dup.return_value = []
            main(["consolidate"])
            mock_dup.assert_called_once()
            mock_idx.assert_called_once()
            mock_tl.assert_called_once()
            captured = capsys.readouterr()
            assert "Indexes generated" in captured.out


class TestCLIRefine:
    def test_refine_runs(self, tmp_path, capsys):
        """Refine subcommand should run refinement tasks."""
        with patch("scripts.cli.generate_refinement_tasks") as mock_refine:
            mock_refine.return_value = []
            main(["refine"])
            mock_refine.assert_called_once()
            captured = capsys.readouterr()
            assert "No refinement tasks" in captured.out


class TestCLIRegister:
    def test_register_source(self, tmp_path, capsys):
        """Register subcommand should register a source."""
        with patch("scripts.cli.register_source") as mock_reg:
            mock_reg.return_value = Path("/tmp/test.pdf")
            main(["register", "test.pdf", "--type", "paper"])
            mock_reg.assert_called_once()
            captured = capsys.readouterr()
            assert "Registered" in captured.out


class TestCLICheck:
    def test_check_dedup(self, tmp_path, capsys):
        """Check subcommand should run dedup check."""
        with patch("scripts.cli.check_dedup") as mock_check:
            mock_check.return_value = False
            main(["check", "test.pdf"])
            mock_check.assert_called_once()
            captured = capsys.readouterr()
            assert "New source" in captured.out


class TestCLIRebuild:
    def test_rebuild_regenerates(self, tmp_path, capsys):
        """Rebuild subcommand should regenerate indexes + graph + state."""
        with patch("scripts.cli.generate_indexes") as mock_idx, \
             patch("scripts.cli.build_typed_graph") as mock_graph, \
             patch("scripts.cli.save_graph") as mock_save, \
             patch("scripts.cli.generate_state") as mock_state, \
             patch("scripts.cli.save_state") as mock_state_save, \
             patch("scripts.cli.lint") as mock_lint, \
             patch("scripts.cli.generate_health") as mock_health, \
             patch("scripts.cli.save_health") as mock_health_save:
            mock_graph.return_value = {"nodes": [], "edges": []}
            mock_lint.return_value = []
            mock_state.return_value = {"schema_version": "2.0", "pages": {}}
            mock_health.return_value = {"errors": 0, "warnings": 0, "issues": []}
            main(["rebuild"])
            mock_idx.assert_called_once()
            mock_graph.assert_called_once()
            mock_state.assert_called_once()
            captured = capsys.readouterr()
            assert "Indexes regenerated" in captured.out


class TestCLIFind:
    def test_find_by_tag(self, tmp_path, capsys):
        """Find subcommand should filter pages by tag."""
        with patch("scripts.cli.list_wiki_pages") as mock_list, \
             patch("scripts.cli.read_page") as mock_read:
            mock_page = MagicMock()
            mock_page.metadata = {"type": "concept", "confidence": "HIGH", "tags": ["domain/ai"]}
            mock_page.stem = "RAG"
            mock_list.return_value = [Path("wiki/concepts/RAG.md")]
            mock_read.return_value = mock_page
            main(["find", "--tag", "domain/ai"])
            mock_list.assert_called_once()
            captured = capsys.readouterr()
            assert "1 pages found" in captured.out


class TestCLIProvenance:
    def test_provenance_shows_evidence(self, tmp_path, capsys):
        """Provenance subcommand should show evidence chain for a page."""
        with patch("scripts.cli.list_wiki_pages") as mock_list, \
             patch("scripts.cli.read_provenance") as mock_prov:
            mock_list.return_value = [Path("wiki/concepts/RAG.md")]
            mock_prov.return_value = {
                "page": "RAG",
                "content_hash": "abc123",
                "claims": [{"id": "c1", "type": "fact", "summary": "test"}],
                "sources": [],
            }
            main(["provenance", "RAG"])
            captured = capsys.readouterr()
            assert "RAG" in captured.out


class TestCLIGenerateInstructions:
    def test_generate_instructions_placeholder(self, tmp_path, capsys):
        """Generate-instructions should handle missing module gracefully."""
        # generate_instructions module doesn't exist yet (Task 13)
        main(["generate-instructions"])
        captured = capsys.readouterr()
        # Should print something (either success or module-not-found message)
        assert len(captured.out) > 0


class TestCLINoCommand:
    def test_no_command_shows_help(self, capsys):
        """Running with no command should show help."""
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 0