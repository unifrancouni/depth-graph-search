# ADR-006: SDK Facade with Port Injection and Factory Classmethods

- **Date**: 2026-06-11
- **Status**: accepted

## Context

The six ports, six adapters, and two pipelines need a single entry point for SDK consumers. Without a facade, users would need to manually construct and wire `PostgresGraphRepository`, `OpenAIProvider`, `DefaultSearchPipeline`, `DefaultIngestionPipeline`, and `DefaultEntityResolutionStrategy` — a 10+ line setup for every usage.

Key forces:

1. **Developer experience**: The common case (ingest + search with OpenAI or OpenRouter) should be a one-liner.
2. **Testability**: The constructor must accept port ABCs directly, so tests can inject mocks without touching any adapter.
3. **Connection lifecycle**: Factory classmethods create database connections — the facade must manage their cleanup.
4. **No async coupling**: The sync facade must not share code with a future async facade. `async` is contagious in Python — inheritance or mixins would force awkward wrappers.

## Decision

### Single facade class: `GraphSearch`

`GraphSearch` in `sdk/client.py` composes all six ports into a 2-method public API (`ingest`, `search`). It is a pure wiring layer — zero business logic, all delegation.

### Port-injection constructor

```python
def __init__(
    self,
    graph_repository: GraphRepository,
    embedding_provider: EmbeddingProvider,
    llm_provider: LLMProvider,
    entity_resolution: EntityResolutionStrategy | None = None,
) -> None:
```

The constructor accepts port ABCs. Pipelines (`DefaultSearchPipeline`, `DefaultIngestionPipeline`, `DefaultEntityResolutionStrategy`) are auto-wired internally — users never need to construct them.

### Convenience factory classmethods

- `GraphSearch.from_openai(dsn, api_key, ...)` — creates connection, repository, OpenAI provider, wires everything.
- `GraphSearch.from_openrouter(dsn, openrouter_api_key, *, openai_api_key=None, ...)` — OpenRouter for LLM, optionally OpenAI for embeddings.

Factory classmethods own the connection lifecycle: they call `psycopg.connect()`, `repo.initialize()`, and store `_connection` for `close()`.

### Context manager pattern

```python
with GraphSearch.from_openai(dsn, api_key) as gs:
    gs.ingest(text)
    results = gs.search(query)
# connection closed automatically
```

`close()` only closes `_connection` when set (classmethod path). In the port-injection path, `_connection` is `None` — the caller owns lifecycle.

### No inheritance with AsyncGraphSearch

`AsyncGraphSearch` is a sibling class, not a subclass. Both are thin wiring layers — code duplication is trivial and avoids `sync_to_async` wrapper complexity.

## Consequences

### Positive

- **One-liner setup**: `with GraphSearch.from_openai(dsn, key) as gs:` — complete wiring in one call.
- **Maximally testable**: Port-injection constructor + `tests/mocks/` fakes = full unit testing with zero real infrastructure.
- **Lean constructor**: 3 required params (4 with optional entity resolution), not 6+ pipeline instances.
- **Safe cleanup**: Context manager ensures connection cleanup even on exceptions.

### Negative / Tradeoffs

- **Auto-wired pipelines are not configurable**: Users cannot inject custom `SearchPipeline` or `IngestionPipeline` implementations through the facade in v0.1. They must use the port-injection constructor to wire custom pipelines manually.
- **`search()` hides `pipeline` param**: The `pipeline` parameter exists on `SearchPipeline.search()` but is not exposed on `GraphSearch.search()` — it's silently ignored in v0.1.
- **Sibling class duplication**: `GraphSearch` and `AsyncGraphSearch` duplicate ~50 LOC of wiring logic. This is acceptable for two classes but would not scale to many variants.

### Future Considerations

- **Pipeline injection**: Adding `search_pipeline` and `ingestion_pipeline` as optional constructor params would allow custom pipeline injection without breaking the existing API.
- **Connection pooling**: Factory classmethods could accept a connection pool instead of creating single connections.

## Alternatives Considered

| Alternative | Pros | Cons | Why Rejected |
|------------|------|------|--------------|
| **No facade — manual wiring** | Maximum flexibility | Terrible DX — 10+ lines of setup for every usage | SDK consumers need a simple entry point |
| **Builder pattern** | Fluent API, step-by-step configuration | Overkill for 3-4 params; adds complexity without benefit | Constructor + classmethods cover all cases |
| **Config dataclass constructor** | Single config object | Extra type to define and maintain; doesn't simplify wiring | Direct port injection is simpler and more testable |
| **Shared base class with async** | DRY | `async` is contagious — shared base forces `sync_to_async` wrappers or awkward dual signatures | Sibling classes with trivial duplication are cleaner |

## See Also

- [ADR-002: Clean Architecture](./ADR-002-clean-architecture.md) — port ABCs that the facade composes
- [ADR-007: Mirrored Sync/Async](./ADR-007-async-architecture.md) — the async sibling facade
- [Layers](../layers.md) — SDK as delivery layer
- [Ports & Adapters](../ports-and-adapters.md) — all six port contracts composed by the facade
