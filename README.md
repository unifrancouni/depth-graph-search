# Depth Graph Search

**Hybrid retrieval engine that bridges semantic search and graph traversal for multi-hop, context-aware information retrieval.**

Most RAG systems stop at similarity. Depth Graph Search goes further — it navigates relationships. Instead of treating documents as isolated chunks, it models data as a connected graph, unlocking contextual reasoning across linked entities, improved recall for complex queries, and more grounded LLM outputs.

> **Status**: v0.1 in development — architecture and requirements defined, implementation next.

---

## How It Works

```mermaid
graph LR
    subgraph Ingestion
        T["📄 Text + Metadata"] --> LLM["🤖 LLM Extraction"]
        LLM --> ER["🔍 Entity Resolution"]
        ER --> EMB["📐 Embeddings"]
        EMB --> PG["🐘 PostgreSQL + AGE"]
    end

    subgraph Search
        Q["💬 Query"] --> MF{"Metadata\nFilter?"}
        MF -->|yes| PRE["🏷️ Pre-filter"]
        MF -->|no| RAG
        PRE --> RAG["⚡ BM25 + Embeddings\ntop N"]
        RAG --> BFS["🌐 BFS Traversal\ndepth M"]
        BFS --> DD["✂️ Deduplicate"]
        DD --> OUT["📦 Context Package"]
    end

    PG -.->|"serves"| Search
```

**Ingest** free text with arbitrary metadata. The engine extracts entities and relationships via LLM, resolves duplicates against the existing graph, generates embeddings, and stores everything in PostgreSQL.

**Search** with a configurable pipeline: optionally pre-filter by metadata, find the top N nodes via hybrid search (BM25 + dense embeddings), then expand M levels deep through graph adjacency. Deduplicate and return a single context package.

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

## Use It Three Ways

| Interface | For | Example |
|-----------|-----|---------|
| **SDK** | Python developers embedding search in their apps | `from depth_graph_search import GraphSearch` |
| **API** | Services consuming search over HTTP | `POST /search` |
| **CLI** | Quick ingestion and search from the terminal | `dgs search --query "..."` |

All three share the same core — no logic duplication.

---

## Quick Start

```bash
# Clone and start with Docker Compose (includes PostgreSQL + AGE)
git clone https://github.com/your-user/depth-graph-search.git
cd depth-graph-search
docker compose up -d

# Or connect to your own PostgreSQL instance via the SDK
```

> **v0.1 scope**: Docker Compose and SDK interface are in development.

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

### Requirements

| Document | What you'll find |
|----------|-----------------|
| [Functional Requirements](docs/requirements/functional.md) | FR-01 through FR-10 — ingestion, search, interfaces, entity resolution |
| [Non-Functional Requirements](docs/requirements/non-functional.md) | Extensibility, testability, portability, v0.1 scope |

### Flows

| Document | What you'll find |
|----------|-----------------|
| [Ingestion Flow](docs/flows/ingestion.md) | Sequence diagram: text → LLM → entity resolution → embeddings → graph |
| [Search Flow](docs/flows/search.md) | Sequence diagram: query → pre-filter → RAG → BFS → deduplicated output |

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
| Language | Python | Ecosystem for ML/NLP, wide adoption |
| Graph + Vectors | PostgreSQL + AGE + pgvector | One connection = relational + JSON + vectors + graphs |
| LLM Providers | OpenAI, OpenRouter | Industry standard + wide range including open source |
| Architecture | Clean Architecture + Strategy Pattern | Swap any component without touching the core |

---

## License

[MIT](LICENSE)
