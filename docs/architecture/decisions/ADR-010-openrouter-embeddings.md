# ADR-010: Optional OpenAI via OpenRouter Embeddings

- **Date**: 2026-06-13
- **Status**: accepted

## Context

In [ADR-003](./ADR-003-dual-llm-providers.md), `OpenRouterProvider` was implemented as `LLMProvider`-only — embeddings required a separate `OpenAIProvider` with an OpenAI API key. This forced users who only had an OpenRouter key to also obtain an OpenAI key, creating an unnecessary barrier to entry.

OpenRouter's API is OpenAI-compatible and supports embedding models. Extending `OpenRouterProvider` to also implement `EmbeddingProvider` enables three runtime configurations:

1. **OpenAI-only**: `OpenAIProvider` handles both LLM and embeddings (existing behavior).
2. **Mixed mode**: `OpenRouterProvider` for LLM + `OpenAIProvider` for embeddings (existing behavior, backward compatible).
3. **OpenRouter-only**: Single `OpenRouterProvider` handles both LLM and embeddings (new capability).

## Decision

### Extend OpenRouterProvider with EmbeddingProvider

Add `EmbeddingProvider` to `OpenRouterProvider`'s base classes and implement `embed()` + `embed_batch()` — identical pattern to `OpenAIProvider`'s implementation. The existing `self._client` (OpenAI SDK pointed at OpenRouter's base URL) already supports `client.embeddings.create()`.

Add a new constructor parameter: `embedding_model: str = "openai/text-embedding-3-large"`.

### Make `openai_api_key` optional in factory classmethods

Change `GraphSearch.from_openrouter()` signature:

- **Before**: `openai_api_key: str` (positional, required)
- **After**: `openai_api_key: str | None = None` (keyword-only, optional)

When `openai_api_key` is provided: mixed mode (backward compatible). When absent: single `OpenRouterProvider` serves both roles — same instance passed as both `embedding_provider` and `llm_provider`.

### Make `openai_api_key` optional in config classes

Change `Settings.openai_api_key` and `CLISettings.openai_api_key` from `str` (required) to `str = ""` (optional with empty default). Update the `model_validator`:

- `LLM_PROVIDER=openai` → `OPENAI_API_KEY` required.
- `LLM_PROVIDER=openrouter` → `OPENAI_API_KEY` optional. If present, mixed mode. If absent, OpenRouter-only.

### Same-instance dual-role pattern

When in OpenRouter-only mode, a single `OpenRouterProvider` instance is passed as both `embedding_provider` and `llm_provider` to the `GraphSearch` constructor. This mirrors the existing `from_openai` pattern where a single `OpenAIProvider` serves both roles.

## Consequences

### Positive

- **No OpenAI key required for OpenRouter users**: Users with only an OpenRouter key can use the full system — ingest + search — without any OpenAI dependency.
- **Zero port interface changes**: `EmbeddingProvider` and `LLMProvider` ABCs are unchanged. The change is purely in the adapter layer.
- **Backward compatible**: Existing callers using `from_openrouter(dsn, openai_key, openrouter_key)` with keyword arguments continue to work. Mixed mode is preserved.
- **Single provider efficiency**: In OpenRouter-only mode, one client instance handles all API calls — one connection, one auth config.

### Negative / Tradeoffs

- **Positional arg breaking change**: Callers using `from_openrouter(dsn, openai_key, openrouter_key)` with positional args will break because the parameter order changed. However, existing callers in `cli/main.py` and `api/lifespan.py` already use keyword arguments.
- **Empty string vs None**: Using `str = ""` instead of `str | None = None` for config is slightly unusual, but lets Pydantic accept env vars that set it to empty.
- **Model name prefix**: OpenRouter embedding models require the `openai/` prefix (e.g., `openai/text-embedding-3-large`), which differs from direct OpenAI usage (`text-embedding-3-large`). Users must be aware of this.

### Future Considerations

- **Default embedding model per provider**: The factory could automatically prefix `openai/` to the embedding model name when using OpenRouter, eliminating the naming difference.
- **Provider auto-detection**: A single factory method could detect available API keys and choose the optimal provider configuration automatically.

## Alternatives Considered

| Alternative | Pros | Cons | Why Rejected |
|------------|------|------|--------------|
| **Standalone `OpenRouterEmbeddingProvider`** | Single-responsibility | One service = one provider class (mirrors `OpenAIProvider` pattern); duplicates client setup | Extending the existing class is consistent with established patterns |
| **`use_openrouter_embeddings: bool` flag** | Explicit intent | Adds a new concept to the API; key presence already signals intent | Simpler API — presence of key IS the decision |
| **`str | None = None` for config** | Standard Python optional | Empty string default plays better with env var handling in Pydantic settings | Minor tradeoff favoring env var ergonomics |
| **Always create two instances** | Simpler wiring code | Wastes resources; inconsistent with `from_openai` single-instance pattern | Matches existing dual-role precedent |

## See Also

- [ADR-003: Dual LLM Providers](./ADR-003-dual-llm-providers.md) — the original dual-provider decision that this extends
- [ADR-001: PostgreSQL + AGE](./ADR-001-postgresql-age.md) — mentions OpenAI + OpenRouter as LLM providers
- [Ports & Adapters](../ports-and-adapters.md) — `EmbeddingProvider` and `LLMProvider` contracts
- [Strategies](../strategies.md) — how providers plug into the Strategy Pattern
