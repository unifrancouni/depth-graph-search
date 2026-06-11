"""AsyncDefaultEntityResolutionStrategy — implements AsyncEntityResolutionStrategy.

Design decisions:
- Injects AsyncSearchPipeline (the ABC) — stays decoupled from implementation.
- Constructor has ZERO side effects: stores injected pipeline only.
- Sequential awaits in loop — NO asyncio.gather (per spec ASYNC-ERES-02).
- Empty input returns [] immediately — pipeline.search is never called.
- StorageError from pipeline propagates unmodified — no catch blocks.
"""

from __future__ import annotations

from depth_graph_search.core.ports.async_ports import (
    AsyncEntityResolutionStrategy,
    AsyncSearchPipeline,
)

from depth_graph_search.core.domain.entities import Node


class AsyncDefaultEntityResolutionStrategy(AsyncEntityResolutionStrategy):
    """Async entity resolution: for each entity string, search the graph sequentially.

    Reuses the injected ``AsyncSearchPipeline`` to find matching nodes. Each entity
    string is searched with ``pipeline.search(entity, top_n=1, depth_m=0)`` awaited
    sequentially — no parallel gather.

    Args:
        pipeline: Adapter implementing ``AsyncSearchPipeline``.

    Note:
        The constructor performs ZERO I/O. It stores the injected pipeline only.
    """

    def __init__(self, pipeline: AsyncSearchPipeline) -> None:
        self._pipeline = pipeline

    async def resolve(self, entities: list[str]) -> list[Node]:
        """Resolve a list of entity strings to graph nodes.

        For each entity string, calls ``pipeline.search(entity, top_n=1, depth_m=0)``
        sequentially. Collects the top result (if any) from each search into a flat list.

        Args:
            entities: Entity name strings to resolve. Empty input returns ``[]``
                immediately without calling ``pipeline.search``.

        Returns:
            A flat list of resolved ``Node`` instances (one per entity that returned
            a result). Empty list if no matches found.
        """
        if not entities:
            return []

        resolved: list[Node] = []
        for entity in entities:
            # Sequential await — NO asyncio.gather per spec ASYNC-ERES-02
            results = await self._pipeline.search(entity, top_n=1, depth_m=0)
            if results:
                resolved.append(results[0])

        return resolved
