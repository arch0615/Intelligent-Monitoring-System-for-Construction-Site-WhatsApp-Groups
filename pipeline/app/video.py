"""Processamento de VÍDEO (RF-06) via ffmpeg.

- Extrai frames em intervalo CONFIGURÁVEL (P-05, VIDEO_FRAME_INTERVAL_SECONDS).
- Extrai a trilha de áudio para transcrição via Whisper.

ATENÇÃO DE CUSTO: o volume/duração de vídeos (P-04) impacta diretamente o custo
da Claude (análise de frames) e o tempo de processamento. Confirmar com o cliente
antes de habilitar em escala.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .config import config, logger


def extrair_audio(caminho_video: str) -> str:
    """Extrai a trilha de áudio do vídeo para um WAV temporário (16kHz mono)."""
    saida = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    cmd = [
        "ffmpeg", "-y", "-i", caminho_video,
        "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", saida,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return saida


def extrair_frames(caminho_video: str, intervalo_seg: int | None = None) -> list[str]:
    """Extrai 1 frame a cada `intervalo_seg` segundos. Retorna os caminhos dos JPEGs."""
    intervalo = intervalo_seg or config.VIDEO_FRAME_INTERVAL
    destino = Path(tempfile.mkdtemp(prefix="frames_"))
    padrao = str(destino / "frame_%04d.jpg")
    cmd = [
        "ffmpeg", "-y", "-i", caminho_video,
        "-vf", f"fps=1/{intervalo}",
        padrao,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    frames = sorted(str(p) for p in destino.glob("frame_*.jpg"))
    logger.debug("Extraídos %d frames de %s (intervalo %ds)", len(frames), caminho_video, intervalo)
    return frames
