"""Extração de texto de documentos (PDF / DOCX)."""
from __future__ import annotations

from pathlib import Path

import pdfplumber
from docx import Document

from .config import logger


def extrair_texto(caminho: str, mime_type: str | None = None) -> str:
    """Extrai texto de um documento conforme o tipo. Retorna string vazia se não suportado."""
    ext = Path(caminho).suffix.lower()
    try:
        if ext == ".pdf" or (mime_type and "pdf" in mime_type):
            return _extrair_pdf(caminho)
        if ext in (".docx",) or (mime_type and "word" in mime_type):
            return _extrair_docx(caminho)
    except Exception:  # noqa: BLE001 — extração é best-effort
        logger.exception("Falha ao extrair texto de %s", caminho)
    logger.warning("Tipo de documento não suportado para extração: %s", caminho)
    return ""


def _extrair_pdf(caminho: str) -> str:
    partes: list[str] = []
    with pdfplumber.open(caminho) as pdf:
        for pagina in pdf.pages:
            partes.append(pagina.extract_text() or "")
    return "\n".join(partes).strip()


def _extrair_docx(caminho: str) -> str:
    doc = Document(caminho)
    return "\n".join(p.text for p in doc.paragraphs).strip()
