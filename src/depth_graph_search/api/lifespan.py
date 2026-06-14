"""FastAPI lifespan context manager for AsyncGraphSearch lifecycle management.

The lifespan manager is responsible for:
1. Reading ``Settings`` from ``app.state.settings`` (set by ``create_app``).
2. Building an ``AsyncGraphSearch`` instance via ``from_openai`` or ``from_openrouter``
   depending on ``settings.llm_provider``.
3. Storing the instance in ``app.state`` for routes.
4. Calling ``await gs.close()`` on shutdown to release the connection.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from depth_graph_search.sdk.async_client import AsyncGraphSearch


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage ``AsyncGraphSearch`` lifecycle tied to the FastAPI application.

    Reads ``app.state.settings`` (a ``Settings`` instance populated by
    ``create_app``). On startup builds and stores the SDK instance; on
    shutdown calls ``await gs.close()``.

    Yields:
        None — control is yielded to the application while it runs.
    """
    settings = app.state.settings

    if settings.llm_provider == "openai":
        gs = await AsyncGraphSearch.from_openai(
            dsn=settings.database_url,
            api_key=settings.openai_api_key,
            model=settings.llm_model,
            embedding_model=settings.embedding_model,
            graph_name=settings.graph_name,
            embedding_dimensions=settings.embedding_dimensions,
        )
    else:
        # validate_api_keys guarantees openrouter_api_key is not None
        # when llm_provider == "openrouter"
        assert settings.openrouter_api_key is not None
        # Pass openai_api_key only when present — factory decides embedding source:
        # non-empty → mixed mode (OpenAI embeddings); empty → OpenRouter-only mode
        gs = await AsyncGraphSearch.from_openrouter(
            dsn=settings.database_url,
            api_key=settings.openrouter_api_key,
            openai_api_key=settings.openai_api_key or None,
            openrouter_model=settings.llm_model,
            embedding_model=settings.embedding_model,
            graph_name=settings.graph_name,
            embedding_dimensions=settings.embedding_dimensions,
        )

    app.state.graph_search = gs

    try:
        yield
    finally:
        await gs.close()
