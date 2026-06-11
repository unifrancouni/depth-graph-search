"""depth-graph-search — Hybrid graph + vector retrieval engine.

Public API surface. All domain entities, exceptions, port contracts, and
pipeline implementations are re-exported here for convenient single-import
access:

    from depth_graph_search import GraphSearch, AsyncGraphSearch
    from depth_graph_search import Node, GraphRepository, StorageError
    from depth_graph_search import AsyncGraphRepository, AsyncEmbeddingProvider
    from depth_graph_search import IngestionPipeline, DefaultIngestionPipeline, IngestionResult
"""

__version__ = "0.1.0"

# Sync adapters and facades
from depth_graph_search.adapters.ingestion.pipeline import DefaultIngestionPipeline
from depth_graph_search.adapters.search.pipeline import DefaultSearchPipeline
from depth_graph_search.sdk.client import GraphSearch

# Async adapters and facades
from depth_graph_search.adapters.ingestion.async_pipeline import AsyncDefaultIngestionPipeline
from depth_graph_search.adapters.openai.async_provider import AsyncOpenAIProvider
from depth_graph_search.adapters.openrouter.async_provider import AsyncOpenRouterProvider
from depth_graph_search.adapters.postgres.async_repository import AsyncPostgresGraphRepository
from depth_graph_search.adapters.search.async_entity_resolution import (
    AsyncDefaultEntityResolutionStrategy,
)
from depth_graph_search.adapters.search.async_pipeline import AsyncDefaultSearchPipeline
from depth_graph_search.sdk.async_client import AsyncGraphSearch

# Domain entities
from depth_graph_search.core.domain.entities import (
    Edge,
    Embedding,
    IngestionResult,
    Metadata,
    Node,
    ResolvedNode,
    ScoredNode,
)

# Domain exceptions
from depth_graph_search.core.domain.exceptions import (
    DepthGraphSearchError,
    IngestionError,
    LLMError,
    StorageError,
    ValidationError,
)

# Sync ports
from depth_graph_search.core.ports.embedding_provider import EmbeddingProvider
from depth_graph_search.core.ports.entity_resolution import EntityResolutionStrategy
from depth_graph_search.core.ports.graph_repository import GraphRepository
from depth_graph_search.core.ports.ingestion_pipeline import IngestionPipeline
from depth_graph_search.core.ports.llm_provider import LLMProvider
from depth_graph_search.core.ports.search_pipeline import SearchPipeline

# Async ports
from depth_graph_search.core.ports.async_ports import (
    AsyncEmbeddingProvider,
    AsyncEntityResolutionStrategy,
    AsyncGraphRepository,
    AsyncIngestionPipeline,
    AsyncLLMProvider,
    AsyncSearchPipeline,
)

__all__ = [
    "__version__",
    # Sync SDK Facade
    "GraphSearch",
    # Async SDK Facade
    "AsyncGraphSearch",
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
    # Sync Ports
    "EmbeddingProvider",
    "EntityResolutionStrategy",
    "GraphRepository",
    "IngestionPipeline",
    "LLMProvider",
    "SearchPipeline",
    # Async Ports
    "AsyncEmbeddingProvider",
    "AsyncEntityResolutionStrategy",
    "AsyncGraphRepository",
    "AsyncIngestionPipeline",
    "AsyncLLMProvider",
    "AsyncSearchPipeline",
    # Sync Pipeline implementations
    "DefaultIngestionPipeline",
    "DefaultSearchPipeline",
    # Async Pipeline implementations
    "AsyncDefaultIngestionPipeline",
    "AsyncDefaultSearchPipeline",
    "AsyncDefaultEntityResolutionStrategy",
    # Async Adapters
    "AsyncOpenAIProvider",
    "AsyncOpenRouterProvider",
    "AsyncPostgresGraphRepository",
]
