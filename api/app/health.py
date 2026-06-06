"""Verificação de saúde do sistema (Etapa 5 — hardening).

Checa conectividade (Postgres, Redis) e lê os heartbeats dos workers de captura
e do pipeline (chaves com TTL no Redis). Alimenta o endpoint /health e a página
de saúde do painel.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import psycopg
import redis

from .config import config

_redis = redis.Redis(
    host=os.environ.get("REDIS_HOST", "redis"),
    port=int(os.environ.get("REDIS_PORT", "6379")),
    decode_responses=True,
)


def _checar_postgres() -> tuple[bool, str | None]:
    try:
        with psycopg.connect(config.pg_dsn, connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        return True, None
    except Exception as err:  # noqa: BLE001
        return False, str(err)


def _checar_redis() -> tuple[bool, str | None]:
    try:
        _redis.ping()
        return True, None
    except Exception as err:  # noqa: BLE001
        return False, str(err)


def _heartbeat(chave: str) -> dict[str, Any]:
    """Lê um heartbeat e calcula há quantos segundos foi atualizado."""
    valor = _redis.get(chave)
    if not valor:
        return {"vivo": False, "ultimo": None, "ha_segundos": None}
    try:
        ts = datetime.fromisoformat(valor)
        ha = (datetime.now(ts.tzinfo) - ts).total_seconds()
    except ValueError:
        return {"vivo": False, "ultimo": valor, "ha_segundos": None}
    return {"vivo": ha < 90, "ultimo": valor, "ha_segundos": round(ha, 1)}


def status() -> dict[str, Any]:
    pg_ok, pg_err = _checar_postgres()
    redis_ok, redis_err = _checar_redis()
    captura = _heartbeat("saude:captura")
    pipeline = _heartbeat("saude:pipeline")

    tudo_ok = pg_ok and redis_ok and captura["vivo"] and pipeline["vivo"]
    return {
        "status": "ok" if tudo_ok else "degradado",
        "postgres": {"ok": pg_ok, "erro": pg_err},
        "redis": {"ok": redis_ok, "erro": redis_err},
        "captura": captura,
        "pipeline": pipeline,
    }
