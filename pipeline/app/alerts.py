"""Alertas proativos (RF-05).

Quando a Claude classifica um item como crítico/urgente, dispara um alerta
IMEDIATO (sem esperar o relatório diário). Dedup garantido pela tabela `alertas`:
cada análise gera no máximo um alerta.

Canal: Telegram (recomendado). NUNCA usar o número de monitoramento, que é
somente leitura — enviar por ele aumentaria o risco de bloqueio.
"""
from __future__ import annotations

import httpx

from . import db
from .config import config, logger

_EMOJI = {"critica": "🔴", "alta": "🟠"}
_ROTULO = {"pendencia": "Pendência", "duvida": "Dúvida", "decisao": "Decisão"}


def _enviar_telegram(texto: str) -> tuple[bool, str | None]:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False, "telegram_nao_configurado"
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = httpx.post(
            url,
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": texto, "parse_mode": "Markdown"},
            timeout=15,
        )
        resp.raise_for_status()
        return True, None
    except httpx.HTTPError as err:
        logger.error("Falha ao enviar alerta pelo Telegram: %s", err)
        return False, str(err)


def _formatar(item: dict) -> str:
    emoji = _EMOJI.get(item["urgencia"], "🔔")
    rotulo = _ROTULO.get(item["categoria"], item["categoria"])
    grupo = item.get("grupo_nome") or "grupo"
    quem = f" · {item['remetente']}" if item.get("remetente") else ""
    return (
        f"{emoji} *ALERTA — {item['urgencia'].upper()}*\n"
        f"{rotulo}: {item['resumo']}\n"
        f"_{grupo}{quem}_"
    )


def processar_alertas(mensagem_id: int) -> int:
    """Dispara alertas para análises urgentes ainda não notificadas. Retorna a quantidade enviada."""
    pendentes = db.analises_urgentes_sem_alerta(mensagem_id, config.ALERTA_URGENCIAS)
    enviados = 0
    for item in pendentes:
        sucesso, detalhe = _enviar_telegram(_formatar(item))
        db.registrar_alerta(item["id"], "telegram", sucesso, detalhe)
        if sucesso:
            enviados += 1
            logger.info("Alerta enviado (analise=%s, urgencia=%s)", item["id"], item["urgencia"])
    return enviados
