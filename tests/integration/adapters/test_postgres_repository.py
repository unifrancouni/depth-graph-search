"""Integration tests for PostgresGraphRepository.

Tests run against a real PostgreSQL 17 + AGE + pgvector container
(built from Dockerfile.dev) via testcontainers-python.

Run with:
    pytest tests/integration/ -v

Requires Docker. Skipped automatically if Docker is unavailable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from depth_graph_search.core.domain.entities import Edge, Embedding, Node
from depth_graph_search.core.domain.exceptions import StorageError

if TYPE_CHECKING:
    from depth_graph_search.adapters.postgres.repository import PostgresGraphRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DIM = 3072


def _make_embedding(dimensions: int = _DIM, seed: float = 0.1) -> Embedding:
    vector = [seed * (i % 100 + 1) / 100 for i in range(dimensions)]
    return Embedding(vector=vector, model="test-model", dimensions=dimensions)


def _make_node(content: str, metadata: dict | None = None, seed: float = 0.1) -> Node:
    return Node(
        content=content,
        embedding=_make_embedding(seed=seed),
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Task 5.3 — initialize() idempotency + schema verification
# ---------------------------------------------------------------------------


class TestInitialize:
    def test_initialize_idempotent_no_error(  # type: ignore[no-untyped-def]
        self, repository: PostgresGraphRepository, connection
    ) -> None:
        """Calling initialize() twice must not raise."""
        # repository fixture already called initialize() once
        repository.initialize()  # second call — must succeed silently

    def test_nodes_table_empty_after_init(  # type: ignore[no-untyped-def]
        self, repository: PostgresGraphRepository, connection
    ) -> None:
        row = connection.execute("SELECT COUNT(*) FROM nodes").fetchone()
        assert row is not None
        assert row[0] == 0

    def test_hnsw_index_exists(self, repository: PostgresGraphRepository, connection) -> None:  # type: ignore[no-untyped-def]
        row = connection.execute(
            "SELECT indexname FROM pg_indexes"
            " WHERE tablename = 'nodes' AND indexname = 'idx_nodes_embedding'"
        ).fetchone()
        assert row is not None, "HNSW index idx_nodes_embedding not found"


# ---------------------------------------------------------------------------
# Task 5.4 — save_node() + get_node() roundtrip
# ---------------------------------------------------------------------------


class TestSaveAndGetNode:
    def test_save_and_get_node_roundtrip(self, repository: PostgresGraphRepository) -> None:  # type: ignore[no-untyped-def]
        node = _make_node("The speed of light is 3e8 m/s", metadata={"topic": "physics"})
        repository.save_node(node)

        fetched = repository.get_node(node.id)

        assert fetched is not None
        assert fetched.id == node.id
        assert fetched.content == node.content
        assert fetched.metadata == node.metadata
        assert fetched.embedding is not None
        assert len(fetched.embedding.vector) == _DIM

    def test_get_node_returns_none_for_unknown_id(  # type: ignore[no-untyped-def]
        self, repository: PostgresGraphRepository
    ) -> None:
        result = repository.get_node("non-existent-id-xyz")
        assert result is None

    def test_save_node_with_null_embedding(self, repository: PostgresGraphRepository) -> None:  # type: ignore[no-untyped-def]
        node = Node(content="no embedding yet", embedding=None)
        repository.save_node(node)

        fetched = repository.get_node(node.id)
        assert fetched is not None
        assert fetched.embedding is None


# ---------------------------------------------------------------------------
# Task 5.5 — save_node() upsert
# ---------------------------------------------------------------------------


class TestSaveNodeUpsert:
    def test_save_same_id_twice_no_exception(self, repository: PostgresGraphRepository) -> None:  # type: ignore[no-untyped-def]
        node = Node(id="fixed-id", content="original", embedding=_make_embedding())
        repository.save_node(node)

        updated = Node(
            id="fixed-id", content="updated content", embedding=_make_embedding(seed=0.5)
        )
        repository.save_node(updated)  # must not raise

    def test_second_save_updates_content(self, repository: PostgresGraphRepository) -> None:  # type: ignore[no-untyped-def]
        node = Node(id="upsert-id", content="first version", embedding=_make_embedding())
        repository.save_node(node)

        updated = Node(
            id="upsert-id", content="second version", embedding=_make_embedding(seed=0.9)
        )
        repository.save_node(updated)

        fetched = repository.get_node("upsert-id")
        assert fetched is not None
        assert fetched.content == "second version"


# ---------------------------------------------------------------------------
# Task 5.6 — save_edge() + traverse_bfs()
# ---------------------------------------------------------------------------


class TestEdgeAndBFS:
    def test_bfs_depth1_finds_direct_neighbors(self, repository: PostgresGraphRepository) -> None:  # type: ignore[no-untyped-def]
        node_a = _make_node("Node A", seed=0.1)
        node_b = _make_node("Node B", seed=0.2)
        node_c = _make_node("Node C", seed=0.3)

        repository.save_node(node_a)
        repository.save_node(node_b)
        repository.save_node(node_c)

        repository.save_edge(Edge(source_id=node_a.id, target_id=node_b.id, relationship="LINKS"))
        repository.save_edge(Edge(source_id=node_a.id, target_id=node_c.id, relationship="LINKS"))

        result = repository.traverse_bfs([node_a], depth_m=1)
        result_ids = {n.id for n in result}

        assert node_a.id in result_ids
        assert node_b.id in result_ids
        assert node_c.id in result_ids

    def test_save_edge_missing_source_raises(self, repository: PostgresGraphRepository) -> None:  # type: ignore[no-untyped-def]
        node_b = _make_node("Node B")
        repository.save_node(node_b)

        edge = Edge(source_id="ghost-id", target_id=node_b.id, relationship="REL")
        with pytest.raises(StorageError, match="source/target node not found"):
            repository.save_edge(edge)

    def test_save_edge_missing_target_raises(self, repository: PostgresGraphRepository) -> None:  # type: ignore[no-untyped-def]
        node_a = _make_node("Node A")
        repository.save_node(node_a)

        edge = Edge(source_id=node_a.id, target_id="ghost-id", relationship="REL")
        with pytest.raises(StorageError, match="source/target node not found"):
            repository.save_edge(edge)


# ---------------------------------------------------------------------------
# Task 5.7 — traverse_bfs() edge cases
# ---------------------------------------------------------------------------


class TestTraverseBFS:
    def test_bfs_depth0_returns_only_entry_nodes(  # type: ignore[no-untyped-def]
        self, repository: PostgresGraphRepository
    ) -> None:
        node_a = _make_node("Entry only")
        node_b = _make_node("Neighbor")
        repository.save_node(node_a)
        repository.save_node(node_b)
        repository.save_edge(Edge(source_id=node_a.id, target_id=node_b.id, relationship="HAS"))

        result = repository.traverse_bfs([node_a], depth_m=0)
        assert len(result) == 1
        assert result[0].id == node_a.id

    def test_bfs_isolated_node_returns_only_that_node(  # type: ignore[no-untyped-def]
        self, repository: PostgresGraphRepository
    ) -> None:
        isolated = _make_node("Isolated node")
        repository.save_node(isolated)

        result = repository.traverse_bfs([isolated], depth_m=2)
        assert len(result) == 1
        assert result[0].id == isolated.id

    def test_bfs_deduplicates_shared_neighbor(self, repository: PostgresGraphRepository) -> None:  # type: ignore[no-untyped-def]
        """Nodes A and B both connect to C — C must appear exactly once."""
        node_a = _make_node("A", seed=0.1)
        node_b = _make_node("B", seed=0.2)
        node_c = _make_node("C", seed=0.3)

        repository.save_node(node_a)
        repository.save_node(node_b)
        repository.save_node(node_c)

        repository.save_edge(Edge(source_id=node_a.id, target_id=node_c.id, relationship="TO"))
        repository.save_edge(Edge(source_id=node_b.id, target_id=node_c.id, relationship="TO"))

        result = repository.traverse_bfs([node_a, node_b], depth_m=1)
        result_ids = [n.id for n in result]

        # node_c must appear exactly once
        assert result_ids.count(node_c.id) == 1


# ---------------------------------------------------------------------------
# Task 5.8 — search_hybrid() RRF ranking
# ---------------------------------------------------------------------------


class TestSearchHybrid:
    def test_hybrid_search_returns_nodes(self, repository: PostgresGraphRepository) -> None:  # type: ignore[no-untyped-def]
        for i in range(5):
            node = Node(
                content=f"quantum physics paper number {i}",
                embedding=_make_embedding(seed=0.1 * (i + 1)),
                metadata={"idx": i},
            )
            repository.save_node(node)

        query_emb = _make_embedding(seed=0.3)
        result = repository.search_hybrid(query_emb, "quantum physics", top_n=3)

        assert len(result) <= 3
        assert all(isinstance(n, Node) for n in result)

    def test_hybrid_search_respects_top_n(self, repository: PostgresGraphRepository) -> None:  # type: ignore[no-untyped-def]
        for i in range(5):
            node = Node(
                content=f"machine learning concept {i}",
                embedding=_make_embedding(seed=0.1 * (i + 1)),
            )
            repository.save_node(node)

        query_emb = _make_embedding(seed=0.2)
        result = repository.search_hybrid(query_emb, "machine learning", top_n=2)

        assert len(result) <= 2


# ---------------------------------------------------------------------------
# Task 5.9 — search_hybrid() with metadata_filter
# ---------------------------------------------------------------------------


class TestSearchHybridMetadataFilter:
    def test_metadata_filter_restricts_results(self, repository: PostgresGraphRepository) -> None:  # type: ignore[no-untyped-def]
        matching = Node(
            content="retrieval augmented generation overview",
            embedding=_make_embedding(seed=0.4),
            metadata={"source": "doc-01"},
        )
        non_matching = Node(
            content="retrieval augmented generation overview copy",
            embedding=_make_embedding(seed=0.5),
            metadata={"source": "doc-99"},
        )
        repository.save_node(matching)
        repository.save_node(non_matching)

        query_emb = _make_embedding(seed=0.4)
        result = repository.search_hybrid(
            query_emb,
            "retrieval augmented generation",
            top_n=10,
            metadata_filter={"source": "doc-01"},
        )

        result_ids = {n.id for n in result}
        assert matching.id in result_ids
        assert non_matching.id not in result_ids

    def test_no_metadata_filter_returns_all_candidates(  # type: ignore[no-untyped-def]
        self, repository: PostgresGraphRepository
    ) -> None:
        node_a = Node(
            content="graph neural network",
            embedding=_make_embedding(seed=0.1),
            metadata={"src": "a"},
        )
        node_b = Node(
            content="graph neural network variant",
            embedding=_make_embedding(seed=0.2),
            metadata={"src": "b"},
        )
        repository.save_node(node_a)
        repository.save_node(node_b)

        query_emb = _make_embedding(seed=0.15)
        result = repository.search_hybrid(query_emb, "graph neural network", top_n=10)
        result_ids = {n.id for n in result}

        # Both nodes are candidates with no filter
        assert node_a.id in result_ids
        assert node_b.id in result_ids


# ---------------------------------------------------------------------------
# Task 5.10 — search_hybrid() returns empty list on no matches
# ---------------------------------------------------------------------------


class TestSearchHybridEmpty:
    def test_returns_empty_list_on_no_matches(self, repository: PostgresGraphRepository) -> None:  # type: ignore[no-untyped-def]
        query_emb = _make_embedding(seed=0.5)
        result = repository.search_hybrid(query_emb, "zzzzz nonexistent term zzzzz", top_n=5)

        assert result == []
        assert isinstance(result, list)
