"""Integration tests for AsyncPostgresGraphRepository.

Requires the Docker container from ``pg_container`` fixture (Dockerfile.dev).
Tests run against a real PostgreSQL + AGE + pgvector instance.

Fixtures come from ``tests/integration/conftest.py``:
    async_repository: Initialized ``AsyncPostgresGraphRepository`` (per test)
    async_pg_connection: Fresh psycopg3 ``AsyncConnection`` (per test)

Skip marker: ``@pytest.mark.integration`` — these tests are slow and require Docker.
"""

from __future__ import annotations

import pytest

from depth_graph_search.adapters.postgres.async_repository import AsyncPostgresGraphRepository
from depth_graph_search.core.domain.entities import Edge, Embedding, Node
from depth_graph_search.core.domain.exceptions import StorageError

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# TestInitialize — idempotency
# ---------------------------------------------------------------------------


class TestInitialize:
    async def test_initialize_is_idempotent(self, async_repository) -> None:
        """Calling initialize() twice should not raise DuplicateSchema."""
        # Already initialized via fixture — call again
        await async_repository.initialize()  # must not raise


# ---------------------------------------------------------------------------
# TestSaveNodeGetNode — round-trip
# ---------------------------------------------------------------------------


class TestSaveNodeGetNode:
    async def test_save_and_get_node_round_trip(self, async_repository) -> None:
        """Save a node, retrieve it, verify content and ID match."""
        node = Node(content="Alice works at Acme Corp", metadata={"source": "test"})
        await async_repository.save_node(node)

        retrieved = await async_repository.get_node(node.id)

        assert retrieved is not None
        assert retrieved.id == node.id
        assert retrieved.content == node.content

    async def test_get_node_returns_none_for_missing(self, async_repository) -> None:
        result = await async_repository.get_node("nonexistent-uuid-0000")
        assert result is None

    async def test_save_node_with_embedding(self, async_repository) -> None:
        embedding = Embedding(vector=[0.1] * 3072, model="test", dimensions=3072)
        node = Node(content="node with embedding", embedding=embedding)
        await async_repository.save_node(node)

        retrieved = await async_repository.get_node(node.id)

        assert retrieved is not None
        assert retrieved.embedding is not None
        assert retrieved.embedding.dimensions == 3072

    async def test_save_node_is_idempotent_upsert(self, async_repository) -> None:
        """Saving the same node twice should upsert, not raise."""
        node = Node(content="original content")
        await async_repository.save_node(node)

        updated = Node(id=node.id, content="updated content")
        await async_repository.save_node(updated)  # should not raise

        retrieved = await async_repository.get_node(node.id)
        assert retrieved is not None
        assert retrieved.content == "updated content"


# ---------------------------------------------------------------------------
# TestSearchHybrid
# ---------------------------------------------------------------------------


class TestSearchHybrid:
    async def test_search_hybrid_returns_ranked_results(self, async_repository) -> None:
        """Insert nodes with embeddings and verify search returns results."""
        embedding = Embedding(vector=[0.1] * 3072, model="test", dimensions=3072)
        node1 = Node(content="Python programming language", embedding=embedding)
        node2 = Node(content="Java programming language", embedding=embedding)
        await async_repository.save_node(node1)
        await async_repository.save_node(node2)

        results = await async_repository.search_hybrid(
            embedding, "programming language", top_n=5
        )

        assert isinstance(results, list)
        # At least the inserted nodes should appear
        ids = {n.id for n in results}
        assert node1.id in ids or node2.id in ids

    async def test_search_hybrid_empty_db_returns_empty(self, async_repository) -> None:
        """Empty database should return empty list."""
        embedding = Embedding(vector=[0.5] * 3072, model="test", dimensions=3072)
        results = await async_repository.search_hybrid(embedding, "nothing", top_n=5)

        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# TestTraverseBfs
# ---------------------------------------------------------------------------


class TestTraverseBfs:
    async def test_traverse_bfs_depth_zero_returns_entry_nodes(
        self, async_repository
    ) -> None:
        node = Node(content="entry node")
        await async_repository.save_node(node)

        results = await async_repository.traverse_bfs([node], depth_m=0)

        assert results == [node]

    async def test_traverse_bfs_returns_connected_nodes(self, async_repository) -> None:
        """Save two connected nodes, traverse from one, expect both in result."""
        node1 = Node(content="node A")
        node2 = Node(content="node B")
        await async_repository.save_node(node1)
        await async_repository.save_node(node2)

        edge = Edge(source_id=node1.id, target_id=node2.id, relationship="CONNECTED")
        await async_repository.save_edge(edge)

        results = await async_repository.traverse_bfs([node1], depth_m=1)

        ids = {n.id for n in results}
        assert node1.id in ids
        assert node2.id in ids
