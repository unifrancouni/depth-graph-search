"""Unit tests for AsyncDefaultIngestionPipeline.

Covers: ingest awaits extract_graph, embed_batch, save_node, save_edge in order;
no save_node calls if nodes list empty; ValidationError on blank text.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call

import pytest

from depth_graph_search.adapters.ingestion.async_pipeline import AsyncDefaultIngestionPipeline
from depth_graph_search.core.domain.entities import Edge, Embedding, IngestionResult, Node
from depth_graph_search.core.domain.exceptions import ValidationError
from depth_graph_search.core.ports.async_ports import AsyncIngestionPipeline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_embedding(dims: int = 3) -> Embedding:
    return Embedding(vector=[0.1] * dims, model="test", dimensions=dims)


def _make_node(content: str = "test node") -> Node:
    return Node(content=content)


def _make_edge(src_id: str, tgt_id: str) -> Edge:
    return Edge(source_id=src_id, target_id=tgt_id, relationship="RELATED")


def _make_pipeline(
    extract_return: tuple[list[Node], list[Edge]] | None = None,
    embed_batch_return: list[Embedding] | None = None,
) -> tuple[AsyncDefaultIngestionPipeline, AsyncMock, AsyncMock, AsyncMock, AsyncMock]:
    llm = AsyncMock()
    embedder = AsyncMock()
    repo = AsyncMock()
    resolution = AsyncMock()
    resolution.resolve.return_value = []

    if extract_return is not None:
        llm.extract_graph.return_value = extract_return
    else:
        llm.extract_graph.return_value = ([], [])

    if embed_batch_return is not None:
        embedder.embed_batch.return_value = embed_batch_return

    pipeline = AsyncDefaultIngestionPipeline(
        llm_provider=llm,
        embedding_provider=embedder,
        graph_repository=repo,
        entity_resolution=resolution,
    )
    return pipeline, llm, embedder, repo, resolution


# ---------------------------------------------------------------------------
# TestIngestionPipeline
# ---------------------------------------------------------------------------


class TestIngestionPipeline:
    def test_isinstance_async_ingestion_pipeline(self) -> None:
        pipeline, *_ = _make_pipeline()
        assert isinstance(pipeline, AsyncIngestionPipeline)

    async def test_ingest_raises_validation_error_on_empty_text(self) -> None:
        pipeline, *_ = _make_pipeline()

        with pytest.raises(ValidationError):
            await pipeline.ingest("")

    async def test_ingest_raises_validation_error_on_whitespace_only(self) -> None:
        pipeline, *_ = _make_pipeline()

        with pytest.raises(ValidationError):
            await pipeline.ingest("   ")

    async def test_ingest_no_save_node_if_llm_returns_empty_nodes(self) -> None:
        pipeline, llm, embedder, repo, _ = _make_pipeline(extract_return=([], []))

        await pipeline.ingest("some text")

        repo.save_node.assert_not_awaited()
        repo.save_edge.assert_not_awaited()
        embedder.embed_batch.assert_not_awaited()

    async def test_ingest_awaits_extract_graph(self) -> None:
        node = _make_node("test node")
        pipeline, llm, embedder, repo, _ = _make_pipeline(
            extract_return=([node], []),
            embed_batch_return=[_make_embedding()],
        )

        await pipeline.ingest("test text", {"source": "doc"})

        llm.extract_graph.assert_awaited_once()

    async def test_ingest_awaits_embed_batch(self) -> None:
        node = _make_node("content")
        pipeline, llm, embedder, repo, _ = _make_pipeline(
            extract_return=([node], []),
            embed_batch_return=[_make_embedding()],
        )

        await pipeline.ingest("test text")

        embedder.embed_batch.assert_awaited_once_with([node.content])

    async def test_ingest_awaits_save_node_for_each_node(self) -> None:
        nodes = [_make_node(f"node {i}") for i in range(3)]
        embeddings = [_make_embedding() for _ in nodes]
        pipeline, llm, embedder, repo, _ = _make_pipeline(
            extract_return=(nodes, []),
            embed_batch_return=embeddings,
        )

        await pipeline.ingest("text with three entities")

        assert repo.save_node.await_count == 3

    async def test_ingest_awaits_save_edge_for_each_edge(self) -> None:
        node1 = _make_node("node 1")
        node2 = _make_node("node 2")
        edge = _make_edge(node1.id, node2.id)
        pipeline, llm, embedder, repo, _ = _make_pipeline(
            extract_return=([node1, node2], [edge]),
            embed_batch_return=[_make_embedding(), _make_embedding()],
        )

        await pipeline.ingest("text with edge")

        repo.save_edge.assert_awaited_once()

    async def test_ingest_calls_entity_resolution(self) -> None:
        nodes = [_make_node("entity1"), _make_node("entity2")]
        pipeline, llm, embedder, repo, resolution = _make_pipeline(
            extract_return=(nodes, []),
            embed_batch_return=[_make_embedding(), _make_embedding()],
        )

        await pipeline.ingest("text")

        resolution.resolve.assert_awaited_once()

    async def test_ingest_extract_called_before_embed(self) -> None:
        """Verify extract_graph is awaited before embed_batch."""
        call_order: list[str] = []

        llm = AsyncMock()
        embedder = AsyncMock()
        repo = AsyncMock()
        resolution = AsyncMock()
        resolution.resolve.return_value = []

        node = _make_node("content")

        async def extract_side_effect(*args, **kwargs):
            call_order.append("extract")
            return ([node], [])

        async def embed_side_effect(*args, **kwargs):
            call_order.append("embed")
            return [_make_embedding()]

        llm.extract_graph.side_effect = extract_side_effect
        embedder.embed_batch.side_effect = embed_side_effect

        pipeline = AsyncDefaultIngestionPipeline(
            llm_provider=llm,
            embedding_provider=embedder,
            graph_repository=repo,
            entity_resolution=resolution,
        )

        await pipeline.ingest("test text")

        assert call_order.index("extract") < call_order.index("embed")

    async def test_ingest_metadata_defaults_to_empty_dict(self) -> None:
        """Passing None metadata should not raise and should default to {}."""
        node = _make_node("content")
        pipeline, llm, embedder, repo, _ = _make_pipeline(
            extract_return=([node], []),
            embed_batch_return=[_make_embedding()],
        )

        await pipeline.ingest("test text", metadata=None)

        # extract_graph should be called with an empty dict as metadata
        call_args = llm.extract_graph.call_args
        assert call_args.args[1] == {} or call_args.kwargs.get("metadata") == {}

    async def test_ingest_returns_ingestion_result(self) -> None:
        """ingest() must return IngestionResult with correct node_count and edge_count."""
        node1 = _make_node("node 1")
        node2 = _make_node("node 2")
        edge = _make_edge(node1.id, node2.id)
        pipeline, llm, embedder, repo, _ = _make_pipeline(
            extract_return=([node1, node2], [edge]),
            embed_batch_return=[_make_embedding(), _make_embedding()],
        )

        result = await pipeline.ingest("text with nodes and edge")

        assert isinstance(result, IngestionResult)
        assert result.node_count == 2
        assert result.edge_count == 1

    async def test_ingest_returns_ingestion_result_zero_counts_on_empty_extraction(self) -> None:
        """When LLM returns empty nodes, IngestionResult(0, 0) is returned."""
        pipeline, *_ = _make_pipeline(extract_return=([], []))

        result = await pipeline.ingest("some text")

        assert isinstance(result, IngestionResult)
        assert result.node_count == 0
        assert result.edge_count == 0
