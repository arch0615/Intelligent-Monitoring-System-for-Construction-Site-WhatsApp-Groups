"""Manutenção / hardening (Etapa 5).

Política de retenção de mídia: remove do disco os arquivos mais antigos que
RETENCAO_MIDIA_DIAS, marcando `midias.arquivada_em`. Os metadados, o texto
transcrito/extraído e as análises permanecem no banco — só o binário pesado
(áudio/vídeo/imagem) é descartado, evitando encher o disco do VPS.
"""
from __future__ import annotations

import os

import psycopg
from psycopg.rows import dict_row

from .config import config, logger


def arquivar_midia_antiga() -> int:
    """Arquiva mídias mais antigas que o limite de retenção. Retorna a quantidade."""
    if config.RETENCAO_MIDIA_DIAS <= 0:
        return 0

    arquivadas = 0
    with psycopg.connect(config.pg_dsn, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, caminho FROM midias
            WHERE arquivada_em IS NULL
              AND criado_em < now() - (%s || ' days')::interval
            """,
            (config.RETENCAO_MIDIA_DIAS,),
        )
        for midia in cur.fetchall():
            try:
                if os.path.isfile(midia["caminho"]):
                    os.remove(midia["caminho"])
            except OSError as err:
                logger.warning("Falha ao remover arquivo %s: %s", midia["caminho"], err)
            cur.execute("UPDATE midias SET arquivada_em = now() WHERE id = %s", (midia["id"],))
            arquivadas += 1
        conn.commit()

    if arquivadas:
        logger.info("Retenção de mídia: %d arquivo(s) arquivado(s)", arquivadas)
    return arquivadas
