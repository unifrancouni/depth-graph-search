"""Request and response DTOs for the depth-graph-search HTTP API.

All schemas are Pydantic ``BaseModel`` subclasses. They deliberately do NOT
re-use domain entities (e.g. ``Node``, ``ScoredNode``) to ensure the API
contract can evolve independently and to prevent leaking internal fields
such as ``embedding`` vectors to API consumers.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    """Request body for ``POST /ingest``.

    Attributes:
        text: The raw text to extract entities from and persist to the graph.
        metadata: Optional free-form key-value context attached to every node.
    """

    text: str
    metadata: dict[str, Any] | None = None


class IngestResponse(BaseModel):
    """Response body for ``POST /ingest`` on success.

    Attributes:
        node_count: Number of new nodes persisted to the graph store.
        edge_count: Number of edges persisted to the graph store.
    """

    node_count: int
    edge_count: int


class SearchRequest(BaseModel):
    """Request body for ``POST /search``.

    Attributes:
        query: Natural language query string.
        top_n: Maximum number of results to return. Must be >= 1. Defaults to 5.
        depth_m: BFS hop depth from entry nodes. Must be >= 0. Defaults to 2.
        metadata_filter: Optional key-value filter applied before hybrid search.
    """

    query: str
    top_n: int = Field(default=5, ge=1)
    depth_m: int = Field(default=2, ge=0)
    metadata_filter: dict[str, Any] | None = None


class SearchResultItem(BaseModel):
    """A single ranked result in a search response.

    Note: The ``embedding`` field from the domain ``Node`` is intentionally
    excluded here to prevent leaking large vector data to API consumers.

    Attributes:
        id: UUID4 string identifier of the node.
        content: Text content of the node.
        metadata: Free-form key-value context attached to the node.
        score: Hybrid similarity score in [0, 1]. Higher is more relevant.
        distance: BFS hops from the nearest entry node. 0 means the node was
            a direct hybrid-search hit.
    """

    id: str
    content: str
    metadata: dict[str, Any]
    score: float
    distance: int


class SearchResponse(BaseModel):
    """Response body for ``POST /search`` on success.

    Attributes:
        results: Ranked list of matching nodes. May be empty.
    """

    results: list[SearchResultItem]


class HealthResponse(BaseModel):
    """Response body for ``GET /health``.

    Attributes:
        status: Overall service status. ``"ok"`` when healthy.
        db: Database connectivity status. ``"connected"`` when the DB probe passes.
    """

    status: Literal["ok", "degraded"]
    db: Literal["connected", "error"]
