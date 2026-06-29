"""Geração e entrega do relatório diário (RF-03).

Formata o relatório do dia em texto (para Telegram/e-mail) e entrega pelo canal
configurado. IMPORTANTE: nunca entregar pelo número de monitoramento (somente
leitura). Canal recomendado: Telegram.
"""
from __future__ import annotations

from datetime import date

import html

import httpx

from . import db
from .config import config, logger

_EMOJI_URGENCIA = {"critica": "🔴", "alta": "🟠", "media": "🟡", "baixa": "⚪"}


def _esc(texto: str | None) -> str:
    """Escapa para HTML do Telegram (evita 400 por conteúdo com <, >, & ou _)."""
    return html.escape(texto or "")


def _formatar_item(item: dict) -> str:
    emoji = _EMOJI_URGENCIA.get(item["urgencia"], "⚪")
    grupo = item.get("grupo_nome") or "grupo"
    return f"{emoji} {_esc(item['resumo'])}  <i>({_esc(grupo)})</i>"


def formatar_texto(relatorio: dict) -> str:
    """Monta o corpo do relatório em texto (HTML do Telegram)."""
    linhas = [f"<b>Relatório diário — {_esc(relatorio['dia'])}</b>", ""]

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
        linhas.append(f"<b>{titulo}</b> ({len(itens)})")
        linhas.extend(_formatar_item(i) for i in itens)
        linhas.append("")

    return "\n".join(linhas).strip()


# Telegram limita cada mensagem a 4096 caracteres; usamos margem.
_LIMITE_TELEGRAM = 3900


def _dividir(texto: str, limite: int = _LIMITE_TELEGRAM) -> list[str]:
    """Quebra o texto em blocos <= limite, sempre em quebras de linha."""
    blocos: list[str] = []
    atual = ""
    for linha in texto.split("\n"):
        if atual and len(atual) + len(linha) + 1 > limite:
            blocos.append(atual)
            atual = linha
        else:
            atual = f"{atual}\n{linha}" if atual else linha
    if atual:
        blocos.append(atual)
    return blocos


def enviar_telegram(texto: str) -> bool:
    """Envia o texto via bot do Telegram (dividido em várias mensagens se for
    maior que o limite de 4096 caracteres). Retorna True se tudo foi entregue."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.warning("Telegram não configurado — relatório não enviado")
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    ok = True
    for bloco in _dividir(texto):
        try:
            resp = httpx.post(
                url,
                json={"chat_id": config.TELEGRAM_CHAT_ID, "text": bloco, "parse_mode": "HTML"},
                timeout=15,
            )
            resp.raise_for_status()
        except httpx.HTTPError as err:
            logger.error("Falha ao enviar relatório pelo Telegram: %s", err)
            ok = False
    return ok


def gerar_e_entregar(dia: date | None = None, grupo_id: int | None = None) -> dict:
    """Gera o relatório do dia e o entrega pelo canal configurado."""
    dia = dia or date.today()
    relatorio = db.relatorio_do_dia(dia, grupo_id)
    texto = formatar_texto(relatorio)
    entregue = enviar_telegram(texto)
    logger.info("Relatório de %s gerado (%d itens, entregue=%s)", dia, relatorio["total"], entregue)
    return {"relatorio": relatorio, "texto": texto, "entregue": entregue}
