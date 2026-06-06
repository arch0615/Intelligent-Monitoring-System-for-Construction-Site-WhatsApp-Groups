-- =====================================================================
-- 002_retencao_midia.sql
-- Hardening (Etapa 5): política de retenção/arquivamento de mídia para não
-- encher o disco do VPS. O job de manutenção marca `arquivada_em` e remove o
-- arquivo do filesystem, preservando os metadados e o texto/análise no banco
-- (RNF-05 — sem perda de informação útil, só o binário pesado é descartado).
-- =====================================================================

ALTER TABLE midias
    ADD COLUMN IF NOT EXISTS arquivada_em TIMESTAMPTZ;

-- Acelera o job de retenção (busca mídias antigas ainda não arquivadas).
CREATE INDEX IF NOT EXISTS idx_midias_retencao
    ON midias (criado_em)
    WHERE arquivada_em IS NULL;
