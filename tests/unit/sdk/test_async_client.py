"""Unit tests for AsyncGraphSearch facade.

All tests mock async ports — no I/O.
Covers: sync constructor with port injection; ingest/search delegation;
async context manager; from_openai awaits repo.initialize().
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from depth_graph_search.core.domain.entities import Node
from depth_graph_search.sdk.async_client import AsyncGraphSearch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_async_ports():
    """Return AsyncMock objects for all required ports."""
    repo = AsyncMock()
    repo.closed = False
    embedder = AsyncMock()
    llm = AsyncMock()
    ingestion = AsyncMock()
    search = AsyncMock()
    search.search.return_value = []
    ingestion.ingest.return_value = None
    return repo, embedder, llm, ingestion, search


def _make_gs_injected(
    repo=None, embedder=None, llm=None, ingestion=None, search=None
) -> AsyncGraphSearch:
    """Build AsyncGraphSearch with fully injected ports (no I/O)."""
    if repo is None:
        repo = AsyncMock()
    if embedder is None:
        embedder = AsyncMock()
    if llm is None:
        llm = AsyncMock()
    if ingestion is None:
        ingestion = AsyncMock()
        ingestion.ingest.return_value = None
    if search is None:
        search = AsyncMock()
        search.search.return_value = []

    return AsyncGraphSearch(
        graph_repository=repo,
        embedding_provider=embedder,
        llm_provider=llm,
        ingestion_pipeline=ingestion,
        search_pipeline=search,
    )


# ---------------------------------------------------------------------------
# TestConstructor
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_constructor_is_sync(self) -> None:
        """Verify constructor is synchronous and stores references without I/O."""
        repo, embedder, llm, ingestion, search = _make_async_ports()

        # This should NOT be a coroutine — it's synchronous
        gs = AsyncGraphSearch(
            graph_repository=repo,
            embedding_provider=embedder,
            llm_provider=llm,
            ingestion_pipeline=ingestion,
            search_pipeline=search,
        )

        # No coroutine was created and no I/O occurred
        assert gs is not None
        repo.initialize.assert_not_awaited()

    def test_constructor_stores_repository(self) -> None:
        repo, embedder, llm, ingestion, search = _make_async_ports()
        gs = AsyncGraphSearch(
            graph_repository=repo,
            embedding_provider=embedder,
            llm_provider=llm,
            ingestion_pipeline=ingestion,
            search_pipeline=search,
        )
        assert gs._repository is repo

    def test_constructor_auto_wires_search_pipeline(self) -> None:
        """Without explicit search_pipeline, AsyncDefaultSearchPipeline is auto-built."""
        repo, embedder, llm, _, _ = _make_async_ports()
        gs = AsyncGraphSearch(
            graph_repository=repo,
            embedding_provider=embedder,
            llm_provider=llm,
        )
        from depth_graph_search.adapters.search.async_pipeline import AsyncDefaultSearchPipeline

        assert isinstance(gs._search_pipeline, AsyncDefaultSearchPipeline)

    def test_constructor_auto_wires_ingestion_pipeline(self) -> None:
        """Without explicit ingestion_pipeline, AsyncDefaultIngestionPipeline is auto-built."""
        repo, embedder, llm, _, _ = _make_async_ports()
        gs = AsyncGraphSearch(
            graph_repository=repo,
            embedding_provider=embedder,
            llm_provider=llm,
        )
        from depth_graph_search.adapters.ingestion.async_pipeline import (
            AsyncDefaultIngestionPipeline,
        )

        assert isinstance(gs._ingestion_pipeline, AsyncDefaultIngestionPipeline)


# ---------------------------------------------------------------------------
# TestIngest
# ---------------------------------------------------------------------------


class TestIngest:
    async def test_ingest_delegates_to_pipeline(self) -> None:
        ingestion = AsyncMock()
        ingestion.ingest.return_value = None
        gs = _make_gs_injected(ingestion=ingestion)

        await gs.ingest("test text", {"source": "doc"})

        ingestion.ingest.assert_awaited_once_with("test text", {"source": "doc"})

    async def test_ingest_with_none_metadata(self) -> None:
        ingestion = AsyncMock()
        ingestion.ingest.return_value = None
        gs = _make_gs_injected(ingestion=ingestion)

        await gs.ingest("text")

        ingestion.ingest.assert_awaited_once_with("text", None)

    async def test_ingest_awaits_pipeline(self) -> None:
        ingestion = AsyncMock()
        ingestion.ingest.return_value = None
        gs = _make_gs_injected(ingestion=ingestion)

        await gs.ingest("text")

        assert ingestion.ingest.await_count == 1


# ---------------------------------------------------------------------------
# TestSearch
# ---------------------------------------------------------------------------


class TestSearch:
    async def test_search_delegates_to_pipeline(self) -> None:
        search = AsyncMock()
        node = Node(content="result")
        search.search.return_value = [node]
        gs = _make_gs_injected(search=search)

        result = await gs.search("query")

        assert result == [node]
        search.search.assert_awaited_once()

    async def test_search_passes_params_to_pipeline(self) -> None:
        search = AsyncMock()
        search.search.return_value = []
        gs = _make_gs_injected(search=search)

        await gs.search("query", top_n=3, depth_m=1, metadata_filter={"k": "v"})

        search.search.assert_awaited_once_with(
            query="query",
            top_n=3,
            depth_m=1,
            metadata_filter={"k": "v"},
        )

    async def test_search_returns_empty_list_when_no_results(self) -> None:
        search = AsyncMock()
        search.search.return_value = []
        gs = _make_gs_injected(search=search)

        result = await gs.search("empty query")

        assert result == []


# ---------------------------------------------------------------------------
# TestContextManager
# ---------------------------------------------------------------------------


class TestContextManager:
    async def test_aenter_returns_self(self) -> None:
        repo = AsyncMock()
        gs = _make_gs_injected(repo=repo)

        result = await gs.__aenter__()

        assert result is gs

    async def test_aexit_calls_close(self) -> None:
        repo = AsyncMock()
        gs = _make_gs_injected(repo=repo)

        await gs.__aexit__(None, None, None)

        repo.close.assert_awaited_once()

    async def test_context_manager_usage(self) -> None:
        repo = AsyncMock()
        ingestion = AsyncMock()
        ingestion.ingest.return_value = None
        gs = _make_gs_injected(repo=repo, ingestion=ingestion)

        async with gs as facade:
            assert facade is gs
            await facade.ingest("test")

        # close() was called on exit
        repo.close.assert_awaited()


# ---------------------------------------------------------------------------
# TestClose
# ---------------------------------------------------------------------------


class TestClose:
    async def test_close_awaits_repository_close(self) -> None:
        repo = AsyncMock()
        gs = _make_gs_injected(repo=repo)

        await gs.close()

        repo.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestFromOpenai
# ---------------------------------------------------------------------------


class TestFromOpenai:
    async def test_from_openai_awaits_repo_initialize(self) -> None:
        """from_openai must call await repo.initialize() before returning."""
        mock_conn = AsyncMock()
        mock_repo = AsyncMock()
        mock_provider = MagicMock()

        # Patch at the module where they're imported inside the classmethod
        with patch(
            "depth_graph_search.adapters.postgres.async_repository.AsyncPostgresGraphRepository",
            return_value=mock_repo,
        ):
            with patch(
                "depth_graph_search.adapters.openai.async_provider.AsyncOpenAIProvider",
                return_value=mock_provider,
            ):
                with patch(
                    "depth_graph_search.adapters.postgres.async_repository.AsyncPostgresGraphRepository"
                ):
                    # Patch psycopg.AsyncConnection.connect
                    with patch(
                        "psycopg.AsyncConnection.connect", new_callable=AsyncMock
                    ) as mock_connect:
                        mock_connect.return_value = mock_conn
                        # Also patch the local imports inside from_openai
                        with patch(
                            "depth_graph_search.adapters.postgres.async_repository.__init__",
                            return_value=None,
                        ):
                            pass

        # Simpler approach: use side_effect on the imported class constructor
        mock_repo2 = AsyncMock()
        mock_prov2 = MagicMock()

        with patch("psycopg.AsyncConnection.connect", new_callable=AsyncMock) as mock_conn_fn:
            mock_conn_fn.return_value = mock_conn
            with patch(
                "depth_graph_search.adapters.postgres.async_repository.AsyncPostgresGraphRepository"
            ) as MockRepo:
                MockRepo.return_value = mock_repo2
                with patch(
                    "depth_graph_search.adapters.openai.async_provider.AsyncOpenAIProvider"
                ) as MockProvider:
                    MockProvider.return_value = mock_prov2
                    gs = await AsyncGraphSearch.from_openai("postgresql://...", "sk-test")

        mock_repo2.initialize.assert_awaited_once()
        assert isinstance(gs, AsyncGraphSearch)

    async def test_from_openai_returns_async_graph_search(self) -> None:
        mock_conn = AsyncMock()
        mock_repo = AsyncMock()

        with patch("psycopg.AsyncConnection.connect", new_callable=AsyncMock) as mock_conn_fn:
            mock_conn_fn.return_value = mock_conn
            with patch(
                "depth_graph_search.adapters.postgres.async_repository.AsyncPostgresGraphRepository"
            ) as MockRepo:
                MockRepo.return_value = mock_repo
                with patch(
                    "depth_graph_search.adapters.openai.async_provider.AsyncOpenAIProvider"
                ) as MockProvider:
                    MockProvider.return_value = MagicMock()
                    result = await AsyncGraphSearch.from_openai("dsn", "key")

        assert isinstance(result, AsyncGraphSearch)


# ---------------------------------------------------------------------------
# TestFromOpenrouter
# ---------------------------------------------------------------------------


class TestFromOpenrouter:
    async def test_from_openrouter_awaits_repo_initialize(self) -> None:
        mock_conn = AsyncMock()
        mock_repo = AsyncMock()

        with patch("psycopg.AsyncConnection.connect", new_callable=AsyncMock) as mock_conn_fn:
            mock_conn_fn.return_value = mock_conn
            with patch(
                "depth_graph_search.adapters.postgres.async_repository.AsyncPostgresGraphRepository"
            ) as MockRepo:
                MockRepo.return_value = mock_repo
                with patch(
                    "depth_graph_search.adapters.openai.async_provider.AsyncOpenAIProvider"
                ) as MockEmbedding:
                    MockEmbedding.return_value = MagicMock()
                    with patch(
                        "depth_graph_search.adapters.openrouter.async_provider.AsyncOpenRouterProvider"
                    ) as MockLLM:
                        MockLLM.return_value = MagicMock()
                        gs = await AsyncGraphSearch.from_openrouter(
                            "dsn", "or-key", openai_api_key="sk-key"
                        )

        mock_repo.initialize.assert_awaited_once()
        assert isinstance(gs, AsyncGraphSearch)
