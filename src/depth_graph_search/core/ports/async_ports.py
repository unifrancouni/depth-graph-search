"""Async port ABCs — parallel async contracts for all adapters.

Six async abstract base classes mirroring the sync port ABCs.
All methods are ``async def`` + ``@abstractmethod``.

These ABCs are INDEPENDENT of the sync ABCs — no inheritance between them.
The only change from the sync counterparts is ``async def`` instead of ``def``.

    from depth_graph_search.core.ports.async_ports import (
        AsyncGraphRepository,
        AsyncEmbeddingProvider,
        AsyncLLMProvider,
        AsyncEntityResolutionStrategy,
        AsyncIngestionPipeline,
        AsyncSearchPipeline,
    )
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from depth_graph_search.core.domain.entities import (
        Edge,
        Embedding,
        Metadata,
        Node,
    )


# ---------------------------------------------------------------------------
# AsyncGraphRepository
# ---------------------------------------------------------------------------


class AsyncGraphRepository(ABC):
    """Async abstract contract for all graph persistence adapters.

    Mirrors ``GraphRepository`` with ``async def`` methods.
    Does NOT inherit from ``GraphRepository`` — parallel independent interface.

    All methods that interact with storage raise ``StorageError`` on failure.
    """

    @abstractmethod
    async def save_node(self, node: Node) -> None:
        """Persist a node to the graph store.

        Args:
            node: The domain ``Node`` to persist.

        Raises:
            StorageError: If the underlying storage operation fails.
        """

    @abstractmethod
    async def save_edge(self, edge: Edge) -> None:
        """Persist a directed edge to the graph store.

        Args:
            edge: The domain ``Edge`` to persist.

        Raises:
            StorageError: If the underlying storage operation fails.
        """

    @abstractmethod
    async def get_node(self, node_id: str) -> Node | None:
        """Retrieve a single node by its ID.

        Args:
            node_id: The uuid4 string ID of the node to retrieve.

        Returns:
            The matching ``Node``, or ``None`` if no node with that ID exists.

        Raises:
            StorageError: If the underlying storage operation fails.
        """

    @abstractmethod
    async def search_hybrid(
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

        Returns:
            Up to ``top_n`` nodes ranked by hybrid similarity, highest first.

        Raises:
            StorageError: If the underlying storage operation fails.
        """

    @abstractmethod
    async def traverse_bfs(
        self,
        entry_nodes: list[Node],
        depth_m: int = 2,
    ) -> list[Node]:
        """Traverse the graph via BFS starting from a set of entry nodes.

        Args:
            entry_nodes: Seed nodes from which BFS traversal begins.
            depth_m: Maximum number of hops to traverse. Defaults to 2.

        Returns:
            All nodes reachable within ``depth_m`` hops from any node in
            ``entry_nodes``.

        Raises:
            StorageError: If the underlying storage operation fails.
        """

    @abstractmethod
    async def initialize(self) -> None:
        """Set up the database schema and extensions.

        Raises:
            StorageError: If any DDL step fails.
        """

    @abstractmethod
    async def close(self) -> None:
        """Close the underlying async connection if still open."""


# ---------------------------------------------------------------------------
# AsyncEmbeddingProvider
# ---------------------------------------------------------------------------


class AsyncEmbeddingProvider(ABC):
    """Async abstract contract for all embedding model adapters.

    Mirrors ``EmbeddingProvider`` with ``async def`` methods.
    Does NOT inherit from ``EmbeddingProvider`` — parallel independent interface.
    """

    @abstractmethod
    async def embed(self, text: str) -> Embedding:
        """Generate a single embedding for the given text.

        Args:
            text: The input text to embed. MUST be non-empty.

        Returns:
            An ``Embedding`` instance with ``vector``, ``model``, and ``dimensions`` set.

        Raises:
            LLMError: If the embedding provider call fails.
        """

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[Embedding]:
        """Generate embeddings for a batch of texts in a single provider call.

        Args:
            texts: List of input texts to embed. Order is preserved in the result.

        Returns:
            A list of ``Embedding`` instances in the same order as ``texts``.

        Raises:
            LLMError: If the embedding provider call fails.
        """


# ---------------------------------------------------------------------------
# AsyncLLMProvider
# ---------------------------------------------------------------------------


class AsyncLLMProvider(ABC):
    """Async abstract contract for all language model adapters.

    Mirrors ``LLMProvider`` with ``async def`` methods.
    Does NOT inherit from ``LLMProvider`` — parallel independent interface.
    """

    @abstractmethod
    async def extract_graph(
        self,
        text: str,
        metadata: Metadata,
    ) -> tuple[list[Node], list[Edge]]:
        """Call the LLM to extract a knowledge graph from unstructured text.

        Args:
            text: The raw text to extract entities and relationships from.
            metadata: Key-value context to pass alongside the text.

        Returns:
            A tuple ``(nodes, edges)``. Empty ``([], [])`` when no entities found.

        Raises:
            LLMError: If the LLM call fails or returns a malformed response.
        """

    @abstractmethod
    async def complete(self, prompt: str) -> str:
        """General-purpose text completion.

        Args:
            prompt: The full prompt to send to the language model.

        Returns:
            Raw string output from the model.

        Raises:
            LLMError: If the LLM call fails.
        """


# ---------------------------------------------------------------------------
# AsyncEntityResolutionStrategy
# ---------------------------------------------------------------------------


class AsyncEntityResolutionStrategy(ABC):
    """Async abstract contract for entity resolution (deduplication) strategies.

    Mirrors ``EntityResolutionStrategy`` with ``async def`` methods.
    Does NOT inherit from ``EntityResolutionStrategy`` — parallel independent interface.
    """

    @abstractmethod
    async def resolve(self, entities: list[str]) -> list[Node]:
        """Resolve a list of entity strings to graph nodes.

        Args:
            entities: Entity name strings to resolve. Order is preserved.

        Returns:
            A flat list of resolved ``Node`` instances.
        """


# ---------------------------------------------------------------------------
# AsyncIngestionPipeline
# ---------------------------------------------------------------------------


class AsyncIngestionPipeline(ABC):
    """Async abstract contract for end-to-end ingestion pipeline implementations.

    Mirrors ``IngestionPipeline`` with ``async def`` methods.
    Does NOT inherit from ``IngestionPipeline`` — parallel independent interface.
    """

    @abstractmethod
    async def ingest(self, text: str, metadata: Metadata | None = None) -> None:
        """Ingest raw text into the knowledge graph.

        Args:
            text: The raw text to ingest.
            metadata: Free-form key-value context. ``None`` defaults to ``{}``.

        Raises:
            ValidationError: If ``text`` is empty or whitespace-only.
            IngestionError: If any pipeline stage fails.
        """


# ---------------------------------------------------------------------------
# AsyncSearchPipeline
# ---------------------------------------------------------------------------


class AsyncSearchPipeline(ABC):
    """Async abstract contract for end-to-end search pipeline implementations.

    Mirrors ``SearchPipeline`` with ``async def`` methods.
    Does NOT inherit from ``SearchPipeline`` — parallel independent interface.
    """

    @abstractmethod
    async def search(
        self,
        query: str,
        top_n: int = 5,
        depth_m: int = 2,
        metadata_filter: Metadata | None = None,
    ) -> list[Node]:
        """Execute a depth-first graph search for the given query.

        Args:
            query: The natural language query string.
            top_n: Maximum number of results to return. Defaults to 5.
            depth_m: Maximum BFS hop depth from entry nodes. Defaults to 2.
            metadata_filter: Key-value dict to pre-filter candidate nodes.

        Returns:
            A list of at most ``top_n`` ``Node`` instances.

        Raises:
            StorageError: If the graph store operation fails.
            LLMError: If the embedding or LLM call fails.
        """
