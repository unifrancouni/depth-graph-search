"""AsyncDefaultSearchPipeline — implements AsyncSearchPipeline via hybrid search + BFS.

Design decisions:
- Mirrors DefaultSearchPipeline with ``await`` on all I/O calls.
- Pure orchestrator: no I/O of its own — delegates to AsyncGraphRepository
  and AsyncEmbeddingProvider.
- Constructor has ZERO side effects: stores injected dependencies only.
- Scoring/ranking stays synchronous (pure CPU) — no await.
- StorageError and LLMError propagate unmodified — no catch blocks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from depth_graph_search.core.ports.async_ports import (
    AsyncEmbeddingProvider,
    AsyncGraphRepository,
    AsyncSearchPipeline,
)

if TYPE_CHECKING:
    from depth_graph_search.core.domain.entities import Metadata, Node


class AsyncDefaultSearchPipeline(AsyncSearchPipeline):
    """Async concrete search pipeline: embed → hybrid search → BFS expand → score → rank.

    Implements the search algorithm defined by ``AsyncSearchPipeline``:

    1. Embed the query via ``AsyncEmbeddingProvider.embed``.
    2. Run hybrid search via ``AsyncGraphRepository.search_hybrid`` → entry nodes.
    3. Early-return ``[]`` if no entry nodes found.
    4. Expand graph via ``AsyncGraphRepository.traverse_bfs`` → all reachable nodes.
    5. Dedup and return combined list.

    Args:
        graph_repository: Adapter implementing ``AsyncGraphRepository``.
        embedding_provider: Adapter implementing ``AsyncEmbeddingProvider``.

    Note:
        The constructor performs ZERO I/O. It stores dependencies only.
    """

    def __init__(
        self,
        graph_repository: AsyncGraphRepository,
        embedding_provider: AsyncEmbeddingProvider,
    ) -> None:
        self._graph_repository = graph_repository
        self._embedding_provider = embedding_provider

    async def search(
        self,
        query: str,
        top_n: int = 5,
        depth_m: int = 2,
        metadata_filter: Metadata | None = None,
    ) -> list[Node]:
        """Execute a hybrid graph search for the given query.

        Algorithm:
        1. Embed query.
        2. Hybrid search → entry_nodes.
        3. Early-return [] if entry_nodes is empty.
        4. BFS expand → bfs_nodes.
        5. Dedup by node.id (entry first), score, sort, return [:top_n].

        Args:
            query: The natural language query string.
            top_n: Maximum number of results to return. Defaults to 5.
            depth_m: Maximum BFS hop depth from entry nodes. Defaults to 2.
            metadata_filter: Key-value dict to pre-filter candidate nodes.

        Returns:
            At most ``top_n`` ``Node`` instances.

        Raises:
            StorageError: If the graph store operation fails.
            LLMError: If the embedding call fails.
        """
        # Step 1: embed query
        embedding = await self._embedding_provider.embed(query)

        # Step 2: hybrid search → entry nodes
        entry_nodes = await self._graph_repository.search_hybrid(
            embedding, query, top_n, metadata_filter
        )

        # Step 3: early return if no results
        if not entry_nodes:
            return []

        # Step 4: BFS expand from entry nodes
        bfs_nodes = await self._graph_repository.traverse_bfs(entry_nodes, depth_m)

        # Step 5: dedup — entry nodes first, then BFS-only
        seen: dict[str, Node] = {}
        for node in entry_nodes:
            if node.id not in seen:
                seen[node.id] = node
        for node in bfs_nodes:
            if node.id not in seen:
                seen[node.id] = node

        return list(seen.values())[:top_n]
