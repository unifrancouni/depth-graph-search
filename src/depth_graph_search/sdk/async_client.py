"""AsyncGraphSearch — async SDK facade wiring all async ports into a 2-method public API.

Design decisions:
- Pure wiring layer: zero business logic, all delegation to internal pipelines.
- Sync ``__init__`` accepts pre-built async ports via dependency injection. No I/O.
- ``from_openai`` and ``from_openrouter`` are ``async classmethod`` because they call
  ``await repo.initialize()``.
- ``__aenter__`` / ``__aexit__`` implement the async context manager protocol.
- ``__aexit__`` calls ``await self.close()`` which awaits the repository's close.
- In port-injection mode, ``close()`` is a no-op — the caller owns the lifecycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from depth_graph_search.adapters.ingestion.async_pipeline import AsyncDefaultIngestionPipeline
from depth_graph_search.adapters.search.async_entity_resolution import (
    AsyncDefaultEntityResolutionStrategy,
)
from depth_graph_search.adapters.search.async_pipeline import AsyncDefaultSearchPipeline
from depth_graph_search.core.ports.async_ports import (
    AsyncEmbeddingProvider,
    AsyncEntityResolutionStrategy,
    AsyncGraphRepository,
    AsyncIngestionPipeline,
    AsyncLLMProvider,
    AsyncSearchPipeline,
)

if TYPE_CHECKING:
    from depth_graph_search.core.domain.entities import IngestionResult, Metadata, ScoredNode


class AsyncGraphSearch:
    """Async high-level SDK entry point for depth-graph-search.

    Wires all async ports internally and exposes a minimal, ergonomic API:
    - ``await gs.ingest(text, metadata)`` — extract entities and persist to the graph.
    - ``await gs.search(query, top_n, depth_m, metadata_filter)`` — hybrid graph search.

    The preferred usage via classmethods is the async context manager::

        async with await AsyncGraphSearch.from_openai(dsn, api_key) as gs:
            await gs.ingest("Alice works at Acme Corp.")
            results = await gs.search("who works at Acme?")

    Port-injection mode (for testing or custom wiring)::

        gs = AsyncGraphSearch(
            graph_repository=repo,
            embedding_provider=embedder,
            llm_provider=llm,
            ingestion_pipeline=ingestion,
            search_pipeline=search,
        )

    Args:
        graph_repository: Adapter implementing ``AsyncGraphRepository``.
        embedding_provider: Adapter implementing ``AsyncEmbeddingProvider``.
        llm_provider: Adapter implementing ``AsyncLLMProvider``.
        entity_resolution: Optional adapter implementing ``AsyncEntityResolutionStrategy``.
            When ``None``, auto-wired from the other ports.
        ingestion_pipeline: Optional pre-built ``AsyncIngestionPipeline``.
            When ``None``, auto-wired from the other ports.
        search_pipeline: Optional pre-built ``AsyncSearchPipeline``.
            When ``None``, auto-wired from the other ports.

    Note:
        The constructor is SYNCHRONOUS and performs ZERO I/O. In port-injection mode,
        ``close()`` is a no-op — the caller owns the connection lifecycle.
    """

    def __init__(
        self,
        graph_repository: AsyncGraphRepository,
        embedding_provider: AsyncEmbeddingProvider,
        llm_provider: AsyncLLMProvider,
        entity_resolution: AsyncEntityResolutionStrategy | None = None,
        ingestion_pipeline: AsyncIngestionPipeline | None = None,
        search_pipeline: AsyncSearchPipeline | None = None,
    ) -> None:
        self._repository = graph_repository
        self._owns_connection: bool = False  # set True by classmethods

        # Build search pipeline if not injected
        if search_pipeline is None:
            search_pipeline = AsyncDefaultSearchPipeline(
                graph_repository=graph_repository,
                embedding_provider=embedding_provider,
            )
        self._search_pipeline = search_pipeline

        # Auto-build entity resolution if not injected
        if entity_resolution is None:
            entity_resolution = AsyncDefaultEntityResolutionStrategy(
                pipeline=self._search_pipeline,
            )

        # Build ingestion pipeline if not injected
        if ingestion_pipeline is None:
            ingestion_pipeline = AsyncDefaultIngestionPipeline(
                llm_provider=llm_provider,
                embedding_provider=embedding_provider,
                graph_repository=graph_repository,
                entity_resolution=entity_resolution,
            )
        self._ingestion_pipeline = ingestion_pipeline

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def repository(self) -> AsyncGraphRepository:
        """The underlying ``AsyncGraphRepository`` adapter.

        Exposed for infrastructure concerns (e.g. health checks) that need
        direct repository access without going through the pipeline layer.
        """
        return self._repository

    # ------------------------------------------------------------------
    # Async context manager protocol
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "AsyncGraphSearch":
        """Enter the async context manager. Returns ``self``."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit the async context manager. Calls ``await self.close()``."""
        await self.close()

    # ------------------------------------------------------------------
    # Factory classmethods
    # ------------------------------------------------------------------

    @classmethod
    async def from_openai(
        cls,
        dsn: str,
        api_key: str,
        *,
        model: str = "gpt-4o",
        embedding_model: str = "text-embedding-3-large",
        graph_name: str = "knowledge_graph",
        embedding_dimensions: int = 3072,
    ) -> "AsyncGraphSearch":
        """Create an AsyncGraphSearch wired to PostgreSQL and OpenAI.

        Creates an ``AsyncConnection``, instantiates ``AsyncPostgresGraphRepository``,
        calls ``await repo.initialize()``, and wires a single ``AsyncOpenAIProvider``
        as both ``embedding_provider`` and ``llm_provider``.

        The facade owns the connection lifecycle — call ``await gs.close()`` or use
        the async context manager to release it.

        Args:
            dsn: PostgreSQL connection string.
            api_key: OpenAI API key.
            model: Chat completion model. Defaults to ``"gpt-4o"``.
            embedding_model: Embedding model. Defaults to ``"text-embedding-3-large"``.
            graph_name: AGE graph name. Defaults to ``"knowledge_graph"``.
            embedding_dimensions: Vector dimension. Defaults to 3072.

        Returns:
            A ready-to-use ``AsyncGraphSearch`` instance with initialized repository.
        """
        import psycopg

        from depth_graph_search.adapters.openai.async_provider import AsyncOpenAIProvider
        from depth_graph_search.adapters.postgres.async_repository import (
            AsyncPostgresGraphRepository,
        )

        conn = await psycopg.AsyncConnection.connect(dsn)
        repo = AsyncPostgresGraphRepository(
            connection=conn,
            graph_name=graph_name,
            embedding_dimensions=embedding_dimensions,
        )
        await repo.initialize()
        provider = AsyncOpenAIProvider(
            api_key=api_key,
            model=model,
            embedding_model=embedding_model,
        )
        instance = cls(
            graph_repository=repo,
            embedding_provider=provider,
            llm_provider=provider,
        )
        instance._owns_connection = True
        return instance

    @classmethod
    async def from_openrouter(
        cls,
        dsn: str,
        api_key: str,
        *,
        openai_api_key: str = "",
        openrouter_model: str = "openai/gpt-4o",
        embedding_model: str = "text-embedding-3-large",
        graph_name: str = "knowledge_graph",
        embedding_dimensions: int = 3072,
    ) -> "AsyncGraphSearch":
        """Create an AsyncGraphSearch with OpenAI embeddings and OpenRouter LLM.

        Uses ``AsyncOpenAIProvider`` for embedding generation and
        ``AsyncOpenRouterProvider`` for LLM graph extraction.

        Args:
            dsn: PostgreSQL connection string.
            api_key: OpenRouter API key.
            openai_api_key: OpenAI API key (for embeddings). Required.
            openrouter_model: OpenRouter model identifier.
            embedding_model: OpenAI embedding model.
            graph_name: AGE graph name.
            embedding_dimensions: Vector dimension.

        Returns:
            A ready-to-use ``AsyncGraphSearch`` instance.
        """
        import psycopg

        from depth_graph_search.adapters.openai.async_provider import AsyncOpenAIProvider
        from depth_graph_search.adapters.openrouter.async_provider import (
            AsyncOpenRouterProvider,
        )
        from depth_graph_search.adapters.postgres.async_repository import (
            AsyncPostgresGraphRepository,
        )

        conn = await psycopg.AsyncConnection.connect(dsn)
        repo = AsyncPostgresGraphRepository(
            connection=conn,
            graph_name=graph_name,
            embedding_dimensions=embedding_dimensions,
        )
        await repo.initialize()
        embedding_provider = AsyncOpenAIProvider(
            api_key=openai_api_key,
            embedding_model=embedding_model,
        )
        llm_provider = AsyncOpenRouterProvider(
            api_key=api_key,
            model=openrouter_model,
        )
        instance = cls(
            graph_repository=repo,
            embedding_provider=embedding_provider,
            llm_provider=llm_provider,
        )
        instance._owns_connection = True
        return instance

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def ingest(
        self,
        text: str,
        metadata: "Metadata | None" = None,
    ) -> "IngestionResult":
        """Ingest raw text into the knowledge graph.

        Delegates to the internal ``AsyncDefaultIngestionPipeline``.

        Args:
            text: The raw text to ingest. MUST be non-empty and non-whitespace-only.
            metadata: Free-form key-value context. ``None`` is accepted.

        Returns:
            ``IngestionResult(node_count, edge_count)``.

        Raises:
            ValidationError: If ``text`` is empty or whitespace-only.
        """
        return await self._ingestion_pipeline.ingest(text, metadata)

    async def search(
        self,
        query: str,
        top_n: int = 5,
        depth_m: int = 2,
        metadata_filter: "Metadata | None" = None,
    ) -> "list[ScoredNode]":
        """Execute a hybrid graph search.

        Delegates to the internal ``AsyncDefaultSearchPipeline``.

        Args:
            query: The natural language query string.
            top_n: Maximum number of results to return. Defaults to 5.
            depth_m: Maximum BFS hop depth from entry nodes. Defaults to 2.
            metadata_filter: Key-value dict to pre-filter candidate nodes.

        Returns:
            At most ``top_n`` ``ScoredNode`` instances ordered by score DESC,
            distance ASC.
        """
        return await self._search_pipeline.search(
            query=query,
            top_n=top_n,
            depth_m=depth_m,
            metadata_filter=metadata_filter,
        )

    # ------------------------------------------------------------------
    # Resource management
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Release the async connection owned by this facade.

        Calls ``await repository.close()``.
        In port-injection mode (direct constructor), also closes if repository
        has a close method.
        """
        await self._repository.close()
