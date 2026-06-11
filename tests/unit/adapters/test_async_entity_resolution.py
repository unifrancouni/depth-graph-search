"""Unit tests for AsyncDefaultEntityResolutionStrategy.

Covers: resolve calls search once per entity in order; empty list returns [];
sequential (not parallel) call pattern.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, call

import pytest

from depth_graph_search.adapters.search.async_entity_resolution import (
    AsyncDefaultEntityResolutionStrategy,
)
from depth_graph_search.core.domain.entities import Node
from depth_graph_search.core.ports.async_ports import AsyncEntityResolutionStrategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_node(node_id: str = "n1", content: str = "content") -> Node:
    return Node(id=node_id, content=content)


def _make_strategy(
    search_return_values: list[list[Node]] | None = None,
) -> tuple[AsyncDefaultEntityResolutionStrategy, AsyncMock]:
    pipeline = AsyncMock()
    if search_return_values is not None:
        pipeline.search.side_effect = search_return_values
    else:
        pipeline.search.return_value = []

    strategy = AsyncDefaultEntityResolutionStrategy(pipeline=pipeline)
    return strategy, pipeline


# ---------------------------------------------------------------------------
# TestEntityResolution
# ---------------------------------------------------------------------------


class TestEntityResolution:
    def test_isinstance_async_entity_resolution_strategy(self) -> None:
        strategy, _ = _make_strategy()
        assert isinstance(strategy, AsyncEntityResolutionStrategy)

    def test_constructor_stores_pipeline(self) -> None:
        pipeline = AsyncMock()
        strategy = AsyncDefaultEntityResolutionStrategy(pipeline=pipeline)
        assert strategy._pipeline is pipeline

    async def test_resolve_empty_list_returns_empty_without_calling_search(self) -> None:
        strategy, pipeline = _make_strategy()

        result = await strategy.resolve([])

        assert result == []
        pipeline.search.assert_not_awaited()

    async def test_resolve_single_entity_calls_search_once(self) -> None:
        node = _make_node("n1", "Python")
        strategy, pipeline = _make_strategy(search_return_values=[[node]])

        result = await strategy.resolve(["Python"])

        assert pipeline.search.await_count == 1
        pipeline.search.assert_awaited_with("Python", top_n=1, depth_m=0)
        assert len(result) == 1
        assert result[0].id == "n1"

    async def test_resolve_three_entities_calls_search_three_times_in_order(self) -> None:
        node1 = _make_node("n1", "Python")
        node2 = _make_node("n2", "Guido")
        node3 = _make_node("n3", "BDFL")
        strategy, pipeline = _make_strategy(
            search_return_values=[[node1], [node2], [node3]]
        )

        result = await strategy.resolve(["Python", "Guido", "BDFL"])

        # Verify search was called 3 times in order
        assert pipeline.search.await_count == 3
        pipeline.search.assert_has_awaits([
            call("Python", top_n=1, depth_m=0),
            call("Guido", top_n=1, depth_m=0),
            call("BDFL", top_n=1, depth_m=0),
        ])
        # All 3 results collected
        assert len(result) == 3

    async def test_resolve_entity_with_no_match_skips_result(self) -> None:
        """If search returns [] for an entity, it should not appear in results."""
        node = _make_node("n1", "Python")
        strategy, pipeline = _make_strategy(
            search_return_values=[[node], []]  # second entity has no match
        )

        result = await strategy.resolve(["Python", "Unknown"])

        assert len(result) == 1
        assert result[0].id == "n1"

    async def test_resolve_preserves_order(self) -> None:
        """Results should appear in the same order as entity inputs."""
        node_a = _make_node("a", "Alice")
        node_b = _make_node("b", "Bob")
        strategy, pipeline = _make_strategy(
            search_return_values=[[node_a], [node_b]]
        )

        result = await strategy.resolve(["Alice", "Bob"])

        assert result[0].id == "a"
        assert result[1].id == "b"
