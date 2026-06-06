"""Agendamento do relatório diário via APScheduler (RF-03).

Dispara `reports.gerar_e_entregar()` no horário configurado (RELATORIO_HORA).
O scheduler sobe junto com a API (lifespan no main.py).
"""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import reports
from .config import config, logger

scheduler = BackgroundScheduler(timezone=config.TZ)


def _job_relatorio_diario() -> None:
    logger.info("Disparando job do relatório diário")
    reports.gerar_e_entregar()


def iniciar() -> None:
    scheduler.add_job(
        _job_relatorio_diario,
        trigger=CronTrigger(hour=config.RELATORIO_HORA, minute=config.RELATORIO_MINUTO),
        id="relatorio_diario",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler iniciado — relatório diário às %02d:%02d (%s)",
        config.RELATORIO_HORA,
        config.RELATORIO_MINUTO,
        config.TZ,
    )


def parar() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
