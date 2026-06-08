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

> **v0.1 scope**: The default implementation will reuse the `SearchPipeline` to find candidates via hybrid search (deferred to SDD-04). `ResolvedNode` is a typed `@dataclass(frozen=True)` wrapping `(node: Node, is_new: bool, matched_id: str | None)`.

## Adapter Mapping

| Adapter | Implements | Technology | Package | Status |
|---------|------------|------------|---------|--------|
| `PostgresGraphRepository` | `GraphRepository` | PostgreSQL 17 + AGE 1.6 + pgvector | `adapters/postgres/` | ✅ Implemented (SDD-02) |
| `OpenAIProvider` | `EmbeddingProvider`, `LLMProvider` | OpenAI API | `adapters/openai/` | ✅ Implemented (SDD-03) |
| `OpenRouterProvider` | `LLMProvider` | OpenRouter API | `adapters/openrouter/` | ✅ Implemented (SDD-03) |

**Key note on `OpenAIProvider`**: It implements both `EmbeddingProvider` and `LLMProvider`. A single adapter class can implement multiple ports when the underlying service provides both capabilities.

**`OpenAIProvider` implementation notes** (SDD-03):
- Constructor accepts `api_key: str`, optional `model: str` (default `"gpt-4o"`), optional `embedding_model: str` (default `"text-embedding-3-large"`). Zero I/O.
- `embed` / `embed_batch`: single API call to `client.embeddings.create(input=[text])`. Batch orders results by `.index`.
- `extract_graph`: uses OpenAI Structured Outputs (`.parse(response_format=_ExtractionResult)`). Pydantic models are adapter-private (underscore-prefixed). First-wins dedup on entity names; edges with unknown source/target silently skipped.
- `complete`: returns `choices[0].message.content or ""`.
- All `openai.OpenAIError` exceptions caught and re-raised as `LLMError` with `__cause__` chaining.

**`OpenRouterProvider` implementation notes** (SDD-03):
- Implements `LLMProvider` only (no embedding support). Uses `openai.OpenAI(base_url="https://openrouter.ai/api/v1")`.
- `extract_graph`: uses `response_format={"type": "json_object"}` then `json.loads()` + `_ExtractionResult.model_validate()`. Raises `LLMError` on `JSONDecodeError` or validation failure.
- Pydantic models duplicated from OpenAI adapter (adapter-private by design — not shared).

**`PostgresGraphRepository` implementation notes** (SDD-02):
- Constructor accepts an open `psycopg.Connection` — the caller owns the connection lifecycle.
- `save_node` with `node.embedding = None` writes `NULL` to the DB (valid for nodes without embeddings).
- `search_hybrid` uses RRF (Reciprocal Rank Fusion, k=60) combining BM25 (GIN/FTS) and pgvector HNSW.
- `traverse_bfs` uses Cypher `[*0..depth_m]` to include entry nodes in results.
- All psycopg exceptions are caught and re-raised as `StorageError` with `__cause__` chaining.

Every port has at least one adapter. Every adapter implements at least one port. No orphan interfaces, no orphan implementations.

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
