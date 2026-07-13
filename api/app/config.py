"""Configuração da API (lida do ambiente)."""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Variável de ambiente obrigatória ausente: {name}")
    return value


class Config:
    PG_HOST = os.environ.get("POSTGRES_HOST", "postgres")
    PG_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
    PG_USER = _required("POSTGRES_USER")
    PG_PASSWORD = _required("POSTGRES_PASSWORD")
    PG_DB = _required("POSTGRES_DB")

    @property
    def pg_dsn(self) -> str:
        return (
            f"host={self.PG_HOST} port={self.PG_PORT} user={self.PG_USER} "
            f"password={self.PG_PASSWORD} dbname={self.PG_DB}"
        )

    # Entrega do relatório diário (Telegram recomendado — NÃO usar o nº de
    # monitoramento, que é somente leitura).
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

    # API Claude — usada para o resumo executivo do histórico (spec #3).
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")

    # Horário do relatório diário (cron). Padrão: 18h, horário do servidor.
    RELATORIO_HORA = int(os.environ.get("RELATORIO_HORA", "18"))
    RELATORIO_MINUTO = int(os.environ.get("RELATORIO_MINUTO", "0"))

    # Monitor de saúde (alertas por Telegram). Dispara um alerta quando um
    # componente fica fora por mais que SAUDE_ALERTA_MINUTOS; verifica a cada
    # SAUDE_CHECK_SEGUNDOS. Evita repetir alerta do mesmo incidente.
    SAUDE_ALERTA_MINUTOS = int(os.environ.get("SAUDE_ALERTA_MINUTOS", "5"))
    SAUDE_CHECK_SEGUNDOS = int(os.environ.get("SAUDE_CHECK_SEGUNDOS", "60"))

    # Retenção de mídia (Etapa 5) — dias após os quais o binário é removido do
    # disco (metadados e texto/análise permanecem no banco). 0 = nunca arquivar.
    RETENCAO_MIDIA_DIAS = int(os.environ.get("RETENCAO_MIDIA_DIAS", "90"))
    MEDIA_DIR = os.environ.get("MEDIA_DIR", "/media")

    TZ = os.environ.get("TZ", "America/Sao_Paulo")
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "info").upper()

    # Segredo para assinar o cookie de sessão (login). Definir no .env.
    SESSION_SECRET = os.environ.get("SESSION_SECRET", "troque-este-segredo-de-sessao")


config = Config()

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("api")
