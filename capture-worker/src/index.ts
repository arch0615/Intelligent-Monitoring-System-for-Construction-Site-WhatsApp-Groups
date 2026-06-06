// Ponto de entrada do worker de captura (Etapa 1).
// Conecta ao número dedicado, lê mensagens em tempo real, grava no Postgres
// e publica eventos no Redis para o pipeline de processamento (Etapa 2).

import { iniciarCaptura } from "./whatsapp.js";
import { logger } from "./logger.js";
import { pool } from "./db.js";
import { redis } from "./redis.js";

async function main(): Promise<void> {
  logger.info("Iniciando worker de captura (Baileys)...");
  await iniciarCaptura();
}

// Encerramento limpo (fecha conexões de banco/redis).
async function encerrar(sinal: string): Promise<void> {
  logger.info({ sinal }, "Encerrando worker de captura");
  await Promise.allSettled([pool.end(), redis.quit()]);
  process.exit(0);
}

process.on("SIGINT", () => encerrar("SIGINT"));
process.on("SIGTERM", () => encerrar("SIGTERM"));

main().catch((err) => {
  logger.fatal({ err }, "Falha fatal no worker de captura");
  process.exit(1);
});
