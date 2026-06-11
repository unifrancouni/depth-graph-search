"""InMemoryGraphRepository — dict-backed fake implementing GraphRepository.

Suitable for unit tests. Supports:
- save_node / save_edge / get_node with in-memory dict storage
- traverse_bfs stub (returns [])
- search_hybrid with configurable preset results (default: [])
- Error injection via set_error(exc) — raised on next primary method call
- Call tracking via call_count(method_name)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from depth_graph_search.core.ports.graph_repository import GraphRepository

if TYPE_CHECKING:
    from depth_graph_search.core.domain.entities import Edge, Embedding, Metadata, Node


class InMemoryGraphRepository(GraphRepository):
    """Fake graph repository backed by in-memory dicts.

    All writes are stored in ``_nodes`` (dict keyed by node id) and ``_edges``
    (dict keyed by edge id). Reads return stored objects or ``None``.

    Error injection: call ``set_error(exc)`` before the test step that should
    fail. The error is raised on the next primary method call and then cleared.

    Call tracking: every call to ``save_node``, ``save_edge``, ``get_node``,
    ``search_hybrid``, and ``traverse_bfs`` is recorded as a tuple of ``(args,
    kwargs)`` in ``_calls[method_name]``. Use ``call_count(name)`` to assert.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._edges: dict[str, Edge] = {}
        self._search_results: list[Node] = []
        self._error: Exception | None = None
        self._calls: dict[str, list[tuple]] = {
            "save_node": [],
            "save_edge": [],
            "get_node": [],
            "search_hybrid": [],
            "traverse_bfs": [],
        }

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    def set_search_results(self, results: list[Node]) -> None:
        """Preset the list returned by ``search_hybrid``."""
        self._search_results = list(results)

    def set_error(self, exc: Exception | None) -> None:
        """Set an error to be raised on the next primary method call.

        Pass ``None`` to clear a previously set error.
        """
        self._error = exc

    def call_count(self, method_name: str) -> int:
        """Return the number of times ``method_name`` was called."""
        return len(self._calls.get(method_name, []))

    def calls(self, method_name: str) -> list[tuple]:
        """Return the recorded call tuples for ``method_name``."""
        return self._calls.get(method_name, [])

    # ------------------------------------------------------------------
    # Private helper
    # ------------------------------------------------------------------

    def _check_error(self) -> None:
        if self._error is not None:
            err = self._error
            self._error = None
            raise err

    # ------------------------------------------------------------------
    # GraphRepository interface
    # ------------------------------------------------------------------

    def save_node(self, node: Node) -> None:
        self._calls["save_node"].append(((node,), {}))
        self._check_error()
        self._nodes[node.id] = node

    def save_edge(self, edge: Edge) -> None:
        self._calls["save_edge"].append(((edge,), {}))
        self._check_error()
        self._edges[edge.id] = edge

    def get_node(self, node_id: str) -> Node | None:
        self._calls["get_node"].append(((node_id,), {}))
        self._check_error()
        return self._nodes.get(node_id)

    def search_hybrid(
        self,
        query_embedding: Embedding,
        query_text: str,
        top_n: int = 5,
        metadata_filter: Metadata | None = None,
    ) -> list[Node]:
        self._calls["search_hybrid"].append(
            ((query_embedding, query_text), {"top_n": top_n, "metadata_filter": metadata_filter})
        )
        self._check_error()
        return list(self._search_results)

    def traverse_bfs(
        self,
        entry_nodes: list[Node],
        depth_m: int = 2,
    ) -> list[Node]:
        self._calls["traverse_bfs"].append(((entry_nodes,), {"depth_m": depth_m}))
        self._check_error()
        return []
