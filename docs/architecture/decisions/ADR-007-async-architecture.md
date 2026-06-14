# ADR-007: Mirrored Sync/Async Architecture

- **Date**: 2026-06-11
- **Status**: accepted

## Context

Python async frameworks (FastAPI, asyncio-native applications) cannot call sync I/O without blocking the event loop. depth-graph-search needs a fully async path — from port ABCs through adapters, pipelines, and facade — to be usable in async runtimes without `run_in_executor` workarounds.

Key tensions:

1. **Separate ABCs required**: Python's `async def` override of a sync `abstractmethod` causes mypy errors. Sync and async ports must be separate class hierarchies.
2. **Helper reuse vs. adapter isolation**: Pure CPU helpers (scoring formulas, row mapping, extraction mapping) should not be duplicated unnecessarily, but cross-adapter imports violate project conventions.
3. **Constructor stays sync**: Constructors only store references — no I/O. Only factory classmethods and port methods become `async`.
4. **psycopg3 async gotchas**: `AsyncCursor.fetchone()` and `fetchall()` are SYNC methods — only `execute()` is async. This is counter-intuitive and a common source of bugs.

## Decision

### Full async mirror of every layer

Every sync class gets an async sibling in a `async_*.py` file next to its sync counterpart:

| Sync | Async | Location |
|------|-------|----------|
| 6 port ABCs | 6 async port ABCs | `core/ports/async_ports.py` (single file) |
| `PostgresGraphRepository` | `AsyncPostgresGraphRepository` | `adapters/postgres/async_repository.py` |
| `OpenAIProvider` | `AsyncOpenAIProvider` | `adapters/openai/async_provider.py` |
| `OpenRouterProvider` | `AsyncOpenRouterProvider` | `adapters/openrouter/async_provider.py` |
| `DefaultSearchPipeline` | `AsyncDefaultSearchPipeline` | `adapters/search/async_pipeline.py` |
| `DefaultEntityResolutionStrategy` | `AsyncDefaultEntityResolutionStrategy` | `adapters/search/async_entity_resolution.py` |
| `DefaultIngestionPipeline` | `AsyncDefaultIngestionPipeline` | `adapters/ingestion/async_pipeline.py` |
| `GraphSearch` | `AsyncGraphSearch` | `sdk/async_client.py` |

### Duplication over abstraction

Pure helpers (`_row_to_node`, `_parse_agtype_scalar`) are duplicated in async adapters (~30 LOC each) rather than extracted to shared modules. This follows the project's established convention where `_map_extraction` is deliberately duplicated between OpenAI and OpenRouter adapters.

Exception: Within the SAME adapter package (e.g., `adapters/openai/`), the async module imports Pydantic models and `_map_extraction` from the sync module. Same-package imports are acceptable.

### Async ABCs in a single file

All 6 async port ABCs live in `core/ports/async_ports.py` rather than individual files. Async ABCs are lightweight (method signatures only) — a single file reduces import sprawl.

### `AsyncMock` for testing (not full fakes)

Async unit tests use `unittest.mock.AsyncMock` rather than building full async fake classes. Full fakes are unnecessary overhead for v0.1 — `AsyncMock` is sufficient for verifying `await` calls and return values.

## Consequences

### Positive

- **Native async**: FastAPI routes, asyncio applications, and any async runtime can use `AsyncGraphSearch` without blocking.
- **No sync-to-async wrappers**: No `run_in_executor`, no `asyncio.to_thread` — every I/O call is genuinely async.
- **Identical API surface**: `AsyncGraphSearch` has the same method signatures as `GraphSearch` (with `async`/`await`), making migration trivial.
- **Independent evolution**: Sync and async implementations can evolve independently without affecting each other.

### Negative / Tradeoffs

- **Code duplication**: ~500 LOC duplicated across sync/async pairs. Every bug fix must be applied to both sides.
- **Double the test surface**: Every sync test has an async counterpart, roughly doubling test maintenance.
- **No shared base class**: Common logic changes (e.g., scoring formula) must be updated in both `pipeline.py` and `async_pipeline.py`.
- **psycopg3 gotcha risk**: `fetchone()`/`fetchall()` being sync on `AsyncCursor` is counter-intuitive. Developers may incorrectly `await` them.

### Future Considerations

- **Code generation**: A codegen tool could generate async variants from sync implementations, reducing manual duplication.
- **`asyncio.gather` optimization**: Async pipelines could parallelize independent port calls (e.g., embedding + extraction) for better throughput.

## Alternatives Considered

| Alternative | Pros | Cons | Why Rejected |
|------------|------|------|--------------|
| **Single ABC with both sync/async methods** | No duplication | mypy errors on `async def` overriding sync `abstractmethod`; forces implementors to provide both | Technically broken with current Python typing |
| **Sync-to-async wrappers (`run_in_executor`)** | Zero code duplication | Blocks a thread pool thread per call; not truly async; worse performance than native async | Defeats the purpose of async support |
| **Mixin sharing between sync/async** | Partial DRY | Async is contagious — shared mixins force awkward dual method definitions or generic patterns | Complexity outweighs the duplication saved |
| **Full async fakes in `tests/mocks/`** | Consistent with sync test strategy | `AsyncMock` is sufficient; building full async fakes is overhead for v0.1 | Pragmatic choice — can add later if needed |

## See Also

- [ADR-006: SDK Facade](./ADR-006-sdk-facade.md) — the sync facade that this mirrors
- [ADR-002: Clean Architecture](./ADR-002-clean-architecture.md) — ABC port pattern used for async ports
- [Ports & Adapters](../ports-and-adapters.md) — all sync and async port contracts
- [Layers](../layers.md) — where async adapters and `AsyncGraphSearch` live
