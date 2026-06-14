# ADR-005: Ingestion Pipeline with LLM Extraction and Entity Resolution

- **Date**: 2026-06-10
- **Status**: accepted

## Context

depth-graph-search needs to convert free text into a knowledge graph. This requires orchestrating four capabilities in sequence: LLM-based entity extraction, embedding generation, entity resolution (deduplication), and graph persistence. The orchestration must be swappable (different ingestion strategies) and testable (no real LLM or database in unit tests).

Key forces:

1. **Pipeline as port**: The ingestion flow must be extensible — developers should be able to subclass for custom flows (e.g., chunked ingestion, batch processing).
2. **Edge rewiring**: When entity resolution matches a new node to an existing node, all edges referencing the new node's ID must be updated to point to the matched node's ID.
3. **Error propagation**: Each stage can fail independently (LLM errors, storage errors). Failures must surface as `IngestionError` with the original exception chained.
4. **Immutability**: Frozen dataclasses mean "attaching" embeddings or rewiring edges produces new instances via `dataclasses.replace()`.

## Decision

### IngestionPipeline as a port ABC

`IngestionPipeline` is the 6th port ABC in `core/ports/`, mirroring the `SearchPipeline` pattern. `DefaultIngestionPipeline` is a concrete adapter in `adapters/ingestion/` that orchestrates the 4-stage flow.

### IngestionResult as a domain value object

`IngestionResult(node_count: int, edge_count: int)` is a frozen dataclass in `core/domain/entities.py`, alongside `ScoredNode` and `ResolvedNode`. This allows all delivery layers (SDK, API, CLI) to use the same return type.

### 4-stage pipeline flow

```
ingest(text, metadata)
  1. Validate     — empty text raises ValidationError
  2. Extract      — LLMProvider.extract_graph() → (nodes, edges)
  3. Embed        — EmbeddingProvider.embed_batch() → attach to nodes
  4. Resolve      — EntityResolutionStrategy.resolve() → rewire edges
  5. Persist      — GraphRepository.save_node/save_edge
  → IngestionResult(node_count, edge_count)
```

### Edge rewiring algorithm

Build an `id_map: dict[str, str]` from resolved nodes where `is_new=False`, mapping original IDs to matched IDs. For each edge, replace `source_id` and `target_id` via the map using `dataclasses.replace()`. Only `is_new=True` nodes are persisted.

### Error mapping

| Stage | Port Error | Raised As |
|-------|-----------|-----------|
| Validation | Empty text | `ValidationError` |
| Extract | `LLMError` | `IngestionError` (chained) |
| Embed | `LLMError` | `IngestionError` (chained) |
| Persist | `StorageError` | `IngestionError` (chained) |

### Test mock adapters

Four ABC-compliant fakes in `tests/mocks/`: `InMemoryGraphRepository`, `FakeLLMProvider`, `FakeEmbeddingProvider`, `FakeEntityResolutionStrategy`. Each has `_calls` tracking (list-of-tuples) and `set_error(exc)` for error injection — no dependency on `unittest.mock`.

## Consequences

### Positive

- **Extensible ingestion**: Custom pipelines (chunked text, PDF parsing, batch) are subclasses of `IngestionPipeline` — no core changes needed.
- **Testable without mocking frameworks**: The four fakes in `tests/mocks/` are real ABC subclasses with call tracking, usable across all test suites.
- **Clean error chain**: `IngestionError.__cause__` always points to the original `LLMError` or `StorageError`, enabling root-cause inspection.
- **Immutability preserved**: Edge rewiring and embedding attachment produce new instances — no mutation of shared objects.

### Negative / Tradeoffs

- **Sequential processing**: Each node is embedded and resolved individually. Batch optimization (e.g., `asyncio.gather`) is deferred.
- **Empty extraction is a no-op**: If the LLM returns no entities, `IngestionResult(0, 0)` is returned silently — no error, no warning.
- **Resolution calls search per node**: Entity resolution uses the search pipeline internally, leading to O(N) search calls per ingestion. Acceptable for v0.1 data volumes.

### Future Considerations

- **Chunked ingestion**: A `ChunkedIngestionPipeline` could split large texts before extraction, running the base pipeline per chunk.
- **Batch embedding optimization**: `embed_batch` is already used, but the pipeline could further parallelize extraction + embedding.
- **Async fakes**: `tests/mocks/` currently has sync fakes only. Async tests use `AsyncMock` from `unittest.mock`.

## Alternatives Considered

| Alternative | Pros | Cons | Why Rejected |
|------------|------|------|--------------|
| **Use-case class in `sdk/`** | Simpler, no port needed | Not extensible — developers can't swap ingestion strategies | Spec explicitly requires pipeline-as-port |
| **IngestionResult as DTO in `sdk/`** | Keeps domain layer smaller | Not reusable across SDK/API/CLI delivery layers | Domain value object is the cleanest approach |
| **Mutate edges in-place** | Simpler code | Violates frozen-dataclass immutability; shared references could cause bugs | `replace()` preserves immutability guarantee |
| **`unittest.mock` for test fakes** | Less code, built-in | No ABC compliance check, no call tracking semantics, mock objects are fragile | Real fakes catch contract violations at construction time |

## See Also

- [ADR-002: Clean Architecture](./ADR-002-clean-architecture.md) — frozen dataclasses and ABC ports
- [ADR-004: Hybrid Search Pipeline](./ADR-004-hybrid-search-pipeline.md) — entity resolution uses search internally
- [Ingestion Flow](../../flows/ingestion.md) — runtime sequence diagram
- [Ports & Adapters](../ports-and-adapters.md) — `IngestionPipeline` contract
