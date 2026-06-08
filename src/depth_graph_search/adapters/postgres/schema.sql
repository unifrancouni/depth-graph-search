-- PostgreSQL schema for depth-graph-search
-- Idempotent: safe to run multiple times (IF NOT EXISTS guards).
-- Extensions are loaded by initialize() before this DDL runs.

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS age;
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- Nodes table — canonical data store (content, embedding, metadata, FTS)
-- AGE graph holds topology only; all data lives here.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nodes (
    id          TEXT        PRIMARY KEY,
    content     TEXT        NOT NULL,
    embedding   vector(3072),                   -- NULL allowed (embed step may not have run)
    metadata    JSONB       NOT NULL DEFAULT '{}',
    fts         TSVECTOR    GENERATED ALWAYS AS (
                    to_tsvector('english', content)
                ) STORED,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Indexes (all idempotent via IF NOT EXISTS)
-- ---------------------------------------------------------------------------

-- HNSW index for approximate nearest-neighbour vector search (cosine distance)
CREATE INDEX IF NOT EXISTS idx_nodes_embedding
    ON nodes USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- GIN index for full-text search via tsvector
CREATE INDEX IF NOT EXISTS idx_nodes_fts
    ON nodes USING GIN (fts);

-- GIN index for JSONB metadata containment queries (@>)
CREATE INDEX IF NOT EXISTS idx_nodes_metadata
    ON nodes USING GIN (metadata);
