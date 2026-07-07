-- =====================================================================
-- 003_usuarios.sql
-- Usuários do painel (login/registro). Protege o acesso ao painel, que antes
-- era aberto. Senhas guardadas apenas como hash (pbkdf2), nunca em texto.
-- =====================================================================

CREATE TABLE IF NOT EXISTS usuarios (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome          TEXT        NOT NULL,
    email         TEXT        NOT NULL UNIQUE,
    senha_hash    TEXT        NOT NULL,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Busca por e-mail (login) é case-insensitive; guardamos o e-mail em minúsculas.
CREATE INDEX IF NOT EXISTS idx_usuarios_email ON usuarios (lower(email));
