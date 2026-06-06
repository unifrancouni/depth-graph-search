# ADR-001: PostgreSQL + AGE as the Unified Storage Backend

- **Date**: 2026-06-05
- **Status**: accepted

## Context

depth-graph-search requires three distinct data capabilities simultaneously:

1. **Vector similarity search** — dense embeddings for semantic retrieval (pgvector)
2. **Graph storage and traversal** — nodes, edges, BFS expansion (Apache AGE)
3. **Metadata filtering** — arbitrary key-value pairs attached to nodes, queryable before RAG

The dominant alternative for graph-native storage is Neo4j. The dominant alternative for vector search is a dedicated vector database (Pinecone, Weaviate, Qdrant). Using them together means:

- Multiple network connections and connection pools
- Multiple authentication configurations
- Multiple driver libraries in the dependency tree
- Multiple failure modes to handle
- Transactions that span two stores (eventual consistency problems)

For a portfolio-grade RAG system where extensibility and simplicity are first-class properties, this multiplicity is a liability.

## Decision

Use **PostgreSQL** as the single external store, extended with:

| Extension | Capability | Replaces |
|-----------|-----------|---------|
| **Apache AGE** | Property graph model, Cypher queries, BFS traversal | Neo4j |
| **pgvector** | Dense vector storage, cosine/L2/dot similarity search | Pinecone, Weaviate |
| **Built-in FTS** | BM25-style full-text search via `tsvector` | Elasticsearch |

**One connection. One authentication config. One transaction scope. Three capabilities.**

### Why PostgreSQL + AGE over Neo4j

| Criterion | PostgreSQL + AGE | Neo4j |
|-----------|-----------------|-------|
| Vector search | Native via pgvector | Requires separate store or plugin |
| Relational joins | Native SQL | Not supported |
| JSON/document storage | Native `jsonb` | Limited |
| Single connection | Yes | No — separate from vector store |
| License | Open source (PG: PostgreSQL License, AGE: Apache 2.0) | Community edition with commercial limits |
| Operational complexity | One service | One service per capability |

**The decisive factor**: pgvector + AGE in one PG instance gives vector search AND graph traversal on a shared data set, with ACID transactions. Neo4j + a separate vector store does not.

Additionally, because nodes are rows in PostgreSQL, future capabilities are already within reach without adding new dependencies:
- Metadata stored as `jsonb` → already queryable via SQL
- Relational table search → plain SQL joins
- JSON document retrieval → `jsonb` path expressions

PostgreSQL is the shortest path to everything in one.

### Why OpenAI + OpenRouter as LLM Providers

Two providers are included in v0.1, covering different user profiles:

| Provider | Role | Rationale |
|----------|------|-----------|
| **OpenAI** | Primary — embeddings + LLM extraction | Industry standard. Most developers already have API access. Best model coverage for extraction quality. |
| **OpenRouter** | Alternative — LLM extraction | Aggregates 100+ models including open-source and free-tier options. Enables zero-cost experimentation. |

Both providers implement the `LLMProvider` port. `OpenAIProvider` additionally implements `EmbeddingProvider`. Adding Anthropic, Cohere, or a local Ollama server is a new adapter — no core changes required.

## Consequences

### Positive

- **Single connection**: One `psycopg2` (or `asyncpg`) connection handles graphs, vectors, and metadata. No connection multiplexing.
- **Transactional safety**: Node + edge + embedding writes are in one ACID transaction. No partial-write inconsistency between stores.
- **Developer experience**: `docker-compose.yml` starts one service. One credential to manage. One log stream to watch.
- **Extensibility already in place**: `jsonb` metadata + relational capability means future search modes (document, relational) require only new `GraphRepository` methods, not new infrastructure.

### Negative / Tradeoffs

- **AGE maturity**: Apache AGE is younger than Neo4j. Cypher compatibility is good but not 100%. Complex graph algorithms available in Neo4j's APOC library are not available in AGE.
- **Operational familiarity**: Teams experienced with Neo4j will face a learning curve with AGE's Cypher dialect.
- **Scale ceiling**: For multi-billion-node graphs, a purpose-built graph database may outperform AGE. For portfolio/PoC scope, this is irrelevant.

### Future Considerations

- **ADR-002** (planned): LLM strategy expansion — structured comparison of provider capabilities as usage data accumulates.
- **JSON document search**: Adding a `search_documents` method to `GraphRepository` that queries `jsonb` metadata requires zero new infrastructure.
- **Relational table search**: If structured data sources are ingested, a `search_relational` method can use standard SQL on the same PG connection.
- **Alternative graph backends**: A `Neo4jGraphRepository` implementing `GraphRepository` can be contributed without touching core logic, if a team prefers Neo4j.

## Alternatives Considered

| Alternative | Pros | Cons | Why Rejected |
|------------|------|------|--------------|
| **Neo4j + Pinecone** | Mature graph DB; specialized vector search | Two services, two connections, no transactions across both, higher operational complexity | Violates "one connection" constraint; adds driver and auth complexity |
| **Neo4j + pgvector** | Mature graph DB; PG for vectors | Still two services; Neo4j license limits for commercial use | Same split-connection problem |
| **Weaviate** | Vectors + basic graph-like references | Graph traversal is limited; no relational queries | Not a true property graph; BFS traversal not native |
| **Qdrant** | High-performance vector search | No graph support; requires separate graph store | Same split-connection problem |
| **SQLite + networkx** | Zero setup for PoC | Not production-ready; no vector search | Not appropriate for a portfolio-quality architecture |

## See Also

- [Ports & Adapters](../ports-and-adapters.md) — `GraphRepository`, `EmbeddingProvider`, `LLMProvider` contracts
- [Layers](../layers.md) — where `PostgresGraphRepository`, `OpenAIProvider`, `OpenRouterProvider` live
- [Strategies](../strategies.md) — how LLM providers plug into the Strategy Pattern
