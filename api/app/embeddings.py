"""Embeddings locais para a busca semântica (spec #5).

Usa fastembed (ONNX, leve — sem torch) com um modelo multilíngue de 384 dims,
bom para português. O modelo é baixado uma vez e cacheado em /app/models.
"""
from __future__ import annotations

from functools import lru_cache

from .config import config, logger

MODELO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DIMENSAO = 384
_CACHE_DIR = "/app/models"


@lru_cache(maxsize=1)
def _modelo():
    from fastembed import TextEmbedding

    logger.info("Carregando modelo de embeddings %s (pode baixar na 1ª vez)…", MODELO)
    return TextEmbedding(model_name=MODELO, cache_dir=_CACHE_DIR)


def embed(textos: list[str]) -> list[list[float]]:
    """Gera os embeddings de uma lista de textos."""
    if not textos:
        return []
    return [v.tolist() for v in _modelo().embed(textos)]


def embed_um(texto: str) -> list[float]:
    """Embedding de um único texto (ex.: a pergunta do usuário)."""
    return embed([texto])[0]
