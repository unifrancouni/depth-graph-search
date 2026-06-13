"""depth-graph-search CLI package.

Re-exports the Typer app so the entry point resolves correctly:

    depth_graph_search.cli.app  →  used by ``[project.scripts] dgs = "depth_graph_search.cli.main:app"``

Usage from Python (e.g. CliRunner in tests)::

    from depth_graph_search.cli import app
"""

from depth_graph_search.cli.main import app

__all__ = ["app"]
