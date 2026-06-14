"""AsyncOpenRouterProvider — implements AsyncLLMProvider + AsyncEmbeddingProvider via OpenAI SDK at OpenRouter.

Uses ``openai.AsyncOpenAI`` with the OpenRouter base URL.
Imports private helpers from the sync provider (same package).

Design decisions:
- Implements AsyncLLMProvider AND AsyncEmbeddingProvider (OpenRouter exposes an
  embeddings API compatible with the OpenAI SDK).
- Uses json_object mode + json.loads() + Pydantic model_validate() because
  OpenRouter does NOT support OpenAI Structured Outputs.
- Imports ``_ExtractionResult``, ``_map_extraction``, ``EXTRACTION_SYSTEM_PROMPT``
  from sync ``provider.py`` (same package).
- Same API key validation as sync counterpart (ValueError on empty key).
- Constructor has ZERO side effects.
"""

from __future__ import annotations

import json as json_mod
from typing import TYPE_CHECKING

import openai

from depth_graph_search.adapters.openrouter.provider import (
    EXTRACTION_SYSTEM_PROMPT,
    _ExtractionResult,
    _map_extraction,
)
from depth_graph_search.core.domain.entities import Embedding
from depth_graph_search.core.domain.exceptions import LLMError
from depth_graph_search.core.ports.async_ports import AsyncEmbeddingProvider, AsyncLLMProvider

if TYPE_CHECKING:
    from depth_graph_search.core.domain.entities import Edge, Metadata, Node


class AsyncOpenRouterProvider(AsyncLLMProvider, AsyncEmbeddingProvider):
    """Async adapter implementing AsyncLLMProvider + AsyncEmbeddingProvider via OpenAI SDK at OpenRouter.

    Uses OpenRouter's OpenAI-compatible API endpoint for both LLM extraction and
    embedding generation.

    Args:
        api_key: OpenRouter API key. MUST be non-empty — raises ``ValueError`` if empty.
        model: Model identifier in OpenRouter format. Defaults to ``"openai/gpt-4o"``.
        embedding_model: Embedding model identifier. Defaults to ``"openai/text-embedding-3-large"``.

    Note:
        The constructor performs ZERO I/O.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-4o",
        embedding_model: str = "openai/text-embedding-3-large",
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        self._model = model
        self._embedding_model = embedding_model

    @property
    def model(self) -> str:
        """Model identifier."""
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
            LLMError: On any OpenAI/OpenRouter API error.
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
            LLMError: On any OpenAI/OpenRouter API error.
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
        """Extract a knowledge graph from unstructured text.

        Uses json_object response mode (OpenRouter does not support Structured Outputs).
        Parses with json.loads() and validates with Pydantic model_validate().

        Args:
            text: Raw text to extract entities and relationships from.
            metadata: Key-value context attached to each extracted Node.

        Returns:
            Tuple (nodes, edges). Empty ([], []) is valid when no entities found.

        Raises:
            LLMError: On API error, non-JSON response, or schema validation failure.
        """
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                response_format={"type": "json_object"},
            )
        except openai.OpenAIError as exc:
            raise LLMError("Graph extraction failed") from exc

        raw = response.choices[0].message.content or ""
        try:
            data = json_mod.loads(raw)
        except json_mod.JSONDecodeError as exc:
            raise LLMError("Invalid JSON in extraction response") from exc

        try:
            result = _ExtractionResult.model_validate(data)
        except Exception as exc:
            raise LLMError("Extraction response validation failed") from exc

        return _map_extraction(result, metadata)

    async def complete(self, prompt: str) -> str:
        """General-purpose text completion.

        Args:
            prompt: The full prompt to send to the model.

        Returns:
            Raw string output from the model.

        Raises:
            LLMError: On any OpenAI/OpenRouter API error.
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
