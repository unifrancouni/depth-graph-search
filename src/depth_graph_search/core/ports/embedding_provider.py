"""EmbeddingProvider port — abstract contract for embedding model adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from depth_graph_search.core.domain.entities import Embedding


class EmbeddingProvider(ABC):
    """Abstract contract for all embedding model adapters.

    Adapters (e.g. OpenAI ``text-embedding-3-small``) MUST inherit from this
    class and implement both abstract methods. Instantiating ``EmbeddingProvider``
    directly raises ``TypeError``.

    Both methods raise ``LLMError`` on provider failure.
    """

    @abstractmethod
    def embed(self, text: str) -> Embedding:
        """Generate a single embedding for the given text.

        Args:
            text: The input text to embed. MUST be non-empty.

        Returns:
            An ``Embedding`` instance with ``vector``, ``model``, and ``dimensions`` set.

        Raises:
            LLMError: If the embedding provider call fails (network error, rate limit,
                invalid response, etc.). The underlying provider exception MUST be
                chained as ``__cause__``.
        """

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[Embedding]:
        """Generate embeddings for a batch of texts in a single provider call.

        Args:
            texts: List of input texts to embed. Order is preserved in the result.

        Returns:
            A list of ``Embedding`` instances in the same order as ``texts``.
            ``len(result) == len(texts)`` MUST always hold.

        Raises:
            LLMError: If the embedding provider call fails. The underlying provider
                exception MUST be chained as ``__cause__``.
        """
