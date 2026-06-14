"""Unit tests for OpenRouterProvider.

All tests mock the openai.OpenAI client — no HTTP calls made.
Covers: constructor, embed, embed_batch, extract_graph (json_object mode), complete.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import openai
import pytest

from depth_graph_search.adapters.openrouter.provider import OpenRouterProvider
from depth_graph_search.core.domain.entities import Embedding
from depth_graph_search.core.domain.exceptions import LLMError
from depth_graph_search.core.ports.embedding_provider import EmbeddingProvider
from depth_graph_search.core.ports.llm_provider import LLMProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider(
    api_key: str = "or-test",
    model: str = "openai/gpt-4o",
    embedding_model: str = "openai/text-embedding-3-large",
) -> OpenRouterProvider:
    with patch("openai.OpenAI"):
        return OpenRouterProvider(api_key=api_key, model=model, embedding_model=embedding_model)


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


def _make_create_response(content: str) -> MagicMock:
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def _extraction_json(
    entities: list[dict[str, object]],
    relationships: list[dict[str, str]],
) -> str:
    return json.dumps({"entities": entities, "relationships": relationships})


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

    def test_isinstance_llm_provider(self) -> None:
        provider = _make_provider()
        assert isinstance(provider, LLMProvider)

    def test_isinstance_embedding_provider(self) -> None:
        provider = _make_provider()
        assert isinstance(provider, EmbeddingProvider)

    def test_no_http_on_construction(self) -> None:
        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            OpenRouterProvider(api_key="or-test")
            mock_client.chat.completions.create.assert_not_called()

    def test_base_url_set_to_openrouter(self) -> None:
        with patch("openai.OpenAI") as mock_openai_cls:
            OpenRouterProvider(api_key="or-key")
            _, kwargs = mock_openai_cls.call_args
            assert kwargs["base_url"] == "https://openrouter.ai/api/v1"


# ---------------------------------------------------------------------------
# TestExtractGraph
# ---------------------------------------------------------------------------


class TestExtractGraph:
    def test_happy_path_valid_json_response(self) -> None:
        provider = _make_provider()
        payload = _extraction_json(
            entities=[
                {"name": "Python", "type": "Language", "properties": {}},
                {"name": "Guido van Rossum", "type": "Person", "properties": {}},
            ],
            relationships=[
                {"source": "Guido van Rossum", "target": "Python", "type": "CREATED"}
            ],
        )
        provider._client.chat.completions.create.return_value = _make_create_response(payload)

        nodes, edges = provider.extract_graph(
            "Python was created by Guido van Rossum", {"source": "doc-01"}
        )

        assert len(nodes) == 2
        assert len(edges) == 1

        python_node = next(n for n in nodes if n.content == "Python")
        guido_node = next(n for n in nodes if n.content == "Guido van Rossum")

        assert python_node.metadata["source"] == "doc-01"
        assert python_node.metadata["type"] == "Language"
        assert edges[0].source_id == guido_node.id
        assert edges[0].target_id == python_node.id
        assert edges[0].relationship == "CREATED"

    def test_empty_extraction_returns_empty_tuples(self) -> None:
        provider = _make_provider()
        provider._client.chat.completions.create.return_value = _make_create_response(
            _extraction_json(entities=[], relationships=[])
        )

        nodes, edges = provider.extract_graph("nothing here", {})

        assert nodes == []
        assert edges == []

    def test_non_json_response_raises_llm_error(self) -> None:
        provider = _make_provider()
        provider._client.chat.completions.create.return_value = _make_create_response(
            "Sure, here are the entities..."
        )

        with pytest.raises(LLMError) as exc_info:
            provider.extract_graph("text", {})

        import json as json_mod

        assert isinstance(exc_info.value.__cause__, json_mod.JSONDecodeError)

    def test_valid_json_missing_keys_raises_llm_error(self) -> None:
        """JSON that parses fine but doesn't match the schema raises LLMError."""
        provider = _make_provider()
        provider._client.chat.completions.create.return_value = _make_create_response(
            '{"result": "ok"}'
        )

        with pytest.raises(LLMError):
            provider.extract_graph("text", {})

    def test_unknown_entity_in_relationship_is_skipped(self) -> None:
        provider = _make_provider()
        payload = _extraction_json(
            entities=[{"name": "Python", "type": "Language", "properties": {}}],
            relationships=[
                {"source": "Python", "target": "UnknownEntity", "type": "RELATED_TO"}
            ],
        )
        provider._client.chat.completions.create.return_value = _make_create_response(payload)

        nodes, edges = provider.extract_graph("text", {})

        assert len(nodes) == 1
        assert len(edges) == 0

    def test_api_rate_limit_error_raises_llm_error(self) -> None:
        provider = _make_provider()
        original = openai.RateLimitError(
            message="rate limit exceeded",
            response=MagicMock(),
            body=None,
        )
        provider._client.chat.completions.create.side_effect = original

        with pytest.raises(LLMError) as exc_info:
            provider.extract_graph("text", {})

        assert exc_info.value.__cause__ is original

    def test_caller_metadata_attached_to_nodes(self) -> None:
        provider = _make_provider()
        payload = _extraction_json(
            entities=[
                {"name": "Alice", "type": "Person", "properties": {}},
                {"name": "Bob", "type": "Person", "properties": {}},
            ],
            relationships=[],
        )
        provider._client.chat.completions.create.return_value = _make_create_response(payload)

        nodes, _ = provider.extract_graph("text", {"source": "wiki", "page": 3})

        for node in nodes:
            assert node.metadata["source"] == "wiki"
            assert node.metadata["page"] == 3

    def test_uses_json_object_response_format(self) -> None:
        """Confirm that extract_graph passes response_format={"type": "json_object"}."""
        provider = _make_provider()
        payload = _extraction_json(entities=[], relationships=[])
        provider._client.chat.completions.create.return_value = _make_create_response(payload)

        provider.extract_graph("text", {})

        _, kwargs = provider._client.chat.completions.create.call_args
        assert kwargs["response_format"] == {"type": "json_object"}


# ---------------------------------------------------------------------------
# TestComplete
# ---------------------------------------------------------------------------


class TestComplete:
    def test_happy_path_returns_raw_string(self) -> None:
        provider = _make_provider()
        provider._client.chat.completions.create.return_value = _make_create_response(
            "Explain graph databases response."
        )

        result = provider.complete("Explain graph databases")

        assert result == "Explain graph databases response."

    def test_none_content_returns_empty_string(self) -> None:
        provider = _make_provider()
        message = MagicMock()
        message.content = None
        choice = MagicMock()
        choice.message = message
        response = MagicMock()
        response.choices = [choice]
        provider._client.chat.completions.create.return_value = response

        result = provider.complete("prompt")

        assert result == ""

    def test_api_error_raises_llm_error(self) -> None:
        provider = _make_provider()
        original = openai.APIConnectionError.__new__(openai.APIConnectionError)
        provider._client.chat.completions.create.side_effect = original

        with pytest.raises(LLMError) as exc_info:
            provider.complete("prompt")

        assert exc_info.value.__cause__ is original

    def test_complete_sends_correct_messages(self) -> None:
        provider = _make_provider()
        provider._client.chat.completions.create.return_value = _make_create_response(
            "response"
        )

        provider.complete("my prompt")

        provider._client.chat.completions.create.assert_called_once_with(
            model="openai/gpt-4o",
            messages=[{"role": "user", "content": "my prompt"}],
        )


# ---------------------------------------------------------------------------
# TestEmbed
# ---------------------------------------------------------------------------


class TestEmbed:
    def test_embed_returns_embedding_instance(self) -> None:
        """embed() returns an Embedding with correct shape."""
        provider = _make_provider()
        vector = [0.1, 0.2, 0.3]
        provider._client.embeddings.create.return_value = _make_embedding_response([vector])

        result = provider.embed("some text")

        assert isinstance(result, Embedding)
        assert result.vector == vector
        assert result.dimensions == 3
        assert result.model == "openai/text-embedding-3-large"

    def test_embed_calls_create_with_correct_args(self) -> None:
        """embed() passes model and input=[text] to the SDK."""
        provider = _make_provider()
        provider._client.embeddings.create.return_value = _make_embedding_response([[0.1]])

        provider.embed("hello world")

        provider._client.embeddings.create.assert_called_once_with(
            model="openai/text-embedding-3-large",
            input=["hello world"],
        )

    def test_embed_propagates_openai_error_as_llm_error(self) -> None:
        """embed() wraps OpenAIError as LLMError."""
        provider = _make_provider()
        original = openai.RateLimitError(
            message="rate limit",
            response=MagicMock(),
            body=None,
        )
        provider._client.embeddings.create.side_effect = original

        with pytest.raises(LLMError) as exc_info:
            provider.embed("text")

        assert exc_info.value.__cause__ is original

    def test_embed_uses_custom_embedding_model(self) -> None:
        """embed() uses the embedding_model set at construction."""
        provider = _make_provider(embedding_model="openai/text-embedding-ada-002")
        provider._client.embeddings.create.return_value = _make_embedding_response([[0.5]])

        result = provider.embed("text")

        assert result.model == "openai/text-embedding-ada-002"
        _, kwargs = provider._client.embeddings.create.call_args
        assert kwargs["model"] == "openai/text-embedding-ada-002"


# ---------------------------------------------------------------------------
# TestEmbedBatch
# ---------------------------------------------------------------------------


class TestEmbedBatch:
    def test_embed_batch_returns_list_of_embeddings(self) -> None:
        """embed_batch() returns one Embedding per input text."""
        provider = _make_provider()
        vectors = [[0.1, 0.2], [0.3, 0.4]]
        provider._client.embeddings.create.return_value = _make_embedding_response(vectors)

        results = provider.embed_batch(["text A", "text B"])

        assert len(results) == 2
        assert all(isinstance(e, Embedding) for e in results)

    def test_embed_batch_preserves_order(self) -> None:
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
        provider._client.embeddings.create.return_value = response

        results = provider.embed_batch(["first", "second"])

        assert results[0].vector == [0.9, 0.8]
        assert results[1].vector == [0.1, 0.2]

    def test_embed_batch_passes_all_texts_to_api(self) -> None:
        """embed_batch() sends all texts as the input list."""
        provider = _make_provider()
        provider._client.embeddings.create.return_value = _make_embedding_response(
            [[0.1], [0.2], [0.3]]
        )

        provider.embed_batch(["a", "b", "c"])

        _, kwargs = provider._client.embeddings.create.call_args
        assert kwargs["input"] == ["a", "b", "c"]

    def test_embed_batch_propagates_openai_error_as_llm_error(self) -> None:
        """embed_batch() wraps OpenAIError as LLMError."""
        provider = _make_provider()
        original = openai.APIConnectionError.__new__(openai.APIConnectionError)
        provider._client.embeddings.create.side_effect = original

        with pytest.raises(LLMError) as exc_info:
            provider.embed_batch(["text"])

        assert exc_info.value.__cause__ is original
