"""PostgresGraphRepository — concrete GraphRepository backed by PostgreSQL 17 + AGE + pgvector.

Architecture:
- Dual-write: SQL ``nodes`` table owns canonical data (content, embedding, metadata, FTS).
  AGE graph holds topology only (vertices + directed edges).
- psycopg3 sync driver. No async, no pooling (v0.1).
- ``initialize()`` executes all DDL idempotently; constructor has ZERO side effects.
- All psycopg exceptions are wrapped as ``StorageError`` at the adapter boundary.
"""

from __future__ import annotations

import contextlib
import json
from importlib import resources
from typing import TYPE_CHECKING, Any

import psycopg
import psycopg.errors
from pgvector.psycopg import register_vector

from depth_graph_search.core.domain.entities import Embedding, Node
from depth_graph_search.core.domain.exceptions import StorageError
from depth_graph_search.core.ports.graph_repository import GraphRepository

if TYPE_CHECKING:
    from depth_graph_search.core.domain.entities import Edge, Metadata


class PostgresGraphRepository(GraphRepository):
    """Graph repository adapter backed by PostgreSQL + Apache AGE + pgvector.

    Implements all five ``GraphRepository`` ABC methods via dual-write strategy:
    - SQL ``nodes`` table: content, embedding (vector), metadata (JSONB), FTS (tsvector)
    - AGE graph: topology vertices + directed edges via Cypher

    Args:
        connection: Open ``psycopg.Connection`` (sync). The adapter does NOT own
            the connection lifecycle — the caller is responsible for closing it.
        graph_name: Name of the AGE graph. Defaults to ``"knowledge_graph"``.
        embedding_dimensions: Expected vector dimension. Must match ``vector(N)``
            column. Defaults to 3072. Dimension mismatches raise ``StorageError``
            at ``save_node`` time, before any SQL is executed.

    Note:
        The constructor executes NO SQL. Call ``initialize()`` after construction
        to create extensions, tables, indexes, and the AGE graph.
    """

    # ------------------------------------------------------------------
    # RRF hybrid search SQL — class-level constant
    # ------------------------------------------------------------------
    _HYBRID_SEARCH_SQL = """
WITH bm25 AS (
    SELECT id,
           ROW_NUMBER() OVER (
               ORDER BY ts_rank_cd(fts, plainto_tsquery('english', %(query)s)) DESC
           ) AS rank
    FROM nodes
    WHERE fts @@ plainto_tsquery('english', %(query)s)
      AND (%(meta)s::jsonb IS NULL OR metadata @> %(meta)s::jsonb)
),
vec AS (
    SELECT id,
           ROW_NUMBER() OVER (
               ORDER BY embedding <=> %(embedding)s::vector
           ) AS rank
    FROM nodes
    WHERE embedding IS NOT NULL
      AND (%(meta)s::jsonb IS NULL OR metadata @> %(meta)s::jsonb)
),
rrf AS (
    SELECT COALESCE(b.id, v.id) AS id,
           COALESCE(1.0 / (60 + b.rank), 0.0)
           + COALESCE(1.0 / (60 + v.rank), 0.0) AS score
    FROM bm25 b
    FULL OUTER JOIN vec v ON b.id = v.id
)
SELECT n.id, n.content, n.embedding, n.metadata
FROM rrf
JOIN nodes n ON n.id = rrf.id
ORDER BY rrf.score DESC
LIMIT %(top_n)s
"""

    def __init__(
        self,
        connection: psycopg.Connection,
        graph_name: str = "knowledge_graph",
        embedding_dimensions: int = 3072,
    ) -> None:
        # Store config only — ZERO SQL, ZERO side effects.
        self._conn = connection
        self._graph_name = graph_name
        self._dimensions = embedding_dimensions

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Set up AGE + pgvector on the connection, then execute schema DDL.

        Idempotent: safe to call multiple times on the same database.
        Creates extensions, ``nodes`` table, indexes, and the AGE graph.

        Raises:
            StorageError: If any DDL step fails.
        """
        try:
            self._setup_connection()
            self._execute_schema()
        except psycopg.Error as exc:
            raise StorageError("Failed to initialize schema") from exc

    def close(self) -> None:
        """Close the underlying psycopg connection if still open."""
        if self._conn and not self._conn.closed:
            self._conn.close()

    # ------------------------------------------------------------------
    # Internal setup helpers
    # ------------------------------------------------------------------

    def _setup_connection(self) -> None:
        """Load AGE extension, set search_path, and register pgvector types.

        Must be called once per connection before any AGE Cypher or vector query.
        """
        self._conn.execute("LOAD 'age';")
        self._conn.execute("SET search_path = ag_catalog, \"$user\", public;")
        register_vector(self._conn)
        self._conn.commit()

    def _execute_schema(self) -> None:
        """Read ``schema.sql`` from the package and execute it, then create the AGE graph."""
        package = resources.files("depth_graph_search.adapters.postgres")
        ddl = (package / "schema.sql").read_text(encoding="utf-8")
        self._conn.execute(ddl)
        # AGE has no CREATE GRAPH IF NOT EXISTS — catch the duplicate error.
        with contextlib.suppress(psycopg.errors.DuplicateSchema):
            self._conn.execute("SELECT create_graph(%s);", (self._graph_name,))
        self._conn.commit()

    # ------------------------------------------------------------------
    # GraphRepository ABC methods
    # ------------------------------------------------------------------

    def save_node(self, node: Node) -> None:
        """Persist a node via dual-write: SQL ``nodes`` table + AGE vertex.

        If ``node.embedding`` is not ``None``, its ``dimensions`` must match
        ``self._dimensions``; mismatches raise ``StorageError`` immediately
        (before any SQL executes).

        If ``node.embedding is None``, the ``embedding`` column is written as
        ``NULL`` — this is valid and raises no error.

        Duplicate IDs are handled via ``ON CONFLICT DO UPDATE`` (upsert).

        Args:
            node: Domain ``Node`` to persist.

        Raises:
            StorageError: On dimension mismatch or any DB failure.
        """
        # Validate dimensions BEFORE touching the DB (spec contract).
        if node.embedding is not None and node.embedding.dimensions != self._dimensions:
            raise StorageError(
                f"dimension mismatch: expected {self._dimensions}, "
                f"got {node.embedding.dimensions}"
            )

        vec = node.embedding.vector if node.embedding is not None else None

        try:
            self._conn.execute(
                """
                INSERT INTO nodes (id, content, embedding, metadata)
                VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    content   = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    metadata  = EXCLUDED.metadata
                """,
                (node.id, node.content, vec, json.dumps(node.metadata)),
            )
            # AGE vertex — MERGE avoids duplicate vertex on second save.
            self._cypher(f"MERGE (:Node {{id: '{node.id}'}})")
            self._conn.commit()
        except psycopg.Error as exc:
            raise StorageError("Failed to save node") from exc

    def save_edge(self, edge: Edge) -> None:
        """Persist a directed edge in the AGE graph after validating both endpoints.

        Validates that ``edge.source_id`` and ``edge.target_id`` both exist in
        the ``nodes`` SQL table before creating the AGE edge. Raises
        ``StorageError("source/target node not found")`` if either is missing.

        Args:
            edge: Domain ``Edge`` to persist.

        Raises:
            StorageError: If source/target missing or any DB failure.
        """
        try:
            row = self._conn.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE id = %s) AS src_count,
                    COUNT(*) FILTER (WHERE id = %s) AS tgt_count
                FROM nodes
                WHERE id IN (%s, %s)
                """,
                (edge.source_id, edge.target_id, edge.source_id, edge.target_id),
            ).fetchone()

            src_count, tgt_count = (row[0], row[1]) if row else (0, 0)
            if src_count == 0 or tgt_count == 0:
                raise StorageError("source/target node not found")

            cypher = (
                f"MATCH (a:Node {{id: '{edge.source_id}'}}), "
                f"(b:Node {{id: '{edge.target_id}'}}) "
                f"CREATE (a)-[:EDGE {{id: '{edge.id}', type: '{edge.relationship}'}}]->(b)"
            )
            self._cypher(cypher)
            self._conn.commit()
        except StorageError:
            raise  # re-raise domain errors unchanged
        except psycopg.Error as exc:
            raise StorageError("Failed to save edge") from exc

    def get_node(self, node_id: str) -> Node | None:
        """Retrieve a single node by ID from the SQL ``nodes`` table.

        Args:
            node_id: UUID4 string ID of the node.

        Returns:
            The matching ``Node``, or ``None`` if not found.

        Raises:
            StorageError: On DB failure.
        """
        try:
            row = self._conn.execute(
                "SELECT id, content, embedding, metadata FROM nodes WHERE id = %s",
                (node_id,),
            ).fetchone()
            return self._row_to_node(row) if row is not None else None
        except psycopg.Error as exc:
            raise StorageError("Failed to get node") from exc

    def search_hybrid(
        self,
        query_embedding: Embedding,
        query_text: str,
        top_n: int = 5,
        metadata_filter: Metadata | None = None,
    ) -> list[Node]:
        """Hybrid search using RRF (BM25 + vector cosine), k=60.

        Applies ``metadata @> filter::jsonb`` when ``metadata_filter`` is not
        ``None``. An empty dict ``{}`` matches all rows (standard JSONB containment).

        Args:
            query_embedding: Dense vector for cosine similarity ranking.
            query_text: Raw text for BM25 (tsvector) ranking.
            top_n: Maximum nodes to return. Defaults to 5.
            metadata_filter: JSONB containment filter. ``None`` = no filter.

        Returns:
            Up to ``top_n`` ``Node`` instances ordered by RRF score descending.

        Raises:
            StorageError: On DB failure.
        """
        meta_json = json.dumps(metadata_filter) if metadata_filter is not None else None
        try:
            rows = self._conn.execute(
                self._HYBRID_SEARCH_SQL,
                {
                    "query": query_text,
                    "embedding": query_embedding.vector,
                    "meta": meta_json,
                    "top_n": top_n,
                },
            ).fetchall()
            return [self._row_to_node(r) for r in rows]
        except psycopg.Error as exc:
            raise StorageError("Hybrid search failed") from exc

    def traverse_bfs(
        self,
        entry_nodes: list[Node],
        depth_m: int = 2,
    ) -> list[Node]:
        """BFS traversal via AGE Cypher, hydrated from SQL ``nodes`` table.

        When ``depth_m=0``, returns only the entry nodes (no traversal).
        Deduplicates results across all entry nodes; entry nodes themselves
        are included in the result (0 hops).

        Args:
            entry_nodes: Seed nodes for BFS.
            depth_m: Maximum hop depth. Defaults to 2.

        Returns:
            Deduplicated list of reachable ``Node`` instances (including entry nodes).

        Raises:
            StorageError: On DB failure.
        """
        if depth_m == 0:
            return list(entry_nodes)

        try:
            all_ids: set[str] = set()

            for node in entry_nodes:
                # Cypher: match node itself (0 hops) + neighbors up to depth_m
                cypher = (
                    f"MATCH (n:Node {{id: '{node.id}'}})-[*0..{depth_m}]-(nb:Node) "
                    "RETURN DISTINCT nb.id"
                )
                rows = self._cypher(cypher)
                for row in rows:
                    nid = self._parse_agtype_scalar(row[0])
                    if nid:
                        all_ids.add(nid)

            if not all_ids:
                return list(entry_nodes)

            # Batch-hydrate from SQL nodes table
            sql_rows = self._conn.execute(
                "SELECT id, content, embedding, metadata FROM nodes WHERE id = ANY(%s)",
                (list(all_ids),),
            ).fetchall()
            return [self._row_to_node(r) for r in sql_rows]
        except psycopg.Error as exc:
            raise StorageError("BFS traversal failed") from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cypher(self, cypher_query: str) -> list[tuple[Any, ...]]:
        """Execute an AGE Cypher query via ``ag_catalog.cypher()``.

        AGE does not support parameterised binding inside Cypher strings.
        All interpolated values in this adapter are domain-generated uuid4 strings
        or validated relationship labels — no user input reaches this path.

        Args:
            cypher_query: Complete Cypher query string with values already embedded.

        Returns:
            List of result tuples from AGE (each element is an ``agtype`` value).
        """
        sql = (
            f"SELECT * FROM cypher('{self._graph_name}', $$ {cypher_query} $$)"
            " AS (result agtype);"
        )
        return self._conn.execute(sql).fetchall()

    def _row_to_node(self, row: tuple[Any, ...]) -> Node:
        """Convert a SQL row ``(id, content, embedding, metadata)`` to a ``Node``.

        pgvector returns the embedding as a numpy array after ``register_vector()``;
        we convert it to ``list[float]`` to satisfy the domain's stdlib-only contract.

        Args:
            row: Four-element tuple from a ``SELECT id, content, embedding, metadata``
                query against the ``nodes`` table.

        Returns:
            Reconstructed ``Node`` domain entity.
        """
        id_, content, vec, meta = row
        embedding: Embedding | None = None
        if vec is not None:
            vec_list: list[float] = list(vec)
            embedding = Embedding(
                vector=vec_list,
                model="unknown",  # model info not stored in DB for v0.1
                dimensions=len(vec_list),
            )
        return Node(
            id=id_,
            content=content,
            embedding=embedding,
            metadata=meta if meta is not None else {},
        )

    def _parse_agtype_scalar(self, value: Any) -> str | None:
        """Extract a plain string from an AGE ``agtype`` scalar result.

        AGE returns scalar strings wrapped in extra double-quotes, e.g.
        ``'"uuid-value"'``. This helper strips those quotes.

        Args:
            value: Raw agtype value from an AGE Cypher RETURN clause.

        Returns:
            The unwrapped string value, or ``None`` if the input is falsy.
        """
        if value is None:
            return None
        s = str(value).strip('"')
        return s if s else None
