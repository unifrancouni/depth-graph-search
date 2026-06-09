"""DefaultEntityResolutionStrategy — implements EntityResolutionStrategy via SearchPipeline.

Design decisions:
- Injects SearchPipeline (the ABC), not DefaultSearchPipeline — stays decoupled from impl.
- Constructor has ZERO side effects: stores injected pipeline only.
- Threshold comparison: score >= threshold (inclusive). Matches port contract.
- Empty input returns [] immediately — pipeline.search is never called.
- len(result) == len(nodes) holds structurally: one ResolvedNode per input node, always.
- StorageError from pipeline propagates unmodified — no catch blocks.
"""

from __future__ import annotations

from depth_graph_search.core.domain.entities import Node, ResolvedNode
from depth_graph_search.core.ports.entity_resolution import EntityResolutionStrategy
from depth_graph_search.core.ports.search_pipeline import SearchPipeline


class DefaultEntityResolutionStrategy(EntityResolutionStrategy):
    """Concrete entity resolution: for each candidate node, search the graph and compare scores.

    Reuses the injected ``SearchPipeline`` to detect existing matches. Each candidate
    node's content is searched with ``top_n=1, depth_m=0`` (no BFS expansion). If the
    top result scores at or above the threshold, the node is considered a duplicate.

    Args:
        pipeline: Adapter implementing ``SearchPipeline``.

    Note:
        The constructor performs ZERO I/O. It stores the injected pipeline only.
    """

    def __init__(self, pipeline: SearchPipeline) -> None:
        self._pipeline = pipeline

    def resolve(
        self,
        nodes: list[Node],
        threshold: float = 0.85,
    ) -> list[ResolvedNode]:
        """Resolve a list of candidate nodes against the existing graph.

        For each candidate node, calls ``pipeline.search(node.content, top_n=1, depth_m=0)``.
        If the top result scores at or above ``threshold``, the node is marked as an existing
        match (``is_new=False``). Otherwise it is marked as new (``is_new=True``).

        Args:
            nodes: Candidate nodes to resolve. Order is preserved in the result.
            threshold: Cosine similarity threshold in [0, 1]. Defaults to 0.85.

        Returns:
            A list of ``ResolvedNode`` instances in the same order as ``nodes``.
            ``len(result) == len(nodes)`` is guaranteed.

        Raises:
            StorageError: If a graph store lookup fails during resolution (via pipeline).
        """
        resolved: list[ResolvedNode] = []
        for node in nodes:
            matches = self._pipeline.search(node.content, top_n=1, depth_m=0)
            if matches and matches[0].score >= threshold:
                resolved.append(
                    ResolvedNode(
                        node=node,
                        is_new=False,
                        matched_id=matches[0].node.id,
                    )
                )
            else:
                resolved.append(
                    ResolvedNode(
                        node=node,
                        is_new=True,
                        matched_id=None,
                    )
                )
        return resolved
