import {
  makeWASocket,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  downloadMediaMessage,
  DisconnectReason,
  type WAMessage,
  type WASocket,
} from "@whiskeysockets/baileys";
import { Boom } from "@hapi/boom";
import { writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { config } from "./config.js";
import { logger } from "./logger.js";
import {
  salvarMensagem,
  atualizarNomeGrupo,
  type MensagemNormalizada,
  type MidiaNormalizada,
} from "./db.js";
import { publicarEvento } from "./redis.js";
import { notificarBloqueio } from "./alerts.js";

// ---------------------------------------------------------------------
// Conexão estável ao número dedicado (Etapa 1).
// - Login por PAIRING CODE (sem necessidade de scanear QR no celular).
// - Sessão persistida em disco (auth_state) -> reconexão automática + Plano B.
// - SOMENTE LEITURA: nunca enviamos mensagens (mitiga bloqueio do número).
// ---------------------------------------------------------------------

const TIPOS_MIDIA = {
  audioMessage: "audio",
  imageMessage: "imagem",
  videoMessage: "video",
  documentMessage: "documento",
} as const;

/** Extrai texto "humano" de uma mensagem (corpo, legenda, etc.). */
function extrairTexto(msg: WAMessage): string | undefined {
  const m = msg.message;
  if (!m) return undefined;
  return (
    m.conversation ??
    m.extendedTextMessage?.text ??
    m.imageMessage?.caption ??
    m.videoMessage?.caption ??
    m.documentMessage?.caption ??
    undefined
  );
}

/** Determina o tipo da mensagem para o nosso enum. */
function determinarTipo(msg: WAMessage): MensagemNormalizada["tipo"] {
  const m = msg.message;
  if (!m) return "outro";
  for (const [chave, tipo] of Object.entries(TIPOS_MIDIA)) {
    if (chave in m) return tipo as MensagemNormalizada["tipo"];
  }
  if (m.conversation || m.extendedTextMessage) return "texto";
  return "outro";
}

/** Baixa e descriptografa a mídia, gravando no MEDIA_DIR. Retorna metadados. */
async function baixarMidia(
  msg: WAMessage,
  tipo: MensagemNormalizada["tipo"],
  waMessageId: string,
): Promise<MidiaNormalizada | undefined> {
  if (tipo === "texto" || tipo === "outro") return undefined;
  try {
    const buffer = (await downloadMediaMessage(msg, "buffer", {})) as Buffer;
    const dir = join(config.mediaDir, tipo);
    await mkdir(dir, { recursive: true });
    const caminho = join(dir, `${waMessageId}`);
    await writeFile(caminho, buffer);

    const conteudo = msg.message?.[`${tipo === "imagem" ? "image" : tipo}Message` as keyof typeof msg.message] as
      | { mimetype?: string; seconds?: number }
      | undefined;

    return {
      tipo,
      mimeType: conteudo?.mimetype,
      caminho,
      tamanhoBytes: buffer.length,
      duracaoSeg: conteudo?.seconds,
    };
  } catch (err) {
    logger.error({ err, waMessageId }, "Falha ao baixar mídia");
    return undefined;
  }
}

/** Processa uma mensagem recebida: normaliza, baixa mídia, grava e publica. */
async function processarMensagem(msg: WAMessage): Promise<void> {
  // Ignora mensagens enviadas por nós e status/broadcast.
  const jid = msg.key.remoteJid ?? "";
  if (msg.key.fromMe) return;
  if (!jid.endsWith("@g.us")) return; // somente grupos
  if (!msg.message) return;

  const waMessageId = msg.key.id;
  if (!waMessageId) return;

  const tipo = determinarTipo(msg);
  const midia = await baixarMidia(msg, tipo, waMessageId);

  const normalizada: MensagemNormalizada = {
    grupoJid: jid,
    remetenteJid: msg.key.participant ?? undefined,
    remetenteNome: msg.pushName ?? undefined,
    waMessageId,
    tipo,
    enviadaEm: new Date(Number(msg.messageTimestamp) * 1000),
    texto: extrairTexto(msg),
    textoOrigem: extrairTexto(msg) ? "original" : undefined,
    payloadBruto: msg,
  };

  const mensagemId = await salvarMensagem(normalizada, midia ? [midia] : []);
  if (mensagemId === null) {
    logger.debug({ waMessageId }, "Mensagem duplicada — ignorada (dedup)");
    return;
  }

  await publicarEvento(mensagemId);
  logger.info({ mensagemId, tipo, grupo: jid }, "Mensagem capturada");
}

/** Busca o assunto (nome) de todos os grupos participantes e atualiza no banco.
 *  Roda ao conectar, para preencher os nomes dos grupos já existentes. */
async function sincronizarNomesGrupos(sock: WASocket): Promise<void> {
  try {
    const grupos = await sock.groupFetchAllParticipating();
    let n = 0;
    for (const [jid, meta] of Object.entries(grupos)) {
      if (meta.subject) {
        await atualizarNomeGrupo(jid, meta.subject);
        n++;
      }
    }
    logger.info(`Nomes de ${n} grupo(s) sincronizados`);
  } catch (err) {
    logger.error({ err }, "Falha ao sincronizar nomes de grupos");
  }
}

/** Inicia o socket Baileys com reconexão automática. */
export async function iniciarCaptura(): Promise<void> {
  const { state, saveCreds } = await useMultiFileAuthState(config.whatsapp.authDir);
  const { version } = await fetchLatestBaileysVersion();

  const sock: WASocket = makeWASocket({
    version,
    auth: state,
    logger: logger.child({ modulo: "baileys" }),
    // SOMENTE LEITURA — não marcamos como online nem enviamos recibos de leitura
    // para reduzir pegada/risco de bloqueio do número.
    markOnlineOnConnect: false,
  });

  // Login por pairing code na primeira conexão (em vez de QR).
  if (!sock.authState.creds.registered && config.whatsapp.phoneNumber) {
    setTimeout(async () => {
      try {
        const code = await sock.requestPairingCode(config.whatsapp.phoneNumber);
        logger.info(`>>> PAIRING CODE: ${code}  (insira no WhatsApp do número dedicado)`);
      } catch (err) {
        logger.error({ err }, "Falha ao solicitar pairing code");
      }
    }, 3000);
  }

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect } = update;
    if (connection === "close") {
      const status = (lastDisconnect?.error as Boom)?.output?.statusCode;
      const deveReconectar = status !== DisconnectReason.loggedOut;
      logger.warn({ status, deveReconectar }, "Conexão fechada");
      if (deveReconectar) {
        setTimeout(() => iniciarCaptura(), 3000); // reconexão automática
      } else {
        // loggedOut = número deslogado/bloqueado -> aciona Plano B (RF-09).
        logger.error("Número deslogado — acionando Plano B (notificação + número de backup)");
        void notificarBloqueio(`desconexão definitiva (status ${status ?? "desconhecido"})`);
      }
    } else if (connection === "open") {
      logger.info("Conexão estabelecida — capturando em tempo real");
      void sincronizarNomesGrupos(sock); // backfill dos nomes dos grupos
    }
  });

  // Mantém os nomes dos grupos em dia: criação e renomeação.
  sock.ev.on("groups.upsert", async (grupos) => {
    for (const g of grupos) {
      if (g.id && g.subject) {
        try {
          await atualizarNomeGrupo(g.id, g.subject);
        } catch (err) {
          logger.error({ err }, "Falha ao salvar nome de grupo (upsert)");
        }
      }
    }
  });
  sock.ev.on("groups.update", async (updates) => {
    for (const u of updates) {
      if (u.id && u.subject) {
        try {
          await atualizarNomeGrupo(u.id, u.subject);
        } catch (err) {
          logger.error({ err }, "Falha ao atualizar nome de grupo (update)");
        }
      }
    }
  });

  // Mensagens novas em tempo real.
  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;
    for (const msg of messages) {
      try {
        await processarMensagem(msg);
      } catch (err) {
        logger.error({ err }, "Erro ao processar mensagem");
      }
    }
  });
}
