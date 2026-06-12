"""Unit tests for api/schemas.py — request/response DTO validation.

Tests cover:
  - IngestRequest: text required, metadata optional
  - SearchRequest: defaults (top_n=5, depth_m=2), top_n≥1 constraint
  - SearchResultItem: correct fields, no embedding field
  - IngestResponse: node_count and edge_count fields
  - SearchResponse: results list
  - HealthResponse: status and db Literal fields
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from depth_graph_search.api.schemas import (
    HealthResponse,
    IngestRequest,
    IngestResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)


# ---------------------------------------------------------------------------
# IngestRequest
# ---------------------------------------------------------------------------


class TestIngestRequest:
    def test_text_is_required(self) -> None:
        """Empty body raises ValidationError identifying missing 'text' field."""
        with pytest.raises(ValidationError) as exc_info:
            IngestRequest.model_validate({})
        assert "text" in str(exc_info.value)

    def test_text_accepted(self) -> None:
        req = IngestRequest(text="Alice knows Bob")
        assert req.text == "Alice knows Bob"

    def test_metadata_defaults_to_none(self) -> None:
        req = IngestRequest(text="some text")
        assert req.metadata is None

    def test_metadata_accepted(self) -> None:
        req = IngestRequest(text="text", metadata={"source": "test"})
        assert req.metadata == {"source": "test"}

    def test_metadata_accepts_nested_values(self) -> None:
        req = IngestRequest(text="text", metadata={"k": 1, "nested": {"a": True}})
        assert req.metadata["nested"]["a"] is True


# ---------------------------------------------------------------------------
# SearchRequest
# ---------------------------------------------------------------------------


class TestSearchRequest:
    def test_query_is_required(self) -> None:
        """Missing query raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRequest.model_validate({})
        assert "query" in str(exc_info.value)

    def test_top_n_defaults_to_five(self) -> None:
        req = SearchRequest(query="test")
        assert req.top_n == 5

    def test_depth_m_defaults_to_two(self) -> None:
        req = SearchRequest(query="test")
        assert req.depth_m == 2

    def test_metadata_filter_defaults_to_none(self) -> None:
        req = SearchRequest(query="test")
        assert req.metadata_filter is None

    def test_top_n_zero_raises(self) -> None:
        """top_n=0 violates ge=1 constraint."""
        with pytest.raises(ValidationError):
            SearchRequest(query="test", top_n=0)

    def test_top_n_negative_raises(self) -> None:
        """top_n=-1 violates ge=1 constraint."""
        with pytest.raises(ValidationError):
            SearchRequest(query="test", top_n=-1)

    def test_top_n_one_is_valid(self) -> None:
        req = SearchRequest(query="test", top_n=1)
        assert req.top_n == 1

    def test_depth_m_zero_is_valid(self) -> None:
        """depth_m=0 is allowed (ge=0)."""
        req = SearchRequest(query="test", depth_m=0)
        assert req.depth_m == 0

    def test_depth_m_negative_raises(self) -> None:
        with pytest.raises(ValidationError):
            SearchRequest(query="test", depth_m=-1)

    def test_custom_values_stored(self) -> None:
        req = SearchRequest(
            query="Alice",
            top_n=10,
            depth_m=3,
            metadata_filter={"tag": "entity"},
        )
        assert req.query == "Alice"
        assert req.top_n == 10
        assert req.depth_m == 3
        assert req.metadata_filter == {"tag": "entity"}


# ---------------------------------------------------------------------------
# SearchResultItem
# ---------------------------------------------------------------------------


class TestSearchResultItem:
    def _make_item(self, **overrides) -> SearchResultItem:
        defaults = {
            "id": "node-uuid-1",
            "content": "Alice is a person.",
            "metadata": {"source": "doc"},
            "score": 0.85,
            "distance": 0,
        }
        return SearchResultItem(**{**defaults, **overrides})

    def test_fields_stored_correctly(self) -> None:
        item = self._make_item()
        assert item.id == "node-uuid-1"
        assert item.content == "Alice is a person."
        assert item.metadata == {"source": "doc"}
        assert item.score == 0.85
        assert item.distance == 0

    def test_no_embedding_field(self) -> None:
        """SearchResultItem must NOT have an embedding field."""
        item = self._make_item()
        assert not hasattr(item, "embedding")

    def test_serialized_dict_excludes_embedding(self) -> None:
        """model_dump() output must not contain 'embedding' key."""
        item = self._make_item()
        serialised = item.model_dump()
        assert "embedding" not in serialised

    def test_serialized_keys(self) -> None:
        item = self._make_item()
        keys = set(item.model_dump().keys())
        assert keys == {"id", "content", "metadata", "score", "distance"}

    def test_score_is_float(self) -> None:
        item = self._make_item(score=0.5)
        assert isinstance(item.score, float)

    def test_distance_is_int(self) -> None:
        item = self._make_item(distance=1)
        assert isinstance(item.distance, int)


# ---------------------------------------------------------------------------
# IngestResponse
# ---------------------------------------------------------------------------


class TestIngestResponse:
    def test_node_and_edge_count_stored(self) -> None:
        resp = IngestResponse(node_count=3, edge_count=2)
        assert resp.node_count == 3
        assert resp.edge_count == 2

    def test_zero_counts_valid(self) -> None:
        resp = IngestResponse(node_count=0, edge_count=0)
        assert resp.node_count == 0
        assert resp.edge_count == 0

    def test_serialized_fields(self) -> None:
        resp = IngestResponse(node_count=1, edge_count=0)
        data = resp.model_dump()
        assert set(data.keys()) == {"node_count", "edge_count"}


# ---------------------------------------------------------------------------
# SearchResponse
# ---------------------------------------------------------------------------


class TestSearchResponse:
    def test_empty_results_list(self) -> None:
        resp = SearchResponse(results=[])
        assert resp.results == []

    def test_results_list_with_items(self) -> None:
        item = SearchResultItem(
            id="x", content="y", metadata={}, score=0.9, distance=0
        )
        resp = SearchResponse(results=[item])
        assert len(resp.results) == 1
        assert resp.results[0].id == "x"


# ---------------------------------------------------------------------------
# HealthResponse
# ---------------------------------------------------------------------------


class TestHealthResponse:
    def test_ok_status(self) -> None:
        resp = HealthResponse(status="ok", db="connected")
        assert resp.status == "ok"
        assert resp.db == "connected"

    def test_degraded_status(self) -> None:
        resp = HealthResponse(status="degraded", db="error")
        assert resp.status == "degraded"
        assert resp.db == "error"

    def test_invalid_status_raises(self) -> None:
        """status must be 'ok' or 'degraded' — anything else raises."""
        with pytest.raises(ValidationError):
            HealthResponse(status="unknown", db="connected")

    def test_invalid_db_raises(self) -> None:
        """db must be 'connected' or 'error' — anything else raises."""
        with pytest.raises(ValidationError):
            HealthResponse(status="ok", db="unknown")
