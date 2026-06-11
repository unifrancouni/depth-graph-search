"""depth-graph-search — Hybrid graph + vector retrieval engine.

Public API surface. All domain entities, exceptions, port contracts, and
pipeline implementations are re-exported here for convenient single-import
access:

    from depth_graph_search import GraphSearch
    from depth_graph_search import Node, GraphRepository, StorageError
    from depth_graph_search import IngestionPipeline, DefaultIngestionPipeline, IngestionResult
"""

__version__ = "0.1.0"

from depth_graph_search.adapters.ingestion.pipeline import DefaultIngestionPipeline
from depth_graph_search.adapters.search.pipeline import DefaultSearchPipeline
from depth_graph_search.sdk.client import GraphSearch
from depth_graph_search.core.domain.entities import (
    Edge,
    Embedding,
    IngestionResult,
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
from depth_graph_search.core.ports.ingestion_pipeline import IngestionPipeline
from depth_graph_search.core.ports.llm_provider import LLMProvider
from depth_graph_search.core.ports.search_pipeline import SearchPipeline

__all__ = [
    "__version__",
    # SDK Facade
    "GraphSearch",
    # Entities
    "Edge",
    "Embedding",
    "IngestionResult",
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
    "IngestionPipeline",
    "LLMProvider",
    "SearchPipeline",
    # Pipeline implementations
    "DefaultIngestionPipeline",
    "DefaultSearchPipeline",
]
