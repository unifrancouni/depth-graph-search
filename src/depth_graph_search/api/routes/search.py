"""POST /search — hybrid graph search over the knowledge graph.

Accepts a JSON body with ``query`` (required) and optional ``top_n``,
``depth_m``, and ``metadata_filter``. Returns a ranked list of result items
with ``id``, ``content``, ``metadata``, ``score``, and ``distance``. The
``embedding`` field from domain ``Node`` is intentionally excluded.

Responses:
    200 OK:        ``{"results": [...]}``
    422 Unprocessable Entity: missing ``query`` or invalid ``top_n`` (FastAPI validation)
    503 Service Unavailable: ``StorageError`` from the SDK
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from depth_graph_search.api.dependencies import get_graph_search
from depth_graph_search.api.schemas import SearchRequest, SearchResponse, SearchResultItem
from depth_graph_search.sdk.async_client import AsyncGraphSearch

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    gs: AsyncGraphSearch = Depends(get_graph_search),
) -> SearchResponse:
    """Execute a hybrid graph search and return ranked results.

    Delegates to ``AsyncGraphSearch.search()``. Maps each ``ScoredNode``
    to a ``SearchResultItem``, omitting the ``embedding`` field.

    Args:
        body: Validated request body with ``query``, ``top_n``, ``depth_m``,
            and optional ``metadata_filter``.
        gs: ``AsyncGraphSearch`` instance injected via ``Depends()``.

    Returns:
        ``SearchResponse`` containing a ranked ``results`` list.

    Raises:
        StorageError: Re-raised as HTTP 503 by the exception handler.
        LLMError: Re-raised as HTTP 502 by the exception handler.
    """
    scored = await gs.search(
        body.query,
        body.top_n,
        body.depth_m,
        body.metadata_filter,
    )
    return SearchResponse(
        results=[
            SearchResultItem(
                id=sn.node.id,
                content=sn.node.content,
                metadata=sn.node.metadata,
                score=sn.score,
                distance=sn.distance,
            )
            for sn in scored
        ]
    )
