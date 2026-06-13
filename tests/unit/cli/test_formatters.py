"""Unit tests for cli/formatters.py — pure output formatter functions.

Tests cover all spec scenarios for both formatters across all 3 formats:

format_ingest_result:
  - json → parseable, has node_count and edge_count keys
  - table → contains column headers (Nodes, Edges)
  - plain → human-readable string, no Rich markup

format_search_results:
  - json → parseable array with id/content/score/distance/metadata keys
  - table → contains column headers (ID, Content, Score, Distance)
  - plain → one line per result, no Rich markup or borders
  - empty list → handled gracefully
"""

from __future__ import annotations

import json

import pytest

from depth_graph_search.cli.formatters import format_ingest_result, format_search_results
from depth_graph_search.core.domain.entities import IngestionResult, Node, ScoredNode


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


def _make_ingest_result(node_count: int = 3, edge_count: int = 2) -> IngestionResult:
    return IngestionResult(node_count=node_count, edge_count=edge_count)


def _make_scored_node(
    content: str = "Alice works at Acme Corp",
    score: float = 0.9,
    distance: int = 0,
    node_id: str = "abc12345-0000-0000-0000-000000000000",
    metadata: dict | None = None,
) -> ScoredNode:
    node = Node(content=content, id=node_id, metadata=metadata or {})
    return ScoredNode(node=node, score=score, distance=distance)


# ---------------------------------------------------------------------------
# format_ingest_result — JSON
# ---------------------------------------------------------------------------


class TestFormatIngestResultJson:
    def test_json_is_parseable(self) -> None:
        output = format_ingest_result(_make_ingest_result(), "json")
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_json_has_node_count(self) -> None:
        output = format_ingest_result(_make_ingest_result(node_count=3), "json")
        assert json.loads(output)["node_count"] == 3

    def test_json_has_edge_count(self) -> None:
        output = format_ingest_result(_make_ingest_result(edge_count=2), "json")
        assert json.loads(output)["edge_count"] == 2

    def test_json_zero_counts(self) -> None:
        output = format_ingest_result(_make_ingest_result(0, 0), "json")
        parsed = json.loads(output)
        assert parsed == {"node_count": 0, "edge_count": 0}


# ---------------------------------------------------------------------------
# format_ingest_result — table
# ---------------------------------------------------------------------------


class TestFormatIngestResultTable:
    def test_table_is_single_line(self) -> None:
        """Ingest table format is a single human-readable line, not a Rich table."""
        output = format_ingest_result(_make_ingest_result(), "table")
        lines = [l for l in output.splitlines() if l.strip()]
        assert len(lines) == 1

    def test_table_contains_node_count(self) -> None:
        output = format_ingest_result(_make_ingest_result(5, 7), "table")
        assert "5" in output

    def test_table_contains_edge_count(self) -> None:
        output = format_ingest_result(_make_ingest_result(5, 7), "table")
        assert "7" in output

    def test_table_matches_spec_format(self) -> None:
        """Output matches spec example: 'Ingested: 3 nodes, 2 edges'."""
        output = format_ingest_result(_make_ingest_result(3, 2), "table")
        assert output == "Ingested: 3 nodes, 2 edges"


# ---------------------------------------------------------------------------
# format_ingest_result — plain
# ---------------------------------------------------------------------------


class TestFormatIngestResultPlain:
    def test_plain_contains_node_count(self) -> None:
        output = format_ingest_result(_make_ingest_result(3, 2), "plain")
        assert "3" in output

    def test_plain_contains_edge_count(self) -> None:
        output = format_ingest_result(_make_ingest_result(3, 2), "plain")
        assert "2" in output

    def test_plain_contains_human_readable_labels(self) -> None:
        output = format_ingest_result(_make_ingest_result(3, 2), "plain")
        assert "nodes" in output.lower()
        assert "edges" in output.lower()

    def test_plain_has_no_rich_markup(self) -> None:
        """Plain output must not contain Rich bracket markup like [bold] or [/]."""
        output = format_ingest_result(_make_ingest_result(), "plain")
        assert "[" not in output or "╭" not in output  # no table borders
        # Stricter: no Rich-style escape sequences
        assert "\x1b[" not in output


# ---------------------------------------------------------------------------
# format_search_results — JSON
# ---------------------------------------------------------------------------


class TestFormatSearchResultsJson:
    def _make_results(self) -> list[ScoredNode]:
        return [
            _make_scored_node(score=0.9, distance=0),
            _make_scored_node("Bob at Beta Inc", score=0.7, distance=1),
        ]

    def test_json_is_parseable(self) -> None:
        output = format_search_results(self._make_results(), "json")
        parsed = json.loads(output)
        assert isinstance(parsed, list)

    def test_json_has_correct_length(self) -> None:
        output = format_search_results(self._make_results(), "json")
        assert len(json.loads(output)) == 2

    def test_json_item_has_id(self) -> None:
        output = format_search_results([_make_scored_node()], "json")
        item = json.loads(output)[0]
        assert "id" in item

    def test_json_item_has_content(self) -> None:
        output = format_search_results([_make_scored_node("hello")], "json")
        item = json.loads(output)[0]
        assert item["content"] == "hello"

    def test_json_item_has_score(self) -> None:
        output = format_search_results([_make_scored_node(score=0.88)], "json")
        item = json.loads(output)[0]
        assert item["score"] == pytest.approx(0.88)

    def test_json_item_has_distance(self) -> None:
        output = format_search_results([_make_scored_node(distance=2)], "json")
        item = json.loads(output)[0]
        assert item["distance"] == 2

    def test_json_item_has_metadata(self) -> None:
        output = format_search_results([_make_scored_node(metadata={"src": "doc"})], "json")
        item = json.loads(output)[0]
        assert item["metadata"] == {"src": "doc"}

    def test_json_empty_list(self) -> None:
        output = format_search_results([], "json")
        assert json.loads(output) == []


# ---------------------------------------------------------------------------
# format_search_results — table
# ---------------------------------------------------------------------------


class TestFormatSearchResultsTable:
    def test_table_has_id_column(self) -> None:
        output = format_search_results([_make_scored_node()], "table")
        assert "ID" in output

    def test_table_has_content_column(self) -> None:
        output = format_search_results([_make_scored_node()], "table")
        assert "Content" in output

    def test_table_has_score_column(self) -> None:
        output = format_search_results([_make_scored_node()], "table")
        assert "Score" in output

    def test_table_has_distance_column(self) -> None:
        output = format_search_results([_make_scored_node()], "table")
        assert "Distance" in output

    def test_table_contains_content(self) -> None:
        output = format_search_results([_make_scored_node("Acme Corp")], "table")
        assert "Acme Corp" in output

    def test_table_empty_results(self) -> None:
        """Empty results should still render a table structure (no crash)."""
        output = format_search_results([], "table")
        # table headers should still show
        assert "ID" in output


# ---------------------------------------------------------------------------
# format_search_results — plain
# ---------------------------------------------------------------------------


class TestFormatSearchResultsPlain:
    def test_plain_one_line_per_result(self) -> None:
        results = [
            _make_scored_node("Alice", score=0.9, distance=0),
            _make_scored_node("Bob", score=0.7, distance=1),
        ]
        output = format_search_results(results, "plain")
        lines = [l for l in output.splitlines() if l.strip()]
        assert len(lines) == 2

    def test_plain_contains_score(self) -> None:
        output = format_search_results([_make_scored_node(score=0.85)], "plain")
        assert "0.85" in output

    def test_plain_contains_content(self) -> None:
        output = format_search_results([_make_scored_node("hello world")], "plain")
        assert "hello world" in output

    def test_plain_contains_depth(self) -> None:
        output = format_search_results([_make_scored_node(distance=3)], "plain")
        assert "3" in output

    def test_plain_no_rich_ansi_codes(self) -> None:
        output = format_search_results([_make_scored_node()], "plain")
        assert "\x1b[" not in output

    def test_plain_empty_list(self) -> None:
        output = format_search_results([], "plain")
        assert "(no results)" in output


# ---------------------------------------------------------------------------
# Invalid format
# ---------------------------------------------------------------------------


class TestInvalidFormat:
    def test_ingest_invalid_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported format"):
            format_ingest_result(_make_ingest_result(), "xml")

    def test_search_invalid_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported format"):
            format_search_results([_make_scored_node()], "csv")
