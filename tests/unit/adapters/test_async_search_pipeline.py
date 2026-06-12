"""Unit tests for AsyncDefaultSearchPipeline.

Covers: search awaits embed then search_hybrid; BFS expand; empty results;
dedup behavior.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from depth_graph_search.adapters.search.async_pipeline import AsyncDefaultSearchPipeline
from depth_graph_search.core.domain.entities import Embedding, Node, ScoredNode
from depth_graph_search.core.ports.async_ports import AsyncSearchPipeline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_embedding(dims: int = 3) -> Embedding:
    return Embedding(vector=[0.1] * dims, model="test", dimensions=dims)


def _make_node(node_id: str = "n1", content: str = "content") -> Node:
    return Node(id=node_id, content=content)


def _make_pipeline(
    embed_return: Embedding | None = None,
    search_hybrid_return: list[Node] | None = None,
    traverse_bfs_return: list[Node] | None = None,
) -> tuple[AsyncDefaultSearchPipeline, AsyncMock, AsyncMock]:
    repo = AsyncMock()
    embedder = AsyncMock()

    embedder.embed.return_value = embed_return or _make_embedding()
    repo.search_hybrid.return_value = search_hybrid_return or []
    repo.traverse_bfs.return_value = traverse_bfs_return or []

    pipeline = AsyncDefaultSearchPipeline(
        graph_repository=repo,
        embedding_provider=embedder,
    )
    return pipeline, repo, embedder


# ---------------------------------------------------------------------------
# TestSearchPipeline
# ---------------------------------------------------------------------------


class TestSearchPipeline:
    def test_isinstance_async_search_pipeline(self) -> None:
        pipeline, _, _ = _make_pipeline()
        assert isinstance(pipeline, AsyncSearchPipeline)

    async def test_search_awaits_embed(self) -> None:
        pipeline, repo, embedder = _make_pipeline()

        await pipeline.search("hello")

        embedder.embed.assert_awaited_once_with("hello")

    async def test_search_awaits_search_hybrid(self) -> None:
        emb = _make_embedding()
        pipeline, repo, embedder = _make_pipeline(embed_return=emb)

        await pipeline.search("hello", top_n=5)

        repo.search_hybrid.assert_awaited_once_with(emb, "hello", 5, None)

    async def test_search_returns_empty_when_no_hybrid_results(self) -> None:
        pipeline, repo, embedder = _make_pipeline(search_hybrid_return=[])

        result = await pipeline.search("empty query")

        assert result == []
        repo.traverse_bfs.assert_not_awaited()

    async def test_search_awaits_traverse_bfs_when_entry_nodes_found(self) -> None:
        entry = [_make_node("n1")]
        pipeline, repo, embedder = _make_pipeline(
            search_hybrid_return=entry,
            traverse_bfs_return=entry,
        )

        await pipeline.search("query", depth_m=2)

        repo.traverse_bfs.assert_awaited_once_with(entry, 2)

    async def test_search_returns_list_of_scored_nodes(self) -> None:
        entry = [_make_node("n1")]
        bfs = [_make_node("n1"), _make_node("n2")]
        pipeline, repo, embedder = _make_pipeline(
            search_hybrid_return=entry,
            traverse_bfs_return=bfs,
        )

        result = await pipeline.search("query", top_n=5)

        assert isinstance(result, list)
        assert len(result) <= 5
        assert all(isinstance(sn, ScoredNode) for sn in result)

    async def test_search_scored_nodes_have_score_and_distance(self) -> None:
        entry = [_make_node("n1")]
        pipeline, repo, embedder = _make_pipeline(
            search_hybrid_return=entry,
            traverse_bfs_return=entry,
        )

        result = await pipeline.search("query", top_n=5)

        assert len(result) >= 1
        sn = result[0]
        assert isinstance(sn.score, float)
        assert isinstance(sn.distance, int)
        assert 0.0 <= sn.score <= 1.0
        assert sn.distance == 0  # entry node

    async def test_search_deduplicates_results(self) -> None:
        """Nodes appearing in both entry and BFS should not be duplicated."""
        node = _make_node("n1")
        pipeline, repo, embedder = _make_pipeline(
            search_hybrid_return=[node],
            traverse_bfs_return=[node, node],  # same node appears twice in BFS
        )

        result = await pipeline.search("query", top_n=5)

        ids = [sn.node.id for sn in result]
        assert len(ids) == len(set(ids))

    async def test_search_respects_top_n(self) -> None:
        nodes = [_make_node(f"n{i}") for i in range(10)]
        pipeline, repo, embedder = _make_pipeline(
            search_hybrid_return=nodes,
            traverse_bfs_return=nodes,
        )

        result = await pipeline.search("query", top_n=3)

        assert len(result) <= 3

    async def test_search_passes_metadata_filter(self) -> None:
        pipeline, repo, embedder = _make_pipeline()
        meta = {"source": "doc-01"}

        await pipeline.search("query", metadata_filter=meta)

        repo.search_hybrid.assert_awaited_once()
        call_kwargs = repo.search_hybrid.call_args
        # metadata_filter is the 4th positional arg or kwarg
        assert meta in call_kwargs.args or call_kwargs.kwargs.get("metadata_filter") == meta
