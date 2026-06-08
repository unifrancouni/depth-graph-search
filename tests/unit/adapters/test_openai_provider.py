"""Unit tests for OpenAIProvider.

All tests mock the openai.OpenAI client — no HTTP calls made.
Covers: constructor, embed, embed_batch, extract_graph, complete.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import openai
import pytest

from depth_graph_search.adapters.openai.provider import OpenAIProvider
from depth_graph_search.core.domain.entities import Embedding
from depth_graph_search.core.domain.exceptions import LLMError
from depth_graph_search.core.ports.embedding_provider import EmbeddingProvider
from depth_graph_search.core.ports.llm_provider import LLMProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider(
    api_key: str = "sk-test",
    model: str = "gpt-4o",
    embedding_model: str = "text-embedding-3-large",
) -> OpenAIProvider:
    with patch("openai.OpenAI"):
        return OpenAIProvider(api_key=api_key, model=model, embedding_model=embedding_model)


def _make_embedding_data(index: int, vector: list[float]) -> MagicMock:
    """Build a mock object that matches openai EmbeddingData shape."""
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
    """Build a mock that matches the shape returned by .parse()."""
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

    def test_isinstance_embedding_provider(self) -> None:
        provider = _make_provider()
        assert isinstance(provider, EmbeddingProvider)

    def test_isinstance_llm_provider(self) -> None:
        provider = _make_provider()
        assert isinstance(provider, LLMProvider)

    def test_no_http_on_construction(self) -> None:
        """Constructor must not make any HTTP calls."""
        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            OpenAIProvider(api_key="sk-test")
            # Embeddings and chat completions should NOT have been called
            mock_client.embeddings.create.assert_not_called()
            mock_client.chat.completions.create.assert_not_called()
            mock_client.chat.completions.parse.assert_not_called()


# ---------------------------------------------------------------------------
# TestEmbed
# ---------------------------------------------------------------------------


class TestEmbed:
    def test_happy_path_returns_embedding(self) -> None:
        provider = _make_provider()
        vector = [0.1, 0.2, 0.3]
        provider._client.embeddings.create.return_value = _make_embeddings_response(
            [_make_embedding_data(0, vector)]
        )

        result = provider.embed("The speed of light")

        assert isinstance(result, Embedding)
        assert result.vector == vector
        assert result.model == "text-embedding-3-large"
        assert result.dimensions == len(vector)

    def test_dimensions_equals_vector_length(self) -> None:
        provider = _make_provider()
        vector = [0.0] * 3072
        provider._client.embeddings.create.return_value = _make_embeddings_response(
            [_make_embedding_data(0, vector)]
        )

        result = provider.embed("test")

        assert result.dimensions == 3072
        assert len(result.vector) == 3072

    def test_api_error_raises_llm_error(self) -> None:
        provider = _make_provider()
        original = openai.APIConnectionError.__new__(openai.APIConnectionError)
        provider._client.embeddings.create.side_effect = original

        with pytest.raises(LLMError) as exc_info:
            provider.embed("text")

        assert exc_info.value.__cause__ is original

    def test_embed_uses_embedding_model(self) -> None:
        provider = _make_provider(embedding_model="text-embedding-3-small")
        vector = [0.5, 0.6]
        provider._client.embeddings.create.return_value = _make_embeddings_response(
            [_make_embedding_data(0, vector)]
        )

        result = provider.embed("hello")

        assert result.model == "text-embedding-3-small"
        provider._client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-small",
            input=["hello"],
        )


# ---------------------------------------------------------------------------
# TestEmbedBatch
# ---------------------------------------------------------------------------


class TestEmbedBatch:
    def test_happy_path_batch_of_three(self) -> None:
        provider = _make_provider()
        # API returns items in order 0, 1, 2
        provider._client.embeddings.create.return_value = _make_embeddings_response([
            _make_embedding_data(0, [0.1]),
            _make_embedding_data(1, [0.2]),
            _make_embedding_data(2, [0.3]),
        ])

        results = provider.embed_batch(["A", "B", "C"])

        assert len(results) == 3
        assert results[0].vector == [0.1]
        assert results[1].vector == [0.2]
        assert results[2].vector == [0.3]

    def test_shuffled_index_order_preserved(self) -> None:
        """API may return data out of index order — adapter must sort by index."""
        provider = _make_provider()
        # Return in reverse index order: 2, 0, 1
        provider._client.embeddings.create.return_value = _make_embeddings_response([
            _make_embedding_data(2, [0.3]),
            _make_embedding_data(0, [0.1]),
            _make_embedding_data(1, [0.2]),
        ])

        results = provider.embed_batch(["A", "B", "C"])

        # Must be sorted by index: 0→[0.1], 1→[0.2], 2→[0.3]
        assert results[0].vector == [0.1]
        assert results[1].vector == [0.2]
        assert results[2].vector == [0.3]

    def test_batch_of_one(self) -> None:
        provider = _make_provider()
        provider._client.embeddings.create.return_value = _make_embeddings_response([
            _make_embedding_data(0, [0.9])
        ])

        results = provider.embed_batch(["single item"])

        assert len(results) == 1
        assert results[0].vector == [0.9]

    def test_rate_limit_error_raises_llm_error(self) -> None:
        provider = _make_provider()
        original = openai.RateLimitError(
            message="rate limit",
            response=MagicMock(),
            body=None,
        )
        provider._client.embeddings.create.side_effect = original

        with pytest.raises(LLMError) as exc_info:
            provider.embed_batch(["a", "b"])

        assert exc_info.value.__cause__ is original


# ---------------------------------------------------------------------------
# TestExtractGraph
# ---------------------------------------------------------------------------


class TestExtractGraph:
    def _make_extraction_result(
        self,
        entities: list[dict[str, object]],
        relationships: list[dict[str, str]],
    ) -> MagicMock:
        """Build a mock _ExtractionResult-like object."""
        # Import the private model to build a real Pydantic instance
        from depth_graph_search.adapters.openai.provider import (  # type: ignore[attr-defined]
            _ExtractionResult,
        )

        return _ExtractionResult(
            entities=[
                {"name": e["name"], "type": e["type"], "properties": e.get("properties", {})}
                for e in entities
            ],
            relationships=relationships,
        )

    def test_happy_path_nodes_and_edges(self) -> None:
        provider = _make_provider()
        result = self._make_extraction_result(
            entities=[
                {"name": "Python", "type": "Language", "properties": {}},
                {"name": "Guido van Rossum", "type": "Person", "properties": {}},
            ],
            relationships=[
                {"source": "Guido van Rossum", "target": "Python", "type": "CREATED"}
            ],
        )
        provider._client.chat.completions.parse.return_value = _make_parse_response(
            parsed=result
        )

        nodes, edges = provider.extract_graph(
            "Python was created by Guido van Rossum", {"source": "doc-01"}
        )

        assert len(nodes) == 2
        assert len(edges) == 1

        python_node = next(n for n in nodes if n.content == "Python")
        guido_node = next(n for n in nodes if n.content == "Guido van Rossum")

        assert python_node.metadata["source"] == "doc-01"
        assert python_node.metadata["type"] == "Language"
        assert python_node.metadata["properties"] == {}

        assert edges[0].source_id == guido_node.id
        assert edges[0].target_id == python_node.id
        assert edges[0].relationship == "CREATED"

    def test_empty_extraction_returns_empty_tuples(self) -> None:
        provider = _make_provider()
        result = self._make_extraction_result(entities=[], relationships=[])
        provider._client.chat.completions.parse.return_value = _make_parse_response(
            parsed=result
        )

        nodes, edges = provider.extract_graph("nothing here", {})

        assert nodes == []
        assert edges == []

    def test_unknown_entity_in_relationship_is_skipped(self) -> None:
        provider = _make_provider()
        result = self._make_extraction_result(
            entities=[{"name": "Python", "type": "Language", "properties": {}}],
            relationships=[
                {"source": "Python", "target": "UnknownEntity", "type": "RELATED_TO"}
            ],
        )
        provider._client.chat.completions.parse.return_value = _make_parse_response(
            parsed=result
        )

        nodes, edges = provider.extract_graph("some text", {})

        assert len(nodes) == 1
        assert len(edges) == 0  # edge skipped

    def test_caller_metadata_attached_to_all_nodes(self) -> None:
        provider = _make_provider()
        result = self._make_extraction_result(
            entities=[
                {"name": "Alice", "type": "Person", "properties": {}},
                {"name": "Bob", "type": "Person", "properties": {}},
            ],
            relationships=[],
        )
        provider._client.chat.completions.parse.return_value = _make_parse_response(
            parsed=result
        )

        nodes, _ = provider.extract_graph("text", {"source": "wiki", "page": 3})

        for node in nodes:
            assert node.metadata["source"] == "wiki"
            assert node.metadata["page"] == 3

    def test_refusal_raises_llm_error(self) -> None:
        provider = _make_provider()
        provider._client.chat.completions.parse.return_value = _make_parse_response(
            parsed=None,
            refusal="I cannot provide this information.",
        )

        with pytest.raises(LLMError, match="refused"):
            provider.extract_graph("text", {})

    def test_parsed_none_raises_llm_error(self) -> None:
        provider = _make_provider()
        provider._client.chat.completions.parse.return_value = _make_parse_response(
            parsed=None,
            refusal=None,
        )

        with pytest.raises(LLMError, match="unparseable"):
            provider.extract_graph("text", {})

    def test_api_status_error_raises_llm_error(self) -> None:
        provider = _make_provider()
        original = openai.APIStatusError(
            message="500 Internal Server Error",
            response=MagicMock(),
            body=None,
        )
        provider._client.chat.completions.parse.side_effect = original

        with pytest.raises(LLMError) as exc_info:
            provider.extract_graph("text", {})

        assert exc_info.value.__cause__ is original

    def test_duplicate_entity_names_first_wins(self) -> None:
        """When two entities share a name, the first one's ID is used for edge resolution."""
        provider = _make_provider()
        from depth_graph_search.adapters.openai.provider import (  # type: ignore[attr-defined]
            _ExtractionResult,
        )

        result = _ExtractionResult(
            entities=[
                {"name": "Python", "type": "Language", "properties": {}},
                {"name": "Python", "type": "Framework", "properties": {}},
            ],
            relationships=[{"source": "Python", "target": "Python", "type": "SELF"}],
        )
        provider._client.chat.completions.parse.return_value = _make_parse_response(
            parsed=result
        )

        nodes, edges = provider.extract_graph("text", {})

        # Only one node should exist (first-wins deduplication)
        assert len(nodes) == 1
        assert nodes[0].metadata["type"] == "Language"


# ---------------------------------------------------------------------------
# TestComplete
# ---------------------------------------------------------------------------


class TestComplete:
    def test_happy_path_returns_string(self) -> None:
        provider = _make_provider()
        provider._client.chat.completions.create.return_value = _make_create_response(
            "This is a completion response."
        )

        result = provider.complete("Tell me about Python")

        assert result == "This is a completion response."

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
            model="gpt-4o",
            messages=[{"role": "user", "content": "my prompt"}],
        )
