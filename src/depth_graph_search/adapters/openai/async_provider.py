"""AsyncOpenAIProvider — implements AsyncEmbeddingProvider + AsyncLLMProvider.

Uses ``openai.AsyncOpenAI`` internally. Imports private helpers from the sync
provider (same package — same-package import is acceptable per design decision).

Design decisions:
- Single class implements both async ports.
- Imports ``_ExtractionResult``, ``_map_extraction``, ``EXTRACTION_SYSTEM_PROMPT``
  from sync ``provider.py`` (same package, not cross-adapter).
- Same API key + model validation as sync counterpart (ValueError on empty key).
- All openai.OpenAIError subclasses propagate unchanged to caller.
- Constructor has ZERO side effects: stores config and creates client object only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import openai

from depth_graph_search.adapters.openai.provider import (
    EXTRACTION_SYSTEM_PROMPT,
    _ExtractionResult,
    _map_extraction,
)
from depth_graph_search.core.domain.entities import Embedding
from depth_graph_search.core.domain.exceptions import LLMError
from depth_graph_search.core.ports.async_ports import AsyncEmbeddingProvider, AsyncLLMProvider

if TYPE_CHECKING:
    from depth_graph_search.core.domain.entities import Edge, Metadata, Node


class AsyncOpenAIProvider(AsyncEmbeddingProvider, AsyncLLMProvider):
    """Async adapter implementing AsyncEmbeddingProvider + AsyncLLMProvider via OpenAI SDK.

    Args:
        api_key: OpenAI API key. MUST be non-empty — raises ``ValueError`` if empty.
        model: Chat completion model. Defaults to ``"gpt-4o"``.
        embedding_model: Embedding model. Defaults to ``"text-embedding-3-large"``.

    Note:
        The constructor performs ZERO I/O. It stores config and creates the async
        client object (which is also side-effect-free until an API call is made).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        embedding_model: str = "text-embedding-3-large",
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model
        self._embedding_model = embedding_model

    @property
    def model(self) -> str:
        """Chat completion model identifier."""
        return self._model

    @property
    def embedding_model(self) -> str:
        """Embedding model identifier."""
        return self._embedding_model

    # ------------------------------------------------------------------
    # AsyncEmbeddingProvider
    # ------------------------------------------------------------------

    async def embed(self, text: str) -> Embedding:
        """Generate a single embedding for the given text.

        Args:
            text: The input text to embed.

        Returns:
            An ``Embedding`` with vector, model, and dimensions set.

        Raises:
            LLMError: On any OpenAI API error.
        """
        try:
            response = await self._client.embeddings.create(
                model=self._embedding_model,
                input=[text],
            )
            data = response.data[0]
            return Embedding(
                vector=data.embedding,
                model=self._embedding_model,
                dimensions=len(data.embedding),
            )
        except openai.OpenAIError as exc:
            raise LLMError("Embedding failed") from exc

    async def embed_batch(self, texts: list[str]) -> list[Embedding]:
        """Generate embeddings for a batch of texts in a single API call.

        Order is preserved: result[i] corresponds to texts[i].

        Args:
            texts: List of input texts to embed.

        Returns:
            List of ``Embedding`` instances in the same order as texts.

        Raises:
            LLMError: On any OpenAI API error.
        """
        try:
            response = await self._client.embeddings.create(
                model=self._embedding_model,
                input=texts,
            )
            # API returns data ordered by index — sort to be safe
            sorted_data = sorted(response.data, key=lambda d: d.index)
            return [
                Embedding(
                    vector=d.embedding,
                    model=self._embedding_model,
                    dimensions=len(d.embedding),
                )
                for d in sorted_data
            ]
        except openai.OpenAIError as exc:
            raise LLMError("Batch embedding failed") from exc

    # ------------------------------------------------------------------
    # AsyncLLMProvider
    # ------------------------------------------------------------------

    async def extract_graph(
        self,
        text: str,
        metadata: Metadata,
    ) -> tuple[list[Node], list[Edge]]:
        """Extract a knowledge graph from unstructured text using Structured Outputs.

        Args:
            text: Raw text to extract entities and relationships from.
            metadata: Key-value context attached to each extracted Node.

        Returns:
            Tuple (nodes, edges). Empty ([], []) is valid when no entities found.

        Raises:
            LLMError: On API error, model refusal, or unparseable response.
        """
        try:
            completion = await self._client.chat.completions.parse(
                model=self._model,
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                response_format=_ExtractionResult,
            )
        except openai.OpenAIError as exc:
            raise LLMError("Graph extraction failed") from exc

        message = completion.choices[0].message
        if message.refusal is not None:
            raise LLMError(f"Model refused extraction: {message.refusal}")
        if message.parsed is None:
            raise LLMError("Model returned unparseable response")

        return _map_extraction(message.parsed, metadata)

    async def complete(self, prompt: str) -> str:
        """General-purpose text completion.

        Args:
            prompt: The full prompt to send to the model.

        Returns:
            Raw string output from the model.

        Raises:
            LLMError: On any OpenAI API error.
        """
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.choices[0].message.content
            return content or ""
        except openai.OpenAIError as exc:
            raise LLMError("Completion failed") from exc
