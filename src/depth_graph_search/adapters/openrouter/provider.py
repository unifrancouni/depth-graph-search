"""OpenRouterProvider — implements LLMProvider via the OpenAI SDK pointed at OpenRouter.

Design decisions:
- Implements LLMProvider only (no embedding — OpenRouter does not expose an embeddings API).
- Extraction uses json_object mode + json.loads() + Pydantic model_validate() because
  OpenRouter does NOT support OpenAI Structured Outputs (.parse()).
- Pydantic models are private to this module — NEVER exported, NEVER used in core/.
- Same private models and system prompt as the OpenAI adapter (duplicated by design —
  adapters do NOT import from each other per Clean Architecture).
- Constructor has ZERO side effects: stores config and creates client object only.
- All openai.OpenAIError subclasses are caught at the adapter boundary and re-raised
  as LLMError. json.JSONDecodeError and Pydantic ValidationError are also caught.
"""

from __future__ import annotations

import json as json_mod
from typing import Any

import openai
from pydantic import BaseModel

from depth_graph_search.core.domain.entities import Edge, Metadata, Node
from depth_graph_search.core.domain.exceptions import LLMError
from depth_graph_search.core.ports.llm_provider import LLMProvider

# ---------------------------------------------------------------------------
# Private Pydantic models — adapter-private, never exported
# ---------------------------------------------------------------------------


class _ExtractionEntity(BaseModel):
    name: str
    type: str
    properties: dict[str, Any]


class _ExtractionRelationship(BaseModel):
    source: str
    target: str
    type: str


class _ExtractionResult(BaseModel):
    entities: list[_ExtractionEntity]
    relationships: list[_ExtractionRelationship]


# ---------------------------------------------------------------------------
# System prompt constant (duplicated from openai adapter by design)
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = (
    "You are a knowledge graph extraction engine. "
    "Given a text, extract all entities and relationships.\n\n"
    "Return a JSON object with exactly two keys:\n"
    '- "entities": a list of objects, each with:\n'
    '  - "name": the entity name (string, unique within this extraction)\n'
    '  - "type": the entity type (string, e.g. "Person", "Organization", "Concept")\n'
    '  - "properties": an object with any additional properties (can be empty {})\n'
    '- "relationships": a list of objects, each with:\n'
    '  - "source": the name of the source entity (must match an entity name)\n'
    '  - "target": the name of the target entity (must match an entity name)\n'
    '  - "type": the relationship type (string, e.g. "WORKS_AT", "CAUSES", "PART_OF")\n\n'
    "Rules:\n"
    "- Entity names must be unique. If the same entity appears multiple times, "
    "use the same name.\n"
    "- Relationship source and target must reference entity names from the entities list.\n"
    '- If no entities are found, return {"entities": [], "relationships": []}.\n'
    "- Return ONLY the JSON object. No explanation, no markdown, no code fences."
)


# ---------------------------------------------------------------------------
# Private mapping helper (duplicated from openai adapter by design)
# ---------------------------------------------------------------------------


def _map_extraction(
    result: _ExtractionResult,
    metadata: Metadata,
) -> tuple[list[Node], list[Edge]]:
    """Convert _ExtractionResult into domain (Nodes, Edges).

    Entity names become Node.content. Metadata is assembled as:
    {**caller_metadata, "type": entity.type, "properties": entity.properties}

    First-occurrence wins for duplicate entity names.
    Relationships referencing unknown entity names are silently skipped.
    """
    name_to_node: dict[str, Node] = {}
    for entity in result.entities:
        if entity.name not in name_to_node:
            node = Node(
                content=entity.name,
                metadata={**metadata, "type": entity.type, "properties": entity.properties},
            )
            name_to_node[entity.name] = node

    edges: list[Edge] = []
    for rel in result.relationships:
        src = name_to_node.get(rel.source)
        tgt = name_to_node.get(rel.target)
        if src is None or tgt is None:
            continue  # skip edges with unknown entity references
        edges.append(
            Edge(
                source_id=src.id,
                target_id=tgt.id,
                relationship=rel.type,
            )
        )

    return list(name_to_node.values()), edges


# ---------------------------------------------------------------------------
# OpenRouterProvider
# ---------------------------------------------------------------------------


class OpenRouterProvider(LLMProvider):
    """Adapter implementing LLMProvider via the OpenAI SDK pointed at OpenRouter.

    Uses OpenRouter's OpenAI-compatible API endpoint. Does NOT implement
    EmbeddingProvider — OpenRouter does not expose an embeddings API.

    Args:
        api_key: OpenRouter API key.
        model: Model identifier in OpenRouter format. Defaults to "openai/gpt-4o".

    Note:
        The constructor performs ZERO I/O. It stores config and creates the client object
        (which is also side-effect-free until an API call is made).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-4o",
    ) -> None:
        self._client = openai.OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        self._model = model

    @property
    def model(self) -> str:
        """Model identifier."""
        return self._model

    # ------------------------------------------------------------------
    # LLMProvider
    # ------------------------------------------------------------------

    def extract_graph(
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
            response = self._client.chat.completions.create(
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

    def complete(self, prompt: str) -> str:
        """General-purpose text completion.

        Args:
            prompt: The full prompt to send to the model.

        Returns:
            Raw string output from the model.

        Raises:
            LLMError: On any OpenAI/OpenRouter API error.
        """
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.choices[0].message.content
            return content or ""
        except openai.OpenAIError as exc:
            raise LLMError("Completion failed") from exc
