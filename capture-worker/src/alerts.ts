import { config } from "./config.js";
import { logger } from "./logger.js";

// Alertas operacionais do worker de captura (Plano B — RF-09).
// Notifica imediatamente quando o número de monitoramento é deslogado/bloqueado,
// para que a equipe acione o número de backup e reconecte rápido.
//
// Usa o fetch global do Node 22 (sem dependência extra). Telegram recomendado —
// nunca enviado pelo próprio número de monitoramento.

export async function notificarOperacional(texto: string): Promise<void> {
  if (!config.telegram.botToken || !config.telegram.chatId) {
    logger.warn("Telegram não configurado — alerta operacional não enviado");
    return;
  }
  const url = `https://api.telegram.org/bot${config.telegram.botToken}/sendMessage`;
  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: config.telegram.chatId, text: texto, parse_mode: "Markdown" }),
    });
    if (!resp.ok) {
      logger.error({ status: resp.status }, "Falha ao enviar alerta operacional");
    }
  } catch (err) {
    logger.error({ err }, "Erro ao enviar alerta operacional");
  }
}

/** Notificação específica de bloqueio/logout do número (aciona o Plano B). */
export async function notificarBloqueio(motivo: string): Promise<void> {
  await notificarOperacional(
    `🚨 *Número de monitoramento desconectado*\n` +
      `Motivo: ${motivo}\n` +
      `Ação: usar o número de BACKUP para reingressar nos grupos e reconectar. ` +
      `Os dados no banco estão preservados.`,
  );
}
