"""Unit tests for GraphSearch facade.

Tests are 1-to-1 with spec scenarios. Each test is self-contained.
The classmethods (from_openai / from_openrouter) are tested with
unittest.mock patching — no live connections, no API calls.

Coverage:
- Constructor with all 4 ports: pipelines wired, _connection=None
- Constructor with entity_resolution=None: DefaultEntityResolutionStrategy auto-created
- ingest() delegates to _ingestion_pipeline.ingest()
- search() delegates to _search_pipeline.search() with correct args
- Error propagation: StorageError, IngestionError, LLMError pass through unchanged
- close() when _connection is set: calls conn.close()
- close() no-op when _connection is None (port-injection mode)
- Context manager: __enter__ returns self, __exit__ calls close()
- from_openai classmethod: correct construction order, initialize() called, single provider
- from_openai with embedding_dimensions=1536: threaded to PostgresGraphRepository
- from_openrouter classmethod: split providers, initialize() called
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from depth_graph_search.adapters.ingestion.pipeline import DefaultIngestionPipeline
from depth_graph_search.adapters.search.entity_resolution import (
    DefaultEntityResolutionStrategy,
)
from depth_graph_search.adapters.search.pipeline import DefaultSearchPipeline
from depth_graph_search.core.domain.entities import IngestionResult, Node, ScoredNode
from depth_graph_search.core.domain.exceptions import (
    IngestionError,
    LLMError,
    StorageError,
)
from depth_graph_search.sdk.client import GraphSearch
from tests.mocks import (
    FakeEmbeddingProvider,
    FakeEntityResolutionStrategy,
    FakeLLMProvider,
    InMemoryGraphRepository,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_repo() -> InMemoryGraphRepository:
    """Fresh in-memory graph repository."""
    return InMemoryGraphRepository()


@pytest.fixture
def fake_embedder() -> FakeEmbeddingProvider:
    """Fresh fake embedding provider."""
    return FakeEmbeddingProvider()


@pytest.fixture
def fake_llm() -> FakeLLMProvider:
    """Fresh fake LLM provider."""
    return FakeLLMProvider()


@pytest.fixture
def fake_resolver() -> FakeEntityResolutionStrategy:
    """Fresh fake entity resolution strategy."""
    return FakeEntityResolutionStrategy()


@pytest.fixture
def gs_with_resolver(
    fake_repo: InMemoryGraphRepository,
    fake_embedder: FakeEmbeddingProvider,
    fake_llm: FakeLLMProvider,
    fake_resolver: FakeEntityResolutionStrategy,
) -> GraphSearch:
    """GraphSearch wired with all 4 explicit ports."""
    return GraphSearch(
        graph_repository=fake_repo,
        embedding_provider=fake_embedder,
        llm_provider=fake_llm,
        entity_resolution=fake_resolver,
    )


@pytest.fixture
def gs_auto_resolver(
    fake_repo: InMemoryGraphRepository,
    fake_embedder: FakeEmbeddingProvider,
    fake_llm: FakeLLMProvider,
) -> GraphSearch:
    """GraphSearch with entity_resolution=None (auto-build)."""
    return GraphSearch(
        graph_repository=fake_repo,
        embedding_provider=fake_embedder,
        llm_provider=fake_llm,
    )


# ---------------------------------------------------------------------------
# 4.1 — Constructor with all 4 ports
# ---------------------------------------------------------------------------


def test_constructor_pipelines_wired(
    fake_repo: InMemoryGraphRepository,
    fake_embedder: FakeEmbeddingProvider,
    fake_llm: FakeLLMProvider,
    fake_resolver: FakeEntityResolutionStrategy,
) -> None:
    """Constructor builds _ingestion_pipeline, _search_pipeline, _connection=None."""
    gs = GraphSearch(
        graph_repository=fake_repo,
        embedding_provider=fake_embedder,
        llm_provider=fake_llm,
        entity_resolution=fake_resolver,
    )
    assert isinstance(gs._ingestion_pipeline, DefaultIngestionPipeline)
    assert isinstance(gs._search_pipeline, DefaultSearchPipeline)
    assert gs._connection is None


# ---------------------------------------------------------------------------
# 4.2 — Constructor with entity_resolution=None: auto-build
# ---------------------------------------------------------------------------


def test_constructor_auto_entity_resolution(gs_auto_resolver: GraphSearch) -> None:
    """When entity_resolution=None, DefaultEntityResolutionStrategy is auto-created."""
    # The ingestion pipeline's _entity_resolution should be DefaultEntityResolutionStrategy
    pipeline: DefaultIngestionPipeline = gs_auto_resolver._ingestion_pipeline
    assert isinstance(pipeline._entity_resolution, DefaultEntityResolutionStrategy)


def test_constructor_auto_entity_resolution_uses_search_pipeline(
    gs_auto_resolver: GraphSearch,
) -> None:
    """The auto-created DefaultEntityResolutionStrategy wraps the facade's _search_pipeline."""
    pipeline: DefaultIngestionPipeline = gs_auto_resolver._ingestion_pipeline
    resolver: DefaultEntityResolutionStrategy = pipeline._entity_resolution  # type: ignore[assignment]
    assert resolver._pipeline is gs_auto_resolver._search_pipeline


# ---------------------------------------------------------------------------
# 4.3 — ingest() delegates to pipeline
# ---------------------------------------------------------------------------


def test_ingest_delegates_to_pipeline(
    gs_with_resolver: GraphSearch,
    fake_llm: FakeLLMProvider,
    fake_embedder: FakeEmbeddingProvider,
) -> None:
    """ingest() delegates to _ingestion_pipeline.ingest with correct args."""
    # Wire the pipeline to return something useful
    node_a = Node(content="Alice")
    fake_llm.set_extraction(nodes=[node_a], edges=[])

    result = gs_with_resolver.ingest("Alice works at Acme.", metadata={"source": "doc1"})

    assert isinstance(result, IngestionResult)
    assert result.node_count == 1
    assert result.edge_count == 0


def test_ingest_delegates_with_none_metadata(
    gs_with_resolver: GraphSearch,
    fake_llm: FakeLLMProvider,
) -> None:
    """ingest() passes metadata=None to the pipeline without error."""
    fake_llm.set_extraction(nodes=[], edges=[])
    result = gs_with_resolver.ingest("some text")
    assert isinstance(result, IngestionResult)
    assert result.node_count == 0


def test_ingest_uses_internal_pipeline_mock() -> None:
    """Verify the delegation by replacing _ingestion_pipeline with a mock."""
    repo = InMemoryGraphRepository()
    embedder = FakeEmbeddingProvider()
    llm = FakeLLMProvider()
    resolver = FakeEntityResolutionStrategy()

    gs = GraphSearch(
        graph_repository=repo,
        embedding_provider=embedder,
        llm_provider=llm,
        entity_resolution=resolver,
    )

    mock_pipeline = MagicMock()
    expected_result = IngestionResult(node_count=3, edge_count=2)
    mock_pipeline.ingest.return_value = expected_result
    gs._ingestion_pipeline = mock_pipeline

    result = gs.ingest("hello world", metadata={"k": "v"})

    mock_pipeline.ingest.assert_called_once_with("hello world", {"k": "v"})
    assert result is expected_result


# ---------------------------------------------------------------------------
# 4.4 — search() delegates to pipeline
# ---------------------------------------------------------------------------


def test_search_delegates_to_pipeline() -> None:
    """search() delegates to _search_pipeline.search with correct kwargs."""
    repo = InMemoryGraphRepository()
    embedder = FakeEmbeddingProvider()
    llm = FakeLLMProvider()
    resolver = FakeEntityResolutionStrategy()

    gs = GraphSearch(
        graph_repository=repo,
        embedding_provider=embedder,
        llm_provider=llm,
        entity_resolution=resolver,
    )

    mock_pipeline = MagicMock()
    scored_node = ScoredNode(node=Node(content="Alice"), score=0.9, distance=0)
    mock_pipeline.search.return_value = [scored_node]
    gs._search_pipeline = mock_pipeline

    results = gs.search("who is Alice?", top_n=3, depth_m=1, metadata_filter={"k": "v"})

    mock_pipeline.search.assert_called_once_with(
        query="who is Alice?",
        top_n=3,
        depth_m=1,
        metadata_filter={"k": "v"},
        pipeline=None,
    )
    assert results == [scored_node]


def test_search_uses_defaults() -> None:
    """search() passes top_n=5, depth_m=2, metadata_filter=None by default."""
    repo = InMemoryGraphRepository()
    gs = GraphSearch(
        graph_repository=repo,
        embedding_provider=FakeEmbeddingProvider(),
        llm_provider=FakeLLMProvider(),
        entity_resolution=FakeEntityResolutionStrategy(),
    )

    mock_pipeline = MagicMock()
    mock_pipeline.search.return_value = []
    gs._search_pipeline = mock_pipeline

    gs.search("test query")

    mock_pipeline.search.assert_called_once_with(
        query="test query",
        top_n=5,
        depth_m=2,
        metadata_filter=None,
        pipeline=None,
    )


# ---------------------------------------------------------------------------
# 4.5 — Error propagation
# ---------------------------------------------------------------------------


def test_ingest_propagates_storage_error() -> None:
    """StorageError from the pipeline propagates through ingest() unchanged."""
    repo = InMemoryGraphRepository()
    embedder = FakeEmbeddingProvider()
    llm = FakeLLMProvider()
    resolver = FakeEntityResolutionStrategy()

    gs = GraphSearch(
        graph_repository=repo,
        embedding_provider=embedder,
        llm_provider=llm,
        entity_resolution=resolver,
    )

    mock_pipeline = MagicMock()
    original_error = StorageError("db is down")
    mock_pipeline.ingest.side_effect = original_error
    gs._ingestion_pipeline = mock_pipeline

    with pytest.raises(StorageError) as exc_info:
        gs.ingest("text")

    assert exc_info.value is original_error


def test_ingest_propagates_ingestion_error() -> None:
    """IngestionError from the pipeline propagates through ingest() unchanged."""
    gs = GraphSearch(
        graph_repository=InMemoryGraphRepository(),
        embedding_provider=FakeEmbeddingProvider(),
        llm_provider=FakeLLMProvider(),
        entity_resolution=FakeEntityResolutionStrategy(),
    )
    mock_pipeline = MagicMock()
    original_error = IngestionError("extraction failed")
    mock_pipeline.ingest.side_effect = original_error
    gs._ingestion_pipeline = mock_pipeline

    with pytest.raises(IngestionError) as exc_info:
        gs.ingest("text")

    assert exc_info.value is original_error


def test_ingest_propagates_llm_error() -> None:
    """LLMError from the pipeline propagates through ingest() unchanged."""
    gs = GraphSearch(
        graph_repository=InMemoryGraphRepository(),
        embedding_provider=FakeEmbeddingProvider(),
        llm_provider=FakeLLMProvider(),
        entity_resolution=FakeEntityResolutionStrategy(),
    )
    mock_pipeline = MagicMock()
    original_error = LLMError("model refused")
    mock_pipeline.ingest.side_effect = original_error
    gs._ingestion_pipeline = mock_pipeline

    with pytest.raises(LLMError) as exc_info:
        gs.ingest("text")

    assert exc_info.value is original_error


def test_search_propagates_storage_error() -> None:
    """StorageError from the pipeline propagates through search() unchanged."""
    gs = GraphSearch(
        graph_repository=InMemoryGraphRepository(),
        embedding_provider=FakeEmbeddingProvider(),
        llm_provider=FakeLLMProvider(),
        entity_resolution=FakeEntityResolutionStrategy(),
    )
    mock_pipeline = MagicMock()
    original_error = StorageError("traverse failed")
    mock_pipeline.search.side_effect = original_error
    gs._search_pipeline = mock_pipeline

    with pytest.raises(StorageError) as exc_info:
        gs.search("query")

    assert exc_info.value is original_error


def test_search_propagates_llm_error() -> None:
    """LLMError from the pipeline propagates through search() unchanged."""
    gs = GraphSearch(
        graph_repository=InMemoryGraphRepository(),
        embedding_provider=FakeEmbeddingProvider(),
        llm_provider=FakeLLMProvider(),
        entity_resolution=FakeEntityResolutionStrategy(),
    )
    mock_pipeline = MagicMock()
    original_error = LLMError("embed failed")
    mock_pipeline.search.side_effect = original_error
    gs._search_pipeline = mock_pipeline

    with pytest.raises(LLMError) as exc_info:
        gs.search("query")

    assert exc_info.value is original_error


# ---------------------------------------------------------------------------
# 4.6 — close() when _connection is set
# ---------------------------------------------------------------------------


def test_close_calls_connection_close() -> None:
    """close() calls _connection.close() when _connection is not None."""
    gs = GraphSearch(
        graph_repository=InMemoryGraphRepository(),
        embedding_provider=FakeEmbeddingProvider(),
        llm_provider=FakeLLMProvider(),
        entity_resolution=FakeEntityResolutionStrategy(),
    )
    mock_conn = MagicMock()
    gs._connection = mock_conn

    gs.close()

    mock_conn.close.assert_called_once()
    assert gs._connection is None


def test_close_can_be_called_twice_without_error() -> None:
    """close() is idempotent — calling it twice does not raise."""
    gs = GraphSearch(
        graph_repository=InMemoryGraphRepository(),
        embedding_provider=FakeEmbeddingProvider(),
        llm_provider=FakeLLMProvider(),
        entity_resolution=FakeEntityResolutionStrategy(),
    )
    mock_conn = MagicMock()
    gs._connection = mock_conn

    gs.close()
    gs.close()  # second call — _connection is now None, must not raise

    mock_conn.close.assert_called_once()  # only once


# ---------------------------------------------------------------------------
# 4.7 — close() is no-op in port-injection mode
# ---------------------------------------------------------------------------


def test_close_noop_when_connection_is_none(gs_with_resolver: GraphSearch) -> None:
    """close() does nothing when _connection is None (port-injection mode)."""
    assert gs_with_resolver._connection is None
    gs_with_resolver.close()  # must not raise
    assert gs_with_resolver._connection is None


# ---------------------------------------------------------------------------
# 4.8 — Context manager
# ---------------------------------------------------------------------------


def test_enter_returns_self(gs_with_resolver: GraphSearch) -> None:
    """__enter__ returns the GraphSearch instance itself."""
    result = gs_with_resolver.__enter__()
    assert result is gs_with_resolver


def test_context_manager_calls_close_on_exit() -> None:
    """__exit__ calls close() — verified via mock connection."""
    gs = GraphSearch(
        graph_repository=InMemoryGraphRepository(),
        embedding_provider=FakeEmbeddingProvider(),
        llm_provider=FakeLLMProvider(),
        entity_resolution=FakeEntityResolutionStrategy(),
    )
    mock_conn = MagicMock()
    gs._connection = mock_conn

    with gs:
        pass

    mock_conn.close.assert_called_once()


def test_context_manager_closes_on_exception() -> None:
    """__exit__ is called even when the body raises, releasing the connection."""
    gs = GraphSearch(
        graph_repository=InMemoryGraphRepository(),
        embedding_provider=FakeEmbeddingProvider(),
        llm_provider=FakeLLMProvider(),
        entity_resolution=FakeEntityResolutionStrategy(),
    )
    mock_conn = MagicMock()
    gs._connection = mock_conn

    with pytest.raises(RuntimeError):
        with gs:
            raise RuntimeError("boom")

    mock_conn.close.assert_called_once()


# ---------------------------------------------------------------------------
# 4.9 — from_openai classmethod
# ---------------------------------------------------------------------------


@patch("depth_graph_search.sdk.client.GraphSearch.from_openai")
def test_from_openai_is_callable(mock_from_openai: MagicMock) -> None:
    """from_openai exists and is a classmethod."""
    assert callable(GraphSearch.from_openai)


def test_from_openai_construction_order() -> None:
    """from_openai: correct construction order + initialize() called + single provider."""
    with (
        patch("psycopg.connect") as mock_connect,
        patch(
            "depth_graph_search.adapters.postgres.repository.PostgresGraphRepository"
        ) as MockRepo,
        patch(
            "depth_graph_search.adapters.openai.provider.OpenAIProvider"
        ) as MockProvider,
    ):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        mock_repo_instance = MagicMock()
        MockRepo.return_value = mock_repo_instance

        mock_provider_instance = MagicMock()
        MockProvider.return_value = mock_provider_instance

        gs = GraphSearch.from_openai("postgresql://localhost/test", "sk-test-key")

        # Connection created first
        mock_connect.assert_called_once_with("postgresql://localhost/test")

        # Repository created with connection
        MockRepo.assert_called_once_with(
            connection=mock_conn,
            graph_name="knowledge_graph",
            embedding_dimensions=3072,
        )

        # initialize() was called on the repo
        mock_repo_instance.initialize.assert_called_once()

        # Provider created with api_key
        MockProvider.assert_called_once_with(
            api_key="sk-test-key",
            model="gpt-4o",
            embedding_model="text-embedding-3-large",
        )

        # _connection set on facade
        assert gs._connection is mock_conn


def test_from_openai_single_provider_for_embed_and_llm() -> None:
    """from_openai uses ONE OpenAIProvider instance for both embedding and LLM."""
    with (
        patch("psycopg.connect") as mock_connect,
        patch(
            "depth_graph_search.adapters.postgres.repository.PostgresGraphRepository"
        ) as MockRepo,
        patch(
            "depth_graph_search.adapters.openai.provider.OpenAIProvider"
        ) as MockProvider,
    ):
        mock_connect.return_value = MagicMock()
        mock_repo_instance = MagicMock()
        MockRepo.return_value = mock_repo_instance
        mock_provider_instance = MagicMock()
        MockProvider.return_value = mock_provider_instance

        gs = GraphSearch.from_openai("postgresql://localhost/test", "sk-key")

        # Only one OpenAIProvider instance created
        assert MockProvider.call_count == 1

        # Both pipelines use the same provider instance
        ingestion_pipeline: DefaultIngestionPipeline = gs._ingestion_pipeline
        search_pipeline: DefaultSearchPipeline = gs._search_pipeline
        assert ingestion_pipeline._llm_provider is mock_provider_instance
        assert ingestion_pipeline._embedding_provider is mock_provider_instance
        assert search_pipeline._embedding_provider is mock_provider_instance


# ---------------------------------------------------------------------------
# 4.10 — from_openai with embedding_dimensions
# ---------------------------------------------------------------------------


def test_from_openai_threads_embedding_dimensions() -> None:
    """from_openai with embedding_dimensions=1536 passes it to PostgresGraphRepository."""
    with (
        patch("psycopg.connect") as mock_connect,
        patch(
            "depth_graph_search.adapters.postgres.repository.PostgresGraphRepository"
        ) as MockRepo,
        patch("depth_graph_search.adapters.openai.provider.OpenAIProvider"),
    ):
        mock_connect.return_value = MagicMock()
        mock_repo_instance = MagicMock()
        MockRepo.return_value = mock_repo_instance

        GraphSearch.from_openai(
            "postgresql://localhost/test",
            "sk-key",
            embedding_dimensions=1536,
        )

        MockRepo.assert_called_once_with(
            connection=mock_connect.return_value,
            graph_name="knowledge_graph",
            embedding_dimensions=1536,
        )


def test_from_openai_threads_graph_name() -> None:
    """from_openai with custom graph_name passes it to PostgresGraphRepository."""
    with (
        patch("psycopg.connect") as mock_connect,
        patch(
            "depth_graph_search.adapters.postgres.repository.PostgresGraphRepository"
        ) as MockRepo,
        patch("depth_graph_search.adapters.openai.provider.OpenAIProvider"),
    ):
        mock_connect.return_value = MagicMock()
        mock_repo_instance = MagicMock()
        MockRepo.return_value = mock_repo_instance

        GraphSearch.from_openai(
            "postgresql://localhost/test",
            "sk-key",
            graph_name="my_graph",
        )

        MockRepo.assert_called_once_with(
            connection=mock_connect.return_value,
            graph_name="my_graph",
            embedding_dimensions=3072,
        )


# ---------------------------------------------------------------------------
# 4.11 — from_openrouter classmethod
# ---------------------------------------------------------------------------


def test_from_openrouter_mixed_mode_construction_order() -> None:
    """from_openrouter with openai_api_key: OpenAIProvider for embeddings, OpenRouterProvider for LLM."""
    with (
        patch("psycopg.connect") as mock_connect,
        patch(
            "depth_graph_search.adapters.postgres.repository.PostgresGraphRepository"
        ) as MockRepo,
        patch(
            "depth_graph_search.adapters.openai.provider.OpenAIProvider"
        ) as MockOAI,
        patch(
            "depth_graph_search.adapters.openrouter.provider.OpenRouterProvider"
        ) as MockOR,
    ):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        mock_repo_instance = MagicMock()
        MockRepo.return_value = mock_repo_instance

        mock_oai_instance = MagicMock()
        MockOAI.return_value = mock_oai_instance

        mock_or_instance = MagicMock()
        MockOR.return_value = mock_or_instance

        gs = GraphSearch.from_openrouter(
            "postgresql://localhost/test",
            openrouter_api_key="sk-openrouter",
            openai_api_key="sk-openai",
        )

        # Connection created
        mock_connect.assert_called_once_with("postgresql://localhost/test")

        # Repository initialized
        mock_repo_instance.initialize.assert_called_once()

        # OpenAIProvider for embeddings
        MockOAI.assert_called_once_with(
            api_key="sk-openai",
            embedding_model="text-embedding-3-large",
        )

        # OpenRouterProvider for LLM (without embedding_model in mixed mode)
        MockOR.assert_called_once_with(
            api_key="sk-openrouter",
            model="openai/gpt-4o",
        )

        # _connection set
        assert gs._connection is mock_conn


def test_from_openrouter_mixed_mode_split_providers() -> None:
    """from_openrouter with openai_api_key uses separate providers: OAI for embed, OR for llm."""
    with (
        patch("psycopg.connect") as mock_connect,
        patch(
            "depth_graph_search.adapters.postgres.repository.PostgresGraphRepository"
        ) as MockRepo,
        patch(
            "depth_graph_search.adapters.openai.provider.OpenAIProvider"
        ) as MockOAI,
        patch(
            "depth_graph_search.adapters.openrouter.provider.OpenRouterProvider"
        ) as MockOR,
    ):
        mock_connect.return_value = MagicMock()
        mock_repo_instance = MagicMock()
        MockRepo.return_value = mock_repo_instance
        mock_oai_instance = MagicMock()
        MockOAI.return_value = mock_oai_instance
        mock_or_instance = MagicMock()
        MockOR.return_value = mock_or_instance

        gs = GraphSearch.from_openrouter(
            "postgresql://localhost/test",
            openrouter_api_key="sk-openrouter",
            openai_api_key="sk-openai",
        )

        # Search pipeline uses OAI for embeddings
        search_pipeline: DefaultSearchPipeline = gs._search_pipeline
        assert search_pipeline._embedding_provider is mock_oai_instance

        # Ingestion pipeline uses OAI for embedding, OR for LLM
        ingestion_pipeline: DefaultIngestionPipeline = gs._ingestion_pipeline
        assert ingestion_pipeline._embedding_provider is mock_oai_instance
        assert ingestion_pipeline._llm_provider is mock_or_instance


def test_from_openrouter_openrouter_only_mode() -> None:
    """from_openrouter without openai_api_key wires single OpenRouterProvider for both roles."""
    with (
        patch("psycopg.connect") as mock_connect,
        patch(
            "depth_graph_search.adapters.postgres.repository.PostgresGraphRepository"
        ) as MockRepo,
        patch(
            "depth_graph_search.adapters.openrouter.provider.OpenRouterProvider"
        ) as MockOR,
    ):
        mock_connect.return_value = MagicMock()
        mock_repo_instance = MagicMock()
        MockRepo.return_value = mock_repo_instance
        mock_or_instance = MagicMock()
        MockOR.return_value = mock_or_instance

        gs = GraphSearch.from_openrouter(
            "postgresql://localhost/test",
            openrouter_api_key="sk-openrouter",
            # no openai_api_key
        )

        # Only one OpenRouterProvider created
        assert MockOR.call_count == 1

        # Both pipelines use the SAME provider instance
        search_pipeline: DefaultSearchPipeline = gs._search_pipeline
        ingestion_pipeline: DefaultIngestionPipeline = gs._ingestion_pipeline
        assert search_pipeline._embedding_provider is mock_or_instance
        assert ingestion_pipeline._embedding_provider is mock_or_instance
        assert ingestion_pipeline._llm_provider is mock_or_instance


def test_from_openrouter_openrouter_only_passes_embedding_model() -> None:
    """from_openrouter without openai_api_key passes embedding_model to OpenRouterProvider."""
    with (
        patch("psycopg.connect") as mock_connect,
        patch(
            "depth_graph_search.adapters.postgres.repository.PostgresGraphRepository"
        ) as MockRepo,
        patch(
            "depth_graph_search.adapters.openrouter.provider.OpenRouterProvider"
        ) as MockOR,
    ):
        mock_connect.return_value = MagicMock()
        MockRepo.return_value = MagicMock()
        MockOR.return_value = MagicMock()

        GraphSearch.from_openrouter(
            "postgresql://localhost/test",
            openrouter_api_key="sk-openrouter",
            embedding_model="openai/text-embedding-ada-002",
        )

        MockOR.assert_called_once_with(
            api_key="sk-openrouter",
            model="openai/gpt-4o",
            embedding_model="openai/text-embedding-ada-002",
        )


# ---------------------------------------------------------------------------
# Top-level import
# ---------------------------------------------------------------------------


def test_top_level_import() -> None:
    """GraphSearch is importable from the top-level depth_graph_search package."""
    from depth_graph_search import GraphSearch as TopLevelGS  # noqa: F401

    assert TopLevelGS is GraphSearch


def test_sdk_import() -> None:
    """GraphSearch is importable from depth_graph_search.sdk."""
    from depth_graph_search.sdk import GraphSearch as SdkGS  # noqa: F401

    assert SdkGS is GraphSearch
