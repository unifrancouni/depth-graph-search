# Non-Functional Requirements

> Quality constraints: extensibility, testability, portability, and code quality.

## Overview

depth-graph-search is a portfolio project demonstrating Clean Architecture applied to RAG systems. Its non-functional requirements reflect that goal: the system must be easy to extend, easy to test, and honest about what v0.1 does and does not guarantee.

No performance SLAs are specified. v0.1 is a proof-of-concept scope — correctness and architecture quality take precedence over throughput optimization.

## NFR Summary

| ID | Quality | Requirement | v0.1 Target |
|----|---------|-------------|-------------|
| NFR-01 | Extensibility | New strategies, providers, and adapters addable without modifying core | Enforced by port design — verified at code review |
| NFR-02 | Testability | Core domain testable without a live database | Port interfaces enable mock injection |
| NFR-03 | Portability | Any PostgreSQL instance with AGE + pgvector is a valid backend | No hard dependency on Docker |
| NFR-04 | Code Quality | Python type hints and docstrings on all public interfaces | Enforced by contribution guidelines |

---

## NFR-01 — Extensibility

**Requirement**: New strategies, LLM providers, embedding providers, and graph adapters MUST be addable without modifying any file in `core/`.

**Mechanism**: The port system. Every external capability is defined as an abstract interface in `core/ports/`. Adding a new implementation is a new file in `adapters/` — the core is untouched.

**Examples**:

| Extension | What changes | What stays the same |
|-----------|-------------|---------------------|
| Add Anthropic LLM | Create `adapters/anthropic/` implementing `LLMProvider` | All of `core/` |
| Add DFS traversal | Create a new `GraphRepository` subclass with DFS method | `core/ports/`, search pipeline logic |
| Add Pinecone vector store | Create `adapters/pinecone/` implementing `GraphRepository` | All of `core/`, all delivery surfaces |
| Add a custom search pipeline | Implement `SearchPipeline` port | Default pipeline, core orchestration logic |

**Verification**: A PR that implements a new adapter but modifies `core/domain/` or `core/ports/` to accommodate it is a design failure and must be rejected.

---

## NFR-02 — Testability

**Requirement**: The core domain logic (entities, ports, pipeline orchestration) MUST be testable without a live PostgreSQL instance, a live LLM API call, or any network I/O.

**Mechanism**: Port interfaces enable mock injection. A test can substitute a real `PostgresGraphRepository` with an in-memory mock that implements `GraphRepository`. The core logic runs against the mock.

**Consequence for architecture**: Core domain code MUST NOT create database connections, HTTP clients, or file handles. All I/O is delegated to ports. This is a hard rule — not a preference.

**Example test pattern** (pseudo-code, not implementation):

```
# Unit test for search pipeline
mock_repo = InMemoryGraphRepository()   # implements GraphRepository
mock_embed = ConstantEmbeddingProvider()  # implements EmbeddingProvider
pipeline = DefaultSearchPipeline(repo=mock_repo, embedder=mock_embed)

results = pipeline.search(query="test", top_n=3, depth_m=2)
assert len(results) > 0
# No database. No network. No Docker.
```

> **v0.1 scope**: Test suite and mock adapters are not yet implemented. This NFR defines the target — implementation follows in a subsequent change.

---

## NFR-03 — Portability

**Requirement**: The system MUST work with any PostgreSQL instance that has AGE and pgvector installed, regardless of how that instance is deployed.

**What this means**:

- No hard-coded connection strings
- Docker Compose is an optional convenience, not a runtime dependency
- A developer with their own PostgreSQL cluster can use the SDK by passing their connection parameters
- Cloud-hosted PostgreSQL (RDS, Cloud SQL, Supabase) with AGE + pgvector extensions is a valid backend

**What this does NOT mean**: Portability to other database engines (MySQL, MongoDB, SQLite) is not a goal in v0.1. PostgreSQL is the specified store. Future adapters can add other stores via the `GraphRepository` port.

---

## NFR-04 — Code Quality

**Requirement**: All public interfaces, classes, and functions MUST include Python type hints and docstrings.

**Type hints**: Every public method signature uses parameter type annotations and return type annotations. No `Any` in core code without explicit justification.

**Docstrings**: Every public class and method has a docstring describing its purpose, parameters, and return value. Format: Google style.

**Rationale**: This is a portfolio project. Code quality signals professionalism. Type hints also enable static analysis (mypy, pyright) which reduces bugs at the architecture boundary — particularly important at port definitions where the wrong type silently breaks adapters.

> **v0.1 scope**: Linting configuration (mypy, ruff, pre-commit) is not yet set up. Type hints and docstrings are a code review requirement enforced by convention.

---

## v0.1 Honesty Statement

> **v0.1 is a portfolio/proof-of-concept scope.** No performance benchmarks, no throughput guarantees, no latency SLAs.

The following are explicitly NOT specified for v0.1:

| Not Specified | Reason |
|--------------|--------|
| Query latency (p50, p99) | No load testing infrastructure yet |
| Ingestion throughput (docs/sec) | No benchmarking harness yet |
| Concurrent request capacity | No load testing yet |
| Data volume limits | Depends on PG hardware — not tested |
| Availability / uptime | Not a production deployment |

These will be specified in future NFR updates as implementation matures and benchmarks are established.

---

## See Also

- [Functional Requirements](./functional.md) — the behavioral requirements these NFRs constrain
- [Ports & Adapters](../architecture/ports-and-adapters.md) — how ports enable NFR-01 and NFR-02
- [Architecture Layers](../architecture/layers.md) — package boundaries that enforce NFR-01
