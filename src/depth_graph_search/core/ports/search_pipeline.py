"""SearchPipeline port — abstract contract for end-to-end search orchestrators."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from depth_graph_search.core.domain.entities import Metadata, ScoredNode


class SearchPipeline(ABC):
    """Abstract contract for end-to-end search pipeline implementations.

    A ``SearchPipeline`` orchestrates the full retrieval flow: embed the query,
    run hybrid search, traverse the graph via BFS, and rank results. Adapters
    MUST inherit from this class and implement ``search``. Instantiating
    ``SearchPipeline`` directly raises ``TypeError``.

    Results MUST be ordered: score descending, distance ascending.
    """

    @abstractmethod
    def search(
        self,
        query: str,
        top_n: int = 5,
        depth_m: int = 2,
        metadata_filter: Metadata | None = None,
        pipeline: str | None = None,
    ) -> list[ScoredNode]:
        """Execute a depth-first graph search for the given query.

        Args:
            query: The natural language query string.
            top_n: Maximum number of ``ScoredNode`` results to return. Defaults to 5.
                Implementations MUST respect this default.
            depth_m: Maximum BFS hop depth from entry nodes. Defaults to 2.
                Implementations MUST respect this default.
            metadata_filter: Key-value dict to pre-filter candidate nodes.
                ``None`` means no metadata filtering is applied.
            pipeline: Reserved for dispatch to named pipeline strategies.
                Concrete implementations MAY ignore this in v0.1.
                ``None`` means use the default strategy.

        Returns:
            A list of at most ``top_n`` ``ScoredNode`` instances, ordered
            by score descending, then distance ascending.

        Raises:
            StorageError: If the graph store operation fails.
            LLMError: If the embedding or LLM call fails.
        """
