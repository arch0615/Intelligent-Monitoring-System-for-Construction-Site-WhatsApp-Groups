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


def historico_recente(limite: int = 50) -> list[dict[str, Any]]:
    """Mensagens mais recentes com texto — exibidas no histórico quando não há
    busca, para a tela não ficar em branco."""
    sql = """
        SELECT m.id, m.texto, m.tipo, m.enviada_em,
               g.nome AS grupo_nome, r.nome_push AS remetente
        FROM mensagens m
        JOIN grupos g ON g.id = m.grupo_id
        LEFT JOIN remetentes r ON r.id = m.remetente_id
        WHERE m.texto IS NOT NULL AND m.texto <> ''
        ORDER BY m.enviada_em DESC
        LIMIT %s
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (limite,))
        return cur.fetchall()


def estatisticas() -> dict[str, Any]:
    """Métricas agregadas para o dashboard (sobre todo o histórico)."""
    ordem_cat = ["pendencia", "duvida", "decisao"]
    ordem_urg = ["critica", "alta", "media", "baixa"]
    ordem_tipo = ["texto", "audio", "imagem", "video", "documento", "outro"]

    def com_pct(pares: list[tuple[str, int]]) -> list[dict[str, Any]]:
        mx = max((n for _, n in pares), default=0) or 1
        return [{"label": l, "n": n, "pct": round(n * 100 / mx)} for l, n in pares]

    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) n FROM mensagens")
        total_msgs = cur.fetchone()["n"]
        cur.execute("SELECT count(*) n FROM analises")
        total_an = cur.fetchone()["n"]
        cur.execute("SELECT count(*) n FROM analises WHERE urgencia IN ('critica','alta')")
        criticos = cur.fetchone()["n"]
        cur.execute("SELECT count(*) FILTER (WHERE is_active) ativos, count(*) total FROM grupos")
        g = cur.fetchone()

        cur.execute("SELECT categoria, count(*) n FROM analises GROUP BY categoria")
        cat = {r["categoria"]: r["n"] for r in cur.fetchall()}
        cur.execute("SELECT urgencia, count(*) n FROM analises GROUP BY urgencia")
        urg = {r["urgencia"]: r["n"] for r in cur.fetchall()}
        cur.execute("SELECT tipo, count(*) n FROM mensagens GROUP BY tipo")
        tip = {r["tipo"]: r["n"] for r in cur.fetchall()}

        dias = [date.today() - timedelta(days=i) for i in range(6, -1, -1)]
        cur.execute(
            "SELECT enviada_em::date d, count(*) n FROM mensagens WHERE enviada_em::date >= %s GROUP BY d",
            (dias[0],),
        )
        md = {r["d"]: r["n"] for r in cur.fetchall()}
        atividade = com_pct([(d.strftime("%d/%m"), md.get(d, 0)) for d in dias])

        cur.execute(
            """SELECT coalesce(g.nome, g.wa_jid) nome, count(*) n
               FROM analises a
               JOIN mensagens m ON m.id = a.mensagem_id
               JOIN grupos g    ON g.id = m.grupo_id
               GROUP BY 1 ORDER BY 2 DESC LIMIT 8"""
        )
        por_grupo = com_pct([(r["nome"], r["n"]) for r in cur.fetchall()])

    return {
        "total_mensagens": total_msgs,
        "total_analises": total_an,
        "criticos": criticos,
        "grupos_ativos": g["ativos"],
        "grupos_total": g["total"],
        "categoria": com_pct([(c, cat.get(c, 0)) for c in ordem_cat]),
        "urgencia": com_pct([(u, urg.get(u, 0)) for u in ordem_urg]),
        "tipo": com_pct([(t, tip.get(t, 0)) for t in ordem_tipo]),
        "atividade": atividade,
        "por_grupo": por_grupo,
    }


# --------------------------- Usuários (login) ----------------------------
def criar_usuario(nome: str, email: str, senha_hash: str) -> dict[str, Any]:
    """Cria um usuário. Levanta psycopg.errors.UniqueViolation se o e-mail já existe."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO usuarios (nome, email, senha_hash)
               VALUES (%s, lower(%s), %s)
               RETURNING id, nome, email""",
            (nome, email, senha_hash),
        )
        row = cur.fetchone()
        conn.commit()
    return row


def buscar_usuario_por_email(email: str) -> dict[str, Any] | None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, nome, email, senha_hash FROM usuarios WHERE email = lower(%s)",
            (email,),
        )
        return cur.fetchone()


def buscar_usuario_por_id(uid: int) -> dict[str, Any] | None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, nome, email FROM usuarios WHERE id = %s", (uid,))
        return cur.fetchone()


def contar_usuarios() -> int:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) n FROM usuarios")
        return cur.fetchone()["n"]


def atualizar_usuario(uid: int, nome: str, email: str, senha_hash: str | None = None) -> None:
    """Atualiza nome/e-mail e, opcionalmente, a senha."""
    with _connect() as conn, conn.cursor() as cur:
        if senha_hash:
            cur.execute(
                """UPDATE usuarios SET nome=%s, email=lower(%s), senha_hash=%s,
                       atualizado_em=now() WHERE id=%s""",
                (nome, email, senha_hash, uid),
            )
        else:
            cur.execute(
                "UPDATE usuarios SET nome=%s, email=lower(%s), atualizado_em=now() WHERE id=%s",
                (nome, email, uid),
            )
        conn.commit()


# ===========================================================================
# Lista Mãe — lista de tarefas persistente construída a partir das análises.
# ===========================================================================
_URGENCIAS = ("critica", "alta", "media", "baixa")
_CATEGORIAS = ("pendencia", "duvida", "decisao")


def _filtros_lista(urgencia: str | None, grupo_id: int | None, categoria: str | None
                   ) -> tuple[list[str], list[Any]]:
    """Monta as condições comuns de filtro (urgência / obra / categoria)."""
    cond: list[str] = []
    params: list[Any] = []
    if urgencia in _URGENCIAS:
        cond.append("a.urgencia = %s"); params.append(urgencia)
    if grupo_id is not None:
        cond.append("g.id = %s"); params.append(grupo_id)
    if categoria in _CATEGORIAS:
        cond.append("a.categoria = %s"); params.append(categoria)
    return cond, params


def lista_mae_itens(status: str = "aberto", urgencia: str | None = None,
                    grupo_id: int | None = None, categoria: str | None = None
                    ) -> list[dict[str, Any]]:
    """Itens já incorporados à Lista Mãe, filtrados. status: aberto|resolvidos|todos.

    Ordena: em aberto primeiro, itens de hoje no topo, depois por urgência e recência.
    """
    cond = ["a.na_lista_mae = true"]
    params: list[Any] = []
    fc, fp = _filtros_lista(urgencia, grupo_id, categoria)
    cond += fc; params += fp
    if status == "aberto":
        cond.append("a.resolvido = false")
    elif status == "resolvidos":
        cond.append("a.resolvido = true")
    sql = f"""
        SELECT a.id, a.categoria, a.urgencia, a.resumo, a.criado_em,
               a.resolvido, a.resolvido_em,
               (a.criado_em >= date_trunc('day', now())) AS novo,
               g.id AS grupo_id, g.nome AS grupo_nome,
               u.nome AS resolvido_por_nome
        FROM analises a
        JOIN mensagens m ON m.id = a.mensagem_id
        JOIN grupos g    ON g.id = m.grupo_id
        LEFT JOIN usuarios u ON u.id = a.resolvido_por
        WHERE {' AND '.join(cond)}
        ORDER BY a.resolvido,
                 (a.criado_em >= date_trunc('day', now())) DESC,
                 {_ORDEM_URGENCIA},
                 a.criado_em DESC
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def lista_mae_novos() -> list[dict[str, Any]]:
    """Itens ainda não incorporados à Lista Mãe (inbox de triagem)."""
    sql = f"""
        SELECT a.id, a.categoria, a.urgencia, a.resumo, a.criado_em,
               g.id AS grupo_id, g.nome AS grupo_nome
        FROM analises a
        JOIN mensagens m ON m.id = a.mensagem_id
        JOIN grupos g    ON g.id = m.grupo_id
        WHERE a.na_lista_mae = false
        ORDER BY {_ORDEM_URGENCIA}, a.criado_em DESC
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def lista_mae_progresso(urgencia: str | None = None, grupo_id: int | None = None,
                        categoria: str | None = None) -> dict[str, Any]:
    """Total/resolvidos/percentual dos itens na Lista Mãe sob os filtros atuais."""
    cond = ["a.na_lista_mae = true"]
    params: list[Any] = []
    fc, fp = _filtros_lista(urgencia, grupo_id, categoria)
    cond += fc; params += fp
    sql = f"""
        SELECT count(*) AS total,
               count(*) FILTER (WHERE a.resolvido) AS resolvidos
        FROM analises a
        JOIN mensagens m ON m.id = a.mensagem_id
        JOIN grupos g    ON g.id = m.grupo_id
        WHERE {' AND '.join(cond)}
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        r = cur.fetchone()
    total, resolvidos = r["total"], r["resolvidos"]
    pct = round(resolvidos / total * 100) if total else 0
    return {"total": total, "resolvidos": resolvidos, "pct": pct}


def contar_novos_lista() -> int:
    """Quantidade de itens aguardando triagem (badge do menu)."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM analises WHERE na_lista_mae = false")
        return cur.fetchone()["n"]


def resolver_item(analise_id: int, resolver: bool, usuario_id: int | None = None
                  ) -> dict[str, Any] | None:
    """Marca um item como resolvido (registra data/autor) ou reabre. Devolve o novo estado."""
    with _connect() as conn, conn.cursor() as cur:
        if resolver:
            cur.execute(
                """UPDATE analises SET resolvido=true, resolvido_em=now(), resolvido_por=%s
                       WHERE id=%s AND na_lista_mae=true
                   RETURNING resolvido, resolvido_em""",
                (usuario_id, analise_id),
            )
        else:
            cur.execute(
                """UPDATE analises SET resolvido=false, resolvido_em=NULL, resolvido_por=NULL
                       WHERE id=%s
                   RETURNING resolvido, resolvido_em""",
                (analise_id,),
            )
        row = cur.fetchone()
        conn.commit()
        return row


def adicionar_lista(analise_id: int | None = None, todos: bool = False) -> int:
    """Incorpora itens à Lista Mãe. Devolve quantos itens foram adicionados."""
    with _connect() as conn, conn.cursor() as cur:
        if todos:
            cur.execute(
                "UPDATE analises SET na_lista_mae=true, adicionado_em=now() WHERE na_lista_mae=false"
            )
        else:
            cur.execute(
                """UPDATE analises SET na_lista_mae=true, adicionado_em=now()
                       WHERE id=%s AND na_lista_mae=false""",
                (analise_id,),
            )
        n = cur.rowcount
        conn.commit()
        return n
