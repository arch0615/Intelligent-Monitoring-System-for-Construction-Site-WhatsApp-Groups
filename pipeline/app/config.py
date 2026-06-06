"""Configuração centralizada lida do ambiente (.env via docker-compose)."""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()  # no-op em produção (vars vêm do compose); útil em dev local


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Variável de ambiente obrigatória ausente: {name}")
    return value


class Config:
    # PostgreSQL
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

    # Redis
    REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
    REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
    REDIS_STREAM = os.environ.get("REDIS_STREAM", "captura:eventos")
    REDIS_GROUP = os.environ.get("REDIS_CONSUMER_GROUP", "pipeline")

    # Claude
    ANTHROPIC_API_KEY = _required("ANTHROPIC_API_KEY")
    CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")

    # Whisper (transcrição local)
    WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
    WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")

    # Vídeo (RF-06) — intervalo configurável de extração de frames (P-05)
    VIDEO_FRAME_INTERVAL = int(os.environ.get("VIDEO_FRAME_INTERVAL_SECONDS", "10"))

    MEDIA_DIR = os.environ.get("MEDIA_DIR", "/media")
    MODELS_DIR = os.environ.get("WHISPER_MODELS_DIR", "/app/models")
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "info").upper()


config = Config()

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("pipeline")
