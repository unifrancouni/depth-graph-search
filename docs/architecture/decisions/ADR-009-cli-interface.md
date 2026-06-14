# ADR-009: CLI with Typer and Rich as Thin Adapter

- **Date**: 2026-06-13
- **Status**: accepted

## Context

depth-graph-search needs a command-line interface for quick ingestion and search operations without writing Python code. The CLI must follow the same thin-adapter principle as the HTTP API — parse input, construct the SDK, call methods, format output. No business logic in the CLI layer.

Key forces:

1. **Optional dependency**: CLI deps (`typer`, `rich`) must be an optional extra, like the API.
2. **Config consistency**: The CLI reads the same core env vars as the HTTP API (minus server-specific ones like `API_HOST`, `API_PORT`, `LOG_LEVEL`), with CLI flags as overrides.
3. **Output flexibility**: Different output formats (table, JSON, plain) for different use cases — piping, scripting, human reading.
4. **Short-lived commands**: CLI commands are one-shot operations — no need for lifespan management or connection pooling.

## Decision

### Typer as CLI framework

Typer for its type-annotation-driven parameter parsing, automatic `--help` generation, and built-in Rich integration. Commands: `ingest`, `search`, `version`.

### Own `CLISettings(BaseSettings)`

A separate settings class for the CLI, excluding API-specific fields. Same validators as the API config (`validate_dsn`, `validate_openrouter_key`). Configuration merge order: CLI flag > env var > `.env` file > default.

### Standalone formatters in `formatters.py`

Output formatting functions are isolated in `formatters.py` for testability:

- `format_ingest_result(result, fmt)` — json / table / plain
- `format_search_results(results, fmt)` — json / table (Rich `Table`) / plain

### Per-command SDK construction

Each command constructs `GraphSearch` via `_build_client(settings)` using a `with` block (context manager). No shared app-level state — CLI commands are short-lived.

### Provider dispatch via if/else

`_build_client` dispatches between `GraphSearch.from_openai()` and `GraphSearch.from_openrouter()` based on `settings.llm_provider`. Only 2 providers — a factory/registry pattern would be overengineering.

### Error handling with exit codes

| Error Source | Exit Code | Message Style |
|-------------|-----------|---------------|
| Missing config (pydantic validation) | 1 | `"Error: {field} is required. Set --{flag} or {ENV_VAR}."` |
| Bad `--metadata` JSON | 1 | `"Error: --metadata must be valid JSON: {detail}"` |
| DB connection failure | 2 | `"Error: Cannot connect to database."` |
| LLM/storage errors | 2 | `"Error: {message}"` |
| Unexpected errors | 2 | `"Unexpected error: {type}: {message}"` |

Errors go to stderr (`typer.echo(msg, err=True)`), then `raise typer.Exit(code)`.

## Consequences

### Positive

- **Installable as optional extra**: `pip install "depth-graph-search[cli]"` — no impact on SDK-only users.
- **Consistent with API config**: Same env vars, same validation logic — users switching between API and CLI have no surprises.
- **Testable output formatting**: Pure functions that take domain objects and return strings — no mocking needed.
- **Scriptable**: `--format json` produces machine-parseable output for piping; `--format table` provides human-readable Rich tables.

### Negative / Tradeoffs

- **Duplicated config class**: `CLISettings` is nearly identical to API `Settings` minus 3 fields. No shared base class — consistent with the project's adapter-isolation philosophy.
- **No streaming output**: Long ingestion operations block until complete with no progress indicator.
- **No `--file` input**: v0.1 only supports `--text` for inline text. File-based ingestion requires shell piping.

### Future Considerations

- **`--file` input**: Accept file paths or stdin for ingestion.
- **Progress bars**: Rich progress bars for long-running ingestion operations.
- **Shell completion**: Typer supports automatic shell completion generation.

## Alternatives Considered

| Alternative | Pros | Cons | Why Rejected |
|------------|------|------|--------------|
| **Click** | Mature, widely used | Manual type coercion; no built-in Rich integration; Typer is built on Click anyway | Typer provides better DX with type annotations |
| **argparse** | Stdlib, zero deps | Verbose, no type-driven parsing, no Rich integration | Too low-level for the desired developer experience |
| **Reuse API `Settings`** | DRY | CLI inherits `API_HOST`, `API_PORT`, `LOG_LEVEL` which are meaningless in CLI context | Clean separation is more important than avoiding ~30 LOC duplication |
| **Shared `_build_client` with API lifespan** | Reuse | API uses async (`AsyncGraphSearch`), CLI uses sync (`GraphSearch`) — different construction paths | Fundamentally different lifecycles |

## See Also

- [ADR-008: HTTP API](./ADR-008-http-api.md) — the other delivery surface, sharing the same config pattern
- [ADR-006: SDK Facade](./ADR-006-sdk-facade.md) — `GraphSearch` that the CLI wraps
- [Layers](../layers.md) — CLI as delivery layer
- [Ports & Adapters](../ports-and-adapters.md) — port contracts used by the underlying SDK
