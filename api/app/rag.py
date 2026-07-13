"""Busca semântica com IA (RAG) — spec #5.

Fluxo: embedding da pergunta -> busca vetorial (pgvector) das mensagens mais
próximas (com filtros de obra/período) -> Claude responde em linguagem natural
usando SOMENTE os trechos recuperados, devolvendo também a lista de fontes.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import anthropic

from . import db, embeddings
from .config import config, logger

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """\
Você responde perguntas da equipe de gestão de uma construtora com base em \
trechos de conversas dos grupos de WhatsApp das obras. Responda em português, de \
forma objetiva e direta, USANDO SOMENTE as informações dos trechos fornecidos. \
Cite fatos concretos (datas, obras, nomes, valores) quando estiverem nos trechos \
e, quando útil, indique a fonte pelo número entre colchetes (ex.: [2]). Se os \
trechos não permitirem responder, diga claramente que não há registro suficiente. \
Nunca invente informação que não esteja nos trechos."""


def _fonte(indice: int, f: dict[str, Any]) -> dict[str, Any]:
    return {
        "n": indice,
        "texto": f["texto"],
        "grupo": f["grupo_nome"],
        "remetente": f["remetente"],
        "quando": f["enviada_em"].strftime("%d/%m/%Y %H:%M"),
        "tipo": f["tipo"],
        "score": round(float(f["score"]), 3),
    }


def perguntar(pergunta: str, inicio: date | None = None, fim: date | None = None,
              grupo_id: int | None = None, usuario_id: int | None = None,
              k: int = 8) -> dict[str, Any]:
    pergunta = (pergunta or "").strip()
    if not pergunta:
        return {"erro": "Digite uma pergunta.", "resposta": None, "fontes": []}

    try:
        qvec = embeddings.embed_um(pergunta)
    except Exception as err:  # noqa: BLE001
        logger.error("Falha ao gerar embedding da pergunta: %s", err)
        return {"erro": "Não foi possível processar a pergunta agora.", "resposta": None, "fontes": []}

    fontes = db.busca_semantica(qvec, inicio, fim, grupo_id, k)
    if usuario_id is not None:
        db.registrar_pergunta(usuario_id, pergunta)

    if not fontes:
        return {
            "erro": None,
            "resposta": "Não encontrei registros relacionados a essa pergunta no período/obra selecionados.",
            "fontes": [],
        }

    contexto = "\n\n".join(
        f"[{i}] ({f['grupo_nome'] or 'obra'} · {f['enviada_em'].strftime('%d/%m/%Y %H:%M')}"
        + (f" · {f['remetente']}" if f["remetente"] else "")
        + f")\n{f['texto']}"
        for i, f in enumerate(fontes, start=1)
    )
    prompt = (
        f"Pergunta: {pergunta}\n\n"
        f"Trechos das conversas (numerados):\n{contexto}\n\n"
        "Responda à pergunta com base apenas nos trechos acima."
    )

    try:
        resp = _client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=1200,
            thinking={"type": "adaptive"},
            output_config={"effort": "low"},
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        )
        resposta = next((b.text for b in resp.content if b.type == "text"), "").strip()
    except Exception as err:  # noqa: BLE001
        logger.error("Falha ao responder (RAG): %s", err)
        return {"erro": "Não foi possível responder agora. Tente novamente.", "resposta": None, "fontes": []}

    return {
        "erro": None,
        "resposta": resposta,
        "fontes": [_fonte(i, f) for i, f in enumerate(fontes, start=1)],
    }
