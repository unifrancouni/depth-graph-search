"""Domain exception hierarchy for depth-graph-search.

All exceptions extend ``DepthGraphSearchError``. Exception chaining is
supported both via the constructor ``cause`` parameter and via the standard
``raise X from cause`` syntax:

    # Constructor-based chaining (useful outside except blocks):
    err = StorageError("Node save failed", cause=db_error)

    # Standard PEP 3134 chaining (inside except blocks):
    try:
        db.save(node)
    except SomePsycopgError as exc:
        raise StorageError("Node save failed") from exc

This module has zero external dependencies — stdlib only.
"""

from __future__ import annotations


class DepthGraphSearchError(Exception):
    """Base exception for all depth-graph-search errors.

    All domain exceptions inherit from this class, making it easy to catch
    any library error with a single ``except DepthGraphSearchError`` clause.

    Args:
        message: Human-readable error description.
        cause: Optional underlying exception to chain as ``__cause__``.
    """

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.__cause__ = cause


class IngestionError(DepthGraphSearchError):
    """Raised when an ingestion pipeline step fails.

    Typically wraps a ``StorageError`` or ``LLMError`` as ``__cause__``.

    Example::

        try:
            llm.extract_graph(text, metadata)
        except LLMError as exc:
            raise IngestionError("Graph extraction failed", cause=exc)
    """


class ValidationError(DepthGraphSearchError):
    """Raised at the SDK boundary for invalid user input.

    No ``__cause__`` expected — validation failures are detected by the SDK,
    not surfaced from downstream adapters.

    Example::

        if not text.strip():
            raise ValidationError("content must not be empty")
    """


class StorageError(DepthGraphSearchError):
    """Raised by a ``GraphRepository`` adapter when a database operation fails.

    Always chain the underlying DB exception as ``__cause__``:

    Example::

        try:
            cursor.execute(query, params)
        except psycopg2.OperationalError as exc:
            raise StorageError("Failed to save node", cause=exc)
    """


class LLMError(DepthGraphSearchError):
    """Raised by an ``LLMProvider`` or ``EmbeddingProvider`` adapter when an API call fails.

    Always chain the underlying HTTP/API exception as ``__cause__``:

    Example::

        try:
            response = openai.embeddings.create(...)
        except openai.APIError as exc:
            raise LLMError("Request timeout after 30s", cause=exc)
    """
