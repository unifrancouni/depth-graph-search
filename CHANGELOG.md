# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added (SDD-06 — SDK Facade)

- **SDD-06 — SDK Facade**: `GraphSearch` is the high-level public entry point for the SDK — wires all 6 ports into a 2-method public API (`ingest`, `search`); `from_openai` and `from_openrouter` classmethods handle real-world wiring; context manager pattern recommended for connection cleanup; 28 new unit tests — all 182 unit tests passing
- `sdk/client.py` — `GraphSearch` class (~230 LOC): pure wiring layer, zero business logic; `__init__` accepts `graph_repository`, `embedding_provider`, `llm_provider`, `entity_resolution=None`; auto-builds `DefaultSearchPipeline` → `DefaultEntityResolutionStrategy` (when `entity_resolution=None`) → `DefaultIngestionPipeline`; `_connection = None` in port-injection mode (caller owns lifecycle)
- `sdk/client.py` — `GraphSearch.from_openai(dsn, api_key, *, model, embedding_model, graph_name, embedding_dimensions)`: `psycopg.connect(dsn)` → `PostgresGraphRepository` → `initialize()` → single `OpenAIProvider` for embed+llm; stores `_connection` for `close()`
- `sdk/client.py` — `GraphSearch.from_openrouter(dsn, openai_api_key, openrouter_api_key, *, ...)`: `OpenAIProvider` for embeddings, `OpenRouterProvider` for LLM; same connection lifecycle
- `sdk/client.py` — `ingest(text, metadata=None) -> IngestionResult`: delegates to `_ingestion_pipeline.ingest()`; errors propagate unchanged
- `sdk/client.py` — `search(query, top_n=5, depth_m=2, metadata_filter=None) -> list[ScoredNode]`: delegates to `_search_pipeline.search(..., pipeline=None)`; `pipeline` param intentionally not exposed
- `sdk/client.py` — `close()`: closes `_connection` only when set (idempotent, no-op in port-injection mode); `__enter__`/`__exit__` context manager
- `sdk/__init__.py` — `GraphSearch` added to imports and `__all__`
- `src/depth_graph_search/__init__.py` — `GraphSearch` added to top-level imports and `__all__`
- `tests/unit/sdk/__init__.py` — empty package init for new test package
- `tests/unit/sdk/test_client.py` — 28 unit tests: constructor wiring, auto-entity-resolution, ingest/search delegation, error propagation (StorageError/IngestionError/LLMError), close() variants, context manager, from_openai construction order + single provider + embedding_dimensions/graph_name threading, from_openrouter split providers, top-level import
- **182 total tests passing** (28 new SDK facade tests + 154 pre-existing; 0 failed, 0 skipped)

---

### Added (SDD-05 — Ingestion Pipeline + Mocks + Tests)

- **SDD-05 — Ingestion Pipeline + Mocks + Tests**: `DefaultIngestionPipeline` completes the ingestion port, `IngestionResult` domain value object added, 4 ABC-compliant mock adapters created, 18 new unit tests — all 152 unit tests passing
- `core/domain/entities.py` — `IngestionResult` frozen dataclass (`node_count: int`, `edge_count: int`) added alongside `ScoredNode` and `ResolvedNode`; reusable across SDK/API/CLI
- `core/ports/ingestion_pipeline.py` — `IngestionPipeline` ABC with `ingest(text, metadata=None) -> IngestionResult`; raises `ValidationError` (blank input) or `IngestionError` (port failures)
- `core/ports/__init__.py` — `IngestionPipeline` added to exports
- `adapters/ingestion/pipeline.py` — `DefaultIngestionPipeline` (110 LOC): implements 4-stage flow: validate → `llm.extract_graph()` → `embedding.embed_batch()` + `dataclasses.replace()` → `entity_resolution.resolve()` + id_map edge rewiring → `save_node` (is_new=True only) + `save_edge` → `IngestionResult`; all port errors wrapped as `IngestionError(cause=exc)` via `raise ... from exc`; empty extraction fast-path returns `IngestionResult(0, 0)` immediately; metadata defaults to `{}` when `None`
- `adapters/ingestion/__init__.py` — re-exports `DefaultIngestionPipeline`
- `sdk/__init__.py` — now exports `DefaultIngestionPipeline` and `DefaultSearchPipeline` (SDK surface activated)
- `src/depth_graph_search/__init__.py` — `IngestionPipeline`, `DefaultIngestionPipeline`, `IngestionResult`, `DefaultSearchPipeline` added to top-level `__all__`
- `tests/mocks/__init__.py` — new package; re-exports all 4 fakes
- `tests/mocks/graph_repository.py` — `InMemoryGraphRepository(GraphRepository)`: dict-backed `_nodes`/`_edges`; `save_node`, `save_edge`, `get_node`, `search_hybrid` (preset via `set_search_results`), `traverse_bfs` (stub → `[]`); `set_error(exc)` error injection; `call_count(method)` / `calls(method)` tracking
- `tests/mocks/llm_provider.py` — `FakeLLMProvider(LLMProvider)`: preset via `set_extraction(nodes, edges)`; stub `complete`; error injection + call tracking
- `tests/mocks/embedding_provider.py` — `FakeEmbeddingProvider(EmbeddingProvider)`: preset via `set_embeddings([emb1, ...])` with fallback repeat; error injection + call tracking
- `tests/mocks/entity_resolution.py` — `FakeEntityResolutionStrategy(EntityResolutionStrategy)`: three modes — `set_all_new()`, `set_all_matched(matched_id)`, `set_custom(resolved_nodes)`; error injection + call tracking
- `tests/unit/conftest.py` — shared fixtures (`fake_llm`, `fake_embedder`, `fake_repo`, `fake_resolver`, `pipeline`) + entity factories (`make_node`, `make_edge`, `make_embedding`)
- `tests/unit/test_ingestion_pipeline.py` — 18 unit tests covering: ABC compliance, missing dependency TypeError, empty/whitespace ValidationError, valid text accepted, happy path full flow (2 nodes 1 edge), embed_batch contents, empty extraction zero result, metadata forwarding, matched entity edges rewired, matched entity not saved, new entity saved, LLM error no writes, storage error propagation, IngestionResult immutability, result counts match, top-level import
- **Post-verify fixes** (W-01 + W-02): spec updated to document empty-extraction fast-path as correct behavior (`embed_batch` NOT called on empty extraction); `DefaultIngestionPipeline` now guarantees caller `metadata` is merged onto every node via `{**metadata, **node.metadata}` before persistence — 2 additional tests added
- **154 total tests passing** (20 new ingestion tests + 134 pre-existing; 0 failed, 0 skipped)

---

### Added (SDD-04 — Search Pipeline + Entity Resolution)

- **SDD-04 — Search Pipeline + Entity Resolution** (`src/depth_graph_search/adapters/search/`): two pure-Python orchestrator adapters closing the last two open ports — all 5 ABCs now have concrete implementations
- `adapters/search/pipeline.py` — `DefaultSearchPipeline` (116 LOC): implements `SearchPipeline`; five-step algorithm: embed query → hybrid search → early-return if empty → BFS expand → dedup by `node.id` (entry-first) → rank-score formula `1.0 - rank / (top_n + 1)` → sort score DESC / distance ASC → return `[:top_n]`; BFS-only nodes receive `score=0.0, distance=1`; `pipeline` parameter accepted and silently ignored; zero catch blocks — `StorageError`/`LLMError` propagate unmodified
- `adapters/search/entity_resolution.py` — `DefaultEntityResolutionStrategy` (77 LOC): implements `EntityResolutionStrategy`; wraps a `SearchPipeline` ABC (decoupled from concrete class); for each node calls `pipeline.search(node.content, top_n=1, depth_m=0)`; score `>= threshold` → `ResolvedNode(is_new=False, matched_id=...)`; otherwise → `ResolvedNode(is_new=True, matched_id=None)`; `len(result) == len(nodes)` holds structurally; zero catch blocks
- `adapters/search/__init__.py` — exports `DefaultSearchPipeline`, `DefaultEntityResolutionStrategy`
- `tests/unit/adapters/test_search_pipeline.py` — 18 unit tests: constructor (stored deps, isinstance, no side effects), happy path (scored nodes, distance-0 entry, distance-1 BFS, top_n cap), empty/edge cases (empty result, skips BFS, depth_m=0), scoring/ordering (rank-0=1.0, rank-1≈0.833, score-DESC/distance-ASC, metadata_filter passthrough), deduplication (entry-first wins), error propagation (StorageError, LLMError)
- `tests/unit/adapters/test_entity_resolution.py` — 12 unit tests: constructor (stored pipeline, isinstance), matching (above threshold → not new, below → new, empty result → new), edge cases (empty input, pipeline never called, output order, len invariant, threshold=0.0, threshold=1.0), error propagation (StorageError)
- **134 total tests passing** (30 new search adapter tests + 104 pre-existing; 19 integration errors — Docker not running, pre-existing SDD-02 condition)
- **100% code coverage** on `adapters/search/` (44/44 statements)

---

### Added (SDD-03 — OpenAI + OpenRouter LLM Adapters)

- **SDD-03 — OpenAI + OpenRouter LLM Adapters** (`src/depth_graph_search/adapters/openai/`, `src/depth_graph_search/adapters/openrouter/`): two concrete LLM adapter implementations completing the adapter layer for all currently specified ports
- `adapters/openai/provider.py` — `OpenAIProvider` (~220 LOC): implements both `EmbeddingProvider` and `LLMProvider`; `embed`, `embed_batch` (single batched API call, index-ordered), `extract_graph` (Structured Outputs via `.parse(response_format=_ExtractionResult)`), `complete`; all `openai.OpenAIError` wrapped as `LLMError`
- `adapters/openai/__init__.py` — exports `OpenAIProvider`
- `adapters/openrouter/provider.py` — `OpenRouterProvider` (~190 LOC): implements `LLMProvider` only; uses OpenAI SDK with `base_url="https://openrouter.ai/api/v1"`; `extract_graph` uses `json_object` + `json.loads()` + Pydantic `model_validate()`; `complete` delegates to chat completions
- `adapters/openrouter/__init__.py` — exports `OpenRouterProvider`
- `tests/unit/adapters/test_openai_provider.py` — 25 unit tests: constructor (default/custom models, isinstance checks, no HTTP), embed, embed_batch (index ordering), extract_graph (happy path, empty, unknown entity, refusal, API errors), complete
- `tests/unit/adapters/test_openrouter_provider.py` — 18 unit tests: constructor (base_url verified, not EmbeddingProvider), extract_graph (valid JSON, empty, malformed JSON, missing keys, API errors), complete
- **104 total tests passing** (43 new LLM adapter tests + 61 pre-existing; 0 failed, 0 skipped)

### Changed (SDD-03)

- `pyproject.toml` — added runtime deps (`openai>=1.0`, `pydantic>=2.0`); added `[[tool.mypy.overrides]]` for `openai.*` to suppress missing stubs

---

### Added (SDD-02 — PostgreSQL + AGE + pgvector Adapter)

- **SDD-02 — PostgreSQL + AGE + pgvector Adapter** (`src/depth_graph_search/adapters/postgres/`): first concrete `GraphRepository` implementation enabling full read/write/search/traverse lifecycle
- `adapters/postgres/repository.py` — `PostgresGraphRepository` (414 LOC): dual-write SQL `nodes` table + AGE graph topology; all 5 `GraphRepository` ABC methods (`save_node`, `save_edge`, `get_node`, `search_hybrid`, `traverse_bfs`)
- `adapters/postgres/schema.sql` — DDL: `nodes` table (6 cols), HNSW index (pgvector), GIN FTS index, GIN metadata index; `CREATE EXTENSION IF NOT EXISTS age/vector`
- `Dockerfile.dev` — `FROM apache/age:release_PG17_1.6.0` with `postgresql-17-pgvector`; implements FR-09
- `docker-compose.yml` — postgres service on 5432:5432 with `pg_isready` healthcheck, named `pgdata` volume
- `docker-init.sql` — extension initialization script (AGE + pgvector)
- `tests/unit/adapters/test_postgres_repository.py` — 28 unit tests: constructor, `_row_to_node`, `_parse_agtype_scalar`, dimension validation, error wrapping, edge validation
- `tests/integration/adapters/test_postgres_repository.py` — 10 integration tests via testcontainers: initialize idempotent, node roundtrip, upsert, edge + BFS, hybrid search, metadata filter
- `tests/integration/conftest.py` — session-scoped Docker container fixture, function-scoped connection + repository fixtures
- `psycopg[binary]>=3.1` and `pgvector>=0.3` runtime dependencies; `testcontainers[postgres]>=4.0` dev dependency
- **61 total tests passing** (28 adapter unit + 33 domain from SDD-01; 0 failed, 0 skipped)

### Changed (SDD-02)

- `pyproject.toml` — added runtime deps (`psycopg[binary]`, `pgvector`) and dev dep (`testcontainers[postgres]`); added `[[tool.mypy.overrides]]` for `pgvector.*` stubs

---

### Added (SDD-01 — Foundation)

- **SDD-01 — Foundation** (`src/depth_graph_search/`): installable Python package with UV, `src/` layout, Python >=3.11
- `pyproject.toml` — UV project config with dev tooling: pytest >=8, pytest-cov >=5, mypy >=1.10 (strict), ruff >=0.4
- `core/domain/entities.py` — six domain types: `Node`, `Edge`, `Embedding`, `Metadata` (TypeAlias), `ScoredNode`, `ResolvedNode` — all `@dataclass(frozen=True)`, zero external dependencies
- `core/domain/exceptions.py` — exception hierarchy: `DepthGraphSearchError` base + `IngestionError`, `ValidationError`, `StorageError`, `LLMError`
- `core/ports/graph_repository.py` — `GraphRepository` ABC: `save_node`, `save_edge`, `get_node`, `search_hybrid`, `traverse_bfs`
- `core/ports/embedding_provider.py` — `EmbeddingProvider` ABC: `embed`, `embed_batch`
- `core/ports/llm_provider.py` — `LLMProvider` ABC: `extract_graph`, `complete`
- `core/ports/search_pipeline.py` — `SearchPipeline` ABC: `search` (defaults: `top_n=5`, `depth_m=2`)
- `core/ports/entity_resolution.py` — `EntityResolutionStrategy` ABC: `resolve` (default: `threshold=0.85`)
- Stub `__init__.py` files for `adapters/`, `sdk/`, `api/`, `cli/` (implementations deferred to SDD-02+)
- 33 unit tests in `tests/unit/domain/test_entities.py` — all passing (0.04s)
- Project architecture documentation (`docs/architecture/`)
- Functional and non-functional requirements (`docs/requirements/`)
- Ingestion and search flow documentation (`docs/flows/`)
- ADR-001: PostgreSQL + AGE as graph backend
- Changelog convention documentation (`docs/changelog-convention.md`)
- GitFlow branching strategy documentation (`docs/branching-strategy.md`)
- Conventional Commits convention documentation (`docs/commit-convention.md`)
- FR-10: Entity resolution during ingestion — deduplication against existing graph
- Entity resolution as fifth strategy level in architecture
- `docs-sync` project skill for automatic documentation synchronization after SDD archive
