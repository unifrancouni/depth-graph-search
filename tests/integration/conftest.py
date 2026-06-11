"""Integration test fixtures for the PostgreSQL adapter.

Uses testcontainers-python to spin up a real PostgreSQL 17 + AGE + pgvector
container built from ``Dockerfile.dev`` at the repo root.

Fixtures:
    pg_container (session-scoped): Starts the container once per test session.
    connection (function-scoped): Fresh psycopg3 sync connection per test.
    repository (function-scoped): Initialized ``PostgresGraphRepository`` per test.
    async_pg_connection (function-scoped): Fresh psycopg3 async connection per test.
    async_repository (function-scoped): Initialized ``AsyncPostgresGraphRepository`` per test.
"""

from __future__ import annotations

import psycopg
import pytest
import pytest_asyncio
from testcontainers.core.image import DockerImage
from testcontainers.postgres import PostgresContainer

from depth_graph_search.adapters.postgres.async_repository import AsyncPostgresGraphRepository
from depth_graph_search.adapters.postgres.repository import PostgresGraphRepository

# ---------------------------------------------------------------------------
# Session-scoped container (expensive — start once, reuse across tests)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def pg_container():  # type: ignore[return]
    """Build and start a custom AGE+pgvector container from Dockerfile.dev.

    The container is shared across the entire test session for performance.
    Individual tests receive a fresh repository + connection via the
    ``repository`` fixture.
    """
    image = DockerImage(path=".", dockerfile="Dockerfile.dev")
    with PostgresContainer(
        image=str(image.build()),
        username="depth",
        password="depth",
        dbname="depth_graph",
    ) as pg:
        yield pg


# ---------------------------------------------------------------------------
# Function-scoped psycopg3 sync connection
# ---------------------------------------------------------------------------


@pytest.fixture
def connection(pg_container):  # type: ignore[return]
    """Open a fresh psycopg3 sync connection to the test database."""
    url = pg_container.get_connection_url(driver="psycopg")
    conn = psycopg.connect(url, autocommit=False)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Function-scoped sync repository (initialize() called each time for isolation)
# ---------------------------------------------------------------------------


@pytest.fixture
def repository(connection):  # type: ignore[return]
    """Initialized ``PostgresGraphRepository`` per test.

    Calls ``initialize()`` on each test so every test starts with the
    schema in place. The connection (and therefore transaction) is
    closed after each test, providing isolation.
    """
    repo = PostgresGraphRepository(connection=connection)
    repo.initialize()
    yield repo
    repo.close()


# ---------------------------------------------------------------------------
# Function-scoped psycopg3 async connection
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def async_pg_connection(pg_container):  # type: ignore[return]
    """Open a fresh psycopg3 async connection to the test database."""
    url = pg_container.get_connection_url(driver="psycopg")
    conn = await psycopg.AsyncConnection.connect(url, autocommit=False)
    yield conn
    await conn.close()


# ---------------------------------------------------------------------------
# Function-scoped async repository
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def async_repository(async_pg_connection):  # type: ignore[return]
    """Initialized ``AsyncPostgresGraphRepository`` per test.

    Calls ``await initialize()`` on each test so every test starts with the
    schema in place. The connection is closed after each test.
    """
    repo = AsyncPostgresGraphRepository(connection=async_pg_connection)
    await repo.initialize()
    yield repo
    await repo.close()
