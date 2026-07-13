"""Resumo executivo do histórico via Claude (spec #3).

Reúne os itens (pendências/dúvidas/decisões) de uma obra num intervalo de datas
e pede à Claude um resumo executivo estruturado em 5 blocos, em JSON validado.
Segue o mesmo padrão do pipeline (output_config.format = json_schema).
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

import anthropic

from . import db
from .config import config, logger

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """\
Você é um analista de obras que resume, para a gestão, o que aconteceu em uma \
obra a partir de registros extraídos de grupos de WhatsApp (pendências, dúvidas \
e decisões já identificadas). Escreva em português claro e objetivo, no tom de \
um resumo executivo. Baseie-se SOMENTE nos itens fornecidos — não invente fatos. \
Se houver poucos itens, seja breve e diga o que dá para concluir.\
"""

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "situacao_geral": {"type": "string"},
        "principais_avancos": {"type": "array", "items": {"type": "string"}},
        "pontos_atencao": {"type": "array", "items": {"type": "string"}},
        "decisoes_chave": {"type": "array", "items": {"type": "string"}},
        "proximo_passo": {"type": "string"},
    },
    "required": [
        "situacao_geral", "principais_avancos", "pontos_atencao",
        "decisoes_chave", "proximo_passo",
    ],
    "additionalProperties": False,
}

_ROT_CAT = {"pendencia": "PENDÊNCIA", "duvida": "DÚVIDA", "decisao": "DECISÃO"}


def _formatar_corpus(itens: list[dict[str, Any]]) -> str:
    linhas = []
    for i in itens:
        data = i["enviada_em"].strftime("%d/%m")
        cat = _ROT_CAT.get(i["categoria"], i["categoria"])
        linhas.append(f"- [{cat} · {i['urgencia']} · {data} · {i['grupo_nome'] or 'obra'}] {i['resumo']}")
    return "\n".join(linhas)


def gerar_resumo(grupo_id: int | None, inicio: date, fim: date) -> dict[str, Any]:
    """Gera o resumo executivo. Devolve os 5 blocos + metadados. `erro` != None
    quando não há dados ou a IA falhou."""
    itens = db.corpus_para_resumo(grupo_id, inicio, fim)
    meta = {
        "total_itens": len(itens),
        "inicio": inicio.isoformat(),
        "fim": fim.isoformat(),
    }
    if not itens:
        return {"erro": "Nenhum item encontrado para esta obra e período.", "meta": meta}

    prompt = (
        f"Período analisado: {inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}.\n"
        f"Total de itens: {len(itens)}.\n\n"
        f"Itens registrados (mais antigos primeiro):\n{_formatar_corpus(itens)}\n\n"
        "Gere um resumo executivo em JSON com:\n"
        "- situacao_geral: 2 a 4 frases sobre o estado geral da obra no período.\n"
        "- principais_avancos: o que avançou, foi concluído ou decidido de positivo.\n"
        "- pontos_atencao: pendências, riscos e itens críticos que exigem atenção.\n"
        "- decisoes_chave: definições/aprovações relevantes tomadas no período.\n"
        "- proximo_passo: a recomendação mais importante para dar sequência.\n\n"
        "Em cada lista, traga no máximo os 5 itens mais relevantes, cada um em uma "
        "frase curta. Priorize o que é crítico para a gestão."
    )

    try:
        response = _client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=2000,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "low",  # resumo é síntese objetiva; prioriza latência (<30s)
                "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
            },
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        )
    except Exception as err:  # noqa: BLE001
        logger.error("Falha ao gerar resumo por IA: %s", err)
        return {"erro": "Não foi possível gerar o resumo agora. Tente novamente.", "meta": meta}

    texto = next((b.text for b in response.content if b.type == "text"), "")
    try:
        dados = json.loads(texto)
    except json.JSONDecodeError:
        logger.error("Resumo da Claude não é JSON válido: %r", texto[:200])
        return {"erro": "Resposta da IA em formato inesperado.", "meta": meta}

    dados["erro"] = None
    dados["meta"] = meta
    return dados
