"""AsyncOpenRouterProvider — implements AsyncLLMProvider via OpenAI SDK at OpenRouter.

Uses ``openai.AsyncOpenAI`` with the OpenRouter base URL.
Imports private helpers from the sync provider (same package).

Design decisions:
- Implements AsyncLLMProvider only (no embedding — OpenRouter has no embeddings API).
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
from depth_graph_search.core.domain.exceptions import LLMError
from depth_graph_search.core.ports.async_ports import AsyncLLMProvider

if TYPE_CHECKING:
    from depth_graph_search.core.domain.entities import Edge, Metadata, Node


class AsyncOpenRouterProvider(AsyncLLMProvider):
    """Async adapter implementing AsyncLLMProvider via the OpenAI SDK at OpenRouter.

    Uses OpenRouter's OpenAI-compatible API endpoint. Does NOT implement
    AsyncEmbeddingProvider — OpenRouter does not expose an embeddings API.

    Args:
        api_key: OpenRouter API key. MUST be non-empty — raises ``ValueError`` if empty.
        model: Model identifier in OpenRouter format. Defaults to ``"openai/gpt-4o"``.

    Note:
        The constructor performs ZERO I/O.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-4o",
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        self._client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        self._model = model

    @property
    def model(self) -> str:
        """Model identifier."""
        return self._model

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
