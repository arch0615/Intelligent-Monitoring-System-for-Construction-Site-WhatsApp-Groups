import pino from "pino";
import { config } from "./config.js";

// Logger estruturado. O Baileys também aceita um logger pino (passado em makeWASocket).
export const logger = pino({
  level: config.logLevel,
  transport: {
    target: "pino-pretty",
    options: { colorize: true, translateTime: "SYS:standard" },
  },
});
