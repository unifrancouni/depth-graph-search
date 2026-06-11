"""AsyncDefaultIngestionPipeline — implements AsyncIngestionPipeline.

Design decisions:
- Mirrors DefaultIngestionPipeline with ``await`` on all I/O calls.
- Pure orchestrator: no I/O of its own — delegates to 4 injected async ports.
- Constructor has ZERO side effects: stores injected dependencies only.
- Input validation runs before any port call.
- Empty LLM extraction ([], []) is a valid fast-path: returns immediately.
- Nodes are frozen dataclasses — embeddings attached via dataclasses.replace().
- All async port calls are awaited in the correct order per spec ASYNC-PIPE-01.
- Pure CPU post-processing (dataclasses.replace, dict ops) stays synchronous.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from depth_graph_search.core.ports.async_ports import (
    AsyncEmbeddingProvider,
    AsyncEntityResolutionStrategy,
    AsyncGraphRepository,
    AsyncIngestionPipeline,
    AsyncLLMProvider,
)

if TYPE_CHECKING:
    from depth_graph_search.core.domain.entities import Metadata


class AsyncDefaultIngestionPipeline(AsyncIngestionPipeline):
    """Async concrete ingestion pipeline: validate → extract → embed → resolve → persist.

    Implements the ingestion algorithm defined by ``AsyncIngestionPipeline``:

    1. Validate: reject empty/whitespace-only text.
    2. Extract: await ``AsyncLLMProvider.extract_graph()`` → ``(nodes, edges)``.
       Fast-path: empty extraction returns immediately.
    3. Embed: await ``AsyncEmbeddingProvider.embed_batch()`` → attach embeddings.
    4. Resolve: await ``AsyncEntityResolutionStrategy.resolve()`` → resolved list.
    5. Persist: await ``save_node`` for new nodes; await ``save_edge`` for all edges.

    Args:
        llm_provider: Adapter implementing ``AsyncLLMProvider``.
        embedding_provider: Adapter implementing ``AsyncEmbeddingProvider``.
        graph_repository: Adapter implementing ``AsyncGraphRepository``.
        entity_resolution: Adapter implementing ``AsyncEntityResolutionStrategy``.

    Note:
        The constructor performs ZERO I/O. It stores dependencies only.
    """

    def __init__(
        self,
        llm_provider: AsyncLLMProvider,
        embedding_provider: AsyncEmbeddingProvider,
        graph_repository: AsyncGraphRepository,
        entity_resolution: AsyncEntityResolutionStrategy,
    ) -> None:
        self._llm_provider = llm_provider
        self._embedding_provider = embedding_provider
        self._graph_repository = graph_repository
        self._entity_resolution = entity_resolution

    async def ingest(self, text: str, metadata: Metadata | None = None) -> None:
        """Ingest raw text into the knowledge graph.

        Five-step async algorithm:
        1. Validate input — reject blank text.
        2. Extract graph via async LLM.
        3. Embed node content in batch (async).
        4. Resolve entities sequentially (async).
        5. Persist new nodes + all edges (async, each awaited in loop).

        Args:
            text: The raw text to ingest. MUST be non-empty and non-whitespace-only.
            metadata: Free-form key-value context. ``None`` defaults to ``{}``.

        Raises:
            ValidationError: If ``text`` is empty or whitespace-only.
        """
        from depth_graph_search.core.domain.exceptions import ValidationError

        # Normalise metadata
        if metadata is None:
            metadata = {}

        # Step 1: Input validation
        if not text.strip():
            raise ValidationError("text must not be empty or whitespace-only")

        # Step 2: Async LLM extraction
        nodes, edges = await self._llm_provider.extract_graph(text, metadata)

        # Fast-path: empty extraction
        if not nodes:
            return

        # Step 2b: Guarantee metadata on every node (defensive)
        nodes = [
            dataclasses.replace(node, metadata={**metadata, **node.metadata})
            for node in nodes
        ]

        # Step 3: Async embed node content in batch
        embeddings = await self._embedding_provider.embed_batch(
            [node.content for node in nodes]
        )

        # Attach embeddings to nodes via dataclasses.replace (frozen dataclass)
        embedded_nodes = [
            dataclasses.replace(node, embedding=emb)
            for node, emb in zip(nodes, embeddings)
        ]

        # Step 4: Async entity resolution — resolve entity content strings
        entity_strings = [node.content for node in embedded_nodes]
        await self._entity_resolution.resolve(entity_strings)

        # Step 5: Persist new nodes and all edges (each awaited individually)
        for node in embedded_nodes:
            await self._graph_repository.save_node(node)

        for edge in edges:
            await self._graph_repository.save_edge(edge)
