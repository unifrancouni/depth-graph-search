"""FakeEntityResolutionStrategy — configurable fake implementing EntityResolutionStrategy.

Suitable for unit tests. Supports:
- all_new mode: every node returned as is_new=True, matched_id=None
- all_matched mode: every node returned as is_new=False, matched_id=<preset>
- custom mode: caller provides exact resolved_nodes list
- Error injection via set_error(exc)
- Call tracking via call_count(method_name)
"""

from __future__ import annotations

from typing import Literal, TYPE_CHECKING

from depth_graph_search.core.domain.entities import ResolvedNode
from depth_graph_search.core.ports.entity_resolution import EntityResolutionStrategy

if TYPE_CHECKING:
    from depth_graph_search.core.domain.entities import Node


class FakeEntityResolutionStrategy(EntityResolutionStrategy):
    """Fake entity resolution strategy with configurable modes.

    Three modes (set one before calling the pipeline):

    - ``set_all_new()``: every input node is returned as a new entity.
    - ``set_all_matched(matched_id)``: every input node is returned as
      matched to the given ``matched_id``.
    - ``set_custom(resolved_nodes)``: caller provides the exact list of
      ``ResolvedNode`` instances to return. The list is returned as-is.

    Default mode is ``all_new``.

    Error injection: call ``set_error(exc)`` to make the next ``resolve``
    call raise that exception.

    Call tracking: ``resolve`` calls are recorded in ``_calls["resolve"]``
    as ``(args, kwargs)`` tuples.
    """

    def __init__(self) -> None:
        self._mode: Literal["all_new", "all_matched", "custom"] = "all_new"
        self._matched_id: str | None = None
        self._custom_resolved: list[ResolvedNode] = []
        self._error: Exception | None = None
        self._calls: dict[str, list[tuple]] = {
            "resolve": [],
        }

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    def set_all_new(self) -> None:
        """Every resolved node will have ``is_new=True, matched_id=None``."""
        self._mode = "all_new"
        self._matched_id = None
        self._custom_resolved = []

    def set_all_matched(self, matched_id: str) -> None:
        """Every resolved node will have ``is_new=False, matched_id=matched_id``."""
        self._mode = "all_matched"
        self._matched_id = matched_id
        self._custom_resolved = []

    def set_custom(self, resolved_nodes: list[ResolvedNode]) -> None:
        """Return the provided list exactly as-is from ``resolve``."""
        self._mode = "custom"
        self._custom_resolved = list(resolved_nodes)

    def set_error(self, exc: Exception | None) -> None:
        """Set an error to raise on the next ``resolve`` call. Pass ``None`` to clear."""
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
    # EntityResolutionStrategy interface
    # ------------------------------------------------------------------

    def resolve(
        self,
        nodes: list[Node],
        threshold: float = 0.85,
    ) -> list[ResolvedNode]:
        self._calls["resolve"].append(((nodes,), {"threshold": threshold}))
        self._check_error()

        if self._mode == "all_new":
            return [ResolvedNode(node=node, is_new=True, matched_id=None) for node in nodes]
        elif self._mode == "all_matched":
            return [
                ResolvedNode(node=node, is_new=False, matched_id=self._matched_id)
                for node in nodes
            ]
        else:  # custom
            return list(self._custom_resolved)
