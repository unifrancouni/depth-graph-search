# ADR-004: Hybrid Search Pipeline (BM25 + Vector + BFS Graph Traversal)

- **Date**: 2026-06-09
- **Status**: accepted

## Context

RAG systems typically retrieve documents via vector similarity alone. This misses contextually related information that is connected through relationships but not semantically similar. depth-graph-search needs a search approach that combines semantic similarity with graph structure to surface multi-hop context.

Key forces:

1. **Entry point quality**: Initial node retrieval must combine lexical (BM25) and semantic (vector) signals for high precision.
2. **Context expansion**: Once entry nodes are found, their graph neighbors provide contextual information that pure vector search would miss.
3. **Scoring transparency**: Results need scores and distance indicators so callers can distinguish entry nodes from graph-expanded context.
4. **Port constraint**: `GraphRepository.search_hybrid()` returns `list[Node]` (not scored results), and `traverse_bfs()` returns a flat `list[Node]` with no hop information.

## Decision

Implement search as a **Pipeline-as-Strategy** pattern via `DefaultSearchPipeline` implementing the `SearchPipeline` port ABC. The pipeline executes a 5-step flow:

1. **Embed query** — `EmbeddingProvider.embed(query)` produces a dense vector.
2. **Hybrid search** — `GraphRepository.search_hybrid(embedding, query, top_n, metadata_filter)` returns ranked entry nodes using BM25 + vector similarity.
3. **BFS traversal** — `GraphRepository.traverse_bfs(entry_nodes, depth_m)` expands through graph edges.
4. **Deduplicate** — `dict[str, ScoredNode]` keyed by `node.id`, entry nodes first (preserves rank order).
5. **Score and sort** — Entry nodes: `score = 1.0 - rank / (top_n + 1)`. BFS-only nodes: `score = 0.0, distance = 1`. Sort by `(-score, distance)`, slice `[:top_n]`.

### Scoring formula

Rank-based scoring is used because `search_hybrid` returns `list[Node]` without scores. The formula `1.0 - rank / (top_n + 1)` maps rank 0 to near-1.0 and distributes scores evenly in `(0, 1]`.

### BFS distance simplification

`traverse_bfs` returns a flat list with no per-hop metadata. Entry nodes get `distance=0`, all BFS-only nodes get `distance=1`. Accurate per-hop tracking would require a port signature change (future SDD).

### Entity Resolution as search consumer

`DefaultEntityResolutionStrategy` uses the search pipeline internally: for each node, it calls `pipeline.search(node.content, top_n=1, depth_m=0)` and compares the score against a configurable threshold (default `0.85`).

## Consequences

### Positive

- **Multi-hop context**: Graph traversal surfaces related nodes that vector-only search would miss entirely.
- **Swappable pipeline**: Any implementation of `SearchPipeline` can replace `DefaultSearchPipeline` — the SDK delegates through the port.
- **Clean orchestration**: The pipeline is a pure orchestrator with zero business logic — it composes port calls and applies scoring.
- **Entity resolution reuse**: Resolution strategy depends on `SearchPipeline` (the ABC), not `DefaultSearchPipeline` — fully decoupled.

### Negative / Tradeoffs

- **Approximate scoring**: Rank-based scoring is a proxy, not a true relevance score. It preserves ordering but loses magnitude information.
- **Flat BFS distance**: All graph-expanded nodes show `distance=1` regardless of actual hop count. Accurate tracking requires port changes.
- **N+1 in entity resolution**: Resolution calls `search()` once per node. For large ingestion batches, this is O(N) search calls. Batch optimization is a future concern.
- **`pipeline` param ignored**: The `pipeline` parameter on `search()` exists in the port signature but is silently ignored in v0.1 — no pipeline registry yet.

### Future Considerations

- **Per-hop distance**: Changing `traverse_bfs` to return `list[tuple[Node, int]]` would enable accurate distance tracking.
- **Pipeline registry**: A named-pipeline registry would allow callers to select different search strategies via the `pipeline` parameter.
- **Batch entity resolution**: Resolving all nodes in a single search call would eliminate the N+1 pattern.

## Alternatives Considered

| Alternative | Pros | Cons | Why Rejected |
|------------|------|------|--------------|
| **Vector-only search** | Simpler pipeline, no graph dependency | Misses contextually related nodes, no multi-hop capability | Core value proposition of the project is graph traversal |
| **Raw RRF score pass-through** | True relevance scores | `search_hybrid` returns `list[Node]` without scores — would require port change | Out of scope for v0.1 |
| **Per-hop BFS tracking** | Accurate distance values | `traverse_bfs` returns flat `list[Node]` — would require port change | Deferred to future SDD |
| **Separate entity resolution from search** | Looser coupling | Resolution needs search capability — using the pipeline ABC keeps it clean | Resolution-as-search-consumer is the cleanest design |

## See Also

- [ADR-001: PostgreSQL + AGE](./ADR-001-postgresql-age.md) — the unified backend that enables hybrid search
- [ADR-002: Clean Architecture](./ADR-002-clean-architecture.md) — port ABC pattern used by `SearchPipeline`
- [Search Flow](../../flows/search.md) — runtime sequence diagram
- [Ports & Adapters](../ports-and-adapters.md) — `SearchPipeline` and `EntityResolutionStrategy` contracts
- [Strategies](../strategies.md) — pipeline-as-strategy pattern
