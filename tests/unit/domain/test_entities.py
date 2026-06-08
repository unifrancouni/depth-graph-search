"""Unit tests for domain entities.

Tests cover: construction with defaults, custom fields, immutability (FrozenInstanceError),
and equality semantics. All entities are @dataclass(frozen=True).

No mocking, no external dependencies — pure construction and invariant verification.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from depth_graph_search.core.domain.entities import (
    Edge,
    Embedding,
    Metadata,
    Node,
    ResolvedNode,
    ScoredNode,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

UUID4_LENGTH = 36
UUID4_HYPHENS = 4


def _is_uuid4_string(value: str) -> bool:
    """Return True if value looks like a UUID4 string (36 chars, 4 hyphens)."""
    return len(value) == UUID4_LENGTH and value.count("-") == UUID4_HYPHENS


# ---------------------------------------------------------------------------
# Node tests
# ---------------------------------------------------------------------------


class TestNodeConstruction:
    def test_node_constructs_with_required_field_only(self) -> None:
        node = Node(content="The speed of light is 3e8 m/s")

        assert node.content == "The speed of light is 3e8 m/s"
        assert _is_uuid4_string(node.id)
        assert node.embedding is None
        assert node.metadata == {}

    def test_node_auto_id_is_uuid4(self) -> None:
        node = Node(content="some text")
        assert _is_uuid4_string(node.id)

    def test_node_custom_id(self) -> None:
        node = Node(content="Some text", id="test-node-01")
        assert node.id == "test-node-01"

    def test_node_with_embedding(self) -> None:
        emb = Embedding(vector=[0.1, 0.2], model="test-model", dimensions=2)
        node = Node(content="With embedding", embedding=emb)
        assert node.embedding == emb

    def test_node_with_metadata(self) -> None:
        meta: Metadata = {"source": "doc-01", "page": 3}
        node = Node(content="text", metadata=meta)
        assert node.metadata == {"source": "doc-01", "page": 3}

    def test_node_metadata_defaults_to_empty_dict(self) -> None:
        node = Node(content="text")
        assert node.metadata == {}
        assert isinstance(node.metadata, dict)


class TestNodeImmutability:
    def test_node_content_is_frozen(self) -> None:
        node = Node(content="original")
        with pytest.raises(FrozenInstanceError):
            node.content = "new content"  # type: ignore[misc]

    def test_node_id_is_frozen(self) -> None:
        node = Node(content="original")
        with pytest.raises(FrozenInstanceError):
            node.id = "new-id"  # type: ignore[misc]

    def test_node_embedding_is_frozen(self) -> None:
        node = Node(content="original")
        with pytest.raises(FrozenInstanceError):
            node.embedding = None  # type: ignore[misc]

    def test_node_metadata_is_frozen(self) -> None:
        node = Node(content="original")
        with pytest.raises(FrozenInstanceError):
            node.metadata = {}  # type: ignore[misc]


class TestNodeEquality:
    def test_nodes_with_same_explicit_fields_are_equal(self) -> None:
        node_a = Node(id="x", content="c", embedding=None, metadata={})
        node_b = Node(id="x", content="c", embedding=None, metadata={})
        assert node_a == node_b

    def test_nodes_with_different_auto_ids_are_not_equal(self) -> None:
        node_a = Node(content="c")
        node_b = Node(content="c")
        # Each call generates a new uuid4 — they MUST differ
        assert node_a != node_b

    def test_node_not_equal_to_different_content(self) -> None:
        node_a = Node(id="same", content="alpha")
        node_b = Node(id="same", content="beta")
        assert node_a != node_b


# ---------------------------------------------------------------------------
# Edge tests
# ---------------------------------------------------------------------------


class TestEdgeConstruction:
    def test_edge_constructs_with_required_fields(self) -> None:
        edge = Edge(source_id="a", target_id="b", relationship="CAUSES")

        assert edge.source_id == "a"
        assert edge.target_id == "b"
        assert edge.relationship == "CAUSES"
        assert _is_uuid4_string(edge.id)

    def test_edge_custom_id(self) -> None:
        edge = Edge(source_id="n1", target_id="n2", relationship="PART_OF", id="edge-01")
        assert edge.id == "edge-01"

    def test_edge_has_no_metadata_field(self) -> None:
        edge = Edge(source_id="a", target_id="b", relationship="IS_A")
        assert not hasattr(edge, "metadata")


class TestEdgeImmutability:
    def test_edge_relationship_is_frozen(self) -> None:
        edge = Edge(source_id="a", target_id="b", relationship="CAUSES")
        with pytest.raises(FrozenInstanceError):
            edge.relationship = "NEW"  # type: ignore[misc]

    def test_edge_source_id_is_frozen(self) -> None:
        edge = Edge(source_id="a", target_id="b", relationship="CAUSES")
        with pytest.raises(FrozenInstanceError):
            edge.source_id = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Embedding tests
# ---------------------------------------------------------------------------


class TestEmbeddingConstruction:
    def test_embedding_constructs_with_all_fields(self) -> None:
        emb = Embedding(vector=[0.1, 0.2, 0.3], model="test-model", dimensions=3)

        assert emb.vector == [0.1, 0.2, 0.3]
        assert emb.model == "test-model"
        assert emb.dimensions == 3

    def test_embedding_with_empty_vector(self) -> None:
        emb = Embedding(vector=[], model="test-model", dimensions=0)
        assert emb.vector == []
        assert emb.dimensions == 0


class TestEmbeddingImmutability:
    def test_embedding_model_is_frozen(self) -> None:
        emb = Embedding(vector=[0.1, 0.2, 0.3], model="test-model", dimensions=3)
        with pytest.raises(FrozenInstanceError):
            emb.model = "other"  # type: ignore[misc]

    def test_embedding_vector_is_frozen(self) -> None:
        emb = Embedding(vector=[0.1, 0.2], model="m", dimensions=2)
        with pytest.raises(FrozenInstanceError):
            emb.vector = [0.3, 0.4]  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ScoredNode tests
# ---------------------------------------------------------------------------


class TestScoredNodeConstruction:
    def test_scored_node_constructs(self) -> None:
        node = Node(content="The speed of light")
        scored = ScoredNode(node=node, score=0.92, distance=1)

        assert scored.node == node
        assert scored.score == 0.92
        assert scored.distance == 1

    def test_scored_node_distance_zero_is_entry_node(self) -> None:
        node = Node(content="Entry point")
        scored = ScoredNode(node=node, score=1.0, distance=0)
        assert scored.distance == 0


class TestScoredNodeImmutability:
    def test_scored_node_score_is_frozen(self) -> None:
        node = Node(content="text")
        scored = ScoredNode(node=node, score=0.9, distance=0)
        with pytest.raises(FrozenInstanceError):
            scored.score = 0.5  # type: ignore[misc]

    def test_scored_node_distance_is_frozen(self) -> None:
        node = Node(content="text")
        scored = ScoredNode(node=node, score=0.9, distance=0)
        with pytest.raises(FrozenInstanceError):
            scored.distance = 5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ResolvedNode tests
# ---------------------------------------------------------------------------


class TestResolvedNodeConstruction:
    def test_resolved_node_new(self) -> None:
        node = Node(content="A novel concept")
        resolved = ResolvedNode(node=node, is_new=True, matched_id=None)

        assert resolved.is_new is True
        assert resolved.matched_id is None

    def test_resolved_node_matched(self) -> None:
        node = Node(content="A familiar concept")
        resolved = ResolvedNode(node=node, is_new=False, matched_id="existing-42")

        assert resolved.is_new is False
        assert resolved.matched_id == "existing-42"

    def test_resolved_node_matched_id_defaults_to_none(self) -> None:
        node = Node(content="text")
        resolved = ResolvedNode(node=node, is_new=True)
        assert resolved.matched_id is None


class TestResolvedNodeImmutability:
    def test_resolved_node_is_new_is_frozen(self) -> None:
        node = Node(content="text")
        resolved = ResolvedNode(node=node, is_new=True, matched_id=None)
        with pytest.raises(FrozenInstanceError):
            resolved.is_new = False  # type: ignore[misc]

    def test_resolved_node_matched_id_is_frozen(self) -> None:
        node = Node(content="text")
        resolved = ResolvedNode(node=node, is_new=False, matched_id="x")
        with pytest.raises(FrozenInstanceError):
            resolved.matched_id = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Metadata type alias tests
# ---------------------------------------------------------------------------


class TestMetadataTypeAlias:
    def test_metadata_is_plain_dict_at_runtime(self) -> None:
        m: Metadata = {"source": "doc-01", "page": 3}
        assert isinstance(m, dict)
        assert m["source"] == "doc-01"
        assert m["page"] == 3

    def test_metadata_empty_dict_is_valid(self) -> None:
        m: Metadata = {}
        assert m == {}
