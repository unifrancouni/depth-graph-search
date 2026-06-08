"""LLMProvider port — abstract contract for language model adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from depth_graph_search.core.domain.entities import Edge, Metadata, Node


class LLMProvider(ABC):
    """Abstract contract for all language model adapters.

    Adapters (e.g. OpenAI GPT-4o, OpenRouter) MUST inherit from this class and
    implement both abstract methods. Instantiating ``LLMProvider`` directly
    raises ``TypeError``.

    Both methods raise ``LLMError`` on provider failure.
    """

    @abstractmethod
    def extract_graph(
        self,
        text: str,
        metadata: Metadata,
    ) -> tuple[list[Node], list[Edge]]:
        """Call the LLM to extract a knowledge graph from unstructured text.

        The LLM identifies entities (nodes) and relationships (edges) in the
        given text and returns them as domain objects.

        Args:
            text: The raw text to extract entities and relationships from.
            metadata: Key-value context to pass alongside the text (e.g. source
                document, page number). Attached to each extracted ``Node``
                at the adapter level.

        Returns:
            A tuple ``(nodes, edges)`` where:
            - ``nodes``: Extracted ``Node`` instances with ``content`` set and
              ``embedding=None``. IDs are domain-generated (uuid4).
            - ``edges``: Extracted ``Edge`` instances whose ``source_id`` and
              ``target_id`` reference nodes from the same call by their ``id``.
            - When no entities are found, returns ``([], [])``.

        Raises:
            LLMError: If the LLM call fails or returns a malformed response.
                The underlying API exception MUST be chained as ``__cause__``.
        """

    @abstractmethod
    def complete(self, prompt: str) -> str:
        """General-purpose text completion.

        Args:
            prompt: The full prompt to send to the language model.

        Returns:
            Raw string output from the model. No parsing or post-processing.

        Raises:
            LLMError: If the LLM call fails. The underlying API exception MUST
                be chained as ``__cause__``.
        """
