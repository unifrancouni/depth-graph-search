# Architecture Overview

> The 30,000-ft view: system boundaries, layer dependencies, and v0.1 scope.

## Overview

depth-graph-search is a RAG library that combines hybrid vector search with graph traversal. It is built on Clean Architecture: a dependency-free core surrounded by swappable adapters. All persistence runs through a single PostgreSQL connection (relational + pgvector + AGE).

The system exposes three delivery surfaces — SDK, HTTP API, and CLI — all sharing the same core.

## System Boundaries

```mermaid
graph TD
    subgraph Delivery["Delivery Layer"]
        SDK["SDK\n(Python import)"]
        API["HTTP API\n(REST)"]
        CLI["CLI\n(command-line)"]
    end

    subgraph Adapters["Adapter Layer"]
        PG["PostgresGraphRepository\n(AGE + pgvector)"]
        OAI["OpenAIProvider\n(embeddings + LLM)"]
        ORI["OpenRouterProvider\n(LLM)"]
    end

    subgraph Core["Core Layer"]
        Ports["Ports\n(interfaces)"]
        Domain["Domain\n(entities + logic)"]
    end

    External[("PostgreSQL\n+ AGE\n+ pgvector")]

    SDK --> Ports
    API --> Ports
    CLI --> Ports
    PG --> Ports
    OAI --> Ports
    ORI --> Ports
    PG --> External

    style Core fill:#1a1a2e,color:#eee,stroke:#444
    style Adapters fill:#16213e,color:#eee,stroke:#444
    style Delivery fill:#0f3460,color:#eee,stroke:#444
```

**Dependency rule**: Core (`core/domain/`, `core/ports/`) imports ZERO adapter code. All dependencies point inward — adapters depend on ports, not the other way around.

## Clean Architecture Layers

| Layer | Responsibility | Allowed Imports |
|-------|---------------|-----------------|
| **Domain** | Entities, value objects, pure logic | Nothing — zero external deps |
| **Ports** | Abstract interfaces for I/O | Domain only |
| **Adapters** | Concrete implementations of ports | Ports, Domain, external libs |
| **Delivery** | Entry points (SDK, API, CLI) | Ports, Domain, Adapters |

The dependency rule is enforced by convention in v0.1 (no import linter yet). Any PR that makes `core/` import from `adapters/` is a hard reject.

## v0.1 Scope

> **v0.1 scope**: Architecture, domain, all 6 ports, all adapters, and the SDK delivery surface are fully implemented. The ingestion pipeline (`DefaultIngestionPipeline`) and search pipeline (`DefaultSearchPipeline`) are both production-ready. The `GraphSearch` facade (SDD-06) is the public entry point — `from depth_graph_search import GraphSearch`. `api/` and `cli/` surfaces are stubbed — deferred to SDD-07+.

**Implemented in v0.1:**
- 4 architecture docs (overview, layers, ports-and-adapters, strategies)
- 1 decision record (ADR-001: PostgreSQL + AGE)
- 2 requirements docs (functional FR-01–FR-10, non-functional)
- 2 flow docs (ingestion, search)
- Domain layer: `Node`, `Edge`, `Embedding`, `Metadata`, `ScoredNode`, `ResolvedNode`, `IngestionResult` (SDD-01, SDD-05)
- All 6 port ABCs: `GraphRepository`, `EmbeddingProvider`, `LLMProvider`, `SearchPipeline`, `EntityResolutionStrategy`, `IngestionPipeline` (SDD-01 through SDD-05)
- All adapters: `PostgresGraphRepository`, `OpenAIProvider`, `OpenRouterProvider`, `DefaultSearchPipeline`, `DefaultEntityResolutionStrategy`, `DefaultIngestionPipeline` (SDD-02 through SDD-05)
- SDK delivery surface: `GraphSearch` facade wiring all 6 ports into `ingest()` / `search()` with `from_openai` / `from_openrouter` classmethods (SDD-06)
- Reusable test mock adapters: `InMemoryGraphRepository`, `FakeLLMProvider`, `FakeEmbeddingProvider`, `FakeEntityResolutionStrategy` in `tests/mocks/` (SDD-05)
- 182 unit tests passing

**Explicitly excluded from v0.1:**
- `api/` and `cli/` delivery surfaces (SDD-06+)
- Packaging / PyPI distribution
- Performance benchmarks or SLAs
- Authentication / authorization
- Multi-tenancy

## Reading Guide

Read the docs in this order for progressive disclosure:

1. **You are here** — system shape and boundaries
2. [Layers](./layers.md) — package-level mapping of Clean Architecture
3. [Ports & Adapters](./ports-and-adapters.md) — every interface contract
4. [Strategies](./strategies.md) — the four-level Strategy Pattern
5. [ADR-001](./decisions/ADR-001-postgresql-age.md) — why PostgreSQL + AGE
6. [Functional Requirements](../requirements/functional.md) — FR-01 through FR-09
7. [Non-Functional Requirements](../requirements/non-functional.md) — quality constraints
8. [Ingestion Flow](../flows/ingestion.md) — runtime: text → graph
9. [Search Flow](../flows/search.md) — runtime: query → results

## See Also

- [Layers](./layers.md) — package-to-layer mapping
- [Ports & Adapters](./ports-and-adapters.md) — interface contracts
- [Strategies](./strategies.md) — Strategy Pattern at four levels
- [ADR-001: PostgreSQL + AGE](./decisions/ADR-001-postgresql-age.md) — technology decision record
