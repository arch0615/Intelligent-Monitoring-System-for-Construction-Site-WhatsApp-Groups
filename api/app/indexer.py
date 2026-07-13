"""Indexação de embeddings para a busca semântica (spec #5).

Percorre as mensagens com texto ainda sem embedding, gera os vetores em lote e
grava no banco. Usado tanto na reindexação inicial quanto pelo job periódico
(mensagens novas processadas pelo pipeline entram aqui em poucos minutos).
"""
from __future__ import annotations

from . import db, embeddings
from .config import logger


def indexar_pendentes(lote: int = 128, max_total: int | None = None) -> int:
    """Indexa mensagens sem embedding. Devolve quantas foram indexadas."""
    total = 0
    while True:
        pendentes = db.mensagens_sem_embedding(lote)
        if not pendentes:
            break
        vetores = embeddings.embed([m["texto"] for m in pendentes])
        db.salvar_embeddings([(m["id"], v) for m, v in zip(pendentes, vetores)])
        total += len(pendentes)
        if len(pendentes) < lote or (max_total is not None and total >= max_total):
            break
    if total:
        logger.info("Busca semântica: %d mensagem(ns) indexada(s)", total)
    return total
