"""Transcrição de áudio com faster-whisper (local, sem custo de API) — RF-07.

O modelo é carregado uma vez (lazy) e reaproveitado entre mensagens.
"""
from __future__ import annotations

from functools import lru_cache

from faster_whisper import WhisperModel

from .config import config, logger


@lru_cache(maxsize=1)
def _modelo() -> WhisperModel:
    logger.info("Carregando modelo Whisper '%s' (%s)", config.WHISPER_MODEL, config.WHISPER_COMPUTE_TYPE)
    return WhisperModel(
        config.WHISPER_MODEL,
        device="cpu",
        compute_type=config.WHISPER_COMPUTE_TYPE,
        download_root=config.MODELS_DIR,
    )


def transcrever(caminho_audio: str, idioma: str = "pt") -> str:
    """Transcreve um arquivo de áudio para texto."""
    segmentos, _info = _modelo().transcribe(caminho_audio, language=idioma, vad_filter=True)
    texto = " ".join(seg.text.strip() for seg in segmentos).strip()
    logger.debug("Transcrição (%d chars) de %s", len(texto), caminho_audio)
    return texto
