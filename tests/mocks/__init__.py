"""Test mock adapters — ABC-compliant fakes for unit testing.

All four fakes implement their port ABCs directly. None use unittest.mock as
a base class. Each supports configurable return values, error injection, and
call tracking.

Usage::

    from tests.mocks import (
        InMemoryGraphRepository,
        FakeLLMProvider,
        FakeEmbeddingProvider,
        FakeEntityResolutionStrategy,
    )
"""

from tests.mocks.embedding_provider import FakeEmbeddingProvider
from tests.mocks.entity_resolution import FakeEntityResolutionStrategy
from tests.mocks.graph_repository import InMemoryGraphRepository
from tests.mocks.llm_provider import FakeLLMProvider

__all__ = [
    "FakeEmbeddingProvider",
    "FakeEntityResolutionStrategy",
    "InMemoryGraphRepository",
    "FakeLLMProvider",
]
