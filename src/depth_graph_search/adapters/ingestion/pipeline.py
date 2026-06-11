"""DefaultIngestionPipeline — implements IngestionPipeline via 4-stage orchestration.

Design decisions:
- Pure orchestrator: no I/O of its own — delegates to 4 injected ports.
- Constructor has ZERO side effects: stores injected dependencies only.
- Input validation runs before any port call — ValidationError if blank.
- Empty LLM extraction ([], []) is a valid fast-path: returns IngestionResult(0, 0).
- Nodes are frozen dataclasses — embeddings attached via dataclasses.replace().
- Edge rewiring uses an id_map dict {original_id -> matched_id} for O(E) traversal.
- Only is_new=True nodes are persisted — matched nodes are reused, not duplicated.
- All port errors are wrapped as IngestionError with the original error as __cause__.
- Metadata defaults to {} when None — forwarded unchanged to LLM and nodes.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from depth_graph_search.core.domain.exceptions import IngestionError, ValidationError
from depth_graph_search.core.ports.embedding_provider import EmbeddingProvider
from depth_graph_search.core.ports.entity_resolution import EntityResolutionStrategy
from depth_graph_search.core.ports.graph_repository import GraphRepository
from depth_graph_search.core.ports.ingestion_pipeline import IngestionPipeline
from depth_graph_search.core.ports.llm_provider import LLMProvider

if TYPE_CHECKING:
    from depth_graph_search.core.domain.entities import IngestionResult, Metadata


class DefaultIngestionPipeline(IngestionPipeline):
    """Concrete ingestion pipeline: validate → extract → embed → resolve → persist.

    Implements the 4-stage algorithm defined by the ``IngestionPipeline`` port:

    1. Validate: reject empty/whitespace-only text with ``ValidationError``.
    2. Extract: call ``LLMProvider.extract_graph()`` → ``(nodes, edges)``.
       Fast-path: empty extraction returns ``IngestionResult(0, 0)`` immediately.
    3. Embed: call ``EmbeddingProvider.embed_batch()`` → attach embeddings to nodes
       via ``dataclasses.replace()``.
    4. Resolve: call ``EntityResolutionStrategy.resolve()`` → build ``id_map`` for
       matched entities, rewire edge source/target IDs accordingly.
    5. Persist: ``save_node`` for ``is_new=True`` nodes only; ``save_edge`` for all
       rewired edges. Return ``IngestionResult(node_count, edge_count)``.

    All port errors (``LLMError``, ``StorageError``) are caught and re-raised as
    ``IngestionError`` with the original exception chained as ``__cause__``.

    Args:
        llm_provider: Adapter implementing ``LLMProvider``.
        embedding_provider: Adapter implementing ``EmbeddingProvider``.
        graph_repository: Adapter implementing ``GraphRepository``.
        entity_resolution: Adapter implementing ``EntityResolutionStrategy``.

    Note:
        The constructor performs ZERO I/O. It stores dependencies only.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        embedding_provider: EmbeddingProvider,
        graph_repository: GraphRepository,
        entity_resolution: EntityResolutionStrategy,
    ) -> None:
        self._llm_provider = llm_provider
        self._embedding_provider = embedding_provider
        self._graph_repository = graph_repository
        self._entity_resolution = entity_resolution

    def ingest(
        self,
        text: str,
        metadata: Metadata | None = None,
    ) -> IngestionResult:
        """Ingest raw text into the knowledge graph.

        Six-step algorithm:
        1. Validate input — reject blank text.
        2. Extract graph via LLM.
        3. Embed node content in batch.
        4. Resolve entities — detect duplicates.
        5. Rewire edges for matched entities.
        6. Persist new nodes + all edges; return IngestionResult.

        Args:
            text: The raw text to ingest. MUST be non-empty and non-whitespace-only.
            metadata: Free-form key-value context. ``None`` defaults to ``{}``.

        Returns:
            ``IngestionResult(node_count, edge_count)`` where ``node_count`` is the
            number of new nodes saved and ``edge_count`` is the number of edges saved.

        Raises:
            ValidationError: If ``text`` is empty or whitespace-only.
            IngestionError: If any pipeline stage fails. ``__cause__`` is set to the
                underlying port error.
        """
        from depth_graph_search.core.domain.entities import IngestionResult

        # Normalise metadata
        if metadata is None:
            metadata = {}

        # Step 1: Input validation
        if not text.strip():
            raise ValidationError("text must not be empty or whitespace-only")

        # Step 2: LLM extraction
        try:
            nodes, edges = self._llm_provider.extract_graph(text, metadata)
        except Exception as exc:
            raise IngestionError("LLM graph extraction failed", cause=exc) from exc

        # Fast-path: empty extraction
        if not nodes and not edges:
            return IngestionResult(node_count=0, edge_count=0)

        # Step 2b: Guarantee metadata on every node (defensive — don't rely
        # on the LLM adapter propagating it).  Node metadata wins on conflicts.
        nodes = [
            dataclasses.replace(node, metadata={**metadata, **node.metadata})
            for node in nodes
        ]

        # Step 3: Embed node content in batch
        try:
            embeddings = self._embedding_provider.embed_batch(
                [node.content for node in nodes]
            )
        except Exception as exc:
            raise IngestionError("Embedding generation failed", cause=exc) from exc

        # Attach embeddings to nodes via dataclasses.replace (frozen dataclass)
        embedded_nodes = [
            dataclasses.replace(node, embedding=emb)
            for node, emb in zip(nodes, embeddings)
        ]

        # Step 4: Entity resolution — detect duplicates
        try:
            resolved = self._entity_resolution.resolve(embedded_nodes)
        except Exception as exc:
            raise IngestionError("Entity resolution failed", cause=exc) from exc

        # Build id_map: {original_node_id -> matched_id} for is_new=False nodes
        id_map: dict[str, str] = {
            r.node.id: r.matched_id
            for r in resolved
            if not r.is_new and r.matched_id is not None
        }

        # Step 5: Rewire edges via id_map using dataclasses.replace
        rewired_edges = []
        for edge in edges:
            new_source = id_map.get(edge.source_id, edge.source_id)
            new_target = id_map.get(edge.target_id, edge.target_id)
            if new_source != edge.source_id or new_target != edge.target_id:
                rewired_edges.append(
                    dataclasses.replace(
                        edge, source_id=new_source, target_id=new_target
                    )
                )
            else:
                rewired_edges.append(edge)

        # Step 6: Persist new nodes and all rewired edges
        node_count = 0
        try:
            for resolved_node in resolved:
                if resolved_node.is_new:
                    self._graph_repository.save_node(resolved_node.node)
                    node_count += 1

            for edge in rewired_edges:
                self._graph_repository.save_edge(edge)
        except Exception as exc:
            raise IngestionError("Graph persistence failed", cause=exc) from exc

        return IngestionResult(node_count=node_count, edge_count=len(rewired_edges))
