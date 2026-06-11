"""Unit tests for DefaultIngestionPipeline.

Tests are 1-to-1 with spec scenarios. Each test is self-contained —
fixtures provide fresh fakes, and each test only configures what it needs.

Coverage:
- ABC compliance
- Constructor injection (missing dependency)
- Input validation (empty, whitespace-only, valid)
- Happy path full flow (2 nodes, 1 edge)
- Empty LLM extraction → IngestionResult(0, 0)
- Metadata forwarding to LLM
- Entity resolution — matched entity edges rewired
- Entity resolution — matched entity NOT saved as new node
- Entity resolution — new entity saved normally
- LLM failure → IngestionError + no writes
- Storage failure → IngestionError
- IngestionResult immutability
"""

from __future__ import annotations

import dataclasses

import pytest

from depth_graph_search.adapters.ingestion.pipeline import DefaultIngestionPipeline
from depth_graph_search.core.domain.entities import IngestionResult
from depth_graph_search.core.domain.exceptions import (
    IngestionError,
    LLMError,
    StorageError,
    ValidationError,
)
from depth_graph_search.core.ports.ingestion_pipeline import IngestionPipeline
from tests.mocks import (
    FakeEmbeddingProvider,
    FakeEntityResolutionStrategy,
    FakeLLMProvider,
    InMemoryGraphRepository,
)
from tests.unit.conftest import make_edge, make_embedding, make_node


# ---------------------------------------------------------------------------
# 1. ABC compliance
# ---------------------------------------------------------------------------


def test_abc_compliance(pipeline: DefaultIngestionPipeline) -> None:
    """DefaultIngestionPipeline is a valid IngestionPipeline subclass."""
    assert isinstance(pipeline, IngestionPipeline)


# ---------------------------------------------------------------------------
# 2. Constructor injection
# ---------------------------------------------------------------------------


def test_missing_dependency_raises_typeerror() -> None:
    """Omitting a constructor argument raises TypeError before any logic runs."""
    with pytest.raises(TypeError):
        DefaultIngestionPipeline(  # type: ignore[call-arg]
            llm_provider=FakeLLMProvider(),
            embedding_provider=FakeEmbeddingProvider(),
            graph_repository=InMemoryGraphRepository(),
            # entity_resolution omitted
        )


# ---------------------------------------------------------------------------
# 3. Input validation
# ---------------------------------------------------------------------------


def test_empty_text_raises_validation_error(
    pipeline: DefaultIngestionPipeline,
    fake_llm: FakeLLMProvider,
) -> None:
    """Empty string raises ValidationError; no port is called."""
    with pytest.raises(ValidationError):
        pipeline.ingest("")

    assert fake_llm.call_count("extract_graph") == 0


def test_whitespace_only_raises_validation_error(
    pipeline: DefaultIngestionPipeline,
    fake_llm: FakeLLMProvider,
) -> None:
    """Whitespace-only text raises ValidationError; no port is called."""
    with pytest.raises(ValidationError):
        pipeline.ingest("   \n\t  ")

    assert fake_llm.call_count("extract_graph") == 0


def test_valid_text_accepted(
    pipeline: DefaultIngestionPipeline,
    fake_llm: FakeLLMProvider,
) -> None:
    """Valid text does not raise ValidationError and calls the LLM."""
    fake_llm.set_extraction(nodes=[], edges=[])
    result = pipeline.ingest("Alice KNOWS Bob.")

    assert isinstance(result, IngestionResult)


# ---------------------------------------------------------------------------
# 4. Happy path — full 4-stage flow
# ---------------------------------------------------------------------------


def test_happy_path_full_flow(
    pipeline: DefaultIngestionPipeline,
    fake_llm: FakeLLMProvider,
    fake_embedder: FakeEmbeddingProvider,
    fake_repo: InMemoryGraphRepository,
) -> None:
    """2 nodes + 1 edge → IngestionResult(node_count=2, edge_count=1)."""
    node_a = make_node("Alice", node_id="id-a")
    node_b = make_node("Bob", node_id="id-b")
    edge_1 = make_edge("id-a", "id-b", relationship="KNOWS")

    fake_llm.set_extraction(nodes=[node_a, node_b], edges=[edge_1])
    emb = make_embedding()
    fake_embedder.set_embeddings([emb, emb])

    result = pipeline.ingest("Alice KNOWS Bob.")

    assert result.node_count == 2
    assert result.edge_count == 1
    assert fake_repo.call_count("save_node") == 2
    assert fake_repo.call_count("save_edge") == 1


def test_happy_path_embed_batch_called_with_node_contents(
    pipeline: DefaultIngestionPipeline,
    fake_llm: FakeLLMProvider,
    fake_embedder: FakeEmbeddingProvider,
) -> None:
    """embed_batch is called with each node's content."""
    node_a = make_node("Alice", node_id="id-a")
    node_b = make_node("Bob", node_id="id-b")
    fake_llm.set_extraction(nodes=[node_a, node_b], edges=[])
    emb = make_embedding()
    fake_embedder.set_embeddings([emb, emb])

    pipeline.ingest("Alice and Bob.")

    assert fake_embedder.call_count("embed_batch") == 1
    # The call was made with the node contents in order
    call_args = fake_embedder.calls("embed_batch")[0][0][0]
    assert call_args == ["Alice", "Bob"]


# ---------------------------------------------------------------------------
# 5. Empty LLM extraction
# ---------------------------------------------------------------------------


def test_empty_extraction_returns_zero_result(
    pipeline: DefaultIngestionPipeline,
    fake_llm: FakeLLMProvider,
    fake_embedder: FakeEmbeddingProvider,
    fake_repo: InMemoryGraphRepository,
) -> None:
    """LLM returning ([], []) yields IngestionResult(0, 0) with no writes."""
    fake_llm.set_extraction(nodes=[], edges=[])

    result = pipeline.ingest("Some text with no entities.")

    assert result == IngestionResult(node_count=0, edge_count=0)
    assert fake_embedder.call_count("embed_batch") == 0
    assert fake_repo.call_count("save_node") == 0
    assert fake_repo.call_count("save_edge") == 0


# ---------------------------------------------------------------------------
# 6. Metadata forwarding
# ---------------------------------------------------------------------------


def test_metadata_forwarded_to_llm(
    pipeline: DefaultIngestionPipeline,
    fake_llm: FakeLLMProvider,
) -> None:
    """Metadata is forwarded unchanged to llm.extract_graph."""
    fake_llm.set_extraction(nodes=[], edges=[])
    metadata = {"source": "paper.pdf", "year": 2024}

    pipeline.ingest("Some text.", metadata=metadata)

    extract_calls = fake_llm.calls("extract_graph")
    assert len(extract_calls) == 1
    called_text, called_metadata = extract_calls[0][0]
    assert called_metadata == {"source": "paper.pdf", "year": 2024}


def test_metadata_attached_to_every_persisted_node(
    pipeline: DefaultIngestionPipeline,
    fake_llm: FakeLLMProvider,
    fake_embedder: FakeEmbeddingProvider,
    fake_repo: InMemoryGraphRepository,
) -> None:
    """Every persisted node carries the caller-supplied metadata."""
    node_a = make_node("Alice", node_id="id-a")
    node_b = make_node("Bob", node_id="id-b")
    fake_llm.set_extraction(nodes=[node_a, node_b], edges=[])
    emb = make_embedding()
    fake_embedder.set_embeddings([emb, emb])

    pipeline.ingest("Alice and Bob.", metadata={"source": "paper.pdf"})

    for saved_node in fake_repo._nodes.values():
        assert saved_node.metadata["source"] == "paper.pdf"


def test_node_metadata_wins_over_caller_metadata(
    pipeline: DefaultIngestionPipeline,
    fake_llm: FakeLLMProvider,
    fake_embedder: FakeEmbeddingProvider,
    fake_repo: InMemoryGraphRepository,
) -> None:
    """If a node already has a metadata key, it takes precedence over caller metadata."""
    node_a = make_node("Alice", node_id="id-a", metadata={"source": "llm-override"})
    fake_llm.set_extraction(nodes=[node_a], edges=[])
    emb = make_embedding()
    fake_embedder.set_embeddings([emb])

    pipeline.ingest("Alice.", metadata={"source": "caller.pdf"})

    saved = fake_repo._nodes["id-a"]
    assert saved.metadata["source"] == "llm-override"


def test_none_metadata_defaults_to_empty_dict(
    pipeline: DefaultIngestionPipeline,
    fake_llm: FakeLLMProvider,
) -> None:
    """metadata=None is normalised to {} before being forwarded."""
    fake_llm.set_extraction(nodes=[], edges=[])

    pipeline.ingest("Some text.", metadata=None)

    extract_calls = fake_llm.calls("extract_graph")
    _, called_metadata = extract_calls[0][0]
    assert called_metadata == {}


# ---------------------------------------------------------------------------
# 7. Entity resolution — edge rewiring
# ---------------------------------------------------------------------------


def test_matched_entity_edges_rewired(
    pipeline: DefaultIngestionPipeline,
    fake_llm: FakeLLMProvider,
    fake_embedder: FakeEmbeddingProvider,
    fake_repo: InMemoryGraphRepository,
    fake_resolver: FakeEntityResolutionStrategy,
) -> None:
    """Edges referencing a matched node are rewritten to use matched_id."""
    node_a = make_node("Alice", node_id="id-a")
    node_b = make_node("Bob", node_id="id-b")
    edge_1 = make_edge("id-a", "id-b", relationship="KNOWS")

    fake_llm.set_extraction(nodes=[node_a, node_b], edges=[edge_1])
    emb = make_embedding()
    fake_embedder.set_embeddings([emb, emb])

    # node_a is matched to an existing node — edge source should be rewired
    from depth_graph_search.core.domain.entities import ResolvedNode
    fake_resolver.set_custom([
        ResolvedNode(node=node_a, is_new=False, matched_id="existing-id"),
        ResolvedNode(node=node_b, is_new=True, matched_id=None),
    ])

    pipeline.ingest("Alice KNOWS Bob.")

    # The saved edge's source_id should be "existing-id"
    saved_edges = list(fake_repo._edges.values())
    assert len(saved_edges) == 1
    assert saved_edges[0].source_id == "existing-id"
    assert saved_edges[0].target_id == "id-b"


def test_matched_entity_not_saved(
    pipeline: DefaultIngestionPipeline,
    fake_llm: FakeLLMProvider,
    fake_embedder: FakeEmbeddingProvider,
    fake_repo: InMemoryGraphRepository,
    fake_resolver: FakeEntityResolutionStrategy,
) -> None:
    """A matched node (is_new=False) does not produce a save_node call."""
    node_a = make_node("Alice", node_id="id-a")
    fake_llm.set_extraction(nodes=[node_a], edges=[])
    emb = make_embedding()
    fake_embedder.set_embeddings([emb])

    fake_resolver.set_all_matched(matched_id="existing-id")

    pipeline.ingest("Alice.")

    assert fake_repo.call_count("save_node") == 0


def test_new_entity_saved_normally(
    pipeline: DefaultIngestionPipeline,
    fake_llm: FakeLLMProvider,
    fake_embedder: FakeEmbeddingProvider,
    fake_repo: InMemoryGraphRepository,
    fake_resolver: FakeEntityResolutionStrategy,
) -> None:
    """A new entity (is_new=True) produces exactly one save_node call."""
    node_b = make_node("Bob", node_id="id-b")
    fake_llm.set_extraction(nodes=[node_b], edges=[])
    emb = make_embedding()
    fake_embedder.set_embeddings([emb])

    fake_resolver.set_all_new()

    pipeline.ingest("Bob.")

    assert fake_repo.call_count("save_node") == 1


# ---------------------------------------------------------------------------
# 8. LLM failure — no writes
# ---------------------------------------------------------------------------


def test_llm_error_raises_ingestion_error_no_writes(
    pipeline: DefaultIngestionPipeline,
    fake_llm: FakeLLMProvider,
    fake_repo: InMemoryGraphRepository,
) -> None:
    """LLMError from extract_graph raises IngestionError with __cause__ set; no writes."""
    llm_error = LLMError("timeout")
    fake_llm.set_error(llm_error)

    with pytest.raises(IngestionError) as exc_info:
        pipeline.ingest("Alice KNOWS Bob.")

    assert exc_info.value.__cause__ is llm_error
    assert fake_repo.call_count("save_node") == 0
    assert fake_repo.call_count("save_edge") == 0


# ---------------------------------------------------------------------------
# 9. Storage failure — error propagation
# ---------------------------------------------------------------------------


def test_storage_error_raises_ingestion_error(
    pipeline: DefaultIngestionPipeline,
    fake_llm: FakeLLMProvider,
    fake_embedder: FakeEmbeddingProvider,
    fake_repo: InMemoryGraphRepository,
) -> None:
    """StorageError from save_node raises IngestionError with __cause__ set."""
    node_a = make_node("Alice", node_id="id-a")
    fake_llm.set_extraction(nodes=[node_a], edges=[])
    emb = make_embedding()
    fake_embedder.set_embeddings([emb])

    storage_error = StorageError("disk full")
    fake_repo.set_error(storage_error)

    with pytest.raises(IngestionError) as exc_info:
        pipeline.ingest("Alice.")

    assert exc_info.value.__cause__ is storage_error


# ---------------------------------------------------------------------------
# 10. IngestionResult immutability
# ---------------------------------------------------------------------------


def test_ingestion_result_is_immutable() -> None:
    """IngestionResult is a frozen dataclass — attribute assignment raises FrozenInstanceError."""
    result = IngestionResult(node_count=3, edge_count=2)

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.node_count = 99  # type: ignore[misc]


def test_ingestion_result_counts_match_persisted_data(
    pipeline: DefaultIngestionPipeline,
    fake_llm: FakeLLMProvider,
    fake_embedder: FakeEmbeddingProvider,
) -> None:
    """IngestionResult counts reflect exactly what was persisted."""
    nodes = [make_node(f"Node {i}", node_id=f"id-{i}") for i in range(3)]
    edges = [
        make_edge("id-0", "id-1"),
        make_edge("id-1", "id-2"),
    ]
    fake_llm.set_extraction(nodes=nodes, edges=edges)
    emb = make_embedding()
    fake_embedder.set_embeddings([emb] * 3)

    result = pipeline.ingest("Three nodes, two edges.")

    assert result.node_count == 3
    assert result.edge_count == 2


# ---------------------------------------------------------------------------
# 11. SDK surface — top-level import
# ---------------------------------------------------------------------------


def test_top_level_import() -> None:
    """IngestionPipeline, DefaultIngestionPipeline, IngestionResult importable from top-level."""
    from depth_graph_search import (  # noqa: F401
        DefaultIngestionPipeline,
        IngestionPipeline,
        IngestionResult,
    )
