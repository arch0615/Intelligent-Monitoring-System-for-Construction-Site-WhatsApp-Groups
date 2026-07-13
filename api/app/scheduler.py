"""Agendamento do relatório diário via APScheduler (RF-03).

Dispara `reports.gerar_e_entregar()` no horário configurado (RELATORIO_HORA).
O scheduler sobe junto com a API (lifespan no main.py).
"""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from . import indexer, maintenance, reports, saude_monitor
from .config import config, logger

scheduler = BackgroundScheduler(timezone=config.TZ)


def _job_relatorio_diario() -> None:
    logger.info("Disparando job do relatório diário")
    reports.gerar_e_entregar()


def _job_retencao_midia() -> None:
    logger.info("Disparando job de retenção de mídia")
    maintenance.arquivar_midia_antiga()


def _job_monitor_saude() -> None:
    saude_monitor.verificar()


def _job_indexar_embeddings() -> None:
    """Indexa (embeddings) as mensagens novas para a busca semântica."""
    try:
        indexer.indexar_pendentes()
    except Exception as err:  # noqa: BLE001
        logger.warning("Indexação de embeddings falhou: %s", err)


def iniciar() -> None:
    scheduler.add_job(
        _job_relatorio_diario,
        trigger=CronTrigger(hour=config.RELATORIO_HORA, minute=config.RELATORIO_MINUTO),
        id="relatorio_diario",
        replace_existing=True,
    )
    # Retenção de mídia: madrugada (03:30), fora do horário de pico (Etapa 5).
    scheduler.add_job(
        _job_retencao_midia,
        trigger=CronTrigger(hour=3, minute=30),
        id="retencao_midia",
        replace_existing=True,
    )
    # Monitor de saúde: verifica os componentes e alerta por Telegram (spec #7).
    scheduler.add_job(
        _job_monitor_saude,
        trigger=IntervalTrigger(seconds=config.SAUDE_CHECK_SEGUNDOS),
        id="monitor_saude",
        replace_existing=True,
    )
    # Indexação incremental de embeddings (busca semântica): a cada 3 min.
    scheduler.add_job(
        _job_indexar_embeddings,
        trigger=IntervalTrigger(seconds=180),
        id="indexar_embeddings",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler iniciado — relatório diário às %02d:%02d (%s); retenção 03:30",
        config.RELATORIO_HORA,
        config.RELATORIO_MINUTO,
        config.TZ,
    )


def parar() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
