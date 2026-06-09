"""DefaultSearchPipeline — implements SearchPipeline via hybrid search + BFS traversal.

Design decisions:
- Pure orchestrator: no I/O of its own — delegates to GraphRepository and EmbeddingProvider.
- Constructor has ZERO side effects: stores injected dependencies only.
- Deduplication uses dict[str, ScoredNode] keyed by node.id (first-occurrence wins, O(1) lookup).
- Score synthesis: rank-based formula 1.0 - rank / (top_n + 1) keeps scores in (0, 1].
- BFS distance is binary: entry nodes → 0, BFS-only nodes → 1 (traverse_bfs returns flat list).
- StorageError and LLMError propagate unmodified — no catch blocks.
- ``pipeline`` parameter accepted and silently ignored in v0.1 (no registry yet).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from depth_graph_search.core.domain.entities import ScoredNode
from depth_graph_search.core.ports.embedding_provider import EmbeddingProvider
from depth_graph_search.core.ports.graph_repository import GraphRepository
from depth_graph_search.core.ports.search_pipeline import SearchPipeline

if TYPE_CHECKING:
    from depth_graph_search.core.domain.entities import Metadata


class DefaultSearchPipeline(SearchPipeline):
    """Concrete search pipeline: embed → hybrid search → BFS expand → score → rank.

    Implements the five-step algorithm defined by the ``SearchPipeline`` port:

    1. Embed the query via ``EmbeddingProvider.embed``.
    2. Run hybrid search via ``GraphRepository.search_hybrid`` → entry nodes.
    3. Early-return ``[]`` if no entry nodes found.
    4. Expand graph via ``GraphRepository.traverse_bfs`` → all reachable nodes.
    5. Dedup, score, sort, and return top ``top_n`` results.

    Args:
        graph_repository: Adapter implementing ``GraphRepository``.
        embedding_provider: Adapter implementing ``EmbeddingProvider``.

    Note:
        The constructor performs ZERO I/O. It stores dependencies only.
    """

    def __init__(
        self,
        graph_repository: GraphRepository,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self._graph_repository = graph_repository
        self._embedding_provider = embedding_provider

    def search(
        self,
        query: str,
        top_n: int = 5,
        depth_m: int = 2,
        metadata_filter: Metadata | None = None,
        pipeline: str | None = None,  # accepted, silently ignored in v0.1
    ) -> list[ScoredNode]:
        """Execute a depth-first graph search for the given query.

        Five-step algorithm:
        1. Embed query.
        2. Hybrid search → entry_nodes.
        3. Early-return [] if entry_nodes is empty.
        4. BFS expand → bfs_nodes.
        5. Dedup by node.id (entry first), score, sort, return [:top_n].

        Args:
            query: The natural language query string.
            top_n: Maximum number of ``ScoredNode`` results to return. Defaults to 5.
            depth_m: Maximum BFS hop depth from entry nodes. Defaults to 2.
            metadata_filter: Key-value dict to pre-filter candidate nodes. ``None``
                means no filtering.
            pipeline: Reserved; silently ignored in v0.1.

        Returns:
            At most ``top_n`` ``ScoredNode`` instances ordered by score DESC,
            distance ASC.

        Raises:
            StorageError: If the graph store operation fails.
            LLMError: If the embedding call fails.
        """
        # Step 1: embed query
        embedding = self._embedding_provider.embed(query)

        # Step 2: hybrid search → entry nodes (ranked by relevance)
        entry_nodes = self._graph_repository.search_hybrid(
            embedding, query, top_n, metadata_filter
        )

        # Step 3: early return if no results
        if not entry_nodes:
            return []

        # Step 4: BFS expand from entry nodes
        bfs_nodes = self._graph_repository.traverse_bfs(entry_nodes, depth_m)

        # Step 5a: dedup — entry nodes first (preserve rank order), then BFS-only
        seen: dict[str, ScoredNode] = {}
        for rank, node in enumerate(entry_nodes):
            if node.id not in seen:
                score = 1.0 - rank / (top_n + 1)
                seen[node.id] = ScoredNode(node=node, score=score, distance=0)
        for node in bfs_nodes:
            if node.id not in seen:
                seen[node.id] = ScoredNode(node=node, score=0.0, distance=1)

        # Step 5b: sort by score DESC, distance ASC; return top_n
        results = sorted(
            seen.values(),
            key=lambda sn: (-sn.score, sn.distance),
        )
        return results[:top_n]
