# Ports & Adapters

> Every port interface and every adapter, with the architectural rationale.

## Overview

Ports are abstract interfaces defined in `core/ports/`. They are the only communication channel between the core and the outside world. Adapters live in `adapters/` and implement these interfaces. The core never knows which adapter is active — it only depends on the port.

This document is the authoritative reference for anyone writing a new adapter or verifying that an existing one satisfies its port interface.

## Port Interfaces

### `GraphRepository`

Manages persistence and retrieval of Nodes, Edges, and their embeddings in the graph store.

| Method | Parameters | Return Type | Description |
|--------|------------|-------------|-------------|
| `save_node` | `node: Node` | `None` | Persist a Node with its embedding and metadata. |
| `save_edge` | `edge: Edge` | `None` | Persist a directed relationship between two Nodes. |
| `get_node` | `node_id: str` | `Node \| None` | Retrieve a Node by its ID. Returns `None` if not found — callers MUST check. |
| `search_hybrid` | `query_embedding: Embedding`, `query_text: str`, `top_n: int = 5`, `metadata_filter: Metadata \| None = None` | `list[Node]` | BM25 + dense vector hybrid search. Returns top N nodes. Applies metadata pre-filter if provided. |
| `traverse_bfs` | `entry_nodes: list[Node]`, `depth_m: int = 2` | `list[Node]` | BFS traversal from each entry node, expanding up to `depth_m` levels. Returns all reachable nodes (deduplicated). |

### `EmbeddingProvider`

Generates dense vector embeddings from text.

| Method | Parameters | Return Type | Description |
|--------|------------|-------------|-------------|
| `embed` | `text: str` | `Embedding` | Generate a dense vector for the given text. |
| `embed_batch` | `texts: list[str]` | `list[Embedding]` | Batch embedding — more efficient than looping `embed`. |

### `LLMProvider`

Extracts structured entities and relationships from raw text.

| Method | Parameters | Return Type | Description |
|--------|------------|-------------|-------------|
| `extract_graph` | `text: str`, `metadata: Metadata` | `tuple[list[Node], list[Edge]]` | Given raw text and metadata, return extracted nodes and edges. |
| `complete` | `prompt: str` | `str` | General-purpose text completion. Used for prompt-based extraction fallback. |

### `SearchPipeline`

Orchestrates the full search flow. This is a strategy port — the pipeline itself is swappable.

| Method | Parameters | Return Type | Description |
|--------|------------|-------------|-------------|
| `search` | `query: str`, `top_n: int = 5`, `depth_m: int = 2`, `metadata_filter: Metadata \| None = None`, `pipeline: str \| None = None` | `list[ScoredNode]` | Execute the full search pipeline. `pipeline` names an alternate strategy; `None` means use the default. |

### `EntityResolutionStrategy`

Detects potential duplicate entities during ingestion by searching the existing graph for candidate matches.

| Method | Parameters | Return Type | Description |
|--------|------------|-------------|-------------|
| `resolve` | `nodes: list[Node]`, `threshold: float = 0.85` | `list[ResolvedNode]` | For each node, find candidates in the existing graph. Returns one `ResolvedNode` per input node — either matched to existing or marked as new. `len(result) == len(nodes)` always holds. |

> **v0.1 scope**: `DefaultEntityResolutionStrategy` reuses the `SearchPipeline` to find candidates via hybrid search (SDD-04). `ResolvedNode` is a typed `@dataclass(frozen=True)` wrapping `(node: Node, is_new: bool, matched_id: str | None)`.

### `IngestionPipeline`

Orchestrates the full ingestion flow. This is a strategy port — the pipeline itself is swappable.

| Method | Parameters | Return Type | Description |
|--------|------------|-------------|-------------|
| `ingest` | `text: str`, `metadata: Metadata \| None = None` | `IngestionResult` | Execute the full ingestion pipeline. Raises `ValidationError` on blank input; raises `IngestionError` (with `__cause__`) on port failures. |

> **v0.1 scope**: `DefaultIngestionPipeline` implements the 4-stage flow: validate → LLM extract → embed → entity resolve + edge rewire → persist → return `IngestionResult`. Empty extraction fast-paths to `IngestionResult(0, 0)` without calling `embed_batch`. Caller-supplied `metadata` is merged onto every persisted node (`{**metadata, **node.metadata}`) — node-level keys take precedence.

## Sync Adapter Mapping

| Adapter | Implements | Technology | Package | Status |
|---------|------------|------------|---------|--------|
| `PostgresGraphRepository` | `GraphRepository` | PostgreSQL 17 + AGE 1.6 + pgvector | `adapters/postgres/` | ✅ Implemented (SDD-02) |
| `OpenAIProvider` | `EmbeddingProvider`, `LLMProvider` | OpenAI API | `adapters/openai/` | ✅ Implemented (SDD-03) |
| `OpenRouterProvider` | `EmbeddingProvider`, `LLMProvider` | OpenRouter API | `adapters/openrouter/` | ✅ Implemented (SDD-03, embeddings added) |
| `DefaultSearchPipeline` | `SearchPipeline` | Pure Python Orchestrator | `adapters/search/` | ✅ Implemented (SDD-04) |
| `DefaultEntityResolutionStrategy` | `EntityResolutionStrategy` | Pure Python Orchestrator | `adapters/search/` | ✅ Implemented (SDD-04) |
| `DefaultIngestionPipeline` | `IngestionPipeline` | Pure Python Orchestrator | `adapters/ingestion/` | ✅ Implemented (SDD-05) |
| `GraphSearch` | SDK Facade | Pure Python Wiring Layer | `sdk/client.py` | ✅ Implemented (SDD-06) |

**Key note on `OpenAIProvider`**: It implements both `EmbeddingProvider` and `LLMProvider`. A single adapter class can implement multiple ports when the underlying service provides both capabilities.

**`OpenAIProvider` implementation notes** (SDD-03):
- Constructor accepts `api_key: str`, optional `model: str` (default `"gpt-4o"`), optional `embedding_model: str` (default `"text-embedding-3-large"`). Zero I/O.
- `embed` / `embed_batch`: single API call to `client.embeddings.create(input=[text])`. Batch orders results by `.index`.
- `extract_graph`: uses OpenAI Structured Outputs (`.parse(response_format=_ExtractionResult)`). Pydantic models are adapter-private (underscore-prefixed). First-wins dedup on entity names; edges with unknown source/target silently skipped.
- `complete`: returns `choices[0].message.content or ""`.
- All `openai.OpenAIError` exceptions caught and re-raised as `LLMError` with `__cause__` chaining.

**`OpenRouterProvider` implementation notes** (SDD-03, embeddings added):
- Implements both `LLMProvider` and `EmbeddingProvider`. Uses `openai.OpenAI(base_url="https://openrouter.ai/api/v1")`.
- `embed` / `embed_batch`: single API call to `client.embeddings.create()`. Batch orders results by `.index`. Uses `embedding_model` parameter (default `"openai/text-embedding-3-large"`).
- `extract_graph`: uses `response_format={"type": "json_object"}` then `json.loads()` + `_ExtractionResult.model_validate()`. Raises `LLMError` on `JSONDecodeError` or validation failure.
- All `openai.OpenAIError` exceptions caught and re-raised as `LLMError` with `__cause__` chaining.
- Pydantic models duplicated from OpenAI adapter (adapter-private by design — not shared).

**`PostgresGraphRepository` implementation notes** (SDD-02):
- Constructor accepts an open `psycopg.Connection` — the caller owns the connection lifecycle.
- `save_node` with `node.embedding = None` writes `NULL` to the DB (valid for nodes without embeddings).
- `search_hybrid` uses RRF (Reciprocal Rank Fusion, k=60) combining BM25 (GIN/FTS) and pgvector HNSW.
- `traverse_bfs` uses Cypher `[*0..depth_m]` to include entry nodes in results.
- All psycopg exceptions are caught and re-raised as `StorageError` with `__cause__` chaining.

**`DefaultSearchPipeline` implementation notes** (SDD-04):
- Constructor accepts `graph_repository: GraphRepository` and `embedding_provider: EmbeddingProvider`. Zero I/O.
- Five-step algorithm: (1) embed query, (2) hybrid search → entry nodes, (3) early-return `[]` if empty, (4) BFS expand, (5) dedup by `node.id` (entry-first, dict-based), score with rank formula `1.0 - rank / (top_n + 1)`, sort score DESC / distance ASC, return `[:top_n]`.
- BFS-only nodes receive `score=0.0, distance=1`; entry nodes receive `distance=0`.
- `pipeline` parameter accepted and silently ignored in v0.1 (no registry yet).
- `StorageError` and `LLMError` from injected ports propagate unmodified — no catch blocks.

**`DefaultEntityResolutionStrategy` implementation notes** (SDD-04):
- Constructor accepts `pipeline: SearchPipeline` (the ABC — decoupled from `DefaultSearchPipeline`). Zero I/O.
- Threshold loop: for each node, calls `pipeline.search(node.content, top_n=1, depth_m=0)`. Score `>= threshold` → `ResolvedNode(is_new=False, matched_id=...)`. Otherwise → `ResolvedNode(is_new=True, matched_id=None)`.
- `len(result) == len(nodes)` holds structurally — one `ResolvedNode` per input, always.
- `StorageError` from pipeline propagates unmodified — no catch blocks.

**`DefaultIngestionPipeline` implementation notes** (SDD-05):
- Constructor accepts all 4 port dependencies: `llm_provider: LLMProvider`, `embedding_provider: EmbeddingProvider`, `graph_repository: GraphRepository`, `entity_resolution: EntityResolutionStrategy`. No defaults — all required.
- Six-step flow: (1) validate `text.strip() == ""` → `ValidationError`; (2) `llm.extract_graph(text, metadata)` → `(nodes, edges)` — `LLMError` wrapped as `IngestionError`; empty result → `IngestionResult(0, 0)` immediately (fast-path); (3) `embedding.embed_batch([n.content for n in nodes])` → attach via `dataclasses.replace(node, embedding=emb)`; (4) `entity_resolution.resolve(nodes)` → build `id_map = {r.node.id: r.matched_id for r in resolved if not r.is_new}`; (5) rewire edges via `id_map` using `dataclasses.replace(edge, source_id=..., target_id=...)`; (6) `save_node` for `is_new=True` nodes only; `save_edge` for all rewired edges — `StorageError` wrapped as `IngestionError`.
- Metadata guarantee: caller-supplied `metadata` is merged onto every node before persistence using `{**metadata, **node.metadata}` — node-level keys take precedence over caller-supplied keys on conflict.
- All port errors use `raise IngestionError(...) from exc` — `__cause__` chain is always set.
- `dataclasses.replace()` is used throughout — frozen dataclasses are never mutated in-place.

**`GraphSearch` facade implementation notes** (SDD-06):
- Lives in `sdk/client.py`. Pure wiring layer — zero business logic.
- Constructor accepts 4 port ABCs: `graph_repository`, `embedding_provider`, `llm_provider`, `entity_resolution=None`.
- When `entity_resolution=None`: auto-builds `DefaultSearchPipeline(graph_repository, embedding_provider)` → `DefaultEntityResolutionStrategy(search_pipeline)` internally.
- Always builds `DefaultIngestionPipeline` and `DefaultSearchPipeline` from the injected ports.
- `_connection` attribute: `None` in port-injection mode (caller owns lifecycle); set to `psycopg.Connection` by classmethods.
- `close()`: only closes `_connection` when `_connection is not None` — no-op otherwise. Sets `_connection = None` after closing (idempotent).
- `ingest(text, metadata=None)` → delegates to `_ingestion_pipeline.ingest(text, metadata)` — propagates all errors unchanged.
- `search(query, top_n=5, depth_m=2, metadata_filter=None)` → delegates to `_search_pipeline.search(..., pipeline=None)` — `pipeline` param is intentionally not exposed.
- `from_openai(dsn, api_key, *, model, embedding_model, graph_name, embedding_dimensions)`: `psycopg.connect(dsn)` → `PostgresGraphRepository(conn, graph_name, embedding_dimensions)` → `repo.initialize()` → single `OpenAIProvider` for both embed+llm → `instance._connection = conn`.
- `from_openrouter(dsn, openrouter_api_key, *, openai_api_key=None, ...)`: same connection sequence. When `openai_api_key` is provided, uses `OpenAIProvider` for embeddings + `OpenRouterProvider` for LLM (mixed mode). When `openai_api_key` is absent, a single `OpenRouterProvider` serves as both LLM and embedding provider (OpenRouter-only mode).
- Context manager: `__enter__` returns `self`; `__exit__` calls `close()`.

Every port has at least one adapter. Every adapter implements at least one port. No orphan interfaces, no orphan implementations.

## Async Port Interfaces (SDD-07)

Six async port ABCs mirror the sync ports exactly. All methods are `async def @abstractmethod`. Async ABCs do NOT inherit from sync ABCs — they are parallel, independent interfaces. This avoids the mypy issue where `async def` overrides a sync `abstractmethod`.

All async ABCs live in `src/depth_graph_search/core/ports/async_ports.py`.

### `AsyncGraphRepository`

| Method | Parameters | Return Type | Description |
|--------|------------|-------------|-------------|
| `initialize` | — | `None` | Set up schema, register vector extension. Idempotent. |
| `save_node` | `node: Node` | `None` | Persist a Node with embedding and metadata. |
| `save_edge` | `edge: Edge` | `None` | Persist a directed relationship. |
| `get_node` | `node_id: str` | `Node \| None` | Retrieve a Node by ID. Returns `None` if not found. |
| `search_hybrid` | `query_embedding: list[float]`, `query_text: str`, `limit: int` | `list[Node]` | BM25 + dense vector hybrid search. |
| `traverse_bfs` | `start_node_id: str`, `max_depth: int` | `list[Node]` | BFS graph expansion. |
| `health_check` | — | `None` | Verify DB connectivity. Raises `StorageError` if the connection is down. Added SDD-08 for the HTTP health endpoint. |
| `close` | — | `None` | Close the async connection. Idempotent. |

### `AsyncEmbeddingProvider`

| Method | Parameters | Return Type | Description |
|--------|------------|-------------|-------------|
| `embed` | `text: str` | `list[float]` | Generate a dense vector for the given text. |
| `embed_batch` | `texts: list[str]` | `list[list[float]]` | Batch embedding. |

### `AsyncLLMProvider`

| Method | Parameters | Return Type | Description |
|--------|------------|-------------|-------------|
| `extract_graph` | `text: str`, `metadata: dict` | `GraphData` | Extract structured entities and relationships. |
| `complete` | `prompt: str` | `str` | General-purpose text completion. |

### `AsyncEntityResolutionStrategy`

| Method | Parameters | Return Type | Description |
|--------|------------|-------------|-------------|
| `resolve` | `entities: list[str]` | `list[Node]` | Sequential resolution — no `asyncio.gather`. |

### `AsyncIngestionPipeline`

| Method | Parameters | Return Type | Description |
|--------|------------|-------------|-------------|
| `ingest` | `text: str`, `metadata: dict` | `IngestionResult` | Execute the full async ingestion flow. Returns `IngestionResult(node_count, edge_count)`. Updated SDD-08 (was `None`). |

### `AsyncSearchPipeline`

| Method | Parameters | Return Type | Description |
|--------|------------|-------------|-------------|
| `search` | `query: str`, `top_n: int`, `depth_m: int`, `metadata_filter: dict \| None` | `list[ScoredNode]` | Execute the full async search flow with rank-based scoring. Updated SDD-08 (was `list[Node]`). |

## Async Adapter Mapping (SDD-07 / SDD-08)

| Adapter | Implements | Technology | Package | Status |
|---------|------------|------------|---------|--------|
| `AsyncPostgresGraphRepository` | `AsyncGraphRepository` | psycopg.AsyncConnection + pgvector async | `adapters/postgres/` | ✅ Implemented (SDD-07, SDD-08 `health_check`) |
| `AsyncOpenAIProvider` | `AsyncEmbeddingProvider`, `AsyncLLMProvider` | openai.AsyncOpenAI | `adapters/openai/` | ✅ Implemented (SDD-07) |
| `AsyncOpenRouterProvider` | `AsyncEmbeddingProvider`, `AsyncLLMProvider` | openai.AsyncOpenAI + OpenRouter base_url | `adapters/openrouter/` | ✅ Implemented (SDD-07, embeddings added) |
| `AsyncDefaultSearchPipeline` | `AsyncSearchPipeline` | Pure Python Async Orchestrator | `adapters/search/` | ✅ Implemented (SDD-07, SDD-08 `list[ScoredNode]`) |
| `AsyncDefaultEntityResolutionStrategy` | `AsyncEntityResolutionStrategy` | Pure Python Async Orchestrator | `adapters/search/` | ✅ Implemented (SDD-07) |
| `AsyncDefaultIngestionPipeline` | `AsyncIngestionPipeline` | Pure Python Async Orchestrator | `adapters/ingestion/` | ✅ Implemented (SDD-07, SDD-08 `IngestionResult`) |
| `AsyncGraphSearch` | Async SDK Facade | Pure Python Async Wiring Layer | `sdk/async_client.py` | ✅ Implemented (SDD-07, SDD-08 parity) |
| `FastAPI HTTP API` | HTTP Delivery Surface | FastAPI + uvicorn + pydantic-settings | `api/` | ✅ Implemented (SDD-08) |

**Critical psycopg3 async gotcha**: In psycopg3, `AsyncCursor.fetchone()` and `AsyncCursor.fetchall()` are **synchronous** methods — only `execute()` is async. The async repository calls `cursor = await conn.execute(sql)` then `cursor.fetchone()` without `await`.

**`AsyncPostgresGraphRepository` implementation notes** (SDD-07):
- Accepts an open `psycopg.AsyncConnection` — caller owns connection lifecycle.
- `initialize()` calls `await register_vector_async(conn)` (imported from `pgvector.psycopg`), loads AGE, sets `search_path`, executes schema DDL. `DuplicateSchema` suppressed via `contextlib.suppress`.
- `_row_to_node()` and `_parse_agtype_scalar()` are duplicated as instance methods (not imported from sync adapter — adapters do not import from each other).
- All `psycopg.Error` → `StorageError` with `__cause__` chaining.
- `close()` is idempotent — no error if already closed.

**`AsyncOpenAIProvider` implementation notes** (SDD-07):
- Imports `_map_extraction`, `EXTRACTION_SYSTEM_PROMPT` from sync `provider.py` within the same `adapters/openai/` package (same-package import is acceptable).
- All `openai.OpenAIError` → `LLMError` with `__cause__` chaining.

**`AsyncDefaultEntityResolutionStrategy` implementation notes** (SDD-07):
- Accepts `AsyncSearchPipeline` (not `DefaultSearchPipeline` — decoupled from concrete class).
- Sequential `await pipeline.search(entity)` per entity — deliberately avoids `asyncio.gather` for v0.1.
- `resolve([])` returns `[]` immediately without calling `search`.

**`AsyncDefaultSearchPipeline` scoring notes** (SDD-08):
- Fixed async parity: now returns `list[ScoredNode]` instead of `list[Node]`.
- Rank-based scoring identical to sync `DefaultSearchPipeline`: `score=1.0 - rank/(top_n+1)` for entry nodes (`distance=0`); `score=0.0` for BFS-only nodes (`distance=1`). Sorted by `(-score, distance)`, sliced `[:top_n]`.

**`AsyncDefaultIngestionPipeline` return type** (SDD-08):
- Fixed async parity: `ingest()` now returns `IngestionResult(node_count, edge_count)` instead of `None`.
- Empty extraction fast-path returns `IngestionResult(0, 0)`.

**`AsyncPostgresGraphRepository.health_check()` notes** (SDD-08):
- New method implementing `AsyncGraphRepository.health_check()`.
- Executes `SELECT 1` via the async connection. Raises `StorageError` on any psycopg error.
- Used by `GET /health` route to probe DB liveness without going through the full SDK stack.

**`AsyncGraphSearch` parity notes** (SDD-08):
- `search()` return annotation updated to `list[ScoredNode]` (was `list[Node]`).
- `ingest()` return annotation updated to `IngestionResult` (was `None`).
- New `repository` public property exposes the underlying `AsyncGraphRepository` for health checks.
- `health_check()` method delegates to the repository's `health_check()`.

## Why This Architecture

### The Problem with Monolithic Coupling

In a monolithic design, the search core directly calls `psycopg2` to query PostgreSQL, calls the OpenAI SDK inline, and hardcodes BM25 logic. This means:

- Swapping the vector store requires rewriting search logic.
- Testing the graph traversal requires a live database.
- Adding a new LLM provider means modifying search code.

**Any integration change risks breaking everything.**

### How Ports & Adapters Solve It

The port defines the interface. The adapter fulfills it. The core depends only on the port:

```
Core: "give me top N nodes for this query" → GraphRepository.search_hybrid()
Adapter: fulfills that interface using AGE + pgvector
Result: tomorrow's adapter could use Pinecone — core is unchanged
```

Concrete wins for depth-graph-search:

| Scenario | Without Ports | With Ports |
|----------|--------------|------------|
| Add Anthropic as LLM provider | Modify core search code | Create `AnthropicProvider` implementing `LLMProvider` |
| Test BFS traversal logic | Spin up PostgreSQL | Inject a mock `GraphRepository` |
| Swap pgvector for Pinecone | Rewrite search pipeline | Implement `PineconeRepository` |
| Run SDK locally without Docker | Must have PG running | Use an in-memory `GraphRepository` mock |

This is the core value proposition of Clean Architecture for a RAG system: **RAG integrates with many technologies. The architecture must make each technology swap cheap.**

## See Also

- [Layers](./layers.md) — package paths for every port and adapter
- [Strategies](./strategies.md) — how `SearchPipeline` orchestrates sub-strategies
- [ADR-001: PostgreSQL + AGE](./decisions/ADR-001-postgresql-age.md) — why these specific adapters
- [Functional Requirements](../requirements/functional.md) — what behavior each port must enable
