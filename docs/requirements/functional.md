# Functional Requirements

> What the system must do: FR-01 through FR-09.

## Overview

depth-graph-search has ten functional requirements spanning ingestion, search, and delivery surfaces. FR-01 through FR-05 define the core pipeline behavior. FR-06 through FR-08 define the three delivery surfaces. FR-09 defines the operational baseline. FR-10 defines entity resolution during ingestion.

## Requirements Summary

| ID | Name | Description | v0.1 |
|----|------|-------------|-------|
| FR-01 | Text Ingestion | Ingest free text + metadata into the graph | ✅ |
| FR-02 | Metadata Pre-filter | Optional metadata filter before RAG | ✅ |
| FR-03 | Hybrid RAG Search | BM25 + embedding similarity, top N | ✅ |
| FR-04 | Graph Traversal | BFS expansion from entry nodes, depth M | ✅ |
| FR-05 | Search Pipeline | Configurable strategy orchestrating FR-02–FR-04 | ✅ |
| FR-06 | SDK Interface | Python importable library | ✅ |
| FR-07 | HTTP API Interface | REST service exposing ingestion and search | ✅ |
| FR-08 | CLI Interface | Command-line tool for ingestion and search | ✅ |
| FR-09 | Docker Compose | Bundled PostgreSQL for local development | Optional |
| FR-10 | Entity Resolution | Deduplicate entities during ingestion against existing graph | ✅ |

---

## FR-01 — Text Ingestion

**Description**: Accept raw text and arbitrary metadata, extract a graph, generate embeddings, and persist to the graph store.

**Input**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | `str` | Yes | Free-form text to ingest |
| `metadata` | `dict` | No | Arbitrary key-value pairs. No schema enforced. |

**Process**:

1. Pass `text` + `metadata` to `LLMProvider.extract_graph()` → returns `(list[Node], list[Edge])`
2. Pass each Node's content to `EmbeddingProvider.embed()` → `Embedding`
3. Attach `Embedding` and `metadata` to each Node
4. Persist all Nodes and Edges via `GraphRepository.save_node()` / `GraphRepository.save_edge()`

**Output**: Confirmation that nodes and edges were stored. No partial writes — if any step fails, the entire ingestion is rolled back.

**Error behavior**: See [Ingestion Flow](../flows/ingestion.md) for the three documented error paths.

---

## FR-02 — Metadata Pre-filter

**Description**: Optionally filter the graph to nodes matching a metadata condition before RAG search begins.

**Input**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `metadata_filter` | `dict` | No | Key-value conditions to filter nodes |

**Behavior**: If `metadata_filter` is `None`, this step is skipped entirely. If provided, the filter runs first and the RAG search (FR-03) operates only on the filtered node set.

**Output**: Filtered node set passed to FR-03, or full graph if no filter is given.

> **v0.1 scope**: Metadata filtering is implemented as an exact-match condition per key. Complex predicates (range, regex, OR) are not supported in v0.1.

---

## FR-03 — Hybrid RAG Search

**Description**: Given a query, return the top N most semantically relevant nodes using BM25 full-text search combined with dense vector similarity.

**Input**:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `query` | `str` | Yes | — | Search query string |
| `top_n` | `int` | No | configurable | Number of results to return |
| `metadata_filter` | `dict \| None` | No | `None` | Passed from FR-02 |

**Process**:

1. Generate query embedding via `EmbeddingProvider.embed(query)`
2. Call `GraphRepository.search_hybrid(query_embedding, query_text, top_n, metadata_filter)`
3. Returns `list[Node]` — the **entry nodes** for FR-04

**Output**: Top N nodes (entry nodes), ranked by hybrid score.

---

## FR-04 — Graph Traversal

**Description**: Starting from each entry node (FR-03 output), expand the graph using BFS up to M depth levels. Deduplicate across all expansions.

**Input**:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `entry_nodes` | `list[Node]` | Yes | — | Top N output from FR-03 |
| `depth_m` | `int` | No | configurable | BFS expansion depth |

**Process**:

1. For each entry node, call `GraphRepository.traverse_bfs(entry_nodes, depth_m)`
2. Collect all reachable nodes across all traversals
3. Deduplicate by node ID — a node reachable from multiple entry nodes appears once

**Output**: Deduplicated list of nodes with scores and graph distance attached.

---

## FR-05 — Search Pipeline

**Description**: Orchestrate FR-02 through FR-04 as a configurable strategy. The pipeline itself is a strategy — callers MAY pass an alternate pipeline name to use a different orchestration.

**Input**:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `query` | `str` | Yes | — | Search query |
| `top_n` | `int` | No | configurable | Passed to FR-03 |
| `depth_m` | `int` | No | configurable | Passed to FR-04 |
| `metadata_filter` | `dict \| None` | No | `None` | Passed to FR-02 |
| `pipeline` | `str \| None` | No | `"default"` | Named pipeline strategy to use |

**Default pipeline**: metadata pre-filter (if provided) → BM25+embeddings top N → BFS depth M → dedup → output package.

**Custom pipeline**: Callers MAY pass `pipeline="my-custom-pipeline"` to substitute the entire orchestration. The custom pipeline must implement the `SearchPipeline` port.

**Output**: `list[ScoredNode]` — deduplicated nodes with scores and BFS distances.

---

## FR-06 — SDK Interface

**Description**: Expose ingestion and search as an importable Python library. No HTTP, no subprocess.

**Behavior**:
- `from depth_graph_search import GraphSearch` (or equivalent)
- Caller instantiates with adapter configuration
- Calls `ingest(text, metadata)` and `search(query, **params)` directly

**Audience**: Python developers building applications on top of depth-graph-search.

> **v0.1 scope**: Public API surface (class names, method signatures) to be finalized during implementation. This requirement names the capability, not the exact API.

---

## FR-07 — HTTP API Interface

**Description**: Expose ingestion and search as a REST API service.

**Endpoints (minimum)**:
- `POST /ingest` — FR-01 behavior over HTTP
- `POST /search` — FR-05 behavior over HTTP, JSON body with search parameters

**Behavior**: HTTP layer is thin — no business logic. All processing delegates to the core via ports.

> **v0.1 scope**: Authentication, rate limiting, and pagination are not specified in v0.1.

---

## FR-08 — CLI Interface

**Description**: Expose ingestion and search as a command-line tool.

**Commands (minimum)**:
- `dgs ingest --text "..." --metadata '{"key": "val"}'`
- `dgs search --query "..." --top-n 5 --depth 2`

**Behavior**: CLI parses arguments, calls the core via SDK surface, prints structured output to stdout.

> **v0.1 scope**: Exact command name and flag names to be finalized during implementation.

---

## FR-09 — Docker Compose

**Description**: Provide a `docker-compose.yml` that starts a PostgreSQL instance with AGE and pgvector pre-configured for local development.

**Behavior**:
- `docker compose up` gives a ready-to-use PG connection
- Developers who already have a PostgreSQL instance MAY skip Docker and configure their connection directly via the SDK

**Optionality**: Docker Compose is a convenience, not a hard requirement. The system MUST work with any PostgreSQL instance that has AGE and pgvector installed.

> **v0.1 scope**: Docker Compose is optional. Developers MAY use their own PostgreSQL instance by passing connection parameters to the SDK adapter.

---

## FR-10 — Entity Resolution

**Description**: During ingestion, before persisting new nodes, search the existing graph for potential duplicate entities and reuse them instead of creating duplicates.

**Input**:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `extracted_nodes` | `list[Node]` | Yes | — | Nodes extracted by LLM in FR-01 |
| `strategy` | `str \| None` | No | `"default"` | Named entity resolution strategy |

**Process**:

1. For each extracted node, run the configured `EntityResolutionStrategy` against the existing graph
2. The default v0.1 strategy reuses the search pipeline (BM25 + embeddings) to find candidate matches
3. If a candidate exceeds the similarity threshold → reuse the existing node (redirect edges)
4. If no candidate matches → insert as a new node

**Output**: Resolved node list — a mix of existing (reused) and new nodes, ready for persistence.

**Relationship to FR-01**: Entity resolution is a sub-step of FR-01 (Text Ingestion). It runs after LLM extraction and embedding generation, but before graph persistence.

> **v0.1 scope**: Entity resolution is best-effort. The default strategy reuses hybrid search with a configurable similarity threshold. False negatives (missed duplicates) are expected. Custom strategies can be implemented via the `EntityResolutionStrategy` port.

---

## See Also

- [Ingestion Flow](../flows/ingestion.md) — runtime sequence for FR-01 and FR-10
- [Search Flow](../flows/search.md) — runtime sequence for FR-02 through FR-05
- [Non-Functional Requirements](./non-functional.md) — quality constraints across all FRs
- [Architecture Layers](../architecture/layers.md) — which package implements each FR
