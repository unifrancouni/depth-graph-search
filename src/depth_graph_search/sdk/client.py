"""GraphSearch — high-level SDK facade wiring all six ports into a 2-method public API.

Design decisions:
- Pure wiring layer: zero business logic, all delegation to internal pipelines.
- Constructor accepts the four port ABCs — maximally testable with existing mocks.
- Auto-wires DefaultSearchPipeline, DefaultEntityResolutionStrategy (if None),
  and DefaultIngestionPipeline internally — caller needs only 3 required ports.
- Classmethods (from_openai, from_openrouter) own the connection lifecycle:
  they create psycopg.connect(), call repo.initialize(), and store _connection
  so close() can release it.
- In port-injection mode, _connection is None and close() is a no-op.
- Context manager pattern (__enter__ / __exit__) is the recommended usage.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from depth_graph_search.adapters.ingestion.pipeline import DefaultIngestionPipeline
from depth_graph_search.adapters.search.entity_resolution import (
    DefaultEntityResolutionStrategy,
)
from depth_graph_search.adapters.search.pipeline import DefaultSearchPipeline
from depth_graph_search.core.ports.embedding_provider import EmbeddingProvider
from depth_graph_search.core.ports.entity_resolution import EntityResolutionStrategy
from depth_graph_search.core.ports.graph_repository import GraphRepository
from depth_graph_search.core.ports.llm_provider import LLMProvider

if TYPE_CHECKING:
    from depth_graph_search.core.domain.entities import IngestionResult, Metadata, ScoredNode


class GraphSearch:
    """High-level SDK entry point for depth-graph-search.

    Wires all six ports internally and exposes a minimal, ergonomic API:
    - ``ingest(text, metadata)`` — extract entities and persist to the graph.
    - ``search(query, top_n, depth_m, metadata_filter)`` — hybrid graph search.

    The preferred usage pattern via classmethods is the context manager::

        with GraphSearch.from_openai(dsn, api_key) as gs:
            gs.ingest("Alice works at Acme Corp.")
            results = gs.search("who works at Acme?")

    Port-injection mode (for testing or custom wiring)::

        gs = GraphSearch(
            graph_repository=repo,
            embedding_provider=embedder,
            llm_provider=llm,
        )

    Args:
        graph_repository: Adapter implementing ``GraphRepository``.
        embedding_provider: Adapter implementing ``EmbeddingProvider``.
        llm_provider: Adapter implementing ``LLMProvider``.
        entity_resolution: Optional adapter implementing ``EntityResolutionStrategy``.
            When ``None``, a ``DefaultEntityResolutionStrategy`` is auto-created
            using a fresh ``DefaultSearchPipeline`` wired from the injected ports.

    Note:
        The constructor performs ZERO I/O. In port-injection mode, ``close()``
        is a no-op — the caller owns the connection lifecycle.
    """

    def __init__(
        self,
        graph_repository: GraphRepository,
        embedding_provider: EmbeddingProvider,
        llm_provider: LLMProvider,
        entity_resolution: EntityResolutionStrategy | None = None,
    ) -> None:
        self._connection: object | None = None  # set only by classmethods

        # Build search pipeline — needed for entity resolution auto-wiring
        self._search_pipeline = DefaultSearchPipeline(
            graph_repository=graph_repository,
            embedding_provider=embedding_provider,
        )

        # Auto-build entity resolution if not injected
        if entity_resolution is None:
            entity_resolution = DefaultEntityResolutionStrategy(
                pipeline=self._search_pipeline,
            )

        # Build ingestion pipeline from all four dependencies
        self._ingestion_pipeline = DefaultIngestionPipeline(
            llm_provider=llm_provider,
            embedding_provider=embedding_provider,
            graph_repository=graph_repository,
            entity_resolution=entity_resolution,
        )

    # ------------------------------------------------------------------
    # Convenience classmethods
    # ------------------------------------------------------------------

    @classmethod
    def from_openai(
        cls,
        dsn: str,
        api_key: str,
        *,
        model: str = "gpt-4o",
        embedding_model: str = "text-embedding-3-large",
        graph_name: str = "knowledge_graph",
        embedding_dimensions: int = 3072,
    ) -> "GraphSearch":
        """Create a GraphSearch wired to a PostgreSQL backend and OpenAI provider.

        Creates a ``psycopg.Connection``, instantiates ``PostgresGraphRepository``,
        calls ``repo.initialize()``, and wires a single ``OpenAIProvider`` as both
        ``embedding_provider`` and ``llm_provider``.

        The facade owns the connection lifecycle — call ``close()`` or use the
        context manager to release it.

        Args:
            dsn: PostgreSQL connection string (e.g. ``"postgresql://user:pw@host/db"``).
            api_key: OpenAI API key.
            model: Chat completion model. Defaults to ``"gpt-4o"``.
            embedding_model: Embedding model. Defaults to ``"text-embedding-3-large"``.
            graph_name: AGE graph name. Defaults to ``"knowledge_graph"``.
            embedding_dimensions: Vector dimension. Defaults to 3072.

        Returns:
            A ready-to-use ``GraphSearch`` instance with connection lifecycle ownership.
        """
        import psycopg

        from depth_graph_search.adapters.openai.provider import OpenAIProvider
        from depth_graph_search.adapters.postgres.repository import (
            PostgresGraphRepository,
        )

        conn = psycopg.connect(dsn)
        repo = PostgresGraphRepository(
            connection=conn,
            graph_name=graph_name,
            embedding_dimensions=embedding_dimensions,
        )
        repo.initialize()
        provider = OpenAIProvider(
            api_key=api_key,
            model=model,
            embedding_model=embedding_model,
        )
        instance = cls(
            graph_repository=repo,
            embedding_provider=provider,
            llm_provider=provider,
        )
        instance._connection = conn
        return instance

    @classmethod
    def from_openrouter(
        cls,
        dsn: str,
        openrouter_api_key: str,
        *,
        openai_api_key: str | None = None,
        openrouter_model: str = "openai/gpt-4o",
        embedding_model: str = "text-embedding-3-large",
        graph_name: str = "knowledge_graph",
        embedding_dimensions: int = 3072,
    ) -> "GraphSearch":
        """Create a GraphSearch with OpenRouter LLM and optional OpenAI embeddings.

        When ``openai_api_key`` is provided, uses ``OpenAIProvider`` for embeddings and
        ``OpenRouterProvider`` for LLM (mixed mode — backward compatible).

        When ``openai_api_key`` is absent or ``None``, a single ``OpenRouterProvider``
        instance serves as BOTH LLM and embedding provider (OpenRouter-only mode).

        Args:
            dsn: PostgreSQL connection string.
            openrouter_api_key: OpenRouter API key (for LLM extraction).
            openai_api_key: OpenAI API key (for embeddings). Optional — when absent,
                OpenRouter handles both LLM and embeddings.
            openrouter_model: OpenRouter model identifier. Defaults to ``"openai/gpt-4o"``.
            embedding_model: Embedding model identifier. Defaults to ``"text-embedding-3-large"``.
            graph_name: AGE graph name. Defaults to ``"knowledge_graph"``.
            embedding_dimensions: Vector dimension. Defaults to 3072.

        Returns:
            A ready-to-use ``GraphSearch`` instance with connection lifecycle ownership.
        """
        import psycopg

        from depth_graph_search.adapters.openrouter.provider import OpenRouterProvider
        from depth_graph_search.adapters.postgres.repository import (
            PostgresGraphRepository,
        )

        conn = psycopg.connect(dsn)
        repo = PostgresGraphRepository(
            connection=conn,
            graph_name=graph_name,
            embedding_dimensions=embedding_dimensions,
        )
        repo.initialize()

        embedding_provider: EmbeddingProvider
        llm_provider: LLMProvider

        if openai_api_key:
            # Mixed mode: OpenAI handles embeddings, OpenRouter handles LLM
            from depth_graph_search.adapters.openai.provider import OpenAIProvider

            embedding_provider = OpenAIProvider(
                api_key=openai_api_key,
                embedding_model=embedding_model,
            )
            llm_provider = OpenRouterProvider(
                api_key=openrouter_api_key,
                model=openrouter_model,
            )
        else:
            # OpenRouter-only mode: single provider for both roles
            provider = OpenRouterProvider(
                api_key=openrouter_api_key,
                model=openrouter_model,
                embedding_model=embedding_model,
            )
            embedding_provider = provider
            llm_provider = provider

        instance = cls(
            graph_repository=repo,
            embedding_provider=embedding_provider,
            llm_provider=llm_provider,
        )
        instance._connection = conn
        return instance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest(
        self,
        text: str,
        metadata: "Metadata | None" = None,
    ) -> "IngestionResult":
        """Ingest raw text into the knowledge graph.

        Delegates to the internal ``DefaultIngestionPipeline``. Errors propagate
        unchanged — ``ValidationError``, ``IngestionError``, ``StorageError``, and
        ``LLMError`` are NOT wrapped.

        Args:
            text: The raw text to ingest. MUST be non-empty and non-whitespace-only.
            metadata: Free-form key-value context. ``None`` is accepted.

        Returns:
            ``IngestionResult(node_count, edge_count)``.

        Raises:
            ValidationError: If ``text`` is empty or whitespace-only.
            IngestionError: If any pipeline stage fails.
        """
        return self._ingestion_pipeline.ingest(text, metadata)

    def search(
        self,
        query: str,
        top_n: int = 5,
        depth_m: int = 2,
        metadata_filter: "Metadata | None" = None,
    ) -> "list[ScoredNode]":
        """Execute a hybrid graph search.

        Delegates to the internal ``DefaultSearchPipeline``. The ``pipeline``
        parameter is intentionally not exposed — it is silently ignored in v0.1.

        Args:
            query: The natural language query string.
            top_n: Maximum number of results to return. Defaults to 5.
            depth_m: Maximum BFS hop depth from entry nodes. Defaults to 2.
            metadata_filter: Key-value dict to pre-filter candidate nodes. ``None``
                means no filtering.

        Returns:
            At most ``top_n`` ``ScoredNode`` instances ordered by score DESC,
            distance ASC.

        Raises:
            StorageError: If the graph store operation fails.
            LLMError: If the embedding call fails.
        """
        return self._search_pipeline.search(
            query=query,
            top_n=top_n,
            depth_m=depth_m,
            metadata_filter=metadata_filter,
            pipeline=None,
        )

    # ------------------------------------------------------------------
    # Resource management
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Release the connection owned by this facade.

        Only closes the connection when the facade was created via a classmethod
        (``from_openai`` / ``from_openrouter``). In port-injection mode (direct
        constructor), this method is a no-op — the caller owns the lifecycle.
        """
        if self._connection is not None:
            self._connection.close()  # type: ignore[union-attr]
            self._connection = None

    def __enter__(self) -> "GraphSearch":
        """Enter the context manager. Returns ``self``."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit the context manager. Calls ``close()``."""
        self.close()
