"""Unit tests for AsyncOpenRouterProvider.

All tests mock ``openai.AsyncOpenAI`` — no HTTP calls made.
Covers: constructor, extract_graph, complete.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest

from depth_graph_search.adapters.openrouter.async_provider import AsyncOpenRouterProvider
from depth_graph_search.core.domain.exceptions import LLMError
from depth_graph_search.core.ports.async_ports import AsyncLLMProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider(
    api_key: str = "or-test",
    model: str = "openai/gpt-4o",
) -> AsyncOpenRouterProvider:
    with patch("openai.AsyncOpenAI"):
        return AsyncOpenRouterProvider(api_key=api_key, model=model)


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
