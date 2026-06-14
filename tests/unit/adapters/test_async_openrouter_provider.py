"""Unit tests for AsyncOpenRouterProvider.

All tests mock ``openai.AsyncOpenAI`` — no HTTP calls made.
Covers: constructor, embed, embed_batch, extract_graph, complete.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest

from depth_graph_search.adapters.openrouter.async_provider import AsyncOpenRouterProvider
from depth_graph_search.core.domain.entities import Embedding
from depth_graph_search.core.domain.exceptions import LLMError
from depth_graph_search.core.ports.async_ports import AsyncEmbeddingProvider, AsyncLLMProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider(
    api_key: str = "or-test",
    model: str = "openai/gpt-4o",
    embedding_model: str = "openai/text-embedding-3-large",
) -> AsyncOpenRouterProvider:
    with patch("openai.AsyncOpenAI"):
        return AsyncOpenRouterProvider(api_key=api_key, model=model, embedding_model=embedding_model)


def _make_embedding_response(vectors: list[list[float]]) -> MagicMock:
    """Build a mock openai embeddings response with multiple data items."""
    data = []
    for idx, vec in enumerate(vectors):
        item = MagicMock()
        item.embedding = vec
        item.index = idx
        data.append(item)
    response = MagicMock()
    response.data = data
    return response


def _make_json_response(data: dict) -> MagicMock:
    message = MagicMock()
    message.content = json.dumps(data)
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


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
    def test_default_model_stored(self) -> None:
        provider = _make_provider()
        assert provider.model == "openai/gpt-4o"

    def test_custom_model_stored(self) -> None:
        provider = _make_provider(model="anthropic/claude-3-opus")
        assert provider.model == "anthropic/claude-3-opus"

    def test_isinstance_async_llm_provider(self) -> None:
        provider = _make_provider()
        assert isinstance(provider, AsyncLLMProvider)

    def test_isinstance_async_embedding_provider(self) -> None:
        provider = _make_provider()
        assert isinstance(provider, AsyncEmbeddingProvider)

    def test_empty_api_key_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            AsyncOpenRouterProvider(api_key="")

    def test_no_http_on_construction(self) -> None:
        with patch("openai.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            AsyncOpenRouterProvider(api_key="or-test")
            mock_client.chat.completions.create.assert_not_called()


# ---------------------------------------------------------------------------
# TestExtractGraph
# ---------------------------------------------------------------------------


class TestExtractGraph:
    async def test_happy_path_returns_graph_data(self) -> None:
        provider = _make_provider()
        payload = {
            "entities": [
                {"name": "Python", "type": "Language", "properties": {}},
            ],
            "relationships": [],
        }
        provider._client.chat.completions.create = AsyncMock(
            return_value=_make_json_response(payload)
        )

        nodes, edges = await provider.extract_graph("Python is a language", {})

        assert len(nodes) == 1
        assert nodes[0].content == "Python"
        assert edges == []

    async def test_empty_extraction_returns_empty_lists(self) -> None:
        provider = _make_provider()
        payload = {"entities": [], "relationships": []}
        provider._client.chat.completions.create = AsyncMock(
            return_value=_make_json_response(payload)
        )

        nodes, edges = await provider.extract_graph("nothing", {})

        assert nodes == []
        assert edges == []

    async def test_api_error_raises_llm_error(self) -> None:
        provider = _make_provider()
        original = openai.APIConnectionError.__new__(openai.APIConnectionError)
        provider._client.chat.completions.create = AsyncMock(side_effect=original)

        with pytest.raises(LLMError) as exc_info:
            await provider.extract_graph("text", {})

        assert exc_info.value.__cause__ is original

    async def test_invalid_json_raises_llm_error(self) -> None:
        provider = _make_provider()
        message = MagicMock()
        message.content = "not json"
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]
        provider._client.chat.completions.create = AsyncMock(return_value=response)

        with pytest.raises(LLMError, match="Invalid JSON"):
            await provider.extract_graph("text", {})


# ---------------------------------------------------------------------------
# TestComplete
# ---------------------------------------------------------------------------


class TestComplete:
    async def test_happy_path_returns_string(self) -> None:
        provider = _make_provider()
        provider._client.chat.completions.create = AsyncMock(
            return_value=_make_create_response("hello world")
        )

        result = await provider.complete("what is python")

        assert result == "hello world"

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


# ---------------------------------------------------------------------------
# TestEmbed
# ---------------------------------------------------------------------------


class TestEmbed:
    async def test_embed_returns_embedding_instance(self) -> None:
        """embed() returns an Embedding with correct shape."""
        provider = _make_provider()
        vector = [0.1, 0.2, 0.3]
        provider._client.embeddings.create = AsyncMock(
            return_value=_make_embedding_response([vector])
        )

        result = await provider.embed("some text")

        assert isinstance(result, Embedding)
        assert result.vector == vector
        assert result.dimensions == 3
        assert result.model == "openai/text-embedding-3-large"

    async def test_embed_calls_create_with_correct_args(self) -> None:
        """embed() passes model and input=[text] to the SDK."""
        provider = _make_provider()
        provider._client.embeddings.create = AsyncMock(
            return_value=_make_embedding_response([[0.1]])
        )

        await provider.embed("hello world")

        provider._client.embeddings.create.assert_awaited_once_with(
            model="openai/text-embedding-3-large",
            input=["hello world"],
        )

    async def test_embed_propagates_openai_error_as_llm_error(self) -> None:
        """embed() wraps OpenAIError as LLMError."""
        provider = _make_provider()
        original = openai.RateLimitError(
            message="rate limit",
            response=MagicMock(),
            body=None,
        )
        provider._client.embeddings.create = AsyncMock(side_effect=original)

        with pytest.raises(LLMError) as exc_info:
            await provider.embed("text")

        assert exc_info.value.__cause__ is original

    async def test_embed_uses_custom_embedding_model(self) -> None:
        """embed() uses the embedding_model set at construction."""
        provider = _make_provider(embedding_model="openai/text-embedding-ada-002")
        provider._client.embeddings.create = AsyncMock(
            return_value=_make_embedding_response([[0.5]])
        )

        result = await provider.embed("text")

        assert result.model == "openai/text-embedding-ada-002"
        _, kwargs = provider._client.embeddings.create.call_args
        assert kwargs["model"] == "openai/text-embedding-ada-002"


# ---------------------------------------------------------------------------
# TestEmbedBatch
# ---------------------------------------------------------------------------


class TestEmbedBatch:
    async def test_embed_batch_returns_list_of_embeddings(self) -> None:
        """embed_batch() returns one Embedding per input text."""
        provider = _make_provider()
        vectors = [[0.1, 0.2], [0.3, 0.4]]
        provider._client.embeddings.create = AsyncMock(
            return_value=_make_embedding_response(vectors)
        )

        results = await provider.embed_batch(["text A", "text B"])

        assert len(results) == 2
        assert all(isinstance(e, Embedding) for e in results)

    async def test_embed_batch_preserves_order(self) -> None:
        """embed_batch() sorts by index — result order matches input order."""
        provider = _make_provider()
        # Simulate API returning items in reverse order
        data = []
        for idx, vec in enumerate([[0.9, 0.8], [0.1, 0.2]]):
            item = MagicMock()
            item.embedding = vec
            item.index = idx
            data.append(item)
        # Shuffle: reverse so index=1 comes first
        response = MagicMock()
        response.data = [data[1], data[0]]
        provider._client.embeddings.create = AsyncMock(return_value=response)

        results = await provider.embed_batch(["first", "second"])

        assert results[0].vector == [0.9, 0.8]
        assert results[1].vector == [0.1, 0.2]

    async def test_embed_batch_passes_all_texts_to_api(self) -> None:
        """embed_batch() sends all texts as the input list."""
        provider = _make_provider()
        provider._client.embeddings.create = AsyncMock(
            return_value=_make_embedding_response([[0.1], [0.2], [0.3]])
        )

        await provider.embed_batch(["a", "b", "c"])

        _, kwargs = provider._client.embeddings.create.call_args
        assert kwargs["input"] == ["a", "b", "c"]

    async def test_embed_batch_propagates_openai_error_as_llm_error(self) -> None:
        """embed_batch() wraps OpenAIError as LLMError."""
        provider = _make_provider()
        original = openai.APIConnectionError.__new__(openai.APIConnectionError)
        provider._client.embeddings.create = AsyncMock(side_effect=original)

        with pytest.raises(LLMError) as exc_info:
            await provider.embed_batch(["text"])

        assert exc_info.value.__cause__ is original
