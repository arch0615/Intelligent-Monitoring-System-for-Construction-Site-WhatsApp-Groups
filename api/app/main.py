"""API + Painel (Etapa 3).

Endpoints:
  GET  /                      -> painel (dashboard do dia)
  GET  /relatorio             -> relatório de um dia (HTML)   ?data=YYYY-MM-DD&grupo_id=
  GET  /historico            -> consulta de histórico (HTML)  ?q=...
  GET  /grupos               -> gestão de grupos (HTML, base do RF-08)
  POST /grupos/{id}/ativar   -> ativa/desativa grupo
  GET  /api/relatorio        -> relatório (JSON)
  GET  /api/historico        -> histórico (JSON)
  POST /api/relatorio/enviar -> gera e entrega o relatório agora (uso manual/teste)
  GET  /health
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import db, reports, scheduler
from .config import logger

templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.iniciar()
    logger.info("API iniciada")
    yield
    scheduler.parar()


app = FastAPI(title="Monitoramento de Obras — API", lifespan=lifespan)


def _parse_data(data: str | None) -> date:
    return date.fromisoformat(data) if data else date.today()


# ----------------------------- Painel (HTML) -----------------------------
@app.get("/", response_class=HTMLResponse)
def painel(request: Request, data: str | None = None, grupo_id: int | None = None):
    dia = _parse_data(data)
    relatorio = db.relatorio_do_dia(dia, grupo_id)
    return templates.TemplateResponse(
        request,
        "relatorio.html",
        {"relatorio": relatorio, "grupos": db.listar_grupos(), "grupo_id": grupo_id},
    )


@app.get("/relatorio", response_class=HTMLResponse)
def relatorio_html(request: Request, data: str | None = None, grupo_id: int | None = None):
    return painel(request, data, grupo_id)


@app.get("/historico", response_class=HTMLResponse)
def historico_html(request: Request, q: str = Query("", description="Termo de busca")):
    resultados = db.buscar_historico(q) if q.strip() else []
    return templates.TemplateResponse(
        request, "historico.html", {"q": q, "resultados": resultados}
    )


@app.get("/grupos", response_class=HTMLResponse)
def grupos_html(request: Request):
    return templates.TemplateResponse(request, "grupos.html", {"grupos": db.listar_grupos()})


@app.post("/grupos/{grupo_id}/ativar")
def grupos_toggle(grupo_id: int, ativo: bool = Form(...)):
    db.definir_grupo_ativo(grupo_id, ativo)
    return RedirectResponse("/grupos", status_code=303)


# ----------------------------- API (JSON) --------------------------------
@app.get("/api/relatorio")
def api_relatorio(data: str | None = None, grupo_id: int | None = None):
    return db.relatorio_do_dia(_parse_data(data), grupo_id)


@app.get("/api/historico")
def api_historico(q: str = Query(...), limite: int = 50):
    return {"q": q, "resultados": db.buscar_historico(q, limite)}


@app.post("/api/relatorio/enviar")
def api_enviar_relatorio(data: str | None = None, grupo_id: int | None = None):
    """Gera e entrega o relatório agora (útil para teste / DEMO da Etapa 3)."""
    resultado = reports.gerar_e_entregar(_parse_data(data) if data else None, grupo_id)
    return {"entregue": resultado["entregue"], "total": resultado["relatorio"]["total"]}


@app.get("/health")
def health():
    return {"status": "ok"}
