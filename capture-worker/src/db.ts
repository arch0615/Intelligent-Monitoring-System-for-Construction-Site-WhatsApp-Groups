import pg from "pg";
import { config } from "./config.js";
import { logger } from "./logger.js";

// Pool de conexões com o PostgreSQL. A captura grava mensagens, mídia-metadados
// e garante dedup por (grupo, wa_message_id). Idempotente: reprocessar o mesmo
// evento não duplica linhas.

const { Pool } = pg;

export const pool = new Pool({
  host: config.postgres.host,
  port: config.postgres.port,
  user: config.postgres.user,
  password: config.postgres.password,
  database: config.postgres.database,
});

export interface MensagemNormalizada {
  grupoJid: string;
  grupoNome?: string;
  remetenteJid?: string;
  remetenteNome?: string;
  waMessageId: string;
  tipo: "texto" | "audio" | "imagem" | "video" | "documento" | "outro";
  enviadaEm: Date;
  texto?: string;
  textoOrigem?: "original" | "transcricao" | "ocr_extracao";
  payloadBruto: unknown;
}

export interface MidiaNormalizada {
  tipo: MensagemNormalizada["tipo"];
  mimeType?: string;
  caminho: string;
  tamanhoBytes?: number;
  duracaoSeg?: number;
}

/** Garante a existência do grupo e retorna seu id. Cria desativado? Não —
 *  na captura assumimos ativo; o painel (RF-08) controla ativação/desativação. */
async function upsertGrupo(client: pg.PoolClient, jid: string, nome?: string): Promise<number> {
  const res = await client.query(
    `INSERT INTO grupos (wa_jid, nome) VALUES ($1, $2)
       ON CONFLICT (wa_jid) DO UPDATE SET nome = COALESCE(EXCLUDED.nome, grupos.nome)
       RETURNING id`,
    [jid, nome ?? null],
  );
  return res.rows[0].id;
}

async function upsertRemetente(
  client: pg.PoolClient,
  jid?: string,
  nome?: string,
): Promise<number | null> {
  if (!jid) return null;
  const res = await client.query(
    `INSERT INTO remetentes (wa_jid, nome_push) VALUES ($1, $2)
       ON CONFLICT (wa_jid) DO UPDATE SET nome_push = COALESCE(EXCLUDED.nome_push, remetentes.nome_push)
       RETURNING id`,
    [jid, nome ?? null],
  );
  return res.rows[0].id;
}

/**
 * Persiste a mensagem + mídias numa transação. Retorna o id da mensagem,
 * ou null se já existia (dedup). O id é usado para publicar o evento no Redis.
 */
export async function salvarMensagem(
  msg: MensagemNormalizada,
  midias: MidiaNormalizada[] = [],
): Promise<number | null> {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");

    const grupoId = await upsertGrupo(client, msg.grupoJid, msg.grupoNome);
    const remetenteId = await upsertRemetente(client, msg.remetenteJid, msg.remetenteNome);

    const insert = await client.query(
      `INSERT INTO mensagens
         (grupo_id, remetente_id, wa_message_id, tipo, enviada_em, texto, texto_origem, payload_bruto)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
       ON CONFLICT (grupo_id, wa_message_id) DO NOTHING
       RETURNING id`,
      [
        grupoId,
        remetenteId,
        msg.waMessageId,
        msg.tipo,
        msg.enviadaEm,
        msg.texto ?? null,
        msg.textoOrigem ?? null,
        JSON.stringify(msg.payloadBruto),
      ],
    );

    // Dedup: mensagem já capturada antes -> nada a fazer.
    if (insert.rowCount === 0) {
      await client.query("ROLLBACK");
      return null;
    }

    const mensagemId: number = insert.rows[0].id;

    for (const m of midias) {
      await client.query(
        `INSERT INTO midias (mensagem_id, tipo, mime_type, caminho, tamanho_bytes, duracao_seg)
         VALUES ($1, $2, $3, $4, $5, $6)`,
        [mensagemId, m.tipo, m.mimeType ?? null, m.caminho, m.tamanhoBytes ?? null, m.duracaoSeg ?? null],
      );
    }

    await client.query("COMMIT");
    return mensagemId;
  } catch (err) {
    await client.query("ROLLBACK");
    logger.error({ err }, "Falha ao salvar mensagem");
    throw err;
  } finally {
    client.release();
  }
}

/** Define/atualiza o nome (assunto) de um grupo. Mantém o nome em dia mesmo
 *  quando o grupo é renomeado no WhatsApp. */
export async function atualizarNomeGrupo(jid: string, nome: string): Promise<void> {
  await pool.query(
    `INSERT INTO grupos (wa_jid, nome) VALUES ($1, $2)
       ON CONFLICT (wa_jid) DO UPDATE SET nome = EXCLUDED.nome`,
    [jid, nome],
  );
}

/** Retorna o conjunto de wa_jid de grupos ativos (RF-08). A captura ignora
 *  mensagens de grupos que não estejam ativos no painel. */
export async function gruposAtivos(): Promise<Set<string>> {
  const res = await pool.query<{ wa_jid: string }>(
    `SELECT wa_jid FROM grupos WHERE is_active = true`,
  );
  return new Set(res.rows.map((r) => r.wa_jid));
}
