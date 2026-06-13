"""Output formatters for the dgs CLI.

Pure functions — zero side effects, zero I/O. Each function accepts a domain
object (or list) and a format string, and returns a string ready to be printed.

Supported formats:
- ``json``:  Valid JSON, machine-readable.
- ``table``: Rich Table rendered to a string, human-readable with borders.
- ``plain``: Plain text, one line per item, no Rich markup or borders.

These functions are intentionally separated from ``main.py`` so they can be
tested in complete isolation without invoking the CLI runner.
"""

from __future__ import annotations

import json
from io import StringIO

from rich.console import Console
from rich.table import Table

from depth_graph_search.core.domain.entities import IngestionResult, ScoredNode


def format_ingest_result(result: IngestionResult, fmt: str) -> str:
    """Format an ``IngestionResult`` for CLI output.

    Args:
        result: The ingestion result containing node and edge counts.
        fmt: One of ``"json"``, ``"table"``, or ``"plain"``.

    Returns:
        A formatted string ready for ``typer.echo()``.

    Raises:
        ValueError: If ``fmt`` is not one of the three supported formats.
    """
    if fmt == "json":
        return json.dumps({"node_count": result.node_count, "edge_count": result.edge_count})

    if fmt == "plain":
        return f"Ingested: {result.node_count} nodes, {result.edge_count} edges"

    if fmt == "table":
        # Ingest has only 2 numbers — a Rich table is overkill.
        # A single human-readable line IS the right "table" for this case.
        # (Rich Table format is reserved for search results which have multiple rows.)
        return f"Ingested: {result.node_count} nodes, {result.edge_count} edges"

    raise ValueError(f"Unsupported format: {fmt!r}. Choose from: json, table, plain")


def format_search_results(results: list[ScoredNode], fmt: str) -> str:
    """Format a list of ``ScoredNode`` objects for CLI output.

    Args:
        results: Ordered list of scored nodes (score DESC, distance ASC).
        fmt: One of ``"json"``, ``"table"``, or ``"plain"``.

    Returns:
        A formatted string ready for ``typer.echo()``.

    Raises:
        ValueError: If ``fmt`` is not one of the three supported formats.
    """
    if fmt == "json":
        items = [
            {
                "id": sn.node.id,
                "content": sn.node.content,
                "score": sn.score,
                "distance": sn.distance,
                "metadata": sn.node.metadata,
            }
            for sn in results
        ]
        return json.dumps(items)

    if fmt == "plain":
        lines = [
            f"{sn.score:.2f}  {sn.node.content}  (depth {sn.distance})"
            for sn in results
        ]
        return "\n".join(lines) if lines else "(no results)"

    if fmt == "table":
        table = Table(title="Search Results")
        table.add_column("ID", style="dim", no_wrap=True, max_width=12)
        table.add_column("Content", style="white")
        table.add_column("Score", style="cyan", justify="right")
        table.add_column("Distance", style="green", justify="right")
        for sn in results:
            table.add_row(
                sn.node.id[:8],
                sn.node.content,
                f"{sn.score:.4f}",
                str(sn.distance),
            )
        return _render_table(table)

    raise ValueError(f"Unsupported format: {fmt!r}. Choose from: json, table, plain")


def _render_table(table: Table) -> str:
    """Render a Rich ``Table`` to a plain string (no ANSI escape codes).

    Uses a ``StringIO`` buffer with ``Console(force_terminal=False)`` so the
    output contains printable characters only — safe for piping and testing.
    """
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, highlight=False)
    console.print(table)
    return buf.getvalue().rstrip("\n")
