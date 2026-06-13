"""Integration tests for dgs CLI commands via typer.testing.CliRunner.

Tests cover all spec scenarios:

dgs ingest:
  - Happy path with mocked GraphSearch → exit 0
  - Missing --text → exit 2 (typer usage error)
  - Invalid --metadata JSON → exit 1 with flag named in error
  - Env-only connection → SDK called with env-resolved values

dgs search:
  - Happy path → exit 0, results printed
  - Missing --query → exit 2
  - Custom --top-n and --depth forwarded to SDK
  - Invalid --metadata-filter → exit 1 with flag named
  - --format json → valid parseable JSON on stdout

dgs version:
  - Prints __version__ string, exit 0

Error scenarios:
  - Bad DSN / missing env → stderr has human-readable message, exit 1, no Traceback
  - Handled exception has no Traceback in output

All tests mock GraphSearch at the module level (depth_graph_search.cli.main)
so no real database or API calls are made.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

import depth_graph_search as dgs
from depth_graph_search.cli.main import app
from depth_graph_search.core.domain.entities import IngestionResult, Node, ScoredNode

runner = CliRunner()

# ---------------------------------------------------------------------------
# Shared stubs
# ---------------------------------------------------------------------------

_VALID_ENV = {
    "DATABASE_URL": "postgresql://depth:depth@localhost:5432/test",
    "OPENAI_API_KEY": "sk-test-key",
}

_INGEST_RESULT = IngestionResult(node_count=3, edge_count=2)

_SCORED_NODES = [
    ScoredNode(
        node=Node(content="Alice works at Acme", id="aaaabbbb-0000-0000-0000-000000000000"),
        score=0.9,
        distance=0,
    ),
    ScoredNode(
        node=Node(content="Bob at Beta Inc", id="ccccdddd-0000-0000-0000-000000000000"),
        score=0.7,
        distance=1,
    ),
]


def _mock_gs(ingest_return: IngestionResult = _INGEST_RESULT, search_return: list = _SCORED_NODES):
    """Build a MagicMock that mimics GraphSearch context-manager usage."""
    mock_gs = MagicMock()
    mock_gs.__enter__ = MagicMock(return_value=mock_gs)
    mock_gs.__exit__ = MagicMock(return_value=False)
    mock_gs.ingest.return_value = ingest_return
    mock_gs.search.return_value = search_return
    return mock_gs


# ---------------------------------------------------------------------------
# dgs ingest — happy path
# ---------------------------------------------------------------------------


class TestIngestHappyPath:
    def test_exit_code_zero(self) -> None:
        mock_gs = _mock_gs()
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs):
            result = runner.invoke(app, ["ingest", "--text", "Alice at Acme"], env=_VALID_ENV)
        assert result.exit_code == 0, result.output

    def test_sdk_ingest_called(self) -> None:
        mock_gs = _mock_gs()
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs):
            runner.invoke(app, ["ingest", "--text", "Alice at Acme"], env=_VALID_ENV)
        mock_gs.ingest.assert_called_once()

    def test_output_contains_node_count(self) -> None:
        mock_gs = _mock_gs()
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs):
            result = runner.invoke(app, ["ingest", "--text", "Alice at Acme"], env=_VALID_ENV)
        assert "3" in result.stdout

    def test_default_format_is_table(self) -> None:
        """Default format is table — ingest table is a single human-readable line."""
        mock_gs = _mock_gs()
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs):
            result = runner.invoke(app, ["ingest", "--text", "Alice"], env=_VALID_ENV)
        # Ingest table format: "Ingested: 3 nodes, 2 edges"
        assert "Ingested:" in result.stdout
        assert "3" in result.stdout


# ---------------------------------------------------------------------------
# dgs ingest — missing --text
# ---------------------------------------------------------------------------


class TestIngestMissingText:
    def test_missing_text_exits_nonzero(self) -> None:
        """Missing --text should cause typer to exit with a usage error (exit 2)."""
        result = runner.invoke(app, ["ingest"], env=_VALID_ENV)
        assert result.exit_code == 2

    def test_missing_text_has_error_output(self) -> None:
        result = runner.invoke(app, ["ingest"], env=_VALID_ENV)
        # Either stderr or stdout should have an error message
        combined = result.stdout + (result.stderr if hasattr(result, "stderr") else "")
        assert combined.strip() != ""


# ---------------------------------------------------------------------------
# dgs ingest — invalid --metadata JSON
# ---------------------------------------------------------------------------


class TestIngestInvalidMetadata:
    def test_invalid_metadata_exits_one(self) -> None:
        result = runner.invoke(
            app,
            ["ingest", "--text", "Alice", "--metadata", "not-json"],
            env=_VALID_ENV,
        )
        assert result.exit_code == 1

    def test_invalid_metadata_names_flag(self) -> None:
        result = runner.invoke(
            app,
            ["ingest", "--text", "Alice", "--metadata", "not-json"],
            env=_VALID_ENV,
        )
        # stderr should name --metadata
        assert "--metadata" in result.stderr


# ---------------------------------------------------------------------------
# dgs ingest — env-only connection
# ---------------------------------------------------------------------------


class TestIngestEnvOnlyConnection:
    def test_env_only_calls_sdk(self) -> None:
        """No CLI flags for connection — SDK called with env-resolved values."""
        mock_gs = _mock_gs()
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs) as mock_factory:
            result = runner.invoke(app, ["ingest", "--text", "Alice"], env=_VALID_ENV)
        assert result.exit_code == 0, result.output
        mock_factory.assert_called_once()
        # Should be called with the DSN from env
        call_kwargs = mock_factory.call_args
        assert "postgresql" in str(call_kwargs)

    def test_env_with_valid_metadata_calls_ingest_with_dict(self) -> None:
        """Valid --metadata JSON is forwarded as dict to gs.ingest()."""
        mock_gs = _mock_gs()
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs):
            runner.invoke(
                app,
                ["ingest", "--text", "Alice", "--metadata", '{"source": "doc"}'],
                env=_VALID_ENV,
            )
        call_args = mock_gs.ingest.call_args
        assert call_args is not None
        # metadata dict forwarded
        passed_metadata = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("metadata")
        assert passed_metadata == {"source": "doc"}


# ---------------------------------------------------------------------------
# dgs search — happy path
# ---------------------------------------------------------------------------


class TestSearchHappyPath:
    def test_exit_code_zero(self) -> None:
        mock_gs = _mock_gs()
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs):
            result = runner.invoke(app, ["search", "--query", "who works at Acme"], env=_VALID_ENV)
        assert result.exit_code == 0, result.output

    def test_sdk_search_called(self) -> None:
        mock_gs = _mock_gs()
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs):
            runner.invoke(app, ["search", "--query", "Alice"], env=_VALID_ENV)
        mock_gs.search.assert_called_once()

    def test_output_contains_content(self) -> None:
        mock_gs = _mock_gs()
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs):
            result = runner.invoke(app, ["search", "--query", "Alice"], env=_VALID_ENV)
        assert "Alice works at Acme" in result.stdout


# ---------------------------------------------------------------------------
# dgs search — missing --query
# ---------------------------------------------------------------------------


class TestSearchMissingQuery:
    def test_missing_query_exits_nonzero(self) -> None:
        result = runner.invoke(app, ["search"], env=_VALID_ENV)
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# dgs search — custom --top-n and --depth
# ---------------------------------------------------------------------------


class TestSearchCustomOptions:
    def test_top_n_forwarded(self) -> None:
        """--top-n 10 is forwarded to gs.search(top_n=10)."""
        mock_gs = _mock_gs()
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs):
            runner.invoke(
                app,
                ["search", "--query", "Alice", "--top-n", "10"],
                env=_VALID_ENV,
            )
        call_kwargs = mock_gs.search.call_args[1]
        assert call_kwargs.get("top_n") == 10

    def test_depth_forwarded(self) -> None:
        """--depth 3 is forwarded to gs.search(depth_m=3)."""
        mock_gs = _mock_gs()
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs):
            runner.invoke(
                app,
                ["search", "--query", "Alice", "--depth", "3"],
                env=_VALID_ENV,
            )
        call_kwargs = mock_gs.search.call_args[1]
        assert call_kwargs.get("depth_m") == 3


# ---------------------------------------------------------------------------
# dgs search — invalid --metadata-filter
# ---------------------------------------------------------------------------


class TestSearchInvalidMetadataFilter:
    def test_invalid_filter_exits_one(self) -> None:
        result = runner.invoke(
            app,
            ["search", "--query", "Alice", "--metadata-filter", "bad"],
            env=_VALID_ENV,
        )
        assert result.exit_code == 1

    def test_invalid_filter_names_flag(self) -> None:
        result = runner.invoke(
            app,
            ["search", "--query", "Alice", "--metadata-filter", "bad"],
            env=_VALID_ENV,
        )
        assert "--metadata-filter" in result.stderr


# ---------------------------------------------------------------------------
# dgs search — --format json
# ---------------------------------------------------------------------------


class TestSearchJsonFormat:
    def test_json_format_stdout_is_parseable(self) -> None:
        mock_gs = _mock_gs()
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs):
            result = runner.invoke(
                app,
                ["search", "--query", "Alice", "--format", "json"],
                env=_VALID_ENV,
            )
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.stdout)
        assert isinstance(parsed, list)

    def test_json_format_has_content_key(self) -> None:
        mock_gs = _mock_gs()
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs):
            result = runner.invoke(
                app,
                ["search", "--query", "Alice", "--format", "json"],
                env=_VALID_ENV,
            )
        items = json.loads(result.stdout)
        assert "content" in items[0]


# ---------------------------------------------------------------------------
# dgs version
# ---------------------------------------------------------------------------


class TestVersion:
    def test_version_exit_zero(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0

    def test_version_prints_version_string(self) -> None:
        result = runner.invoke(app, ["version"])
        assert dgs.__version__ in result.stdout


# ---------------------------------------------------------------------------
# Error scenarios — no traceback leakage
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_missing_dsn_env_exits_nonzero(self) -> None:
        """Missing DATABASE_URL with no --dsn → exit nonzero with human-readable message."""
        result = runner.invoke(
            app,
            ["ingest", "--text", "Alice"],
            env={"OPENAI_API_KEY": "sk-test"},  # no DATABASE_URL
        )
        assert result.exit_code != 0

    def test_missing_dsn_has_no_traceback_in_stderr(self) -> None:
        result = runner.invoke(
            app,
            ["ingest", "--text", "Alice"],
            env={"OPENAI_API_KEY": "sk-test"},
        )
        # Traceback must NOT appear in stderr
        assert "Traceback" not in result.stderr
        assert 'File "' not in result.stderr

    def test_missing_dsn_has_no_traceback_in_stdout(self) -> None:
        result = runner.invoke(
            app,
            ["ingest", "--text", "Alice"],
            env={"OPENAI_API_KEY": "sk-test"},
        )
        assert "Traceback" not in result.stdout
        assert 'File "' not in result.stdout

    def test_runtime_error_exits_two(self) -> None:
        """A runtime error from SDK should exit with code 2."""
        mock_gs = _mock_gs()
        mock_gs.ingest.side_effect = dgs.LLMError("LLM service unavailable")
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs):
            result = runner.invoke(app, ["ingest", "--text", "Alice"], env=_VALID_ENV)
        assert result.exit_code == 2

    def test_runtime_error_has_no_traceback(self) -> None:
        """Runtime SDK errors must not produce tracebacks."""
        mock_gs = _mock_gs()
        mock_gs.ingest.side_effect = dgs.LLMError("API key invalid")
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs):
            result = runner.invoke(app, ["ingest", "--text", "Alice"], env=_VALID_ENV)
        assert "Traceback" not in result.stderr
        assert "Traceback" not in result.stdout

    def test_runtime_error_has_human_readable_stderr(self) -> None:
        """LLMError message appears in stderr."""
        mock_gs = _mock_gs()
        mock_gs.ingest.side_effect = dgs.LLMError("service down")
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs):
            result = runner.invoke(app, ["ingest", "--text", "Alice"], env=_VALID_ENV)
        assert "Error" in result.stderr or "service down" in result.stderr


# ---------------------------------------------------------------------------
# W-01: CLI flag --dsn overrides DATABASE_URL env var
# ---------------------------------------------------------------------------


class TestFlagBeatsEnv:
    def test_dsn_flag_overrides_env(self) -> None:
        """--dsn flag value must win over DATABASE_URL env var.

        Passes both a CLI flag (postgres://flag/db) and an env var
        (postgres://env/db) and asserts GraphSearch.from_openai receives
        the flag value, not the env value.
        """
        mock_gs = _mock_gs()
        flag_dsn = "postgresql://flag:flag@localhost:5432/flagdb"
        env_dsn = "postgresql://env:env@localhost:5432/envdb"
        env = {**_VALID_ENV, "DATABASE_URL": env_dsn}

        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs) as mock_factory:
            result = runner.invoke(
                app,
                ["ingest", "--text", "Alice", "--dsn", flag_dsn],
                env=env,
            )

        assert result.exit_code == 0, result.output
        mock_factory.assert_called_once()
        call_str = str(mock_factory.call_args)
        assert "flagdb" in call_str, f"Expected flag DSN to win, but got: {call_str}"
        assert "envdb" not in call_str, f"Env DSN leaked into call: {call_str}"


# ---------------------------------------------------------------------------
# W-02: dgs --help lists all three commands
# ---------------------------------------------------------------------------


class TestHelp:
    def test_help_lists_ingest(self) -> None:
        """dgs --help output must include the 'ingest' command."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0, result.output
        assert "ingest" in result.stdout

    def test_help_lists_search(self) -> None:
        """dgs --help output must include the 'search' command."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0, result.output
        assert "search" in result.stdout

    def test_help_lists_version(self) -> None:
        """dgs --help output must include the 'version' command."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0, result.output
        assert "version" in result.stdout


# ---------------------------------------------------------------------------
# S-01: dgs ingest --format json
# ---------------------------------------------------------------------------


class TestIngestJsonFormat:
    def test_json_format_stdout_is_parseable(self) -> None:
        mock_gs = _mock_gs()
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs):
            result = runner.invoke(
                app,
                ["ingest", "--text", "Alice", "--format", "json"],
                env=_VALID_ENV,
            )
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.stdout)
        assert isinstance(parsed, dict)

    def test_json_format_has_node_count(self) -> None:
        mock_gs = _mock_gs()
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs):
            result = runner.invoke(
                app,
                ["ingest", "--text", "Alice", "--format", "json"],
                env=_VALID_ENV,
            )
        parsed = json.loads(result.stdout)
        assert "node_count" in parsed
        assert parsed["node_count"] == 3

    def test_json_format_has_edge_count(self) -> None:
        mock_gs = _mock_gs()
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs):
            result = runner.invoke(
                app,
                ["ingest", "--text", "Alice", "--format", "json"],
                env=_VALID_ENV,
            )
        parsed = json.loads(result.stdout)
        assert "edge_count" in parsed
        assert parsed["edge_count"] == 2


# ---------------------------------------------------------------------------
# S-02: --format plain CliRunner tests for ingest and search
# ---------------------------------------------------------------------------


class TestIngestPlainFormat:
    def test_plain_format_exit_zero(self) -> None:
        mock_gs = _mock_gs()
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs):
            result = runner.invoke(
                app,
                ["ingest", "--text", "Alice", "--format", "plain"],
                env=_VALID_ENV,
            )
        assert result.exit_code == 0, result.output

    def test_plain_format_is_human_readable_line(self) -> None:
        """--format plain outputs a single human-readable line."""
        mock_gs = _mock_gs()
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs):
            result = runner.invoke(
                app,
                ["ingest", "--text", "Alice", "--format", "plain"],
                env=_VALID_ENV,
            )
        assert "Ingested:" in result.stdout
        assert "3" in result.stdout
        assert "2" in result.stdout


class TestSearchPlainFormat:
    def test_plain_format_exit_zero(self) -> None:
        mock_gs = _mock_gs()
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs):
            result = runner.invoke(
                app,
                ["search", "--query", "Alice", "--format", "plain"],
                env=_VALID_ENV,
            )
        assert result.exit_code == 0, result.output

    def test_plain_format_contains_content(self) -> None:
        """--format plain shows result content without Rich markup."""
        mock_gs = _mock_gs()
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs):
            result = runner.invoke(
                app,
                ["search", "--query", "Alice", "--format", "plain"],
                env=_VALID_ENV,
            )
        assert "Alice works at Acme" in result.stdout

    def test_plain_format_has_no_ansi_codes(self) -> None:
        """Plain output must not contain ANSI escape sequences."""
        mock_gs = _mock_gs()
        with patch("depth_graph_search.cli.main.dgs.GraphSearch.from_openai", return_value=mock_gs):
            result = runner.invoke(
                app,
                ["search", "--query", "Alice", "--format", "plain"],
                env=_VALID_ENV,
            )
        assert "\x1b[" not in result.stdout
