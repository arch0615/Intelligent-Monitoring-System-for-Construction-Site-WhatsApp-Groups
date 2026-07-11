import Redis from "ioredis";
import { config } from "./config.js";
import { logger } from "./logger.js";

// Publicação de eventos no Redis Stream. Usamos Stream (não pub/sub) para que
// o pipeline Python possa consumir com grupo de consumidores, confirmar (ACK)
// e reprocessar em caso de queda — sem perda de dados (RNF-05).

export const redis = new Redis({
  host: config.redis.host,
  port: config.redis.port,
  password: config.redis.password,
  maxRetriesPerRequest: null,
});

redis.on("error", (err) => logger.error({ err }, "Erro no Redis"));

/**
 * Publica um evento "mensagem capturada" para o pipeline processar.
 * Carrega apenas o id da mensagem — o pipeline busca o conteúdo no Postgres
 * (fonte da verdade), mantendo o payload do stream pequeno.
 */
export async function publicarEvento(mensagemId: number): Promise<void> {
  await redis.xadd(config.redis.stream, "*", "mensagem_id", String(mensagemId));
  logger.debug({ mensagemId }, "Evento publicado no stream");
}

// Heartbeat de saúde (Etapa 5). A API lê esta chave para mostrar se a captura
// está viva. TTL de 90s: se o worker cair, a chave expira e o painel acusa.
export async function registrarSaude(): Promise<void> {
  await redis.set("saude:captura", new Date().toISOString(), "EX", 90);
}
