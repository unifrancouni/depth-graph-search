# ADR-002: Clean Architecture with Frozen Dataclasses and ABC Ports

- **Date**: 2026-06-06
- **Status**: accepted

## Context

depth-graph-search needs a foundational architecture that separates concerns, enforces immutability in the domain layer, and defines explicit contracts between components. The project has four layers (domain, ports, adapters, delivery) and six port interfaces that must remain stable as adapters are swapped.

Key tensions:

1. **Domain purity**: Domain entities must have zero external dependencies — no Pydantic, no SQLAlchemy, no runtime validation libraries in the core.
2. **Contract enforcement**: Adapters must explicitly declare which port they implement, with errors at class definition time if methods are missing.
3. **Identity ownership**: Entities must be valid and complete before any adapter touches them — the domain owns identity, not the database.
4. **Immutability**: Entity mutation after construction leads to subtle state bugs in pipelines where nodes flow through multiple stages.

## Decision

### Frozen dataclasses for all domain entities

Use `@dataclass(frozen=True)` from the standard library for all domain entities (`Node`, `Edge`, `Embedding`, `ScoredNode`, `ResolvedNode`, `IngestionResult`). IDs are generated domain-side via `uuid4()` as `str`, with `field(default_factory=lambda: str(uuid4()))`.

| Option | Tradeoff | Verdict |
|--------|----------|---------|
| `@dataclass(frozen=True)` | Pure stdlib, `__eq__`/`__hash__` free, IDE support, no runtime validation | **Chosen** |
| Pydantic `BaseModel` | Runtime validation + JSON serialization, but external dep in domain layer — violates dependency rule | Rejected |
| `NamedTuple` | Immutable, but positional access is fragile, no defaults without workarounds | Rejected |
| `attrs` | Similar to dataclass but external dep; adds nothing stdlib doesn't already give here | Rejected |

### ABC with `@abstractmethod` for all port interfaces

Use `ABC` + `@abstractmethod` for all six port interfaces (`GraphRepository`, `EmbeddingProvider`, `LLMProvider`, `SearchPipeline`, `EntityResolutionStrategy`, `IngestionPipeline`). Adapters inherit from the ABC explicitly.

| Option | Tradeoff | Verdict |
|--------|----------|---------|
| ABC + `@abstractmethod` | `TypeError` on direct instantiation, enforces implementation at class definition time | **Chosen** |
| `Protocol` (structural subtyping) | Duck typing — errors deferred to type-checker, no runtime enforcement | Rejected |

### Domain-side UUID generation

Entities generate their own `str(uuid4())` IDs at construction time, before any adapter interaction.

### `Metadata` as `TypeAlias`

`Metadata: TypeAlias = dict[str, Any]` — free-form key-value pairs with no fixed schema, giving a named type for annotations without runtime overhead.

## Consequences

### Positive

- **Zero domain dependencies**: `core/domain/` imports only stdlib. Pydantic, psycopg, openai — all confined to adapter layer.
- **Immutability enforced at runtime**: `node.id = "x"` raises `FrozenInstanceError`. Mutation in pipelines uses `dataclasses.replace()` to produce new instances.
- **Contract failures caught early**: Forgetting to implement an abstract method raises `TypeError` at class definition, not at runtime when the method is called.
- **Testable in isolation**: Domain entities and ports can be tested with zero setup — no database, no API keys, no mocking frameworks needed.

### Negative / Tradeoffs

- **No runtime validation in domain**: Invalid data (empty strings, wrong types) must be caught at adapter or delivery boundaries, not in entity constructors.
- **Frozen mutation overhead**: Every pipeline stage that modifies a node creates a new instance via `replace()`. For the expected data volumes, this is negligible.
- **Explicit inheritance required**: Adapters must consciously inherit from ABCs — no duck typing convenience.

### Future Considerations

- **Import linter**: Currently enforced by convention. A CI check (e.g., `import-linter`) could automate dependency rule enforcement.
- **Validation layer**: A thin validation utility at the SDK boundary could validate inputs before they reach the domain.

## Alternatives Considered

| Alternative | Pros | Cons | Why Rejected |
|------------|------|------|--------------|
| **Pydantic in domain** | Built-in validation, JSON serialization | External dependency in domain layer — violates Clean Architecture dependency rule | Domain purity is non-negotiable |
| **Protocol-based ports** | No inheritance required, structural subtyping | No runtime enforcement, errors only at type-check time, less explicit in IDE | Ports are explicit contracts — explicitness wins over convenience |
| **DB-generated IDs** | Guaranteed uniqueness via serial/UUID | Entity requires persistence before it's "complete", breaks entity independence | Domain must own identity |
| **Mutable dataclasses** | Simpler mutation in pipelines | State bugs when entities are shared across pipeline stages | Immutability prevents an entire class of bugs |

## See Also

- [Layers](../layers.md) — package-to-layer mapping showing where domain, ports, and adapters live
- [Ports & Adapters](../ports-and-adapters.md) — all six port ABC contracts with method signatures
- [ADR-001: PostgreSQL + AGE](./ADR-001-postgresql-age.md) — storage backend decision
