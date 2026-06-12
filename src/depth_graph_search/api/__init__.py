"""depth-graph-search HTTP API package.

Entry point for the FastAPI application. Import ``create_app`` to get the
application factory, which is suitable for use with uvicorn's ``--factory`` flag::

    uvicorn depth_graph_search.api:create_app --factory --host 0.0.0.0 --port 8000

Usage in tests::

    from depth_graph_search.api import create_app
    from depth_graph_search.api.config import Settings

    app = create_app(settings=test_settings)
"""

from __future__ import annotations

from fastapi import FastAPI

from depth_graph_search.api.config import Settings
from depth_graph_search.api.exceptions import register_exception_handlers
from depth_graph_search.api.lifespan import lifespan
from depth_graph_search.api.routes.health import router as health_router
from depth_graph_search.api.routes.ingest import router as ingest_router
from depth_graph_search.api.routes.search import router as search_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Instantiates ``FastAPI`` with the lifespan manager, registers all
    exception handlers, and includes the ``/ingest``, ``/search``, and
    ``/health`` routers.

    Args:
        settings: Optional pre-built ``Settings`` instance. When ``None``,
            ``Settings()`` is constructed from the environment (or ``.env``).
            Pass a custom instance in tests to avoid reading real env vars.

    Returns:
        A fully configured ``FastAPI`` application ready to serve requests.
    """
    if settings is None:
        settings = Settings()

    app = FastAPI(
        title="depth-graph-search",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Store settings on app.state before lifespan runs so the lifespan
    # manager can read them during startup.
    app.state.settings = settings

    register_exception_handlers(app)

    app.include_router(ingest_router)
    app.include_router(search_router)
    app.include_router(health_router)

    return app
