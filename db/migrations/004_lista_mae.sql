-- =====================================================================
-- Lista Mãe — estado persistente de resolução dos itens (análises).
--
-- Cada análise (pendência / dúvida / decisão) vira um item de uma lista de
-- tarefas acumulada. Guardamos se o item foi resolvido (com data e autor) e
-- se já foi incorporado à Lista Mãe.
-- =====================================================================

ALTER TABLE analises
  ADD COLUMN IF NOT EXISTS resolvido     boolean     NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS resolvido_em  timestamptz,
  ADD COLUMN IF NOT EXISTS resolvido_por bigint REFERENCES usuarios(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS na_lista_mae  boolean     NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS adicionado_em timestamptz;

-- Backfill: todo o histórico já nasce dentro da Lista Mãe ("itens desde o início").
-- Itens novos criados pelo pipeline daqui pra frente entram como não-adicionados
-- (na_lista_mae = false) e aparecem na seção "Novos itens" para triagem.
UPDATE analises
   SET na_lista_mae = true,
       adicionado_em = COALESCE(adicionado_em, criado_em)
 WHERE na_lista_mae = false;

CREATE INDEX IF NOT EXISTS idx_analises_lista_mae ON analises (na_lista_mae, resolvido);
CREATE INDEX IF NOT EXISTS idx_analises_criado_em ON analises (criado_em);
