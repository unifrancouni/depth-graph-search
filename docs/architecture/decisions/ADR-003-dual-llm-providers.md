# ADR-003: Dual LLM Provider Strategy (OpenAI + OpenRouter)

- **Date**: 2026-06-08
- **Status**: accepted

## Context

depth-graph-search requires two LLM capabilities: entity extraction (converting free text into graph nodes and edges) and text embedding (generating dense vectors for semantic search). Different users have different API access: some have OpenAI keys, others prefer OpenRouter for access to open-source models or zero-cost experimentation.

Key forces:

1. **Single adapter, multiple roles**: OpenAI provides both LLM and embeddings; the adapter should implement both ports without unnecessary class splitting.
2. **Extraction reliability**: Structured output parsing must be robust — LLMs return noisy, sometimes invalid JSON.
3. **Adapter isolation**: Each adapter owns its parsing logic. Shared models between adapters create coupling that complicates independent evolution.
4. **Error transparency**: All API failures must surface as domain exceptions (`LLMError`) with the original exception chained as `__cause__`.

## Decision

Two adapter classes implementing the `LLMProvider` and `EmbeddingProvider` port ABCs:

| Adapter | Ports Implemented | Extraction Strategy | Client |
|---------|------------------|-------------------|--------|
| `OpenAIProvider` | `LLMProvider` + `EmbeddingProvider` | Pydantic Structured Outputs (`.parse()`) | `openai.OpenAI` |
| `OpenRouterProvider` | `LLMProvider` only (extended to `EmbeddingProvider` in [ADR-010](./ADR-010-openrouter-embeddings.md)) | `json_object` mode + `json.loads()` + `model_validate()` | `openai.OpenAI` with `base_url="https://openrouter.ai/api/v1"` |

### Extraction parsing approach

- **OpenAI**: Uses `.parse(response_format=ExtractionResult)` — the SDK auto-validates the response against a Pydantic schema and returns a typed `.parsed` attribute. Model refusals are detected via `message.refusal`.
- **OpenRouter**: Uses `response_format={"type": "json_object"}` since OpenRouter does not support Structured Outputs. Response is parsed via `json.loads()` then validated with `ExtractionResult.model_validate()`.

### Pydantic models are adapter-private

Each adapter defines identical `ExtractionResult`, `ExtractionEntity`, and `ExtractionRelationship` Pydantic models inside its own `provider.py`. They are duplicated by design — adapters don't import from each other.

### Unknown entity references in relationships are silently skipped

When the LLM produces a relationship referencing an entity name that doesn't exist in the extracted entities list, the edge is dropped. This is safer than raising an error (LLM output is inherently noisy) or inventing missing nodes.

## Consequences

### Positive

- **Zero new dependencies for OpenRouter**: Reuses the `openai` SDK with a different `base_url` — same client, same patterns.
- **Type-safe extraction with OpenAI**: `.parse()` guarantees the response matches the Pydantic schema or raises a clear error.
- **Independent adapter evolution**: If OpenRouter adds Structured Outputs support, only its adapter changes. OpenAI adapter is untouched.
- **Graceful degradation**: Noisy LLM output (hallucinated entity names) results in fewer edges, not crashes.

### Negative / Tradeoffs

- **Duplicated code**: `_map_extraction()` (~25 LOC) and Pydantic models are identical in both adapters. This is deliberate — adapter isolation over DRY.
- **OpenRouter extraction is less reliable**: `json_object` mode is weaker than Structured Outputs. Invalid JSON or schema mismatches are caught but can't be prevented at the API level.
- **OpenRouter was LLM-only in this SDD**: Embeddings were added later (see [ADR-010](./ADR-010-openrouter-embeddings.md)).

### Future Considerations

- **Additional providers**: Adding Anthropic, Cohere, or local Ollama is a new adapter implementing `LLMProvider` — no core changes.
- **Retry logic**: v0.1 has no retry on transient API failures. A decorator or middleware pattern could add this without touching adapter internals.

## Alternatives Considered

| Alternative | Pros | Cons | Why Rejected |
|------------|------|------|--------------|
| **LiteLLM** | Unified API for 100+ providers | Extra dependency, abstracts away provider-specific features (Structured Outputs) | Loses type-safe parsing; overkill when two adapters suffice |
| **Separate `OpenAIEmbedder` + `OpenAIExtractor`** | Single-responsibility per class | Contradicts architecture docs ("single adapter can implement multiple ports"), harder wiring | Architecture explicitly allows multi-port adapters |
| **Shared Pydantic models in `adapters/_shared/`** | DRY | Premature coupling — if schemas diverge (different field names per provider), shared models become a liability | Adapter isolation is more valuable than avoiding ~50 LOC duplication |
| **Prompt-only extraction (no `json_object` mode)** | Works with any model | Unreliable — models often wrap JSON in markdown fences or add explanatory text | Too fragile for production use |

## See Also

- [ADR-001: PostgreSQL + AGE](./ADR-001-postgresql-age.md) — mentions the dual-provider strategy in its LLM section
- [ADR-010: OpenRouter Embeddings](./ADR-010-openrouter-embeddings.md) — extends OpenRouter to support embeddings
- [Ports & Adapters](../ports-and-adapters.md) — `LLMProvider` and `EmbeddingProvider` contracts
- [Strategies](../strategies.md) — how LLM providers plug into the Strategy Pattern
