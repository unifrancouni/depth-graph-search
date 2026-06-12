"""GET /health — liveness and database connectivity check.

The health endpoint delegates to the repository's ``health_check()`` method
via the ``AsyncGraphSearch`` facade stored in ``app.state.graph_search``.

Responses:
    200 OK:  ``{"status": "ok", "db": "connected"}``
    503 Service Unavailable: ``{"status": "degraded", "db": "error"}``
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from depth_graph_search.api.dependencies import get_graph_search
from depth_graph_search.api.schemas import HealthResponse
from depth_graph_search.sdk.async_client import AsyncGraphSearch

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(
    gs: AsyncGraphSearch = Depends(get_graph_search),
) -> HealthResponse | JSONResponse:
    """Return service health status.

    Calls ``repository.health_check()`` via the ``AsyncGraphSearch`` facade.
    Returns ``HTTP 200`` with ``{"status": "ok", "db": "connected"}`` on success,
    or ``HTTP 503`` with ``{"status": "degraded", "db": "error"}`` on any failure.

    Args:
        gs: ``AsyncGraphSearch`` instance injected via ``Depends()``.

    Returns:
        ``HealthResponse`` on success, or a ``JSONResponse`` with status 503
        on failure.
    """
    healthy = await gs.repository.health_check()
    if healthy:
        return HealthResponse(status="ok", db="connected")
    return JSONResponse(
        status_code=503,
        content={"status": "degraded", "db": "error"},
    )
