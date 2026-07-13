"""API + Painel — com autenticação (login/registro/perfil).

Páginas do painel exigem login. Rotas abertas: /login, /register, /health,
/favicon.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

import psycopg
from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import auth, db, health, maintenance, reports, resumo_ia, scheduler
from .config import config, logger

templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.iniciar()
    logger.info("API iniciada")
    yield
    scheduler.parar()


app = FastAPI(title="Monitoramento de Obras — API", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SESSION_SECRET,
    max_age=14 * 24 * 3600,
    https_only=True,  # cookie de sessão só trafega sob HTTPS (painel servido pelo Caddy/TLS)
    same_site="lax",
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


def _parse_data(data: str | None) -> date:
    return date.fromisoformat(data) if data else date.today()


def _parse_grupo_id(grupo_id: str | None) -> int | None:
    """grupo_id vazio ('Todos os grupos') ou inválido -> None."""
    if not grupo_id or not grupo_id.strip():
        return None
    try:
        return int(grupo_id)
    except ValueError:
        return None


# =============================== Autenticação =============================
@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, erro: str | None = None):
    if auth.usuario_logado(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"erro": erro})


@app.post("/login")
def login(request: Request, email: str = Form(...), senha: str = Form(...)):
    u = db.buscar_usuario_por_email(email.strip())
    if not u or not auth.verificar_senha(senha, u["senha_hash"]):
        return templates.TemplateResponse(
            request, "login.html", {"erro": "E-mail ou senha incorretos."}, status_code=401
        )
    request.session["user_id"] = u["id"]
    return RedirectResponse("/", status_code=303)


@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    if auth.usuario_logado(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "register.html", {"erro": None})


@app.post("/register")
def register(
    request: Request,
    nome: str = Form(...),
    email: str = Form(...),
    senha: str = Form(...),
    confirmar: str = Form(...),
):
    if len(senha) < 6:
        erro = "A senha deve ter pelo menos 6 caracteres."
    elif senha != confirmar:
        erro = "As senhas não conferem."
    else:
        erro = None
    if erro:
        return templates.TemplateResponse(request, "register.html", {"erro": erro}, status_code=400)
    try:
        u = db.criar_usuario(nome.strip(), email.strip(), auth.hash_senha(senha))
    except psycopg.errors.UniqueViolation:
        return templates.TemplateResponse(
            request, "register.html", {"erro": "Já existe uma conta com esse e-mail."}, status_code=400
        )
    request.session["user_id"] = u["id"]
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/perfil", response_class=HTMLResponse)
def perfil_form(request: Request, usuario: dict = Depends(auth.requer_login), ok: str | None = None):
    return templates.TemplateResponse(
        request, "perfil.html", {"usuario": usuario, "erro": None, "ok": ok}
    )


@app.post("/perfil")
def perfil_salvar(
    request: Request,
    usuario: dict = Depends(auth.requer_login),
    nome: str = Form(...),
    email: str = Form(...),
    senha_atual: str = Form(""),
    nova_senha: str = Form(""),
    confirmar: str = Form(""),
):
    novo_hash = None
    if nova_senha:
        atual = db.buscar_usuario_por_email(usuario["email"])
        if not atual or not auth.verificar_senha(senha_atual, atual["senha_hash"]):
            return templates.TemplateResponse(
                request, "perfil.html",
                {"usuario": usuario, "erro": "Senha atual incorreta.", "ok": None}, status_code=400,
            )
        if len(nova_senha) < 6 or nova_senha != confirmar:
            return templates.TemplateResponse(
                request, "perfil.html",
                {"usuario": usuario, "erro": "Nova senha inválida (mín. 6 e deve conferir).", "ok": None},
                status_code=400,
            )
        novo_hash = auth.hash_senha(nova_senha)
    try:
        db.atualizar_usuario(usuario["id"], nome.strip(), email.strip(), novo_hash)
    except psycopg.errors.UniqueViolation:
        return templates.TemplateResponse(
            request, "perfil.html",
            {"usuario": usuario, "erro": "Esse e-mail já está em uso.", "ok": None}, status_code=400,
        )
    return RedirectResponse("/perfil?ok=1", status_code=303)


# ============================ Painel (protegido) =========================
def _render_relatorio(request, data, grupo_id, usuario):
    gid = _parse_grupo_id(grupo_id)
    relatorio = db.relatorio_do_dia(_parse_data(data), gid)
    return templates.TemplateResponse(
        request, "relatorio.html",
        {"relatorio": relatorio, "grupos": db.listar_grupos(), "grupo_id": gid, "usuario": usuario},
    )


@app.get("/", response_class=HTMLResponse)
def painel(request: Request, data: str | None = None, grupo_id: str | None = None,
           usuario: dict = Depends(auth.requer_login)):
    return _render_relatorio(request, data, grupo_id, usuario)


@app.get("/relatorio", response_class=HTMLResponse)
def relatorio_html(request: Request, data: str | None = None, grupo_id: str | None = None,
                   usuario: dict = Depends(auth.requer_login)):
    return _render_relatorio(request, data, grupo_id, usuario)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, usuario: dict = Depends(auth.requer_login)):
    return templates.TemplateResponse(
        request, "dashboard.html", {"est": db.estatisticas(), "usuario": usuario}
    )


@app.get("/historico", response_class=HTMLResponse)
def historico_html(request: Request, q: str = Query(""), usuario: dict = Depends(auth.requer_login)):
    busca = q.strip()
    resultados = db.buscar_historico(busca) if busca else db.historico_recente()
    return templates.TemplateResponse(
        request, "historico.html",
        {"q": q, "resultados": resultados, "grupos": db.listar_grupos(), "usuario": usuario},
    )


@app.post("/api/historico/resumo")
def api_historico_resumo(
    grupo_id: str | None = Form(None),
    data_inicio: str | None = Form(None),
    data_fim: str | None = Form(None),
    usuario: dict = Depends(auth.requer_login),
):
    hoje = date.today()
    try:
        ini = date.fromisoformat(data_inicio) if data_inicio else hoje.replace(day=1)
        fim = date.fromisoformat(data_fim) if data_fim else hoje
    except ValueError:
        raise HTTPException(status_code=400, detail="Datas inválidas.")
    if ini > fim:
        ini, fim = fim, ini
    return resumo_ia.gerar_resumo(_parse_grupo_id(grupo_id), ini, fim)


@app.get("/grupos", response_class=HTMLResponse)
def grupos_html(request: Request, usuario: dict = Depends(auth.requer_login)):
    return templates.TemplateResponse(
        request, "grupos.html", {"grupos": db.listar_grupos(), "usuario": usuario}
    )


@app.get("/saude", response_class=HTMLResponse)
def saude_html(request: Request, usuario: dict = Depends(auth.requer_login)):
    return templates.TemplateResponse(
        request, "saude.html",
        {
            "saude": health.status(),
            "incidentes": db.incidentes_recentes(),
            "alerta_min": config.SAUDE_ALERTA_MINUTOS,
            "usuario": usuario,
        },
    )


@app.post("/grupos/{grupo_id}/ativar")
def grupos_toggle(grupo_id: int, ativo: bool = Form(...), usuario: dict = Depends(auth.requer_login)):
    db.definir_grupo_ativo(grupo_id, ativo)
    return RedirectResponse("/grupos", status_code=303)


# ============================= Lista Mãe (protegido) =====================
@app.get("/lista-mae", response_class=HTMLResponse)
def lista_mae_html(request: Request, status: str = "aberto", urgencia: str = "",
                   grupo_id: str | None = None, categoria: str = "",
                   usuario: dict = Depends(auth.requer_login)):
    gid = _parse_grupo_id(grupo_id)
    urg = urgencia if urgencia in db._URGENCIAS else None
    cat = categoria if categoria in db._CATEGORIAS else None
    st = status if status in ("aberto", "resolvidos", "todos") else "aberto"
    return templates.TemplateResponse(
        request, "lista_mae.html",
        {
            "usuario": usuario,
            "itens": db.lista_mae_itens(st, urg, gid, cat),
            "novos": db.lista_mae_novos(),
            "progresso": db.lista_mae_progresso(urg, gid, cat),
            "grupos": db.listar_grupos(),
            "f": {"status": st, "urgencia": urgencia, "grupo_id": gid, "categoria": categoria},
        },
    )


@app.post("/lista-mae/adicionar")
def lista_mae_adicionar(item_id: str = Form(""), todos: str = Form(""),
                        usuario: dict = Depends(auth.requer_login)):
    if todos:
        db.adicionar_lista(todos=True)
    elif item_id.isdigit():
        db.adicionar_lista(int(item_id))
    return RedirectResponse("/lista-mae", status_code=303)


@app.post("/api/lista-mae/{item_id}/toggle")
def api_lista_toggle(item_id: int, resolver: bool = Form(...),
                     usuario: dict = Depends(auth.requer_login)):
    novo = db.resolver_item(item_id, resolver, usuario["id"])
    if novo is None:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    return {
        "resolvido": novo["resolvido"],
        "resolvido_em": novo["resolvido_em"].strftime("%d/%m/%Y") if novo["resolvido_em"] else None,
        "por": usuario["nome"] if novo["resolvido"] else None,
    }


# ============================== API (protegido) ==========================
@app.get("/api/relatorio")
def api_relatorio(data: str | None = None, grupo_id: str | None = None,
                  usuario: dict = Depends(auth.requer_login)):
    return db.relatorio_do_dia(_parse_data(data), _parse_grupo_id(grupo_id))


@app.get("/api/historico")
def api_historico(q: str = Query(...), limite: int = 50, usuario: dict = Depends(auth.requer_login)):
    return {"q": q, "resultados": db.buscar_historico(q, limite)}


@app.get("/api/estatisticas")
def api_estatisticas(usuario: dict = Depends(auth.requer_login)):
    return db.estatisticas()


@app.post("/api/relatorio/enviar")
def api_enviar_relatorio(data: str | None = None, grupo_id: str | None = None,
                         usuario: dict = Depends(auth.requer_login)):
    resultado = reports.gerar_e_entregar(_parse_data(data) if data else None, _parse_grupo_id(grupo_id))
    return {"entregue": resultado["entregue"], "total": resultado["relatorio"]["total"]}


@app.post("/api/manutencao/retencao")
def api_retencao(usuario: dict = Depends(auth.requer_login)):
    return {"arquivadas": maintenance.arquivar_midia_antiga()}


# ============================== Aberto ===================================
FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect width="32" height="32" rx="7" fill="#3b82f6"/>'
    '<text x="16" y="23" text-anchor="middle" '
    'font-family="Arial,Helvetica,sans-serif" font-size="21" font-weight="bold" '
    'fill="#ffffff">M</text></svg>'
)


@app.get("/favicon.svg")
@app.get("/favicon.ico")
def favicon():
    return Response(content=FAVICON_SVG, media_type="image/svg+xml")


@app.get("/health")
def health_endpoint():
    return health.status()
