-- =====================================================================
-- Histórico de incidentes de saúde — registra quando cada componente
-- (captura, pipeline, banco, Redis) ficou fora e por quanto tempo.
-- Alimenta os alertas por Telegram (down > 5 min) e a tela de Saúde.
-- =====================================================================

CREATE TABLE IF NOT EXISTS incidentes_saude (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    componente text        NOT NULL,
    inicio     timestamptz NOT NULL,
    fim        timestamptz,           -- NULL enquanto o incidente estiver aberto
    notificado boolean     NOT NULL DEFAULT false,
    criado_em  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_incidentes_inicio ON incidentes_saude (inicio DESC);
