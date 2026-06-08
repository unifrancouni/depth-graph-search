"""Domain layer — entities and exceptions.

Single import point for all domain types:

    from depth_graph_search.core.domain import Node, Edge, StorageError
"""

from depth_graph_search.core.domain.entities import (
    Edge,
    Embedding,
    Metadata,
    Node,
    ResolvedNode,
    ScoredNode,
)
from depth_graph_search.core.domain.exceptions import (
    DepthGraphSearchError,
    IngestionError,
    LLMError,
    StorageError,
    ValidationError,
)

__all__ = [
    # Entities
    "Edge",
    "Embedding",
    "Metadata",
    "Node",
    "ResolvedNode",
    "ScoredNode",
    # Exceptions
    "DepthGraphSearchError",
    "IngestionError",
    "LLMError",
    "StorageError",
    "ValidationError",
]
