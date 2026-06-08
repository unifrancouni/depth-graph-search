"""depth-graph-search — Hybrid graph + vector retrieval engine.

Public API surface. All domain entities, exceptions, and port contracts
are re-exported here for convenient single-import access:

    from depth_graph_search import Node, GraphRepository, StorageError
"""

__version__ = "0.1.0"

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
from depth_graph_search.core.ports.embedding_provider import EmbeddingProvider
from depth_graph_search.core.ports.entity_resolution import EntityResolutionStrategy
from depth_graph_search.core.ports.graph_repository import GraphRepository
from depth_graph_search.core.ports.llm_provider import LLMProvider
from depth_graph_search.core.ports.search_pipeline import SearchPipeline

__all__ = [
    "__version__",
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
    # Ports
    "EmbeddingProvider",
    "EntityResolutionStrategy",
    "GraphRepository",
    "LLMProvider",
    "SearchPipeline",
]
