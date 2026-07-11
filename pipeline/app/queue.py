"""Consumo do Redis Stream publicado pela captura.

Usa grupo de consumidores para entrega confiável: cada evento é confirmado (ACK)
só após processado. Se o pipeline cair no meio, o evento volta a ser entregue
(sem perda de dados — RNF-05).
"""
from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import datetime

import redis

from .config import config, logger

_r = redis.Redis(host=config.REDIS_HOST, port=config.REDIS_PORT, password=config.REDIS_PASSWORD, decode_responses=True)


def garantir_grupo() -> None:
    """Cria o grupo de consumidores (idempotente)."""
    try:
        _r.xgroup_create(config.REDIS_STREAM, config.REDIS_GROUP, id="0", mkstream=True)
        logger.info("Grupo de consumidores '%s' criado", config.REDIS_GROUP)
    except redis.ResponseError as err:
        if "BUSYGROUP" not in str(err):
            raise  # grupo já existe é esperado; outros erros propagam


def consumir(consumidor: str = "pipeline-1", bloco_ms: int = 5000) -> Iterator[tuple[str, int]]:
    """Itera indefinidamente entregando (id_do_evento, mensagem_id)."""
    garantir_grupo()
    while True:
        try:
            # Bloqueia esperando novas mensagens; o heartbeat de saúde roda em
            # thread separada (ver worker.py), pois ficar bloqueado aqui é normal.
            resposta = _r.xreadgroup(
                config.REDIS_GROUP,
                consumidor,
                {config.REDIS_STREAM: ">"},
                count=10,
                block=bloco_ms,
            )
        except redis.exceptions.TimeoutError:
            # Janela de `block` sem mensagens: comportamento NORMAL em ocioso.
            # (o cliente redis levanta TimeoutError no bloqueio sem dados)
            continue
        except redis.exceptions.ConnectionError as err:
            # Redis indisponível temporariamente: aguarda e tenta de novo,
            # sem derrubar o worker (RNF-02 — estabilidade).
            logger.warning("Redis indisponível, reconectando em 2s: %s", err)
            time.sleep(2)
            continue
        if not resposta:
            continue
        for _stream, eventos in resposta:
            for evento_id, campos in eventos:
                yield evento_id, int(campos["mensagem_id"])


def confirmar(evento_id: str) -> None:
    """ACK do evento processado."""
    _r.xack(config.REDIS_STREAM, config.REDIS_GROUP, evento_id)


def registrar_saude() -> None:
    """Heartbeat de saúde (Etapa 5). Chave com TTL 90s, lida pela API."""
    _r.set("saude:pipeline", datetime.now().isoformat(), ex=90)
