"""Monitor de saúde com alertas por Telegram (spec #7).

Roda periodicamente (agendado no scheduler). Para cada componente monitorado,
detecta quando ele fica fora do ar por mais que `SAUDE_ALERTA_MINUTOS` e dispara
UM alerta por incidente no Telegram (nunca pelo número de WhatsApp, que é somente
leitura). Quando o componente volta, envia um aviso de recuperação. Todos os
incidentes são gravados em `incidentes_saude` para histórico.

O estado do incidente vive em memória (reinicia junto com a API — o que é seguro:
a próxima verificação em até 1 min reavalia tudo). O histórico persiste no banco.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import db, health, reports
from .config import config, logger

# (rótulo exibido, função que extrai o "vivo" do status())
_COMPONENTES: list[tuple[str, str]] = [
    ("Captura (WhatsApp)", "captura"),
    ("Pipeline de IA", "pipeline"),
    ("Banco de dados", "postgres"),
    ("Redis", "redis"),
]

# componente -> {"desde": datetime, "notificado": bool, "inc_id": int | None}
_estado: dict[str, dict] = {}


def _vivo(status: dict, chave: str) -> bool:
    parte = status.get(chave, {})
    # captura/pipeline expõem "vivo"; postgres/redis expõem "ok".
    return bool(parte.get("vivo", parte.get("ok", False)))


def _fmt_dur(segundos: float) -> str:
    m = int(segundos // 60)
    if m < 1:
        return "menos de 1 min"
    if m < 60:
        return f"{m} min"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}"


def verificar() -> None:
    """Uma rodada de verificação. Idempotente; segura para rodar a cada minuto."""
    try:
        s = health.status()
    except Exception as err:  # noqa: BLE001
        logger.warning("Monitor de saúde: falha ao obter status: %s", err)
        return

    agora = datetime.now()
    limite = timedelta(minutes=config.SAUDE_ALERTA_MINUTOS)

    for nome, chave in _COMPONENTES:
        vivo = _vivo(s, chave)
        st = _estado.get(nome)

        if not vivo:
            if st is None:
                # Início de um possível incidente.
                inc_id = db.abrir_incidente(nome, agora)
                _estado[nome] = {"desde": agora, "notificado": False, "inc_id": inc_id}
            elif not st["notificado"] and (agora - st["desde"]) >= limite:
                dur = (agora - st["desde"]).total_seconds()
                texto = (
                    "🔴 <b>Alerta de Saúde — Monreal Obras</b>\n\n"
                    f"O componente <b>{nome}</b> está fora do ar há {_fmt_dur(dur)} "
                    f"(desde {st['desde'].strftime('%d/%m %H:%M')}).\n\n"
                    "A captura/processamento das mensagens pode estar interrompida. "
                    "Verifique o servidor."
                )
                enviado = reports.enviar_telegram(texto)
                st["notificado"] = True
                if st["inc_id"]:
                    db.marcar_incidente_notificado(st["inc_id"])
                logger.warning(
                    "Alerta de saúde: %s fora há %s (telegram=%s)", nome, _fmt_dur(dur), enviado
                )
        else:
            if st is not None:
                dur = (agora - st["desde"]).total_seconds()
                db.fechar_incidente(st["inc_id"], nome, st["desde"], agora, st["notificado"])
                if st["notificado"]:
                    reports.enviar_telegram(
                        "✅ <b>Saúde recuperada — Monreal Obras</b>\n\n"
                        f"O componente <b>{nome}</b> voltou ao normal.\n"
                        f"Tempo total fora: ~{_fmt_dur(dur)}."
                    )
                    logger.info("Componente recuperado: %s (fora por %s)", nome, _fmt_dur(dur))
                _estado.pop(nome, None)
