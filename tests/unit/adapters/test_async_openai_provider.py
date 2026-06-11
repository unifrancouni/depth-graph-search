"""Unit tests for AsyncOpenAIProvider.

All tests mock ``openai.AsyncOpenAI`` — no HTTP calls made.
Covers: constructor, embed, embed_batch, extract_graph, complete.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest

from depth_graph_search.adapters.openai.async_provider import AsyncOpenAIProvider
from depth_graph_search.core.domain.entities import Embedding
from depth_graph_search.core.domain.exceptions import LLMError
from depth_graph_search.core.ports.async_ports import AsyncEmbeddingProvider, AsyncLLMProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider(
    api_key: str = "sk-test",
    model: str = "gpt-4o",
    embedding_model: str = "text-embedding-3-large",
) -> AsyncOpenAIProvider:
    with patch("openai.AsyncOpenAI"):
        return AsyncOpenAIProvider(api_key=api_key, model=model, embedding_model=embedding_model)


def _make_embedding_data(index: int, vector: list[float]) -> MagicMock:
    data = MagicMock()
    data.index = index
    data.embedding = vector
    return data


def _make_embeddings_response(data_items: list[MagicMock]) -> MagicMock:
    response = MagicMock()
    response.data = data_items
    return response


def _make_parse_response(
    parsed: object | None = None,
    refusal: str | None = None,
) -> MagicMock:
    message = MagicMock()
    message.parsed = parsed
    message.refusal = refusal
    choice = MagicMock()
    choice.message = message
    completion = MagicMock()
    completion.choices = [choice]
    return completion


def _make_create_response(content: str) -> MagicMock:
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


# ---------------------------------------------------------------------------
# TestConstructor
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_default_models_stored(self) -> None:
        provider = _make_provider()
        assert provider.model == "gpt-4o"
        assert provider.embedding_model == "text-embedding-3-large"

    def test_custom_models_stored(self) -> None:
        provider = _make_provider(model="gpt-4o-mini", embedding_model="text-embedding-3-small")
        assert provider.model == "gpt-4o-mini"
        assert provider.embedding_model == "text-embedding-3-small"

    def test_isinstance_async_embedding_provider(self) -> None:
        provider = _make_provider()
        assert isinstance(provider, AsyncEmbeddingProvider)

    def test_isinstance_async_llm_provider(self) -> None:
        provider = _make_provider()
        assert isinstance(provider, AsyncLLMProvider)

    def test_empty_api_key_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            AsyncOpenAIProvider(api_key="")

    def test_no_http_on_construction(self) -> None:
        with patch("openai.AsyncOpenAI") as mock_async_openai_cls:
            mock_client = AsyncMock()
            mock_async_openai_cls.return_value = mock_client
            AsyncOpenAIProvider(api_key="sk-test")
            mock_client.embeddings.create.assert_not_called()
            mock_client.chat.completions.create.assert_not_called()
            mock_client.chat.completions.parse.assert_not_called()


# ---------------------------------------------------------------------------
# TestEmbed
# ---------------------------------------------------------------------------


class TestEmbed:
    async def test_happy_path_returns_embedding(self) -> None:
        provider = _make_provider()
        vector = [0.1, 0.2, 0.3]
        provider._client.embeddings.create = AsyncMock(
            return_value=_make_embeddings_response([_make_embedding_data(0, vector)])
        )

        result = await provider.embed("The speed of light")

        assert isinstance(result, Embedding)
        assert result.vector == vector
        assert result.model == "text-embedding-3-large"
        assert result.dimensions == 3

    async def test_dimensions_equals_vector_length(self) -> None:
        provider = _make_provider()
        vector = [0.0] * 3072
        provider._client.embeddings.create = AsyncMock(
            return_value=_make_embeddings_response([_make_embedding_data(0, vector)])
        )

        result = await provider.embed("test")

        assert result.dimensions == 3072

    async def test_api_error_raises_llm_error(self) -> None:
        provider = _make_provider()
        original = openai.APIConnectionError.__new__(openai.APIConnectionError)
        provider._client.embeddings.create = AsyncMock(side_effect=original)

        with pytest.raises(LLMError) as exc_info:
            await provider.embed("text")

        assert exc_info.value.__cause__ is original

    async def test_embed_uses_embedding_model(self) -> None:
        provider = _make_provider(embedding_model="text-embedding-3-small")
        vector = [0.5, 0.6]
        provider._client.embeddings.create = AsyncMock(
            return_value=_make_embeddings_response([_make_embedding_data(0, vector)])
        )

        result = await provider.embed("hello")

        assert result.model == "text-embedding-3-small"
        provider._client.embeddings.create.assert_awaited_once_with(
            model="text-embedding-3-small",
            input=["hello"],
        )


# ---------------------------------------------------------------------------
# TestEmbedBatch
# ---------------------------------------------------------------------------


class TestEmbedBatch:
    async def test_happy_path_batch_of_three(self) -> None:
        provider = _make_provider()
        provider._client.embeddings.create = AsyncMock(
            return_value=_make_embeddings_response([
                _make_embedding_data(0, [0.1]),
                _make_embedding_data(1, [0.2]),
                _make_embedding_data(2, [0.3]),
            ])
        )

        results = await provider.embed_batch(["A", "B", "C"])

        assert len(results) == 3
        assert results[0].vector == [0.1]
        assert results[1].vector == [0.2]
        assert results[2].vector == [0.3]

    async def test_shuffled_index_order_preserved(self) -> None:
        provider = _make_provider()
        provider._client.embeddings.create = AsyncMock(
            return_value=_make_embeddings_response([
                _make_embedding_data(2, [0.3]),
                _make_embedding_data(0, [0.1]),
                _make_embedding_data(1, [0.2]),
            ])
        )

        results = await provider.embed_batch(["A", "B", "C"])

        assert results[0].vector == [0.1]
        assert results[1].vector == [0.2]
        assert results[2].vector == [0.3]

    async def test_api_error_raises_llm_error(self) -> None:
        provider = _make_provider()
        original = openai.RateLimitError(
            message="rate limit", response=MagicMock(), body=None
        )
        provider._client.embeddings.create = AsyncMock(side_effect=original)

        with pytest.raises(LLMError) as exc_info:
            await provider.embed_batch(["a", "b"])

        assert exc_info.value.__cause__ is original


# ---------------------------------------------------------------------------
# TestExtractGraph
# ---------------------------------------------------------------------------


class TestExtractGraph:
    def _make_extraction_result(
        self,
        entities: list[dict],
        relationships: list[dict],
    ) -> object:
        from depth_graph_search.adapters.openai.provider import _ExtractionResult  # type: ignore

        return _ExtractionResult(
            entities=[
                {"name": e["name"], "type": e["type"], "properties": e.get("properties", {})}
                for e in entities
            ],
            relationships=relationships,
        )

    async def test_happy_path_nodes_and_edges(self) -> None:
        provider = _make_provider()
        result = self._make_extraction_result(
            entities=[
                {"name": "Python", "type": "Language", "properties": {}},
                {"name": "Guido", "type": "Person", "properties": {}},
            ],
            relationships=[{"source": "Guido", "target": "Python", "type": "CREATED"}],
        )
        provider._client.chat.completions.parse = AsyncMock(
            return_value=_make_parse_response(parsed=result)
        )

        nodes, edges = await provider.extract_graph("Python was created by Guido", {})

        assert len(nodes) == 2
        assert len(edges) == 1

    async def test_empty_extraction_returns_empty_tuples(self) -> None:
        provider = _make_provider()
        result = self._make_extraction_result(entities=[], relationships=[])
        provider._client.chat.completions.parse = AsyncMock(
            return_value=_make_parse_response(parsed=result)
        )

        nodes, edges = await provider.extract_graph("nothing here", {})

        assert nodes == []
        assert edges == []

    async def test_refusal_raises_llm_error(self) -> None:
        provider = _make_provider()
        provider._client.chat.completions.parse = AsyncMock(
            return_value=_make_parse_response(parsed=None, refusal="I cannot do that.")
        )

        with pytest.raises(LLMError, match="refused"):
            await provider.extract_graph("text", {})

    async def test_parsed_none_raises_llm_error(self) -> None:
        provider = _make_provider()
        provider._client.chat.completions.parse = AsyncMock(
            return_value=_make_parse_response(parsed=None, refusal=None)
        )

        with pytest.raises(LLMError, match="unparseable"):
            await provider.extract_graph("text", {})

    async def test_api_error_raises_llm_error(self) -> None:
        provider = _make_provider()
        original = openai.APIStatusError(
            message="500", response=MagicMock(), body=None
        )
        provider._client.chat.completions.parse = AsyncMock(side_effect=original)

        with pytest.raises(LLMError) as exc_info:
            await provider.extract_graph("text", {})

        assert exc_info.value.__cause__ is original


# ---------------------------------------------------------------------------
# TestComplete
# ---------------------------------------------------------------------------


class TestComplete:
    async def test_happy_path_returns_string(self) -> None:
        provider = _make_provider()
        provider._client.chat.completions.create = AsyncMock(
            return_value=_make_create_response("This is a response.")
        )

        result = await provider.complete("Tell me about Python")

        assert result == "This is a response."

    async def test_none_content_returns_empty_string(self) -> None:
        provider = _make_provider()
        message = MagicMock()
        message.content = None
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]
        provider._client.chat.completions.create = AsyncMock(return_value=response)

        result = await provider.complete("prompt")

        assert result == ""

    async def test_api_error_raises_llm_error(self) -> None:
        provider = _make_provider()
        original = openai.APIConnectionError.__new__(openai.APIConnectionError)
        provider._client.chat.completions.create = AsyncMock(side_effect=original)

        with pytest.raises(LLMError) as exc_info:
            await provider.complete("prompt")

        assert exc_info.value.__cause__ is original
