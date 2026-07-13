-- =====================================================================
-- Busca semântica (RAG) — pgvector.
-- Embeddings das mensagens (384 dims, modelo multilingual MiniLM) para
-- busca por similaridade + histórico de perguntas.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE mensagens ADD COLUMN IF NOT EXISTS embedding vector(384);

-- HNSW (cosine): funciona sem treino e cresce de forma incremental.
CREATE INDEX IF NOT EXISTS idx_mensagens_embedding
    ON mensagens USING hnsw (embedding vector_cosine_ops);

-- Histórico das últimas perguntas da busca semântica.
CREATE TABLE IF NOT EXISTS perguntas_rag (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id bigint REFERENCES usuarios(id) ON DELETE SET NULL,
    pergunta   text        NOT NULL,
    criado_em  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_perguntas_rag_criado ON perguntas_rag (criado_em DESC);
