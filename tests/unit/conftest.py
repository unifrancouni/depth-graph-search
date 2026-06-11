"""Shared pytest fixtures and entity factories for unit tests.

Fixtures:
- fake_llm: FakeLLMProvider (reset on each test)
- fake_embedder: FakeEmbeddingProvider (reset on each test)
- fake_repo: InMemoryGraphRepository (reset on each test)
- fake_resolver: FakeEntityResolutionStrategy (reset on each test, all_new mode)
- pipeline: DefaultIngestionPipeline wired with all 4 fakes

Entity factories:
- make_node(content, node_id=..., embedding=None, metadata={}) → Node
- make_edge(source_id, target_id, relationship="RELATES_TO") → Edge
- make_embedding() → Embedding (minimal test vector)
"""

from __future__ import annotations

import pytest

from depth_graph_search.adapters.ingestion.pipeline import DefaultIngestionPipeline
from depth_graph_search.core.domain.entities import Edge, Embedding, Node
from tests.mocks import (
    FakeEmbeddingProvider,
    FakeEntityResolutionStrategy,
    FakeLLMProvider,
    InMemoryGraphRepository,
)


# ---------------------------------------------------------------------------
# Entity factories
# ---------------------------------------------------------------------------


def make_node(
    content: str = "test content",
    node_id: str | None = None,
    embedding: Embedding | None = None,
    metadata: dict | None = None,
) -> Node:
    """Create a Node with sensible defaults for tests."""
    kwargs: dict = {"content": content}
    if node_id is not None:
        kwargs["id"] = node_id
    if embedding is not None:
        kwargs["embedding"] = embedding
    if metadata is not None:
        kwargs["metadata"] = metadata
    return Node(**kwargs)


def make_edge(
    source_id: str,
    target_id: str,
    relationship: str = "RELATES_TO",
) -> Edge:
    """Create an Edge between two node IDs."""
    return Edge(source_id=source_id, target_id=target_id, relationship=relationship)


def make_embedding(
    vector: list[float] | None = None,
    model: str = "fake",
    dimensions: int = 1,
) -> Embedding:
    """Create a minimal Embedding for tests."""
    return Embedding(
        vector=vector if vector is not None else [0.1],
        model=model,
        dimensions=dimensions,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_llm() -> FakeLLMProvider:
    """Fresh FakeLLMProvider — no preset extraction, no errors."""
    return FakeLLMProvider()


@pytest.fixture
def fake_embedder() -> FakeEmbeddingProvider:
    """Fresh FakeEmbeddingProvider — returns default zero-vector embeddings."""
    return FakeEmbeddingProvider()


@pytest.fixture
def fake_repo() -> InMemoryGraphRepository:
    """Fresh InMemoryGraphRepository — empty storage, no preset search results."""
    return InMemoryGraphRepository()


@pytest.fixture
def fake_resolver() -> FakeEntityResolutionStrategy:
    """Fresh FakeEntityResolutionStrategy — all_new mode."""
    return FakeEntityResolutionStrategy()


@pytest.fixture
def pipeline(
    fake_llm: FakeLLMProvider,
    fake_embedder: FakeEmbeddingProvider,
    fake_repo: InMemoryGraphRepository,
    fake_resolver: FakeEntityResolutionStrategy,
) -> DefaultIngestionPipeline:
    """DefaultIngestionPipeline wired with all 4 fakes."""
    return DefaultIngestionPipeline(
        llm_provider=fake_llm,
        embedding_provider=fake_embedder,
        graph_repository=fake_repo,
        entity_resolution=fake_resolver,
    )
