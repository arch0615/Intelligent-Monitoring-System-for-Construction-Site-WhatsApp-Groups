"""Consultas para relatório diário (RF-03) e histórico (RF-04)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .config import config

# Ordem de urgência para apresentação (crítica primeiro).
_ORDEM_URGENCIA = "CASE a.urgencia WHEN 'critica' THEN 0 WHEN 'alta' THEN 1 WHEN 'media' THEN 2 ELSE 3 END"


def _connect() -> psycopg.Connection:
    return psycopg.connect(config.pg_dsn, row_factory=dict_row)


def listar_grupos(apenas_ativos: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT id, wa_jid, nome, is_active FROM grupos"
    if apenas_ativos:
        sql += " WHERE is_active = true"
    sql += " ORDER BY nome NULLS LAST, id"
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def definir_grupo_ativo(grupo_id: int, ativo: bool) -> None:
    """RF-08 — ativa/desativa um grupo (base do painel de autogestão)."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("UPDATE grupos SET is_active = %s WHERE id = %s", (ativo, grupo_id))
        conn.commit()


def relatorio_do_dia(dia: date, grupo_id: int | None = None) -> dict[str, Any]:
    """Monta o relatório de um dia: itens agrupados por categoria, ordenados por urgência.

    O recorte é [dia 00:00, dia+1 00:00) sobre a data de envio da mensagem.
    """
    inicio = datetime.combine(dia, datetime.min.time())
    fim = inicio + timedelta(days=1)

    sql = f"""
        SELECT a.categoria, a.urgencia, a.resumo, a.confianca,
               m.enviada_em, m.texto, g.nome AS grupo_nome, g.id AS grupo_id,
               r.nome_push AS remetente
        FROM analises a
        JOIN mensagens m ON m.id = a.mensagem_id
        JOIN grupos g    ON g.id = m.grupo_id
        LEFT JOIN remetentes r ON r.id = m.remetente_id
        WHERE m.enviada_em >= %s AND m.enviada_em < %s
          AND (%s::bigint IS NULL OR g.id = %s::bigint)
        ORDER BY {_ORDEM_URGENCIA}, m.enviada_em
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (inicio, fim, grupo_id, grupo_id))
        linhas = cur.fetchall()

    grupos: dict[str, list[dict[str, Any]]] = {"pendencia": [], "duvida": [], "decisao": []}
    for linha in linhas:
        grupos[linha["categoria"]].append(linha)

    return {
        "dia": dia.isoformat(),
        "total": len(linhas),
        "pendencias": grupos["pendencia"],
        "duvidas": grupos["duvida"],
        "decisoes": grupos["decisao"],
        "criticos": [l for l in linhas if l["urgencia"] in ("critica", "alta")],
    }


def buscar_historico(consulta: str, limite: int = 50) -> list[dict[str, Any]]:
    """Consulta de histórico (RF-04) — busca full-text em português, ranqueada.

    Responde dúvidas recorrentes com base em registros anteriores.
    """
    sql = """
        SELECT m.id, m.texto, m.tipo, m.enviada_em,
               g.nome AS grupo_nome, r.nome_push AS remetente,
               ts_rank(m.busca, plainto_tsquery('portuguese', %s)) AS rank
        FROM mensagens m
        JOIN grupos g ON g.id = m.grupo_id
        LEFT JOIN remetentes r ON r.id = m.remetente_id
        WHERE m.busca @@ plainto_tsquery('portuguese', %s)
        ORDER BY rank DESC, m.enviada_em DESC
        LIMIT %s
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (consulta, consulta, limite))
        return cur.fetchall()
