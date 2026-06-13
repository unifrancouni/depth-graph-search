"""dgs — CLI entry point for depth-graph-search.

Thin Typer adapter. Zero business logic — all delegation to the GraphSearch SDK.
Data flow per command:
  1. Typer parses flags.
  2. Build ``CLISettings`` by merging CLI flags (non-None) over env/defaults.
  3. Construct ``GraphSearch`` via ``_build_client(settings)``.
  4. Call the appropriate SDK method.
  5. Format output via ``formatters.py``.
  6. Print to stdout, exit 0.

On any error: print human-readable message to stderr, exit 1 (user error) or
exit 2 (runtime error). No Python tracebacks are ever printed.
"""

from __future__ import annotations

import json
from typing import Annotated

import typer

import depth_graph_search as dgs
from depth_graph_search.cli.config import CLISettings
from depth_graph_search.cli.formatters import format_ingest_result, format_search_results

app = typer.Typer(
    name="dgs",
    help="depth-graph-search — hybrid graph + vector retrieval engine.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_client(settings: CLISettings) -> dgs.GraphSearch:
    """Construct a ``GraphSearch`` from resolved settings.

    Dispatches to ``from_openai`` or ``from_openrouter`` based on
    ``settings.llm_provider``.  The returned instance is NOT a context manager
    here — callers are responsible for calling ``close()`` or using ``with``.
    """
    if settings.llm_provider == "openrouter":
        return dgs.GraphSearch.from_openrouter(
            dsn=settings.database_url,
            openai_api_key=settings.openai_api_key,
            openrouter_api_key=settings.openrouter_api_key or "",
            openrouter_model=settings.llm_model,
            embedding_model=settings.embedding_model,
            graph_name=settings.graph_name,
            embedding_dimensions=settings.embedding_dimensions,
        )
    return dgs.GraphSearch.from_openai(
        dsn=settings.database_url,
        api_key=settings.openai_api_key,
        model=settings.llm_model,
        embedding_model=settings.embedding_model,
        graph_name=settings.graph_name,
        embedding_dimensions=settings.embedding_dimensions,
    )


def _build_settings(**overrides: object) -> CLISettings:
    """Construct ``CLISettings`` with non-None CLI overrides on top of env.

    pydantic-settings merges: explicit kwargs > env vars > .env > defaults.
    We strip None values so missing CLI flags fall through to env resolution.
    """
    clean = {k: v for k, v in overrides.items() if v is not None}
    return CLISettings(**clean)  # type: ignore[arg-type]


def _parse_json_flag(value: str | None, flag_name: str) -> dict | None:
    """Parse a JSON string flag value. Exits with code 1 on parse failure."""
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        typer.echo(
            f"Error: {flag_name} must be valid JSON: {exc}",
            err=True,
        )
        raise typer.Exit(code=1) from exc
    if not isinstance(parsed, dict):
        typer.echo(
            f"Error: {flag_name} must be a JSON object (dict), got {type(parsed).__name__}",
            err=True,
        )
        raise typer.Exit(code=1)
    return parsed


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def ingest(
    text: Annotated[str, typer.Option("--text", help="Text to ingest into the knowledge graph.")],
    metadata: Annotated[
        str | None,
        typer.Option("--metadata", help="Optional JSON object with context metadata."),
    ] = None,
    dsn: Annotated[
        str | None,
        typer.Option("--dsn", help="PostgreSQL DSN. Falls back to DATABASE_URL env var."),
    ] = None,
    openai_key: Annotated[
        str | None,
        typer.Option("--openai-key", help="OpenAI API key. Falls back to OPENAI_API_KEY."),
    ] = None,
    provider: Annotated[
        str | None,
        typer.Option("--provider", help="LLM provider: openai or openrouter."),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", help="LLM model identifier."),
    ] = None,
    embedding_model: Annotated[
        str | None,
        typer.Option("--embedding-model", help="Embedding model identifier."),
    ] = None,
    graph_name: Annotated[
        str | None,
        typer.Option("--graph-name", help="Apache AGE graph name."),
    ] = None,
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: table (default), json, plain."),
    ] = "table",
) -> None:
    """Ingest text into the knowledge graph.

    Extracts entities and relationships from TEXT and persists them to the graph.
    """
    # Parse optional JSON metadata — fail fast on bad JSON
    metadata_dict = _parse_json_flag(metadata, "--metadata")

    # Build settings — CLI flags override env vars
    try:
        settings = _build_settings(
            database_url=dsn,
            openai_api_key=openai_key,
            llm_provider=provider,
            llm_model=model,
            embedding_model=embedding_model,
            graph_name=graph_name,
        )
    except Exception as exc:  # pydantic ValidationError or similar
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    # Execute ingest via SDK
    try:
        with _build_client(settings) as gs:
            result = gs.ingest(text, metadata_dict)
    except dgs.ValidationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        _handle_runtime_error(exc)

    # Format and print
    output = format_ingest_result(result, fmt)
    typer.echo(output)


@app.command()
def search(
    query: Annotated[str, typer.Option("--query", help="Natural language search query.")],
    top_n: Annotated[
        int,
        typer.Option("--top-n", help="Maximum number of results to return."),
    ] = 5,
    depth: Annotated[
        int,
        typer.Option("--depth", help="Maximum BFS hop depth from entry nodes."),
    ] = 2,
    metadata_filter: Annotated[
        str | None,
        typer.Option("--metadata-filter", help="Optional JSON object to pre-filter nodes."),
    ] = None,
    dsn: Annotated[
        str | None,
        typer.Option("--dsn", help="PostgreSQL DSN. Falls back to DATABASE_URL env var."),
    ] = None,
    openai_key: Annotated[
        str | None,
        typer.Option("--openai-key", help="OpenAI API key. Falls back to OPENAI_API_KEY."),
    ] = None,
    provider: Annotated[
        str | None,
        typer.Option("--provider", help="LLM provider: openai or openrouter."),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", help="LLM model identifier."),
    ] = None,
    embedding_model: Annotated[
        str | None,
        typer.Option("--embedding-model", help="Embedding model identifier."),
    ] = None,
    graph_name: Annotated[
        str | None,
        typer.Option("--graph-name", help="Apache AGE graph name."),
    ] = None,
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: table (default), json, plain."),
    ] = "table",
) -> None:
    """Search the knowledge graph with a natural language query.

    Returns the top N nodes ranked by hybrid graph+vector relevance.
    """
    # Parse optional JSON metadata filter
    filter_dict = _parse_json_flag(metadata_filter, "--metadata-filter")

    # Build settings — CLI flags override env vars
    try:
        settings = _build_settings(
            database_url=dsn,
            openai_api_key=openai_key,
            llm_provider=provider,
            llm_model=model,
            embedding_model=embedding_model,
            graph_name=graph_name,
        )
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    # Execute search via SDK
    try:
        with _build_client(settings) as gs:
            results = gs.search(query=query, top_n=top_n, depth_m=depth, metadata_filter=filter_dict)
    except dgs.ValidationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        _handle_runtime_error(exc)

    # Format and print
    output = format_search_results(results, fmt)
    typer.echo(output)


@app.command()
def version() -> None:
    """Print the depth-graph-search version and exit."""
    typer.echo(dgs.__version__)


# ---------------------------------------------------------------------------
# Error handling helpers
# ---------------------------------------------------------------------------


def _handle_runtime_error(exc: Exception) -> None:
    """Classify a runtime exception, print to stderr, and exit with code 2.

    This function never returns — it always raises ``typer.Exit(code=2)``.
    No Python tracebacks are ever printed.
    """
    import psycopg  # type: ignore[import-not-found]

    if isinstance(exc, psycopg.OperationalError):
        typer.echo(
            "Error: Cannot connect to database. Check --dsn or DATABASE_URL.",
            err=True,
        )
    elif isinstance(exc, dgs.LLMError):
        typer.echo(f"Error: LLM service failed: {exc}", err=True)
    elif isinstance(exc, dgs.DepthGraphSearchError):
        typer.echo(f"Error: {exc}", err=True)
    else:
        typer.echo(f"Unexpected error: {type(exc).__name__}: {exc}", err=True)
    raise typer.Exit(code=2)
