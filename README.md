# Depth Graph Search

**Hybrid retrieval engine that bridges semantic search and graph traversal for multi-hop, context-aware information retrieval.**

Most RAG systems stop at similarity. Depth Graph Search goes further — it navigates relationships. Instead of treating documents as isolated chunks, it models data as a connected graph, unlocking contextual reasoning across linked entities, improved recall for complex queries, and more grounded LLM outputs.

> **Status**: v0.1 — SDK (sync + async), HTTP API, and CLI are all functional.

---

## Get Started

### 1. Start the database (and API)

The engine requires PostgreSQL 17 with [Apache AGE](https://age.apache.org/) (graph) and [pgvector](https://github.com/pgvector/pgvector) (embeddings).

The fastest way is Docker Compose:

```bash
git clone https://github.com/francougarte/depth-graph-search.git
cd depth-graph-search
cp .env.example .env          # fill in API keys (OPENAI_API_KEY or OPENROUTER_API_KEY — see Configuration Reference)
docker compose up -d          # starts postgres + api (port 8000)
```

This starts a PostgreSQL instance with both extensions pre-installed, and the FastAPI service at `http://localhost:8000`. Default credentials:

| Variable | Value |
|----------|-------|
| Host | `localhost:5432` |
| User | `depth` |
| Password | `depth` |
| Database | `depth_graph` |
| DSN | `postgresql://depth:depth@localhost:5432/depth_graph` |

> Already have a compatible PostgreSQL? Skip Docker — just make sure `age` and `vector` extensions are available.

### 2. Install the SDK

```bash
pip install depth-graph-search
```

Or install from source in development mode:

```bash
pip install -e ".[dev]"
```

To include HTTP API dependencies:

```bash
pip install "depth-graph-search[api]"
# or from source:
pip install -e ".[api]"
```

To include CLI dependencies:

```bash
pip install "depth-graph-search[cli]"
# or from source:
pip install -e ".[cli]"
```

**Requirements**: Python 3.11+

### 3. Ingest and search

```python
from depth_graph_search import GraphSearch

# Option A: OpenAI for both LLM and embeddings
with GraphSearch.from_openai(
    dsn="postgresql://depth:depth@localhost:5432/depth_graph",
    api_key="sk-...",
) as gs:
    # Ingest free text — entities and relationships are extracted automatically
    result = gs.ingest("Marie Curie won the Nobel Prize in Physics in 1903.")
    print(f"Stored {result.node_count} nodes, {result.edge_count} edges")

    # Search with hybrid retrieval + graph traversal
    nodes = gs.search("Who won the Nobel Prize?", top_n=5, depth_m=2)
    for node in nodes:
        print(f"  [{node.score:.2f}] {node.node.content}")
```

```python
# Option B: OpenRouter for LLM + OpenAI for embeddings (mixed mode)
with GraphSearch.from_openrouter(
    dsn="postgresql://depth:depth@localhost:5432/depth_graph",
    openrouter_api_key="sk-or-...",
    openai_api_key="sk-...",           # optional — when provided, OpenAI handles embeddings
    openrouter_model="anthropic/claude-sonnet-4",
) as gs:
    gs.ingest("Alexander Fleming discovered penicillin in 1928.")
    nodes = gs.search("antibiotic discoveries")
```

```python
# Option C: OpenRouter for BOTH LLM and embeddings (no OpenAI key needed)
with GraphSearch.from_openrouter(
    dsn="postgresql://depth:depth@localhost:5432/depth_graph",
    openrouter_api_key="sk-or-...",
    openrouter_model="anthropic/claude-sonnet-4",
) as gs:
    gs.ingest("Alan Turing proposed the Turing test in 1950.")
    nodes = gs.search("Turing test")
```

### 4. Async usage

For async runtimes (FastAPI, asyncio apps):

```python
import asyncio
from depth_graph_search import AsyncGraphSearch

async def main():
    async with await AsyncGraphSearch.from_openai(
        dsn="postgresql://depth:depth@localhost:5432/depth_graph",
        api_key="sk-...",
    ) as gs:
        await gs.ingest("The mitochondria is the powerhouse of the cell.")
        nodes = await gs.search("cell biology", top_n=3, depth_m=1)
        for node in nodes:
            print(node.content)

asyncio.run(main())
```

### 5. HTTP API usage

When running via Docker Compose (or `uvicorn depth_graph_search.api:create_app --factory`), the HTTP API is available at `http://localhost:8000`.

```bash
# Ingest text
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"text": "Marie Curie won the Nobel Prize in Physics in 1903.", "metadata": {"source": "wiki"}}'
# → {"node_count": 2, "edge_count": 1}

# Search
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "Nobel Prize winners", "top_n": 5}'
# → {"results": [{"id": "...", "content": "...", "metadata": {}, "score": 0.833, "distance": 0}]}

# Health check
curl http://localhost:8000/health
# → {"status": "ok", "db": "connected"}
```

OpenAPI docs are available at `http://localhost:8000/docs`.

### 6. CLI usage

Install the CLI extra:

```bash
pip install "depth-graph-search[cli]"
```

Configure via environment variables (or a `.env` file) — the same vars as the HTTP API (minus `API_HOST`, `API_PORT`, `LOG_LEVEL`):

```bash
export DATABASE_URL="postgresql://depth:depth@localhost:5432/depth_graph"
export OPENAI_API_KEY="sk-..."       # optional when LLM_PROVIDER=openrouter (OpenRouter handles embeddings)
```

When using `LLM_PROVIDER=openrouter`, `OPENAI_API_KEY` is not required — OpenRouter can handle both LLM and embeddings:

```bash
export DATABASE_URL="postgresql://depth:depth@localhost:5432/depth_graph"
export LLM_PROVIDER=openrouter
export OPENROUTER_API_KEY="sk-or-..."
# No OPENAI_API_KEY needed — OpenRouter handles embeddings too
```

Then run:

```bash
# Ingest text
dgs ingest --text "Marie Curie won the Nobel Prize in Physics in 1903." --metadata '{"source": "wiki"}'
# → Ingested: 2 nodes, 1 edges

# Search
dgs search --query "Nobel Prize winners" --top-n 5 --depth 2
# → Rich table with ID / Content / Score / Distance columns

# Output as JSON
dgs search --query "Nobel Prize winners" --format json

# Output as plain text
dgs ingest --text "Fleming discovered penicillin." --format plain

# Show version
dgs version
# → dgs 0.1.0

# Override connection via flags (takes precedence over env vars)
dgs ingest --text "..." --dsn "postgresql://other@host/db" --openai-key "sk-other"
```

---

## Configuration Reference

### SDK — explicit parameters

When using the SDK directly, all configuration is passed explicitly — no env vars, no config files.

### Factory classmethods

| Parameter | Default | Description |
|-----------|---------|-------------|
| `dsn` | *required* | PostgreSQL connection string |
| `api_key` | *required* | OpenAI API key (or OpenRouter key in `from_openrouter`) |
| `model` | `"gpt-4o"` | Chat completion model for entity extraction |
| `embedding_model` | `"text-embedding-3-large"` | Embedding model |
| `graph_name` | `"knowledge_graph"` | Apache AGE graph name |
| `embedding_dimensions` | `3072` | Vector dimension (must match the embedding model) |

### Search parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `query` | *required* | Natural language search query |
| `top_n` | `5` | Number of entry-point nodes from hybrid search |
| `depth_m` | `2` | BFS traversal depth from each entry node |
| `metadata_filter` | `None` | Optional `dict` to pre-filter nodes before search |

### Ingest parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `text` | *required* | Free text to ingest |
| `metadata` | `None` | Optional `dict` attached to every node created from this text |

### CLI — environment variables

When using the `dgs` CLI, configuration is read from environment variables (or a `.env` file). The CLI reads the same core env vars as the HTTP API, minus the server-specific ones (`API_HOST`, `API_PORT`, `LOG_LEVEL`). All env vars can also be overridden via CLI flags (`--dsn`, `--openai-key`, `--model`, `--embedding-model`, `--graph-name`, `--provider`).

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | **Yes** | — | PostgreSQL DSN |
| `OPENAI_API_KEY` | Conditional | — | Required when `LLM_PROVIDER=openai`, or when using OpenAI for embeddings in mixed mode. Not required when `LLM_PROVIDER=openrouter` (OpenRouter handles embeddings). |
| `OPENROUTER_API_KEY` | Conditional | `None` | Required when `LLM_PROVIDER=openrouter` |
| `LLM_PROVIDER` | No | `openai` | `openai` or `openrouter` |
| `LLM_MODEL` | No | `gpt-4o` | Chat completion model |
| `EMBEDDING_MODEL` | No | `text-embedding-3-large` | Embedding model |
| `GRAPH_NAME` | No | `knowledge_graph` | Apache AGE graph name |
| `EMBEDDING_DIMENSIONS` | No | `3072` | Vector dimensions |

### HTTP API — environment variables

When running the HTTP API service, configuration is read from environment variables (or a `.env` file). Copy `.env.example` to `.env` and fill in the required values.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | **Yes** | — | PostgreSQL DSN (`postgresql://` or `postgresql+psycopg://`) |
| `OPENAI_API_KEY` | Conditional | — | Required when `LLM_PROVIDER=openai`, or when using OpenAI for embeddings. Not required when `LLM_PROVIDER=openrouter` (OpenRouter handles embeddings). |
| `OPENROUTER_API_KEY` | Conditional | `None` | Required when `LLM_PROVIDER=openrouter` |
| `LLM_PROVIDER` | No | `openai` | `openai` or `openrouter` |
| `LLM_MODEL` | No | `gpt-4o` | Chat completion model |
| `EMBEDDING_MODEL` | No | `text-embedding-3-large` | Embedding model |
| `GRAPH_NAME` | No | `knowledge_graph` | Apache AGE graph name |
| `EMBEDDING_DIMENSIONS` | No | `3072` | Vector dimensions (must match embedding model) |
| `API_HOST` | No | `0.0.0.0` | Uvicorn bind host |
| `API_PORT` | No | `8000` | Uvicorn bind port |
| `LOG_LEVEL` | No | `info` | Log level: `debug`, `info`, `warning`, `error` |

---

## How It Works

<p align="center">
  <img src="depth-graph-search.gif" alt="Depth Graph Search — ingestion and search flow" width="800" />
</p>

**Ingest** free text with arbitrary metadata. The engine extracts entities and relationships via LLM, resolves duplicates against the existing graph, generates embeddings, and stores everything in PostgreSQL.

**Search** with a configurable pipeline: optionally pre-filter by metadata, find the top N nodes via hybrid search (BM25 + dense embeddings), then expand M levels deep through graph adjacency. Deduplicate and return a single context package.

<details>
<summary>Mermaid diagram (text version)</summary>

```mermaid
graph LR
    subgraph Ingestion
        T["Text + Metadata"] --> LLM["LLM Extraction"]
        LLM --> ER["Entity Resolution"]
        ER --> EMB["Embeddings"]
        EMB --> PG["PostgreSQL + AGE"]
    end

    subgraph Search
        Q["Query"] --> MF{"Metadata\nFilter?"}
        MF -->|yes| PRE["Pre-filter"]
        MF -->|no| RAG
        PRE --> RAG["BM25 + Embeddings\ntop N"]
        RAG --> BFS["BFS Traversal\ndepth M"]
        BFS --> DD["Deduplicate"]
        DD --> OUT["Context Package"]
    end

    PG -.->|"serves"| Search
```

</details>

---

## Key Capabilities

| Capability | Description |
|-----------|-------------|
| **Hybrid Retrieval** | BM25 full-text + dense vector similarity for high-precision entry points |
| **Graph Traversal** | BFS expansion from entry nodes with configurable depth |
| **Entity Resolution** | Deduplicate entities during ingestion to maintain graph quality |
| **Metadata Pre-filter** | Optional metadata conditions applied before search |
| **Pipeline as Strategy** | The entire search flow is swappable — bring your own pipeline |
| **Backend Agnostic Core** | Clean Architecture with ports & adapters — swap any component |

---

## Interfaces

| Interface | Status | Description |
|-----------|--------|-------------|
| **SDK** | ✅ Available | `from depth_graph_search import GraphSearch, AsyncGraphSearch` |
| **HTTP API** | ✅ Available | `POST /ingest`, `POST /search`, `GET /health` — FastAPI + uvicorn |
| **CLI** | ✅ Available | `dgs ingest`, `dgs search`, `dgs version` — Typer + Rich |

All three share the same core — no logic duplication.

---

## Documentation

### Architecture

| Document | What you'll find |
|----------|-----------------|
| [Overview](docs/architecture/overview.md) | System boundary diagram, Clean Architecture layers, dependency rule |
| [Layers](docs/architecture/layers.md) | Layer-to-Python-package mapping, domain entities, adapters |
| [Ports & Adapters](docs/architecture/ports-and-adapters.md) | Every port interface with method signatures, adapter mapping |
| [Strategies](docs/architecture/strategies.md) | 5-level strategy hierarchy — RAG, traversal, LLM, pipeline, entity resolution |

### Decisions

| Document | What you'll find |
|----------|-----------------|
| [ADR-001: PostgreSQL + AGE](docs/architecture/decisions/ADR-001-postgresql-age.md) | Why PostgreSQL over Neo4j, why OpenAI + OpenRouter |
| [ADR-002: Clean Architecture](docs/architecture/decisions/ADR-002-clean-architecture.md) | Frozen dataclasses for entities, ABC ports, domain-side UUIDs |
| [ADR-003: Dual LLM Providers](docs/architecture/decisions/ADR-003-dual-llm-providers.md) | OpenAI + OpenRouter adapters, Structured Outputs vs json_object |
| [ADR-004: Hybrid Search Pipeline](docs/architecture/decisions/ADR-004-hybrid-search-pipeline.md) | BM25 + vector entry points, BFS graph traversal, rank-based scoring |
| [ADR-005: Ingestion Pipeline](docs/architecture/decisions/ADR-005-ingestion-pipeline.md) | Pipeline-as-port, LLM extraction, entity resolution, edge rewiring |
| [ADR-006: SDK Facade](docs/architecture/decisions/ADR-006-sdk-facade.md) | GraphSearch facade, port injection, factory classmethods, context manager |
| [ADR-007: Mirrored Sync/Async](docs/architecture/decisions/ADR-007-async-architecture.md) | Full async mirror, duplication over abstraction, AsyncGraphSearch |
| [ADR-008: HTTP API](docs/architecture/decisions/ADR-008-http-api.md) | FastAPI, pydantic-settings, lifespan pattern, app factory |
| [ADR-009: CLI Interface](docs/architecture/decisions/ADR-009-cli-interface.md) | Typer + Rich, CLISettings, three output formats |
| [ADR-010: OpenRouter Embeddings](docs/architecture/decisions/ADR-010-openrouter-embeddings.md) | Optional OpenAI key, three runtime configs |

### Requirements

| Document | What you'll find |
|----------|-----------------|
| [Functional Requirements](docs/requirements/functional.md) | FR-01 through FR-10 — ingestion, search, interfaces, entity resolution |
| [Non-Functional Requirements](docs/requirements/non-functional.md) | Extensibility, testability, portability, v0.1 scope |

### Flows

| Document | What you'll find |
|----------|-----------------|
| [Ingestion Flow](docs/flows/ingestion.md) | Sequence diagram: text > LLM > entity resolution > embeddings > graph |
| [Search Flow](docs/flows/search.md) | Sequence diagram: query > pre-filter > RAG > BFS > deduplicated output |

### Conventions

| Document | What you'll find |
|----------|-----------------|
| [Branching Strategy](docs/branching-strategy.md) | GitFlow model — branches, naming, rules |
| [Commit Convention](docs/commit-convention.md) | Conventional Commits — types, scopes, format |
| [Changelog Convention](docs/changelog-convention.md) | Keep a Changelog — categories, versioning |

---

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Language | Python 3.11+ | Ecosystem for ML/NLP, wide adoption |
| Graph + Vectors | PostgreSQL 17 + AGE + pgvector | One connection = relational + JSON + vectors + graphs |
| LLM Providers | OpenAI, OpenRouter | Industry standard + wide range including open source |
| Architecture | Clean Architecture + Strategy Pattern | Swap any component without touching the core |

---

## License

[MIT](LICENSE)
