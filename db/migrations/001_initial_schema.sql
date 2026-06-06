-- =====================================================================
-- 001_initial_schema.sql
-- Esquema inicial do Sistema de Monitoramento de Grupos de WhatsApp.
-- Roda automaticamente na primeira subida do Postgres (initdb).
--
-- Cobre: gestão de grupos (RF-08), captura (RF-01/RF-10), análise da
-- Claude (RF-02) e base para relatórios/histórico/alertas (RF-03..RF-05).
-- =====================================================================

-- Busca full-text (RF-04) usa to_tsvector; pg_trgm ajuda em buscas por
-- similaridade. pgvector fica para uma migration futura (busca semântica).
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------------------------------------------------------------------
-- GRUPOS monitorados. O cliente ativa/desativa pelo painel (RF-08);
-- o worker de captura só processa grupos com is_active = true.
-- ---------------------------------------------------------------------
CREATE TABLE grupos (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    wa_jid        TEXT        NOT NULL UNIQUE,      -- ex.: 12036304...@g.us
    nome          TEXT,
    is_active     BOOLEAN     NOT NULL DEFAULT true,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- REMETENTES (participantes). O número aparece como participante do grupo
-- (RNF-01, ressalva honesta). Guardamos para atribuir autoria às mensagens.
-- ---------------------------------------------------------------------
CREATE TABLE remetentes (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    wa_jid     TEXT        NOT NULL UNIQUE,         -- ex.: 5511999998888@s.whatsapp.net
    nome_push  TEXT,                                -- pushName do WhatsApp
    criado_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- MENSAGENS capturadas (RF-01). Uma linha por mensagem.
-- payload_bruto (JSONB) preserva o evento original do Baileys para auditoria
-- e reprocessamento. dedup garantido por (grupo, wa_message_id).
-- ---------------------------------------------------------------------
CREATE TYPE tipo_mensagem AS ENUM (
    'texto', 'audio', 'imagem', 'video', 'documento', 'outro'
);

CREATE TYPE status_processamento AS ENUM (
    'capturada',     -- gravada pela captura, ainda não processada
    'processando',   -- consumida pelo pipeline
    'processada',    -- transcrição/extração + análise concluídas
    'erro'           -- falhou (ver erro_detalhe)
);

CREATE TABLE mensagens (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    grupo_id        BIGINT       NOT NULL REFERENCES grupos(id),
    remetente_id    BIGINT       REFERENCES remetentes(id),
    wa_message_id   TEXT         NOT NULL,          -- key.id do WhatsApp
    tipo            tipo_mensagem NOT NULL,
    enviada_em      TIMESTAMPTZ  NOT NULL,          -- messageTimestamp do WA
    capturada_em    TIMESTAMPTZ  NOT NULL DEFAULT now(),

    -- Conteúdo textual: texto da mensagem OU transcrição (áudio/vídeo) OU
    -- texto extraído (documento) OU legenda (imagem/vídeo).
    texto           TEXT,
    -- De onde veio o `texto`: 'original' | 'transcricao' | 'ocr_extracao'
    texto_origem    TEXT,

    status          status_processamento NOT NULL DEFAULT 'capturada',
    erro_detalhe    TEXT,

    payload_bruto   JSONB        NOT NULL,

    -- Coluna gerada para busca full-text (RF-04, consulta de histórico).
    busca           tsvector GENERATED ALWAYS AS
                        (to_tsvector('portuguese', coalesce(texto, ''))) STORED,

    UNIQUE (grupo_id, wa_message_id)
);

CREATE INDEX idx_mensagens_grupo_data ON mensagens (grupo_id, enviada_em DESC);
CREATE INDEX idx_mensagens_status     ON mensagens (status);
CREATE INDEX idx_mensagens_busca      ON mensagens USING GIN (busca);

-- ---------------------------------------------------------------------
-- MÍDIA — metadados dos arquivos baixados/descriptografados pela captura.
-- O binário fica no filesystem (MEDIA_DIR), aqui só o caminho + metadados.
-- ---------------------------------------------------------------------
CREATE TABLE midias (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mensagem_id   BIGINT      NOT NULL REFERENCES mensagens(id) ON DELETE CASCADE,
    tipo          tipo_mensagem NOT NULL,
    mime_type     TEXT,
    caminho       TEXT        NOT NULL,             -- caminho relativo em MEDIA_DIR
    tamanho_bytes BIGINT,
    duracao_seg   NUMERIC,                          -- áudio/vídeo
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_midias_mensagem ON midias (mensagem_id);

-- ---------------------------------------------------------------------
-- ANÁLISES da Claude (RF-02). Uma mensagem pode gerar 0..N itens
-- (uma conversa pode conter mais de uma pendência/dúvida/decisão).
-- ---------------------------------------------------------------------
CREATE TYPE categoria_analise AS ENUM ('pendencia', 'duvida', 'decisao');

CREATE TYPE nivel_urgencia AS ENUM ('baixa', 'media', 'alta', 'critica');

CREATE TABLE analises (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mensagem_id   BIGINT       NOT NULL REFERENCES mensagens(id) ON DELETE CASCADE,
    categoria     categoria_analise NOT NULL,
    urgencia      nivel_urgencia    NOT NULL DEFAULT 'baixa',
    resumo        TEXT         NOT NULL,            -- frase curta para o relatório
    -- Confiança 0..1 reportada pelo modelo (para ordenar/filtrar no painel).
    confianca     NUMERIC,
    modelo        TEXT,                             -- ex.: claude-opus-4-8
    criado_em     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_analises_mensagem    ON analises (mensagem_id);
CREATE INDEX idx_analises_categoria   ON analises (categoria);
CREATE INDEX idx_analises_urgencia    ON analises (urgencia);

-- ---------------------------------------------------------------------
-- ALERTAS disparados (RF-05). Registra o que já foi notificado para não
-- alertar duas vezes a mesma situação crítica.
-- ---------------------------------------------------------------------
CREATE TABLE alertas (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    analise_id   BIGINT      NOT NULL REFERENCES analises(id) ON DELETE CASCADE,
    canal        TEXT        NOT NULL,              -- 'telegram' | 'email'
    enviado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    sucesso      BOOLEAN     NOT NULL DEFAULT true,
    detalhe      TEXT
);

CREATE INDEX idx_alertas_analise ON alertas (analise_id);

-- ---------------------------------------------------------------------
-- Trigger simples para manter grupos.atualizado_em em dia.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_atualizado_em() RETURNS trigger AS $$
BEGIN
    NEW.atualizado_em = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_grupos_atualizado
    BEFORE UPDATE ON grupos
    FOR EACH ROW EXECUTE FUNCTION set_atualizado_em();
