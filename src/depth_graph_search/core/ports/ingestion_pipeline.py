"""IngestionPipeline port — abstract contract for end-to-end ingestion orchestrators."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from depth_graph_search.core.domain.entities import IngestionResult, Metadata


class IngestionPipeline(ABC):
    """Abstract contract for end-to-end ingestion pipeline implementations.

    An ``IngestionPipeline`` orchestrates the full ingestion flow: validate input,
    extract a knowledge graph via LLM, embed node content, resolve duplicate entities,
    and persist the graph. Adapters MUST inherit from this class and implement
    ``ingest``. Instantiating ``IngestionPipeline`` directly raises ``TypeError``.

    All implementations MUST raise ``ValidationError`` for invalid input before
    calling any port, and MUST propagate port failures as ``IngestionError``.
    """

    @abstractmethod
    def ingest(
        self,
        text: str,
        metadata: Metadata | None = None,
    ) -> IngestionResult:
        """Ingest raw text into the knowledge graph.

        Validates input, extracts entities and relationships via LLM, generates
        embeddings, resolves duplicate entities, and persists the result.

        Args:
            text: The raw text to ingest. MUST be non-empty and non-whitespace-only.
            metadata: Free-form key-value context forwarded to the LLM and attached
                to every persisted node. ``None`` defaults to an empty dict ``{}``.

        Returns:
            An ``IngestionResult`` with ``node_count`` (new nodes saved) and
            ``edge_count`` (edges saved).

        Raises:
            ValidationError: If ``text`` is empty or whitespace-only. No port is
                called when this error is raised.
            IngestionError: If any pipeline stage fails (LLM extraction, embedding,
                entity resolution, or graph persistence). The underlying port error
                is chained as ``__cause__``.
        """
