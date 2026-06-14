# ADR-008: HTTP API with FastAPI, pydantic-settings, and Lifespan

- **Date**: 2026-06-12
- **Status**: accepted

## Context

depth-graph-search needs an HTTP delivery surface for non-Python consumers and containerized deployments. The API must wrap `AsyncGraphSearch` as a thin adapter — no business logic in route handlers. Configuration must come from environment variables with validation and sensible defaults.

Key forces:

1. **Optional dependency**: SDK users should not need `fastapi` or `uvicorn` installed. API deps must be an optional extra.
2. **Testable without a running server**: The app factory pattern must support in-process testing via `httpx.AsyncClient` with `ASGITransport`.
3. **SDK lifecycle**: `AsyncGraphSearch` must be constructed once at startup and torn down on shutdown — not per-request.
4. **Domain exceptions to HTTP status codes**: `ValidationError` → 422, `IngestionError` → 500, `LLMError` → 502, `StorageError` → 503.

## Decision

### FastAPI as the framework

FastAPI for its async-native design, automatic OpenAPI docs, Pydantic integration, and dependency injection.

### App factory pattern

```python
def create_app(settings: Settings | None = None) -> FastAPI:
```

`create_app()` returns a `FastAPI` instance — no module-level `app` variable. This enables testing with different configurations and avoids import-time side effects.

### pydantic-settings for env config

`Settings(BaseSettings)` validates 11 environment variables with type checking, DSN validation, and conditional key requirements:

| Variable | Required | Default |
|----------|----------|---------|
| `DATABASE_URL` | Yes | — |
| `OPENAI_API_KEY` | Conditional | — |
| `OPENROUTER_API_KEY` | Conditional | `None` |
| `LLM_PROVIDER` | No | `openai` |
| `LLM_MODEL` | No | `gpt-4o` |
| `EMBEDDING_MODEL` | No | `text-embedding-3-large` |
| `GRAPH_NAME` | No | `knowledge_graph` |
| `EMBEDDING_DIMENSIONS` | No | `3072` |
| `API_HOST` | No | `0.0.0.0` |
| `API_PORT` | No | `8000` |
| `LOG_LEVEL` | No | `info` |

A `model_validator` enforces that `OPENROUTER_API_KEY` is required when `LLM_PROVIDER=openrouter`.

### Lifespan pattern for SDK lifecycle

`AsyncGraphSearch` is constructed in `lifespan()` (an `@asynccontextmanager`), stored in `app.state`, and torn down on shutdown. The raw database connection is also stored for the health check endpoint.

### Separate DTOs from domain entities

Request/response schemas are Pydantic `BaseModel` classes in `api/schemas.py` — not domain dataclasses. Domain entities expose internal fields (e.g., `embedding`) that should not leak into the API contract.

### Exception handlers

Registered via `register_exception_handlers(app)`:

| Domain Exception | HTTP Status | Response Body |
|-----------------|-------------|---------------|
| `ValidationError` | 422 | `{"detail": str(exc)}` |
| `IngestionError` | 500 | `{"detail": "Ingestion failed"}` |
| `LLMError` | 502 | `{"detail": "LLM service error"}` |
| `StorageError` | 503 | `{"detail": "Storage service unavailable"}` |

### Health check with direct DB probe

`GET /health` executes `SELECT 1` on the raw psycopg connection, not through `AsyncGraphSearch`. Health must work even if SDK wiring fails.

### Optional extras packaging

```toml
[project.optional-dependencies]
api = ["fastapi>=0.115", "uvicorn[standard]>=0.30", "pydantic-settings>=2.0"]
```

## Consequences

### Positive

- **Zero business logic in routes**: Route handlers call `await gs.ingest()` or `await gs.search()` and map results to DTOs — nothing else.
- **Testable without server**: `httpx.AsyncClient(transport=ASGITransport(app=create_app(settings)))` enables full integration testing in-process.
- **Validated configuration**: Typos in env vars or missing required keys fail fast at startup with clear error messages.
- **Containerizable**: `Dockerfile` + `docker-compose.yml` provide a production-ready deployment path.

### Negative / Tradeoffs

- **Three-layer fix for async parity**: This SDD also fixed `AsyncSearchPipeline` and `AsyncIngestionPipeline` return types to match sync behavior (`list[ScoredNode]` and `IngestionResult` respectively). This was a type parity bug, not an API concern.
- **Health check accesses internal `_repository._conn`**: Reaching into SDK internals for the health probe is fragile. A dedicated health method on `AsyncGraphSearch` would be cleaner.
- **No authentication**: v0.1 has no auth — appropriate for local/development use, not production.

### Future Considerations

- **Authentication middleware**: JWT or API key auth as FastAPI middleware.
- **Rate limiting**: Per-endpoint rate limits for production deployments.
- **WebSocket streaming**: Streaming search results as they're found, rather than waiting for the full pipeline.

## Alternatives Considered

| Alternative | Pros | Cons | Why Rejected |
|------------|------|------|--------------|
| **Module-level `app = FastAPI()`** | Simpler | Not testable with different configs; import-time side effects | Factory pattern is standard for testable FastAPI apps |
| **Reuse domain dataclasses as response models** | Less code | Exposes internal fields (`embedding`); domain types shouldn't be coupled to HTTP contract | DTO separation is the right architectural choice |
| **Bundle API deps with core** | Simpler install | Forces `fastapi`/`uvicorn` on SDK-only users | Optional extras keep the core install light |
| **Flask or Starlette** | Simpler, fewer features | No automatic OpenAPI docs, no built-in Pydantic integration, less async support | FastAPI provides more value with similar complexity |

## See Also

- [ADR-007: Mirrored Sync/Async](./ADR-007-async-architecture.md) — `AsyncGraphSearch` that the API wraps
- [ADR-006: SDK Facade](./ADR-006-sdk-facade.md) — the facade pattern that the API delegates to
- [Ports & Adapters](../ports-and-adapters.md) — port contracts used by the underlying SDK
- [Layers](../layers.md) — API as delivery layer
