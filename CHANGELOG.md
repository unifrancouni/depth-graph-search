# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
