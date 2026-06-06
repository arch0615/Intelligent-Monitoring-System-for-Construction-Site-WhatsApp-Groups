"""Geração e entrega do relatório diário (RF-03).

Formata o relatório do dia em texto (para Telegram/e-mail) e entrega pelo canal
configurado. IMPORTANTE: nunca entregar pelo número de monitoramento (somente
leitura). Canal recomendado: Telegram.
"""
from __future__ import annotations

from datetime import date

import httpx

from . import db
from .config import config, logger

_EMOJI_URGENCIA = {"critica": "🔴", "alta": "🟠", "media": "🟡", "baixa": "⚪"}


def _formatar_item(item: dict) -> str:
    emoji = _EMOJI_URGENCIA.get(item["urgencia"], "⚪")
    grupo = item.get("grupo_nome") or "grupo"
    return f"{emoji} {item['resumo']}  _( {grupo} )_"


def formatar_texto(relatorio: dict) -> str:
    """Monta o corpo do relatório em texto (Markdown leve, compatível com Telegram)."""
    linhas = [f"*Relatório diário — {relatorio['dia']}*", ""]

    if relatorio["total"] == 0:
        linhas.append("Nenhuma pendência, dúvida ou decisão relevante hoje.")
        return "\n".join(linhas)

    secoes = [
        ("⚠️ Pendências", relatorio["pendencias"]),
        ("❓ Dúvidas", relatorio["duvidas"]),
        ("✅ Decisões", relatorio["decisoes"]),
    ]
    for titulo, itens in secoes:
        if not itens:
            continue
        linhas.append(f"*{titulo}* ({len(itens)})")
        linhas.extend(_formatar_item(i) for i in itens)
        linhas.append("")

    return "\n".join(linhas).strip()


def enviar_telegram(texto: str) -> bool:
    """Envia o texto via bot do Telegram. Retorna True em sucesso."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.warning("Telegram não configurado — relatório não enviado")
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = httpx.post(
            url,
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": texto, "parse_mode": "Markdown"},
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except httpx.HTTPError as err:
        logger.error("Falha ao enviar relatório pelo Telegram: %s", err)
        return False


def gerar_e_entregar(dia: date | None = None, grupo_id: int | None = None) -> dict:
    """Gera o relatório do dia e o entrega pelo canal configurado."""
    dia = dia or date.today()
    relatorio = db.relatorio_do_dia(dia, grupo_id)
    texto = formatar_texto(relatorio)
    entregue = enviar_telegram(texto)
    logger.info("Relatório de %s gerado (%d itens, entregue=%s)", dia, relatorio["total"], entregue)
    return {"relatorio": relatorio, "texto": texto, "entregue": entregue}
