"""Integration tests for the HTTP API — full ASGI stack with mocked SDK.

Uses ``httpx.AsyncClient`` + ``ASGITransport`` to test routes through the
real FastAPI application. The ``AsyncGraphSearch`` instance is mocked at
``app.state.graph_search`` so no database or LLM is needed.

Tested endpoints:
    GET  /health  — 200 ok / 503 degraded
    POST /ingest  — 200 success / 422 missing text
    POST /search  — 200 results without embedding / 422 invalid top_n
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import httpx
import pytest
from fastapi import FastAPI

from depth_graph_search.api import create_app
from depth_graph_search.api.config import Settings
from depth_graph_search.core.domain.entities import (
    Embedding,
    IngestionResult,
    Node,
    ScoredNode,
)
from depth_graph_search.sdk.async_client import AsyncGraphSearch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_test_settings() -> Settings:
    """Build a minimal ``Settings`` instance for testing (no env vars needed)."""
    return Settings(
        database_url="postgresql://test:test@localhost/test",
        openai_api_key="sk-test-key-for-testing",
    )


def _make_mock_gs() -> AsyncMock:
    """Build an ``AsyncMock`` that satisfies ``AsyncGraphSearch`` for happy-path tests."""
    gs = AsyncMock(spec=AsyncGraphSearch)
    gs.ingest.return_value = IngestionResult(node_count=2, edge_count=1)

    node = Node(
        id="node-1",
        content="Alice works at Acme",
        embedding=Embedding(
            vector=[0.1] * 3072,
            model="text-embedding-3-large",
            dimensions=3072,
        ),
        metadata={"source": "test"},
    )
    gs.search.return_value = [
        ScoredNode(node=node, score=0.95, distance=0),
    ]

    # Mock the repository property with a healthy health_check
    mock_repo = AsyncMock()
    mock_repo.health_check.return_value = True
    type(gs).repository = PropertyMock(return_value=mock_repo)

    return gs


@pytest.fixture()
def test_app() -> FastAPI:
    """Create a FastAPI app with a mocked ``AsyncGraphSearch`` in app.state.

    Bypasses the real lifespan (no DB/LLM connection needed).
    """
    settings = _make_test_settings()
    app = create_app(settings=settings)

    # Override lifespan by injecting mock directly into app.state
    # The real lifespan won't run because we use the app directly via ASGITransport
    app.state.graph_search = _make_mock_gs()

    return app


@pytest.fixture()
async def client(test_app: FastAPI) -> httpx.AsyncClient:
    """Async HTTP client wired to the test app via ASGI transport."""
    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """Integration tests for GET /health."""

    async def test_health_returns_200_when_db_healthy(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["db"] == "connected"

    async def test_health_returns_503_when_db_unhealthy(
        self, test_app: FastAPI
    ) -> None:
        # Override the mock repository to return unhealthy
        mock_repo = AsyncMock()
        mock_repo.health_check.return_value = False
        type(test_app.state.graph_search).repository = PropertyMock(
            return_value=mock_repo
        )

        transport = httpx.ASGITransport(app=test_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            response = await c.get("/health")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "degraded"
        assert body["db"] == "error"


# ---------------------------------------------------------------------------
# POST /ingest
# ---------------------------------------------------------------------------


class TestIngestEndpoint:
    """Integration tests for POST /ingest."""

    async def test_ingest_valid_payload_returns_200(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post(
            "/ingest",
            json={"text": "Alice works at Acme Corp."},
        )

        assert response.status_code == 200
        body = response.json()
        assert "node_count" in body
        assert "edge_count" in body
        assert body["node_count"] == 2
        assert body["edge_count"] == 1

    async def test_ingest_with_metadata_returns_200(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post(
            "/ingest",
            json={"text": "Bob is an engineer.", "metadata": {"source": "resume"}},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["node_count"] == 2

    async def test_ingest_empty_text_returns_422(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post("/ingest", json={})

        assert response.status_code == 422

    async def test_ingest_no_body_returns_422(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post(
            "/ingest",
            content=b"",
            headers={"content-type": "application/json"},
        )

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /search
# ---------------------------------------------------------------------------


class TestSearchEndpoint:
    """Integration tests for POST /search."""

    async def test_search_valid_query_returns_200(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post(
            "/search",
            json={"query": "who works at Acme?"},
        )

        assert response.status_code == 200
        body = response.json()
        assert "results" in body
        assert len(body["results"]) == 1

        item = body["results"][0]
        assert item["id"] == "node-1"
        assert item["content"] == "Alice works at Acme"
        assert item["score"] == 0.95
        assert item["distance"] == 0
        assert item["metadata"] == {"source": "test"}

    async def test_search_results_exclude_embedding(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post(
            "/search",
            json={"query": "test query"},
        )

        assert response.status_code == 200
        body = response.json()
        for item in body["results"]:
            assert "embedding" not in item

    async def test_search_top_n_zero_returns_422(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post(
            "/search",
            json={"query": "test", "top_n": 0},
        )

        assert response.status_code == 422

    async def test_search_missing_query_returns_422(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post("/search", json={})

        assert response.status_code == 422

    async def test_search_negative_top_n_returns_422(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post(
            "/search",
            json={"query": "test", "top_n": -1},
        )

        assert response.status_code == 422
