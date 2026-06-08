"""Unit tests for PostgresGraphRepository.

All tests mock ``psycopg.Connection`` — no database required.
Covers: constructor defaults, helper methods, dimension validation,
error wrapping, and edge validation logic.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import psycopg
import pytest

from depth_graph_search.adapters.postgres.repository import PostgresGraphRepository
from depth_graph_search.core.domain.entities import Edge, Embedding, Node
from depth_graph_search.core.domain.exceptions import StorageError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_conn() -> MagicMock:
    """Return a minimal mock that satisfies psycopg.Connection usage."""
    conn = MagicMock(spec=psycopg.Connection)
    conn.closed = False
    cursor_mock = MagicMock()
    cursor_mock.fetchone.return_value = None
    cursor_mock.fetchall.return_value = []
    conn.execute.return_value = cursor_mock
    return conn


def _make_repo(
    conn: psycopg.Connection | None = None,  # type: ignore[type-arg]
    graph_name: str = "knowledge_graph",
    embedding_dimensions: int = 3072,
) -> PostgresGraphRepository:
    if conn is None:
        conn = _make_conn()  # type: ignore[assignment]
    return PostgresGraphRepository(
        connection=conn,  # type: ignore[arg-type]
        graph_name=graph_name,
        embedding_dimensions=embedding_dimensions,
    )


def _make_embedding(dimensions: int = 3072) -> Embedding:
    return Embedding(vector=[0.1] * dimensions, model="test", dimensions=dimensions)


# ---------------------------------------------------------------------------
# Task 4.2 — Constructor tests
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_conn_stored_after_init(self) -> None:
        conn = _make_conn()
        repo = _make_repo(conn=conn)
        assert repo._conn is conn

    def test_default_graph_name(self) -> None:
        repo = _make_repo()
        assert repo._graph_name == "knowledge_graph"

    def test_custom_graph_name_stored(self) -> None:
        repo = _make_repo(graph_name="my_graph")
        assert repo._graph_name == "my_graph"

    def test_default_embedding_dimensions(self) -> None:
        repo = _make_repo()
        assert repo._dimensions == 3072

    def test_custom_embedding_dimensions_stored(self) -> None:
        repo = _make_repo(embedding_dimensions=1536)
        assert repo._dimensions == 1536

    def test_constructor_executes_no_sql(self) -> None:
        conn = _make_conn()
        _make_repo(conn=conn)
        conn.execute.assert_not_called()
        conn.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Task 4.3 — _row_to_node() mapping tests
# ---------------------------------------------------------------------------


class TestRowToNode:
    def test_row_with_embedding_returns_node_with_embedding(self) -> None:
        repo = _make_repo()
        vec = [0.1, 0.2, 0.3]
        row = ("test-id", "hello world", vec, {"key": "val"})
        node = repo._row_to_node(row)

        assert node.id == "test-id"
        assert node.content == "hello world"
        assert node.metadata == {"key": "val"}
        assert node.embedding is not None
        assert node.embedding.vector == vec
        assert node.embedding.dimensions == 3

    def test_row_with_null_embedding_returns_node_without_embedding(self) -> None:
        repo = _make_repo()
        row = ("null-emb-id", "content", None, {})
        node = repo._row_to_node(row)

        assert node.embedding is None

    def test_metadata_deserialized_correctly(self) -> None:
        repo = _make_repo()
        meta = {"source": "doc-01", "page": 5}
        row = ("meta-id", "text", None, meta)
        node = repo._row_to_node(row)

        assert node.metadata == meta

    def test_null_metadata_defaults_to_empty_dict(self) -> None:
        repo = _make_repo()
        row = ("id", "text", None, None)
        node = repo._row_to_node(row)

        assert node.metadata == {}

    def test_embedding_vector_converted_to_list(self) -> None:
        """pgvector may return numpy arrays; _row_to_node must convert to list."""
        import array

        repo = _make_repo()
        # Simulate numpy-like iterable (array.array works the same way)
        arr = array.array("f", [0.5, 0.6])
        row = ("arr-id", "content", arr, {})
        node = repo._row_to_node(row)

        assert isinstance(node.embedding, Embedding)
        assert isinstance(node.embedding.vector, list)


# ---------------------------------------------------------------------------
# Task 4.4 — _parse_agtype_scalar() tests
# ---------------------------------------------------------------------------


class TestParseAgtypeScalar:
    def test_quoted_string_returns_unquoted(self) -> None:
        repo = _make_repo()
        result = repo._parse_agtype_scalar('"uuid-value"')
        assert result == "uuid-value"

    def test_none_returns_none(self) -> None:
        repo = _make_repo()
        assert repo._parse_agtype_scalar(None) is None

    def test_empty_string_returns_none(self) -> None:
        repo = _make_repo()
        assert repo._parse_agtype_scalar("") is None

    def test_unquoted_string_returned_as_is(self) -> None:
        repo = _make_repo()
        result = repo._parse_agtype_scalar("plain-value")
        assert result == "plain-value"

    def test_doubly_quoted_string_stripped_once(self) -> None:
        repo = _make_repo()
        # AGE returns: '"some-uuid"' → strip outer quotes → "some-uuid"
        result = repo._parse_agtype_scalar('"some-uuid"')
        assert result == "some-uuid"


# ---------------------------------------------------------------------------
# Task 4.5 — Dimension validation in save_node()
# ---------------------------------------------------------------------------


class TestSaveNodeDimensionValidation:
    def test_matching_dimensions_does_not_raise(self) -> None:
        conn = _make_conn()
        repo = _make_repo(conn=conn, embedding_dimensions=3)

        cursor_mock = MagicMock()
        cursor_mock.fetchone.return_value = None
        cursor_mock.fetchall.return_value = []
        conn.execute.return_value = cursor_mock

        node = Node(content="test", embedding=_make_embedding(dimensions=3))
        # Should not raise; SQL execute should be called
        repo.save_node(node)
        conn.execute.assert_called()

    def test_dimension_mismatch_raises_storage_error(self) -> None:
        conn = _make_conn()
        repo = _make_repo(conn=conn, embedding_dimensions=3072)

        node = Node(content="test", embedding=_make_embedding(dimensions=1536))
        with pytest.raises(StorageError, match="dimension mismatch"):
            repo.save_node(node)

    def test_dimension_mismatch_no_sql_executed(self) -> None:
        conn = _make_conn()
        repo = _make_repo(conn=conn, embedding_dimensions=3072)

        node = Node(content="test", embedding=_make_embedding(dimensions=1536))
        with pytest.raises(StorageError):
            repo.save_node(node)

        # No SQL should have been executed
        conn.execute.assert_not_called()

    def test_none_embedding_writes_null_no_dimension_error(self) -> None:
        conn = _make_conn()
        repo = _make_repo(conn=conn, embedding_dimensions=3072)

        cursor_mock = MagicMock()
        cursor_mock.fetchall.return_value = []
        conn.execute.return_value = cursor_mock

        node = Node(content="no embedding", embedding=None)
        # Must NOT raise StorageError
        repo.save_node(node)

        # SQL must have been called (not skipped)
        conn.execute.assert_called()

    def test_dimension_mismatch_error_message_contains_both_dimensions(self) -> None:
        conn = _make_conn()
        repo = _make_repo(conn=conn, embedding_dimensions=3072)

        node = Node(content="test", embedding=_make_embedding(dimensions=512))
        with pytest.raises(StorageError) as exc_info:
            repo.save_node(node)

        assert "3072" in str(exc_info.value)
        assert "512" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Task 4.6 — Error wrapping tests
# ---------------------------------------------------------------------------


class TestErrorWrapping:
    def _make_raising_conn(self) -> MagicMock:
        conn = _make_conn()
        conn.execute.side_effect = psycopg.OperationalError("connection refused")
        return conn

    def test_save_node_wraps_psycopg_error(self) -> None:
        conn = self._make_raising_conn()
        repo = _make_repo(conn=conn, embedding_dimensions=3)

        node = Node(content="test", embedding=_make_embedding(dimensions=3))
        with pytest.raises(StorageError) as exc_info:
            repo.save_node(node)

        assert isinstance(exc_info.value.__cause__, psycopg.OperationalError)

    def test_get_node_wraps_psycopg_error(self) -> None:
        conn = self._make_raising_conn()
        repo = _make_repo(conn=conn)

        with pytest.raises(StorageError) as exc_info:
            repo.get_node("some-id")

        assert isinstance(exc_info.value.__cause__, psycopg.OperationalError)

    def test_save_edge_wraps_psycopg_error(self) -> None:
        conn = self._make_raising_conn()
        repo = _make_repo(conn=conn)

        edge = Edge(source_id="a", target_id="b", relationship="LINKS")
        with pytest.raises(StorageError) as exc_info:
            repo.save_edge(edge)

        assert isinstance(exc_info.value.__cause__, psycopg.OperationalError)

    def test_storage_error_cause_is_set(self) -> None:
        """Verify __cause__ chaining works correctly (raise X from exc)."""
        conn = _make_conn()
        original_exc = psycopg.OperationalError("timeout")
        conn.execute.side_effect = original_exc
        repo = _make_repo(conn=conn)

        with pytest.raises(StorageError) as exc_info:
            repo.get_node("any")

        assert exc_info.value.__cause__ is original_exc


# ---------------------------------------------------------------------------
# Task 4.7 — save_edge() missing-node validation
# ---------------------------------------------------------------------------


class TestSaveEdgeMissingNodeValidation:
    def _make_count_conn(self, src_count: int, tgt_count: int) -> MagicMock:
        conn = _make_conn()
        cursor_mock = MagicMock()
        cursor_mock.fetchone.return_value = (src_count, tgt_count)
        cursor_mock.fetchall.return_value = []
        conn.execute.return_value = cursor_mock
        return conn

    def test_missing_source_raises_storage_error(self) -> None:
        conn = self._make_count_conn(src_count=0, tgt_count=1)
        repo = _make_repo(conn=conn)

        edge = Edge(source_id="missing-src", target_id="exists-tgt", relationship="REL")
        with pytest.raises(StorageError, match="source/target node not found"):
            repo.save_edge(edge)

    def test_missing_target_raises_storage_error(self) -> None:
        conn = self._make_count_conn(src_count=1, tgt_count=0)
        repo = _make_repo(conn=conn)

        edge = Edge(source_id="exists-src", target_id="missing-tgt", relationship="REL")
        with pytest.raises(StorageError, match="source/target node not found"):
            repo.save_edge(edge)

    def test_both_nodes_present_does_not_raise_on_validation(self) -> None:
        """When both nodes exist, the validation passes and AGE edge creation is attempted."""
        conn = self._make_count_conn(src_count=1, tgt_count=1)
        # Second execute call (for _cypher) returns empty list
        execute_results = [
            MagicMock(**{"fetchone.return_value": (1, 1), "fetchall.return_value": []}),
            MagicMock(**{"fetchone.return_value": None, "fetchall.return_value": []}),
        ]
        conn.execute.side_effect = execute_results
        repo = _make_repo(conn=conn)

        edge = Edge(source_id="src", target_id="tgt", relationship="REL")
        # Should not raise StorageError for missing nodes
        repo.save_edge(edge)
