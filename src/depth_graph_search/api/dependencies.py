"""FastAPI dependency providers for the depth-graph-search HTTP API.

All dependencies are injected via ``Depends()`` in route handlers.
The ``AsyncGraphSearch`` instance lives in ``app.state`` (populated by
the lifespan manager) and is retrieved here per-request.
"""

from __future__ import annotations

from fastapi import Request

from depth_graph_search.sdk.async_client import AsyncGraphSearch


async def get_graph_search(request: Request) -> AsyncGraphSearch:
    """Provide the ``AsyncGraphSearch`` instance stored in ``app.state``.

    Intended for use with FastAPI's ``Depends()``::

        @router.post("/ingest")
        async def ingest(
            body: IngestRequest,
            gs: AsyncGraphSearch = Depends(get_graph_search),
        ):
            ...

    Args:
        request: The incoming FastAPI ``Request`` (injected automatically).

    Returns:
        The ``AsyncGraphSearch`` singleton stored in ``app.state.graph_search``.
    """
    return request.app.state.graph_search  # type: ignore[no-any-return]
