"""Unit tests for DefaultEntityResolutionStrategy.

All tests mock SearchPipeline — no I/O made.
Covers: constructor, matching above/below threshold, empty graph,
edge cases (empty input, order, len invariant), and error propagation.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from depth_graph_search.adapters.search.entity_resolution import DefaultEntityResolutionStrategy
from depth_graph_search.core.domain.entities import Node, ResolvedNode, ScoredNode
from depth_graph_search.core.domain.exceptions import StorageError
from depth_graph_search.core.ports.entity_resolution import EntityResolutionStrategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_strategy() -> DefaultEntityResolutionStrategy:
    """Return a DefaultEntityResolutionStrategy with a MagicMock pipeline."""
    pipeline = MagicMock()
    return DefaultEntityResolutionStrategy(pipeline=pipeline)


def _make_node(content: str = "some content", node_id: str | None = None) -> Node:
    """Build a domain Node with optional fixed ID."""
    if node_id is not None:
        return Node(content=content, id=node_id)
    return Node(content=content)


def _make_scored_node(score: float, node_id: str = "existing-id") -> ScoredNode:
    """Build a ScoredNode with the given score."""
    return ScoredNode(
        node=Node(content="existing", id=node_id),
        score=score,
        distance=0,
    )


# ---------------------------------------------------------------------------
# TestConstructor
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_pipeline_stored(self) -> None:
        pipeline = MagicMock()
        strategy = DefaultEntityResolutionStrategy(pipeline=pipeline)
        assert strategy._pipeline is pipeline

    def test_isinstance_entity_resolution_strategy(self) -> None:
        strategy = _make_strategy()
        assert isinstance(strategy, EntityResolutionStrategy)


# ---------------------------------------------------------------------------
# TestResolve_Matching
# ---------------------------------------------------------------------------


class TestResolve_Matching:
    def test_score_above_threshold_is_not_new(self) -> None:
        strategy = _make_strategy()
        node = _make_node("AI concept")
        strategy._pipeline.search.return_value = [_make_scored_node(score=0.9)]

        result = strategy.resolve([node], threshold=0.85)

        assert len(result) == 1
        assert result[0].is_new is False
        assert result[0].matched_id == "existing-id"

    def test_score_below_threshold_is_new(self) -> None:
        strategy = _make_strategy()
        node = _make_node("AI concept")
        strategy._pipeline.search.return_value = [_make_scored_node(score=0.5)]

        result = strategy.resolve([node], threshold=0.85)

        assert len(result) == 1
        assert result[0].is_new is True
        assert result[0].matched_id is None

    def test_empty_result_is_new(self) -> None:
        strategy = _make_strategy()
        node = _make_node("something")
        strategy._pipeline.search.return_value = []

        result = strategy.resolve([node], threshold=0.85)

        assert result[0].is_new is True
        assert result[0].matched_id is None


# ---------------------------------------------------------------------------
# TestResolve_EdgeCases
# ---------------------------------------------------------------------------


class TestResolve_EdgeCases:
    def test_empty_input_returns_empty(self) -> None:
        strategy = _make_strategy()

        result = strategy.resolve([], threshold=0.85)

        assert result == []

    def test_empty_input_pipeline_never_called(self) -> None:
        strategy = _make_strategy()

        strategy.resolve([], threshold=0.85)

        strategy._pipeline.search.assert_not_called()

    def test_output_order_matches_input(self) -> None:
        strategy = _make_strategy()
        n1 = _make_node("alpha", "id-1")
        n2 = _make_node("beta", "id-2")
        n3 = _make_node("gamma", "id-3")

        # n1 → match, n2 → no match, n3 → match
        def search_side_effect(content: str, **_kwargs: object) -> list[ScoredNode]:
            if content == "alpha":
                return [_make_scored_node(0.9, "match-1")]
            if content == "beta":
                return []
            return [_make_scored_node(0.95, "match-3")]

        strategy._pipeline.search.side_effect = search_side_effect

        result = strategy.resolve([n1, n2, n3], threshold=0.85)

        assert result[0].node.id == "id-1"
        assert result[1].node.id == "id-2"
        assert result[2].node.id == "id-3"

    def test_len_result_equals_len_input(self) -> None:
        strategy = _make_strategy()
        nodes = [_make_node(f"node {i}") for i in range(5)]
        strategy._pipeline.search.return_value = []

        result = strategy.resolve(nodes, threshold=0.85)

        assert len(result) == len(nodes)

    def test_threshold_zero_any_score_matches(self) -> None:
        """threshold=0.0: any non-empty result (score ≥ 0) is a match."""
        strategy = _make_strategy()
        node = _make_node("anything")
        strategy._pipeline.search.return_value = [_make_scored_node(score=0.0)]

        result = strategy.resolve([node], threshold=0.0)

        assert result[0].is_new is False

    def test_threshold_one_score_099_is_new(self) -> None:
        """threshold=1.0: score=0.99 is strictly below threshold → is_new=True."""
        strategy = _make_strategy()
        node = _make_node("almost")
        strategy._pipeline.search.return_value = [_make_scored_node(score=0.99)]

        result = strategy.resolve([node], threshold=1.0)

        assert result[0].is_new is True


# ---------------------------------------------------------------------------
# TestResolve_ErrorPropagation
# ---------------------------------------------------------------------------


class TestResolve_ErrorPropagation:
    def test_storage_error_propagates(self) -> None:
        strategy = _make_strategy()
        node = _make_node("will fail")
        strategy._pipeline.search.side_effect = StorageError("Graph store unavailable")

        with pytest.raises(StorageError, match="Graph store unavailable"):
            strategy.resolve([node], threshold=0.85)
