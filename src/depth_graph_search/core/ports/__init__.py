"""Ports layer — abstract contracts for all adapters.

Single import point for all port ABCs (sync and async):

    from depth_graph_search.core.ports import GraphRepository, EmbeddingProvider
    from depth_graph_search.core.ports import AsyncGraphRepository, AsyncEmbeddingProvider
"""

from depth_graph_search.core.ports.async_ports import (
    AsyncEmbeddingProvider,
    AsyncEntityResolutionStrategy,
    AsyncGraphRepository,
    AsyncIngestionPipeline,
    AsyncLLMProvider,
    AsyncSearchPipeline,
)
from depth_graph_search.core.ports.embedding_provider import EmbeddingProvider
from depth_graph_search.core.ports.entity_resolution import EntityResolutionStrategy
from depth_graph_search.core.ports.graph_repository import GraphRepository
from depth_graph_search.core.ports.ingestion_pipeline import IngestionPipeline
from depth_graph_search.core.ports.llm_provider import LLMProvider
from depth_graph_search.core.ports.search_pipeline import SearchPipeline

__all__ = [
    # Sync ports
    "EmbeddingProvider",
    "EntityResolutionStrategy",
    "GraphRepository",
    "IngestionPipeline",
    "LLMProvider",
    "SearchPipeline",
    # Async ports
    "AsyncEmbeddingProvider",
    "AsyncEntityResolutionStrategy",
    "AsyncGraphRepository",
    "AsyncIngestionPipeline",
    "AsyncLLMProvider",
    "AsyncSearchPipeline",
]
