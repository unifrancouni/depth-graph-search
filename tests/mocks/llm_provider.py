"""FakeLLMProvider — configurable fake implementing LLMProvider.

Suitable for unit tests. Supports:
- Preset extraction via set_extraction(nodes, edges)
- Stub complete() — returns empty string by default
- Error injection via set_error(exc) — raised on next extract_graph call
- Call tracking via call_count(method_name)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from depth_graph_search.core.ports.llm_provider import LLMProvider

if TYPE_CHECKING:
    from depth_graph_search.core.domain.entities import Edge, Metadata, Node


class FakeLLMProvider(LLMProvider):
    """Fake LLM provider with configurable extraction results.

    Set up the desired return value before calling the pipeline:

        fake_llm.set_extraction(nodes=[node_a, node_b], edges=[edge_1])

    Error injection: call ``set_error(exc)`` to make the next call to
    ``extract_graph`` raise that exception.

    Call tracking: ``extract_graph`` and ``complete`` calls are recorded in
    ``_calls[method_name]`` as ``(args, kwargs)`` tuples.
    """

    def __init__(self) -> None:
        self._extraction: tuple[list[Node], list[Edge]] = ([], [])
        self._error: Exception | None = None
        self._calls: dict[str, list[tuple]] = {
            "extract_graph": [],
            "complete": [],
        }

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    def set_extraction(self, nodes: list[Node], edges: list[Edge]) -> None:
        """Preset the value returned by ``extract_graph``."""
        self._extraction = (list(nodes), list(edges))

    def set_error(self, exc: Exception | None) -> None:
        """Set an error to raise on the next ``extract_graph`` call.

        Pass ``None`` to clear.
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
    # LLMProvider interface
    # ------------------------------------------------------------------

    def extract_graph(
        self,
        text: str,
        metadata: Metadata,
    ) -> tuple[list[Node], list[Edge]]:
        self._calls["extract_graph"].append(((text, metadata), {}))
        self._check_error()
        nodes, edges = self._extraction
        return list(nodes), list(edges)

    def complete(self, prompt: str) -> str:
        self._calls["complete"].append(((prompt,), {}))
        return ""
