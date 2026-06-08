"""GraphRepository port — abstract contract for graph persistence adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from depth_graph_search.core.domain.entities import Edge, Embedding, Metadata, Node


class GraphRepository(ABC):
    """Abstract contract for all graph persistence adapters.

    Adapters (e.g. PostgreSQL + pgvector) MUST inherit from this class and
    implement every abstract method. Instantiating ``GraphRepository`` directly
    raises ``TypeError``.

    All methods that interact with storage raise ``StorageError`` on failure.
    Callers MUST handle ``StorageError`` at the use-case layer.
    """

    @abstractmethod
    def save_node(self, node: Node) -> None:
        """Persist a node to the graph store.

        Args:
            node: The domain ``Node`` to persist. The node's ``id`` is already
                set (domain-generated uuid4). If a node with the same ``id``
                already exists, behaviour is adapter-defined (upsert or error —
                documented by each adapter implementation).

        Raises:
            StorageError: If the underlying storage operation fails.
        """

    @abstractmethod
    def save_edge(self, edge: Edge) -> None:
        """Persist a directed edge to the graph store.

        Args:
            edge: The domain ``Edge`` to persist. Both ``edge.source_id`` and
                ``edge.target_id`` SHOULD reference existing nodes. The adapter
                may enforce referential integrity at the DB level.

        Raises:
            StorageError: If the underlying storage operation fails.
        """

    @abstractmethod
    def get_node(self, node_id: str) -> Node | None:
        """Retrieve a single node by its ID.

        Args:
            node_id: The uuid4 string ID of the node to retrieve.

        Returns:
            The matching ``Node``, or ``None`` if no node with that ID exists.
            Callers MUST check for ``None`` — this method does NOT raise on
            a missing ID.

        Raises:
            StorageError: If the underlying storage operation fails.
        """

    @abstractmethod
    def search_hybrid(
        self,
        query_embedding: Embedding,
        query_text: str,
        top_n: int = 5,
        metadata_filter: Metadata | None = None,
    ) -> list[Node]:
        """Search for nodes using hybrid vector + keyword similarity.

        Args:
            query_embedding: Dense vector representation of the query text.
            query_text: Raw query string (used for keyword/BM25 component).
            top_n: Maximum number of nodes to return. Defaults to 5.
            metadata_filter: Key-value dict to pre-filter candidate nodes.
                ``None`` means no metadata filtering is applied.

        Returns:
            Up to ``top_n`` nodes ranked by hybrid similarity, highest first.

        Raises:
            StorageError: If the underlying storage operation fails.
        """

    @abstractmethod
    def traverse_bfs(
        self,
        entry_nodes: list[Node],
        depth_m: int = 2,
    ) -> list[Node]:
        """Traverse the graph via BFS starting from a set of entry nodes.

        Args:
            entry_nodes: Seed nodes from which BFS traversal begins.
            depth_m: Maximum number of hops to traverse. Defaults to 2.
                ``depth_m=0`` returns only the entry nodes themselves.

        Returns:
            All nodes reachable within ``depth_m`` hops from any node in
            ``entry_nodes``. Deduplication across BFS levels is the
            adapter's responsibility.

        Raises:
            StorageError: If the underlying storage operation fails.
        """
