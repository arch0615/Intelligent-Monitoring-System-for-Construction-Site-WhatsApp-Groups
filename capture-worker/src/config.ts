// Configuração centralizada lida do ambiente (.env via docker-compose).
// Falha rápido se algo essencial estiver faltando.

function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Variável de ambiente obrigatória ausente: ${name}`);
  }
  return value;
}

export const config = {
  postgres: {
    host: process.env.POSTGRES_HOST ?? "postgres",
    port: Number(process.env.POSTGRES_PORT ?? 5432),
    user: required("POSTGRES_USER"),
    password: required("POSTGRES_PASSWORD"),
    database: required("POSTGRES_DB"),
  },
  redis: {
    host: process.env.REDIS_HOST ?? "redis",
    port: Number(process.env.REDIS_PORT ?? 6379),
    stream: process.env.REDIS_STREAM ?? "captura:eventos",
  },
  whatsapp: {
    // Número dedicado em formato internacional só com dígitos (ex.: 5511999998888).
    phoneNumber: process.env.WA_PHONE_NUMBER ?? "",
    authDir: process.env.WA_AUTH_DIR ?? "./auth_state",
  },
  mediaDir: process.env.MEDIA_DIR ?? "/media",
  logLevel: process.env.LOG_LEVEL ?? "info",
  // Alertas operacionais (Plano B): notificação de bloqueio/desconexão do número.
  telegram: {
    botToken: process.env.TELEGRAM_BOT_TOKEN ?? "",
    chatId: process.env.TELEGRAM_CHAT_ID ?? "",
  },
};
