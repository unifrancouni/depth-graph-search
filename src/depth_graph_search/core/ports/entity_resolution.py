"""EntityResolutionStrategy port — abstract contract for deduplication strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from depth_graph_search.core.domain.entities import Node, ResolvedNode


class EntityResolutionStrategy(ABC):
    """Abstract contract for entity resolution (deduplication) strategies.

    An ``EntityResolutionStrategy`` decides, for each candidate node, whether it
    matches an existing node in the graph above a similarity threshold. This
    prevents duplicate nodes during ingestion. Adapters MUST inherit from this
    class and implement ``resolve``. Instantiating ``EntityResolutionStrategy``
    directly raises ``TypeError``.

    ``len(result) == len(nodes)`` MUST always hold — every input node gets
    exactly one ``ResolvedNode`` in the output.
    """

    @abstractmethod
    def resolve(
        self,
        nodes: list[Node],
        threshold: float = 0.85,
    ) -> list[ResolvedNode]:
        """Resolve a list of candidate nodes against the existing graph.

        For each candidate node:
        - If a match is found above ``threshold`` cosine similarity:
          ``ResolvedNode(node=node, is_new=False, matched_id=<existing_id>)``
        - If no match found:
          ``ResolvedNode(node=node, is_new=True, matched_id=None)``

        Args:
            nodes: Candidate nodes to resolve. Order is preserved in the result.
            threshold: Cosine similarity threshold in [0, 1] above which two nodes
                are considered a match. Defaults to 0.85. Concrete implementations
                MUST use this value — do not hard-code a threshold.

        Returns:
            A list of ``ResolvedNode`` instances in the same order as ``nodes``.
            ``len(result) == len(nodes)`` is guaranteed.

        Raises:
            StorageError: If the graph store lookup fails during resolution.
        """
