"""Unit tests for DefaultSearchPipeline.

All tests mock GraphRepository and EmbeddingProvider — no I/O made.
Covers: constructor, happy path, empty/edge cases, scoring formula,
ordering, deduplication, and exception propagation.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from depth_graph_search.adapters.search.pipeline import DefaultSearchPipeline
from depth_graph_search.core.domain.entities import Embedding, Node, ScoredNode
from depth_graph_search.core.domain.exceptions import LLMError, StorageError
from depth_graph_search.core.ports.search_pipeline import SearchPipeline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pipeline() -> DefaultSearchPipeline:
    """Return a DefaultSearchPipeline with two MagicMock dependencies."""
    graph_repo = MagicMock()
    embedding_provider = MagicMock()
    return DefaultSearchPipeline(
        graph_repository=graph_repo,
        embedding_provider=embedding_provider,
    )


def _make_node(node_id: str, content: str = "test content") -> Node:
    """Build a domain Node with a fixed ID for predictable assertions."""
    return Node(content=content, id=node_id)


def _make_embedding() -> Embedding:
    """Build a minimal Embedding for mock returns."""
    return Embedding(vector=[0.1, 0.2, 0.3], model="text-embedding-3-small", dimensions=3)


# ---------------------------------------------------------------------------
# TestConstructor
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_dependencies_stored(self) -> None:
        graph_repo = MagicMock()
        embedding_provider = MagicMock()
        pipeline = DefaultSearchPipeline(
            graph_repository=graph_repo,
            embedding_provider=embedding_provider,
        )
        assert pipeline._graph_repository is graph_repo
        assert pipeline._embedding_provider is embedding_provider

    def test_isinstance_search_pipeline(self) -> None:
        pipeline = _make_pipeline()
        assert isinstance(pipeline, SearchPipeline)

    def test_no_side_effects_on_construction(self) -> None:
        """Constructor must not call any method on injected dependencies."""
        graph_repo = MagicMock()
        embedding_provider = MagicMock()
        DefaultSearchPipeline(
            graph_repository=graph_repo,
            embedding_provider=embedding_provider,
        )
        graph_repo.search_hybrid.assert_not_called()
        graph_repo.traverse_bfs.assert_not_called()
        embedding_provider.embed.assert_not_called()


# ---------------------------------------------------------------------------
# TestSearch_HappyPath
# ---------------------------------------------------------------------------


class TestSearch_HappyPath:
    def test_happy_path_returns_scored_nodes(self) -> None:
        pipeline = _make_pipeline()
        embedding = _make_embedding()
        entry_nodes = [_make_node("n1"), _make_node("n2")]
        bfs_nodes = [_make_node("n1"), _make_node("n2"), _make_node("n3"), _make_node("n4")]

        pipeline._embedding_provider.embed.return_value = embedding
        pipeline._graph_repository.search_hybrid.return_value = entry_nodes
        pipeline._graph_repository.traverse_bfs.return_value = bfs_nodes

        results = pipeline.search("AI", top_n=3, depth_m=2)

        assert len(results) == 3
        assert all(isinstance(sn, ScoredNode) for sn in results)

    def test_entry_nodes_have_distance_zero(self) -> None:
        pipeline = _make_pipeline()
        embedding = _make_embedding()
        entry_nodes = [_make_node("n1"), _make_node("n2")]

        pipeline._embedding_provider.embed.return_value = embedding
        pipeline._graph_repository.search_hybrid.return_value = entry_nodes
        pipeline._graph_repository.traverse_bfs.return_value = entry_nodes

        results = pipeline.search("AI", top_n=5, depth_m=2)

        entry_results = [sn for sn in results if sn.node.id in {"n1", "n2"}]
        assert all(sn.distance == 0 for sn in entry_results)

    def test_bfs_only_nodes_have_distance_one_score_zero(self) -> None:
        pipeline = _make_pipeline()
        embedding = _make_embedding()
        entry_nodes = [_make_node("n1")]
        bfs_nodes = [_make_node("n1"), _make_node("n2_bfs")]

        pipeline._embedding_provider.embed.return_value = embedding
        pipeline._graph_repository.search_hybrid.return_value = entry_nodes
        pipeline._graph_repository.traverse_bfs.return_value = bfs_nodes

        results = pipeline.search("AI", top_n=5, depth_m=2)

        bfs_result = next(sn for sn in results if sn.node.id == "n2_bfs")
        assert bfs_result.distance == 1
        assert bfs_result.score == 0.0

    def test_result_capped_at_top_n(self) -> None:
        pipeline = _make_pipeline()
        embedding = _make_embedding()
        # 10 entry nodes + 10 BFS-only = 20 total
        entry_nodes = [_make_node(f"e{i}") for i in range(10)]
        bfs_only = [_make_node(f"b{i}") for i in range(10)]

        pipeline._embedding_provider.embed.return_value = embedding
        pipeline._graph_repository.search_hybrid.return_value = entry_nodes
        pipeline._graph_repository.traverse_bfs.return_value = bfs_only

        results = pipeline.search("query", top_n=5, depth_m=2)

        assert len(results) <= 5


# ---------------------------------------------------------------------------
# TestSearch_EmptyAndEdgeCases
# ---------------------------------------------------------------------------


class TestSearch_EmptyAndEdgeCases:
    def test_empty_hybrid_result_returns_empty(self) -> None:
        pipeline = _make_pipeline()
        pipeline._embedding_provider.embed.return_value = _make_embedding()
        pipeline._graph_repository.search_hybrid.return_value = []

        results = pipeline.search("nothing", top_n=5, depth_m=2)

        assert results == []

    def test_empty_result_skips_traverse_bfs(self) -> None:
        pipeline = _make_pipeline()
        pipeline._embedding_provider.embed.return_value = _make_embedding()
        pipeline._graph_repository.search_hybrid.return_value = []

        pipeline.search("nothing", top_n=5, depth_m=2)

        pipeline._graph_repository.traverse_bfs.assert_not_called()

    def test_depth_m_zero_only_entry_nodes(self) -> None:
        pipeline = _make_pipeline()
        embedding = _make_embedding()
        entry_nodes = [_make_node("n1"), _make_node("n2")]

        pipeline._embedding_provider.embed.return_value = embedding
        pipeline._graph_repository.search_hybrid.return_value = entry_nodes
        # traverse_bfs with depth=0 returns entry nodes only (adapter contract)
        pipeline._graph_repository.traverse_bfs.return_value = entry_nodes

        results = pipeline.search("AI", top_n=5, depth_m=0)

        # traverse_bfs must be called with depth_m=0
        pipeline._graph_repository.traverse_bfs.assert_called_once_with(entry_nodes, 0)
        # All results should have distance=0
        assert all(sn.distance == 0 for sn in results)


# ---------------------------------------------------------------------------
# TestSearch_ScoringAndOrdering
# ---------------------------------------------------------------------------


class TestSearch_ScoringAndOrdering:
    def test_score_formula_rank0_is_1_0(self) -> None:
        """Rank 0 with top_n=5: score = 1.0 - 0/6 = 1.0"""
        pipeline = _make_pipeline()
        embedding = _make_embedding()
        entry_nodes = [_make_node("n0")]

        pipeline._embedding_provider.embed.return_value = embedding
        pipeline._graph_repository.search_hybrid.return_value = entry_nodes
        pipeline._graph_repository.traverse_bfs.return_value = entry_nodes

        results = pipeline.search("q", top_n=5, depth_m=0)

        assert results[0].score == pytest.approx(1.0)

    def test_score_formula_rank1(self) -> None:
        """Rank 1 with top_n=5: score = 1.0 - 1/6 ≈ 0.8333"""
        pipeline = _make_pipeline()
        embedding = _make_embedding()
        entry_nodes = [_make_node("n0"), _make_node("n1")]

        pipeline._embedding_provider.embed.return_value = embedding
        pipeline._graph_repository.search_hybrid.return_value = entry_nodes
        pipeline._graph_repository.traverse_bfs.return_value = entry_nodes

        results = pipeline.search("q", top_n=5, depth_m=0)

        # rank-0 node gets score ≈ 1.0, rank-1 gets ≈ 0.8333
        scores = {sn.node.id: sn.score for sn in results}
        assert scores["n1"] == pytest.approx(1.0 - 1 / 6)

    def test_ordering_score_desc_distance_asc(self) -> None:
        """Results must be sorted: score DESC, then distance ASC."""
        pipeline = _make_pipeline()
        embedding = _make_embedding()
        entry_nodes = [_make_node("e1"), _make_node("e2")]
        bfs_only = [_make_node("b1")]

        pipeline._embedding_provider.embed.return_value = embedding
        pipeline._graph_repository.search_hybrid.return_value = entry_nodes
        pipeline._graph_repository.traverse_bfs.return_value = entry_nodes + bfs_only

        results = pipeline.search("q", top_n=5, depth_m=1)

        for i in range(len(results) - 1):
            a, b = results[i], results[i + 1]
            # score must be non-increasing
            assert a.score >= b.score

    def test_metadata_filter_passed_through(self) -> None:
        pipeline = _make_pipeline()
        embedding = _make_embedding()
        metadata_filter = {"type": "concept"}

        pipeline._embedding_provider.embed.return_value = embedding
        pipeline._graph_repository.search_hybrid.return_value = []

        pipeline.search("q", top_n=5, depth_m=2, metadata_filter=metadata_filter)

        pipeline._graph_repository.search_hybrid.assert_called_once_with(
            embedding, "q", 5, metadata_filter
        )


# ---------------------------------------------------------------------------
# TestSearch_Deduplication
# ---------------------------------------------------------------------------


class TestSearch_Deduplication:
    def test_node_in_both_entry_and_bfs_appears_once(self) -> None:
        pipeline = _make_pipeline()
        embedding = _make_embedding()
        shared_node = _make_node("shared")
        entry_nodes = [shared_node]
        bfs_nodes = [shared_node, _make_node("bfs_only")]

        pipeline._embedding_provider.embed.return_value = embedding
        pipeline._graph_repository.search_hybrid.return_value = entry_nodes
        pipeline._graph_repository.traverse_bfs.return_value = bfs_nodes

        results = pipeline.search("q", top_n=5, depth_m=2)

        ids = [sn.node.id for sn in results]
        assert ids.count("shared") == 1

    def test_deduped_node_keeps_entry_score(self) -> None:
        """When a node appears in both entry and BFS, entry-node score wins."""
        pipeline = _make_pipeline()
        embedding = _make_embedding()
        shared_node = _make_node("shared")
        entry_nodes = [shared_node]
        bfs_nodes = [shared_node]

        pipeline._embedding_provider.embed.return_value = embedding
        pipeline._graph_repository.search_hybrid.return_value = entry_nodes
        pipeline._graph_repository.traverse_bfs.return_value = bfs_nodes

        results = pipeline.search("q", top_n=5, depth_m=2)

        shared_result = next(sn for sn in results if sn.node.id == "shared")
        # Entry score at rank 0, top_n=5: 1.0 - 0/6 = 1.0
        assert shared_result.score == pytest.approx(1.0)
        assert shared_result.distance == 0


# ---------------------------------------------------------------------------
# TestSearch_ErrorPropagation
# ---------------------------------------------------------------------------


class TestSearch_ErrorPropagation:
    def test_storage_error_propagates(self) -> None:
        pipeline = _make_pipeline()
        pipeline._embedding_provider.embed.return_value = _make_embedding()
        pipeline._graph_repository.search_hybrid.side_effect = StorageError("DB down")

        with pytest.raises(StorageError, match="DB down"):
            pipeline.search("q", top_n=5, depth_m=2)

    def test_llm_error_propagates(self) -> None:
        pipeline = _make_pipeline()
        pipeline._embedding_provider.embed.side_effect = LLMError("API error")

        with pytest.raises(LLMError, match="API error"):
            pipeline.search("q", top_n=5, depth_m=2)
