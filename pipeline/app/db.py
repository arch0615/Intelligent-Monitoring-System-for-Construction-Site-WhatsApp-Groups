"""Acesso ao PostgreSQL para o pipeline.

Lê mensagens capturadas, grava texto transcrito/extraído e as análises da Claude.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .config import config


@dataclass
class Mensagem:
    id: int
    grupo_id: int
    tipo: str
    texto: str | None
    enviada_em: Any
    midias: list[dict[str, Any]]


def _connect() -> psycopg.Connection:
    return psycopg.connect(config.pg_dsn, row_factory=dict_row, autocommit=False)


def carregar_mensagem(mensagem_id: int) -> Mensagem | None:
    """Carrega a mensagem + suas mídias para processamento."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, grupo_id, tipo, texto, enviada_em FROM mensagens WHERE id = %s",
            (mensagem_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        cur.execute(
            "SELECT tipo, mime_type, caminho, duracao_seg FROM midias WHERE mensagem_id = %s",
            (mensagem_id,),
        )
        midias = cur.fetchall()
    return Mensagem(
        id=row["id"],
        grupo_id=row["grupo_id"],
        tipo=row["tipo"],
        texto=row["texto"],
        enviada_em=row["enviada_em"],
        midias=midias,
    )


def marcar_status(mensagem_id: int, status: str, erro: str | None = None) -> None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE mensagens SET status = %s, erro_detalhe = %s WHERE id = %s",
            (status, erro, mensagem_id),
        )
        conn.commit()


def gravar_texto(mensagem_id: int, texto: str, origem: str) -> None:
    """Grava o texto derivado (transcrição de áudio/vídeo ou extração de doc)."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE mensagens SET texto = %s, texto_origem = %s WHERE id = %s",
            (texto, origem, mensagem_id),
        )
        conn.commit()


def analises_urgentes_sem_alerta(
    mensagem_id: int, urgencias: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Retorna análises urgentes desta mensagem que ainda NÃO foram alertadas.

    A junção com `alertas` garante dedup: uma situação crítica só dispara um
    alerta, mesmo se a mensagem for reprocessada.
    """
    if not urgencias:
        return []
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.id, a.categoria, a.urgencia, a.resumo,
                   g.nome AS grupo_nome, r.nome_push AS remetente
            FROM analises a
            JOIN mensagens m ON m.id = a.mensagem_id
            JOIN grupos g    ON g.id = m.grupo_id
            LEFT JOIN remetentes r ON r.id = m.remetente_id
            LEFT JOIN alertas al ON al.analise_id = a.id
            WHERE a.mensagem_id = %s
              AND a.urgencia = ANY(%s)
              AND al.id IS NULL
            """,
            (mensagem_id, list(urgencias)),
        )
        return cur.fetchall()


def registrar_alerta(analise_id: int, canal: str, sucesso: bool, detalhe: str | None = None) -> None:
    """Registra o disparo de um alerta (base do dedup acima)."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO alertas (analise_id, canal, sucesso, detalhe) VALUES (%s, %s, %s, %s)",
            (analise_id, canal, sucesso, detalhe),
        )
        conn.commit()


def gravar_analises(mensagem_id: int, itens: list[dict[str, Any]], modelo: str) -> None:
    """Grava as análises da Claude. Uma mensagem pode gerar 0..N itens."""
    if not itens:
        return
    with _connect() as conn, conn.cursor() as cur:
        for item in itens:
            cur.execute(
                """INSERT INTO analises
                     (mensagem_id, categoria, urgencia, resumo, confianca, modelo)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    mensagem_id,
                    item["categoria"],
                    item.get("urgencia", "baixa"),
                    item["resumo"],
                    item.get("confianca"),
                    modelo,
                ),
            )
        conn.commit()
