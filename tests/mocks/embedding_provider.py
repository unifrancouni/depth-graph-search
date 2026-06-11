"""FakeEmbeddingProvider — configurable fake implementing EmbeddingProvider.

Suitable for unit tests. Supports:
- Preset batch embeddings via set_embeddings([emb1, emb2, ...])
- Stub embed() — returns a default zero-vector Embedding
- Error injection via set_error(exc) — raised on next embed_batch call
- Call tracking via call_count(method_name)
"""

from __future__ import annotations

from depth_graph_search.core.domain.entities import Embedding
from depth_graph_search.core.ports.embedding_provider import EmbeddingProvider


class FakeEmbeddingProvider(EmbeddingProvider):
    """Fake embedding provider with configurable batch results.

    Set up the desired embeddings before calling the pipeline:

        fake_embedder.set_embeddings([emb1, emb2])

    The preset list is returned in order by ``embed_batch``. If more texts
    are passed than embeddings preset, the last embedding is repeated to
    fill the gap (safe default for tests that don't care about values).

    Error injection: call ``set_error(exc)`` to make the next call raise.

    Call tracking: ``embed`` and ``embed_batch`` calls are recorded in
    ``_calls[method_name]`` as ``(args, kwargs)`` tuples.
    """

    _DEFAULT_EMBEDDING = Embedding(vector=[0.0], model="fake", dimensions=1)

    def __init__(self) -> None:
        self._embeddings: list[Embedding] = []
        self._error: Exception | None = None
        self._calls: dict[str, list[tuple]] = {
            "embed": [],
            "embed_batch": [],
        }

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    def set_embeddings(self, embeddings: list[Embedding]) -> None:
        """Preset the list returned by ``embed_batch`` (in order)."""
        self._embeddings = list(embeddings)

    def set_error(self, exc: Exception | None) -> None:
        """Set an error to raise on the next call. Pass ``None`` to clear."""
        self._error = exc

    def call_count(self, method_name: str) -> int:
        """Return the number of times ``method_name`` was called."""
        return len(self._calls.get(method_name, []))

    def calls(self, method_name: str) -> list[tuple]:
        """Return the recorded call tuples for ``method_name``."""
        return self._calls.get(method_name, [])

    # ------------------------------------------------------------------
    # Private helper
    # ------------------------------------------------------------------

    def _check_error(self) -> None:
        if self._error is not None:
            err = self._error
            self._error = None
            raise err

    # ------------------------------------------------------------------
    # EmbeddingProvider interface
    # ------------------------------------------------------------------

    def embed(self, text: str) -> Embedding:
        self._calls["embed"].append(((text,), {}))
        self._check_error()
        return self._embeddings[0] if self._embeddings else self._DEFAULT_EMBEDDING

    def embed_batch(self, texts: list[str]) -> list[Embedding]:
        self._calls["embed_batch"].append(((texts,), {}))
        self._check_error()
        if not texts:
            return []
        fallback = self._embeddings[-1] if self._embeddings else self._DEFAULT_EMBEDDING
        result = []
        for i in range(len(texts)):
            if i < len(self._embeddings):
                result.append(self._embeddings[i])
            else:
                result.append(fallback)
        return result
