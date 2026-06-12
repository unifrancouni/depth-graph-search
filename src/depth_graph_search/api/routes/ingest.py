"""POST /ingest — ingest text into the knowledge graph.

Accepts a JSON body with ``text`` (required) and optional ``metadata``.
On success returns an ``IngestResponse`` with the count of nodes and edges
persisted. Domain exceptions are handled by the registered exception handlers
in ``api/exceptions.py``.

Responses:
    200 OK:        ``{"node_count": int, "edge_count": int}``
    422 Unprocessable Entity: missing ``text`` field (FastAPI validation)
    500 Internal Server Error: ``IngestionError`` from the SDK
    502 Bad Gateway: ``LLMError`` from the SDK
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from depth_graph_search.api.dependencies import get_graph_search
from depth_graph_search.api.schemas import IngestRequest, IngestResponse
from depth_graph_search.sdk.async_client import AsyncGraphSearch

router = APIRouter()


@router.post("/ingest", response_model=IngestResponse)
async def ingest(
    body: IngestRequest,
    gs: AsyncGraphSearch = Depends(get_graph_search),
) -> IngestResponse:
    """Ingest raw text into the knowledge graph.

    Delegates to ``AsyncGraphSearch.ingest()``. Domain exceptions propagate
    to the registered exception handlers which convert them to HTTP responses.

    Args:
        body: Validated request body with ``text`` and optional ``metadata``.
        gs: ``AsyncGraphSearch`` instance injected via ``Depends()``.

    Returns:
        ``IngestResponse`` with ``node_count`` and ``edge_count`` from the pipeline.

    Raises:
        ValidationError: Re-raised as HTTP 422 by the exception handler.
        IngestionError: Re-raised as HTTP 500 by the exception handler.
        LLMError: Re-raised as HTTP 502 by the exception handler.
    """
    result = await gs.ingest(body.text, body.metadata)
    return IngestResponse(node_count=result.node_count, edge_count=result.edge_count)
