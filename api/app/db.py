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


def _cond_periodo(inicio: date | None, fim: date | None, grupo_id: int | None
                  ) -> tuple[list[str], list[Any]]:
    """Condições de filtro (período + obra) sobre a tabela mensagens (alias m)."""
    cond: list[str] = []
    params: list[Any] = []
    if inicio is not None:
        cond.append("m.enviada_em >= %s")
        params.append(datetime.combine(inicio, datetime.min.time()))
    if fim is not None:
        cond.append("m.enviada_em < %s")
        params.append(datetime.combine(fim, datetime.min.time()) + timedelta(days=1))
    if grupo_id is not None:
        cond.append("m.grupo_id = %s")
        params.append(grupo_id)
    return cond, params


def _where(cond: list[str]) -> str:
    return ("WHERE " + " AND ".join(cond)) if cond else ""


def estatisticas(inicio: date | None = None, fim: date | None = None,
                 grupo_id: int | None = None) -> dict[str, Any]:
    """Métricas agregadas para o dashboard, filtradas por período e obra.

    Sem argumentos, cobre todo o histórico (a Atividade cai para os últimos 7 dias).
    """
    ordem_cat = ["pendencia", "duvida", "decisao"]
    ordem_urg = ["critica", "alta", "media", "baixa"]
    ordem_tipo = ["texto", "audio", "imagem", "video", "documento", "outro"]

    def com_pct(pares: list[tuple[str, int]]) -> list[dict[str, Any]]:
        mx = max((n for _, n in pares), default=0) or 1
        return [{"label": l, "n": n, "pct": round(n * 100 / mx)} for l, n in pares]

    cond, params = _cond_periodo(inicio, fim, grupo_id)
    w = _where(cond)
    # análises herdam o filtro de mensagens via JOIN.
    base_an = f"FROM analises a JOIN mensagens m ON m.id = a.mensagem_id {w}"

    with _connect() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT count(*) n FROM mensagens m {w}", params)
        total_msgs = cur.fetchone()["n"]
        cur.execute(f"SELECT count(*) n {base_an}", params)
        total_an = cur.fetchone()["n"]

        cond_crit = cond + ["a.urgencia IN ('critica','alta')"]
        cur.execute(f"SELECT count(*) n FROM analises a JOIN mensagens m ON m.id = a.mensagem_id {_where(cond_crit)}", params)
        criticos = cur.fetchone()["n"]

        # Grupos ativos (estado de ativação, não depende de período) + quantos têm
        # itens críticos/altos EM ABERTO no recorte selecionado.
        cur.execute("SELECT count(*) FILTER (WHERE is_active) ativos, count(*) total FROM grupos")
        g = cur.fetchone()
        cond_alerta = cond + ["a.urgencia IN ('critica','alta')", "a.resolvido = false"]
        cur.execute(f"SELECT count(DISTINCT m.grupo_id) n FROM analises a JOIN mensagens m ON m.id = a.mensagem_id {_where(cond_alerta)}", params)
        grupos_com_alerta = cur.fetchone()["n"]

        cur.execute(f"SELECT a.categoria, count(*) n {base_an} GROUP BY a.categoria", params)
        cat = {r["categoria"]: r["n"] for r in cur.fetchall()}
        cur.execute(f"SELECT a.urgencia, count(*) n {base_an} GROUP BY a.urgencia", params)
        urg = {r["urgencia"]: r["n"] for r in cur.fetchall()}
        cur.execute(f"SELECT m.tipo, count(*) n FROM mensagens m {w} GROUP BY m.tipo", params)
        tip = {r["tipo"]: r["n"] for r in cur.fetchall()}

        # Atividade diária: dentro do período (limitada a 45 dias); sem período,
        # mostra os últimos 7 dias.
        if inicio is not None and fim is not None:
            d_ini = max(inicio, fim - timedelta(days=44))
            n_dias = (fim - d_ini).days
            dias = [d_ini + timedelta(days=i) for i in range(n_dias + 1)]
        else:
            dias = [date.today() - timedelta(days=i) for i in range(6, -1, -1)]
        cond_ativ = list(cond) if cond else ["m.enviada_em::date >= %s"]
        params_ativ = list(params) if cond else [dias[0]]
        cur.execute(
            f"SELECT m.enviada_em::date d, count(*) n FROM mensagens m {_where(cond_ativ)} GROUP BY d",
            params_ativ,
        )
        md = {r["d"]: r["n"] for r in cur.fetchall()}
        atividade = com_pct([(d.strftime("%d/%m"), md.get(d, 0)) for d in dias])

        cur.execute(
            f"""SELECT coalesce(g.nome, g.wa_jid) nome, count(*) n
                FROM analises a
                JOIN mensagens m ON m.id = a.mensagem_id
                JOIN grupos g    ON g.id = m.grupo_id
                {w}
                GROUP BY 1 ORDER BY 2 DESC LIMIT 8""",
            params,
        )
        por_grupo = com_pct([(r["nome"], r["n"]) for r in cur.fetchall()])

    return {
        "total_mensagens": total_msgs,
        "total_analises": total_an,
        "criticos": criticos,
        "grupos_ativos": g["ativos"],
        "grupos_total": g["total"],
        "grupos_com_alerta": grupos_com_alerta,
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
        cur.execute("SELECT id, nome, email, criado_em FROM usuarios WHERE id = %s", (uid,))
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


def _cond_lista(status: str, urgencia: str | None, grupo_id: int | None,
                categoria: str | None) -> tuple[list[str], list[Any]]:
    cond = ["a.na_lista_mae = true"]
    params: list[Any] = []
    fc, fp = _filtros_lista(urgencia, grupo_id, categoria)
    cond += fc; params += fp
    if status == "aberto":
        cond.append("a.resolvido = false")
    elif status == "resolvidos":
        cond.append("a.resolvido = true")
    return cond, params


def lista_mae_contar(status: str = "aberto", urgencia: str | None = None,
                     grupo_id: int | None = None, categoria: str | None = None) -> int:
    """Total de itens da Lista Mãe que casam com o filtro (para a paginação)."""
    cond, params = _cond_lista(status, urgencia, grupo_id, categoria)
    sql = f"""SELECT count(*) AS n FROM analises a
              JOIN mensagens m ON m.id = a.mensagem_id
              JOIN grupos g    ON g.id = m.grupo_id
              WHERE {' AND '.join(cond)}"""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()["n"]


def lista_mae_itens(status: str = "aberto", urgencia: str | None = None,
                    grupo_id: int | None = None, categoria: str | None = None,
                    limit: int | None = None, offset: int = 0
                    ) -> list[dict[str, Any]]:
    """Itens já incorporados à Lista Mãe, filtrados. status: aberto|resolvidos|todos.

    Ordena: em aberto primeiro, itens de hoje no topo, depois por urgência e recência.
    limit/offset paginam o resultado (limit=None traz tudo — usado no export PDF).
    """
    cond, params = _cond_lista(status, urgencia, grupo_id, categoria)
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
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params = [*params, limit, offset]
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def lista_mae_novos_contar() -> int:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM analises WHERE na_lista_mae = false")
        return cur.fetchone()["n"]


def lista_mae_novos(limit: int | None = None, offset: int = 0) -> list[dict[str, Any]]:
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
    params: list[Any] = []
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"
        params = [limit, offset]
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
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


# ===========================================================================
# Incidentes de saúde — histórico de indisponibilidade dos componentes.
# Todas as funções são "best-effort": se o banco estiver fora (que pode ser o
# próprio incidente), elas apenas logam e não derrubam o monitor.
# ===========================================================================
def abrir_incidente(componente: str, inicio: datetime) -> int | None:
    """Registra o início de um incidente. Devolve o id (ou None em falha)."""
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO incidentes_saude (componente, inicio) VALUES (%s, %s) RETURNING id",
                (componente, inicio),
            )
            iid = cur.fetchone()["id"]
            conn.commit()
            return iid
    except Exception:  # noqa: BLE001
        return None


def marcar_incidente_notificado(incidente_id: int) -> None:
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("UPDATE incidentes_saude SET notificado=true WHERE id=%s", (incidente_id,))
            conn.commit()
    except Exception:  # noqa: BLE001
        pass


def fechar_incidente(incidente_id: int | None, componente: str, inicio: datetime,
                     fim: datetime, notificado: bool) -> None:
    """Fecha o incidente (fim). Se não houver id (falha ao abrir), insere já fechado."""
    try:
        with _connect() as conn, conn.cursor() as cur:
            if incidente_id:
                cur.execute("UPDATE incidentes_saude SET fim=%s WHERE id=%s", (fim, incidente_id))
            else:
                cur.execute(
                    """INSERT INTO incidentes_saude (componente, inicio, fim, notificado)
                       VALUES (%s, %s, %s, %s)""",
                    (componente, inicio, fim, notificado),
                )
            conn.commit()
    except Exception:  # noqa: BLE001
        pass


def corpus_para_resumo(grupo_id: int | None, inicio: date, fim: date,
                       limite: int = 300) -> list[dict[str, Any]]:
    """Itens analisados (pendências/dúvidas/decisões) de uma obra em um intervalo,
    em ordem cronológica — matéria-prima do resumo executivo por IA (spec #3).

    O recorte é [inicio 00:00, fim+1 00:00) sobre a data de envio da mensagem.
    """
    ini = datetime.combine(inicio, datetime.min.time())
    f = datetime.combine(fim, datetime.min.time()) + timedelta(days=1)
    sql = """
        SELECT a.categoria, a.urgencia, a.resumo, m.enviada_em,
               g.nome AS grupo_nome
        FROM analises a
        JOIN mensagens m ON m.id = a.mensagem_id
        JOIN grupos g    ON g.id = m.grupo_id
        WHERE m.enviada_em >= %s AND m.enviada_em < %s
          AND (%s::bigint IS NULL OR g.id = %s::bigint)
        ORDER BY m.enviada_em
        LIMIT %s
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (ini, f, grupo_id, grupo_id, limite))
        return cur.fetchall()


# ===========================================================================
# Busca semântica (RAG) — embeddings + histórico de perguntas.
# ===========================================================================
def mensagens_sem_embedding(limite: int = 128) -> list[dict[str, Any]]:
    """Mensagens com texto e ainda sem embedding (fila de indexação)."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT id, texto FROM mensagens
               WHERE embedding IS NULL AND texto IS NOT NULL AND texto <> ''
               ORDER BY id LIMIT %s""",
            (limite,),
        )
        return cur.fetchall()


def salvar_embeddings(pares: list[tuple[int, list[float]]]) -> None:
    """Grava os embeddings (id da mensagem -> vetor)."""
    if not pares:
        return
    with _connect() as conn, conn.cursor() as cur:
        cur.executemany(
            "UPDATE mensagens SET embedding = %s::vector WHERE id = %s",
            [(str(vec), mid) for mid, vec in pares],
        )
        conn.commit()


def contar_embeddings() -> dict[str, int]:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT count(*) FILTER (WHERE embedding IS NOT NULL) AS indexadas,
                      count(*) FILTER (WHERE texto IS NOT NULL AND texto <> '') AS com_texto
               FROM mensagens"""
        )
        return cur.fetchone()


def busca_semantica(qvec: list[float], inicio: date | None = None, fim: date | None = None,
                    grupo_id: int | None = None, k: int = 8) -> list[dict[str, Any]]:
    """Top-k mensagens mais próximas do vetor da pergunta (distância de cosseno),
    respeitando filtros de obra e período."""
    cond, fparams = _cond_periodo(inicio, fim, grupo_id)
    cond = ["m.embedding IS NOT NULL"] + cond
    qs = str(qvec)
    sql = f"""
        SELECT m.id, m.texto, m.tipo, m.enviada_em, g.nome AS grupo_nome,
               r.nome_push AS remetente,
               1 - (m.embedding <=> %s::vector) AS score
        FROM mensagens m
        JOIN grupos g ON g.id = m.grupo_id
        LEFT JOIN remetentes r ON r.id = m.remetente_id
        WHERE {' AND '.join(cond)}
        ORDER BY m.embedding <=> %s::vector
        LIMIT %s
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, [qs, *fparams, qs, k])
        return cur.fetchall()


def registrar_pergunta(usuario_id: int | None, pergunta: str) -> None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO perguntas_rag (usuario_id, pergunta) VALUES (%s, %s)",
            (usuario_id, pergunta.strip()),
        )
        conn.commit()


def ultimas_perguntas(limite: int = 5) -> list[dict[str, Any]]:
    """Últimas perguntas distintas, mais recentes primeiro."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT pergunta, max(criado_em) AS quando
               FROM perguntas_rag GROUP BY pergunta ORDER BY quando DESC LIMIT %s""",
            (limite,),
        )
        return cur.fetchall()


def incidentes_recentes(limite: int = 10) -> list[dict[str, Any]]:
    """Últimos incidentes (abertos e fechados), mais recentes primeiro."""
    sql = """
        SELECT id, componente, inicio, fim, notificado,
               EXTRACT(EPOCH FROM (COALESCE(fim, now()) - inicio))::bigint AS duracao_seg
        FROM incidentes_saude
        ORDER BY inicio DESC
        LIMIT %s
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (limite,))
        return cur.fetchall()
