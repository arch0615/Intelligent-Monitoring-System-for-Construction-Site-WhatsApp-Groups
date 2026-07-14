"""Exportação de relatórios em PDF (fpdf2 — puro Python, sem dependências de SO).

Gera PDFs de: Lista Mãe, Relatório do dia, Dashboard (resumo) e Histórico.
Usa fontes core (Latin-1); o texto é saneado para evitar erros com caracteres
fora do conjunto (emojis viram '?', travessões/aspas viram equivalentes ASCII).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fpdf import FPDF

# Cores (RGB)
AZUL = (59, 130, 246)
ESCURO = (15, 23, 42)
CINZA = (120, 130, 150)
TINTA = (30, 35, 45)
LINHA = (222, 226, 234)
VERDE = (22, 163, 74)
VERMELHO = (185, 28, 28)
LARANJA = (234, 88, 12)
AMARELO = (202, 138, 4)

ROT_CAT = {"pendencia": "Pendencia", "duvida": "Duvida", "decisao": "Decisao"}
ROT_URG = {"critica": "CRITICA", "alta": "ALTA", "media": "MEDIA", "baixa": "BAIXA"}
ROT_TIPO = {"texto": "Texto", "audio": "Audio", "imagem": "Imagem", "video": "Video",
            "documento": "Documento", "outro": "Outro"}
COR_URG = {"critica": VERMELHO, "alta": LARANJA, "media": AMARELO, "baixa": CINZA}

_SUBST = {"—": "-", "–": "-", "•": "-", "→": "->", "“": '"', "”": '"',
          "‘": "'", "’": "'", "…": "...", "²": "2", "³": "3", "ª": "a", "º": "o"}


def _s(t: Any) -> str:
    """Saneia texto para as fontes core (Latin-1)."""
    s = str(t if t is not None else "")
    for k, v in _SUBST.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


class _PDF(FPDF):
    titulo_doc = ""

    def header(self) -> None:
        self.set_fill_color(*ESCURO)
        self.rect(0, 0, self.w, 20, "F")
        self.set_xy(12, 5)
        self.set_text_color(255, 255, 255)
        self.set_font("helvetica", "B", 13)
        self.cell(0, 6, _s("Monreal - Monitor de Obras"), new_x="LMARGIN", new_y="NEXT")
        self.set_x(12)
        self.set_font("helvetica", "", 9)
        self.set_text_color(185, 195, 210)
        self.cell(0, 5, _s(self.titulo_doc), new_x="LMARGIN", new_y="NEXT")
        self.ln(7)
        self.set_text_color(*TINTA)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("helvetica", "", 8)
        self.set_text_color(*CINZA)
        self.cell(0, 8, _s(f"Gerado em {datetime.now():%d/%m/%Y %H:%M}  -  pagina {self.page_no()}"),
                  align="C")


def _novo(titulo_doc: str, subtitulo: str | None = None) -> _PDF:
    pdf = _PDF()
    pdf.titulo_doc = titulo_doc
    pdf.set_auto_page_break(True, margin=16)
    pdf.set_left_margin(12)
    pdf.set_right_margin(12)
    pdf.add_page()
    if subtitulo:
        pdf.set_font("helvetica", "", 10)
        pdf.set_text_color(*CINZA)
        pdf.multi_cell(0, 5, _s(subtitulo))
        pdf.set_text_color(*TINTA)
        pdf.ln(2)
    return pdf


def _titulo_secao(pdf: _PDF, texto: str) -> None:
    pdf.ln(2)
    pdf.set_font("helvetica", "B", 12)
    pdf.set_text_color(*ESCURO)
    pdf.cell(0, 7, _s(texto), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*LINHA)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)
    pdf.set_text_color(*TINTA)


def _item(pdf: _PDF, tag: str, cor_tag: tuple, titulo: str, meta: str,
          riscado: bool = False) -> None:
    """Uma linha de item: [TAG colorida] título (multi-linha) + meta em cinza."""
    pdf.set_font("helvetica", "B", 8)
    pdf.set_text_color(*cor_tag)
    pdf.cell(24, 5, _s(tag), new_x="RIGHT", new_y="TOP")
    pdf.set_font("helvetica", "" if not riscado else "I", 10)
    pdf.set_text_color(150, 155, 165) if riscado else pdf.set_text_color(*TINTA)
    x = pdf.get_x()
    pdf.multi_cell(pdf.w - pdf.r_margin - x, 5, _s(("[resolvido] " if riscado else "") + titulo),
                   new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(pdf.l_margin + 24)
    pdf.set_font("helvetica", "", 8)
    pdf.set_text_color(*CINZA)
    pdf.multi_cell(0, 4.5, _s(meta), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*TINTA)
    pdf.ln(1.5)


def _barra_tabela(pdf: _PDF, linhas: list[tuple[str, int]], titulo_col: str) -> None:
    """Tabela simples de duas colunas (rótulo | valor) com barra proporcional."""
    mx = max((n for _, n in linhas), default=0) or 1
    pdf.set_font("helvetica", "", 9)
    for label, n in linhas:
        y = pdf.get_y()
        pdf.set_text_color(*TINTA)
        pdf.cell(70, 6, _s(label), new_x="RIGHT", new_y="TOP")
        # barra
        pdf.set_fill_color(*LINHA)
        pdf.rect(pdf.get_x(), y + 1.5, 80, 3, "F")
        pdf.set_fill_color(*AZUL)
        pdf.rect(pdf.get_x(), y + 1.5, 80 * n / mx, 3, "F")
        pdf.set_xy(pdf.w - pdf.r_margin - 18, y)
        pdf.set_font("helvetica", "B", 9)
        pdf.cell(18, 6, _s(str(n)), align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "", 9)


# --------------------------------------------------------------------------- #
#  Builders
# --------------------------------------------------------------------------- #
def lista_mae(itens: list[dict], progresso: dict, subtitulo: str) -> bytes:
    pdf = _novo("Lista Mae - pendencias acumuladas", subtitulo)
    pdf.set_font("helvetica", "B", 11)
    pdf.set_text_color(*VERDE)
    pdf.cell(0, 6, _s(f"{progresso['resolvidos']} de {progresso['total']} itens resolvidos "
                      f"({progresso['pct']}%)"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*TINTA)
    pdf.ln(2)
    _titulo_secao(pdf, f"Itens ({len(itens)})")
    if not itens:
        pdf.set_font("helvetica", "I", 10)
        pdf.cell(0, 6, _s("Nenhum item para os filtros selecionados."))
    for i in itens:
        meta = f"{ROT_CAT.get(i['categoria'], i['categoria'])}  -  {i['grupo_nome'] or 'obra'}" \
               f"  -  {i['criado_em']:%d/%m/%Y}"
        if i["resolvido"] and i.get("resolvido_em"):
            meta += f"  -  resolvido em {i['resolvido_em']:%d/%m/%Y}"
            if i.get("resolvido_por_nome"):
                meta += f" por {i['resolvido_por_nome']}"
        _item(pdf, ROT_URG.get(i["urgencia"], i["urgencia"]), COR_URG.get(i["urgencia"], CINZA),
              i["resumo"], meta, riscado=i["resolvido"])
    return bytes(pdf.output())


def relatorio(rel: dict, subtitulo: str) -> bytes:
    pdf = _novo(f"Relatorio do dia - {rel['dia']}", subtitulo)
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 6, _s(f"Total de itens: {rel['total']}  |  Criticos/urgentes: "
                      f"{len(rel['criticos'])}"), new_x="LMARGIN", new_y="NEXT")

    for chave, titulo in [("pendencias", "Pendencias"), ("duvidas", "Duvidas"),
                          ("decisoes", "Decisoes")]:
        lista = rel[chave]
        _titulo_secao(pdf, f"{titulo} ({len(lista)})")
        if not lista:
            pdf.set_font("helvetica", "I", 10)
            pdf.set_text_color(*CINZA)
            pdf.cell(0, 6, _s("Nada nesta categoria."), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(*TINTA)
            continue
        for it in lista:
            meta = f"{it['grupo_nome'] or 'obra'}"
            if it.get("remetente"):
                meta += f"  -  {it['remetente']}"
            meta += f"  -  {it['enviada_em']:%d/%m %H:%M}"
            _item(pdf, ROT_URG.get(it["urgencia"], it["urgencia"]),
                  COR_URG.get(it["urgencia"], CINZA), it["resumo"], meta)
    return bytes(pdf.output())


def dashboard(est: dict, subtitulo: str) -> bytes:
    pdf = _novo("Dashboard - resumo", subtitulo)
    # KPIs
    pdf.set_font("helvetica", "", 10)
    for rotulo, valor in [
        ("Mensagens capturadas", est["total_mensagens"]),
        ("Itens analisados pela IA", est["total_analises"]),
        ("Grupos ativos", f"{est['grupos_ativos']}/{est['grupos_total']}"),
        ("Criticos / urgentes", est["criticos"]),
    ]:
        pdf.set_text_color(*CINZA)
        pdf.cell(60, 6, _s(rotulo), new_x="RIGHT", new_y="TOP")
        pdf.set_font("helvetica", "B", 11)
        pdf.set_text_color(*TINTA)
        pdf.cell(0, 6, _s(str(valor)), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "", 10)

    _titulo_secao(pdf, "Por categoria")
    _barra_tabela(pdf, [(ROT_CAT.get(r["label"], r["label"]), r["n"]) for r in est["categoria"]], "")
    _titulo_secao(pdf, "Por urgencia")
    _barra_tabela(pdf, [(ROT_URG.get(r["label"], r["label"]), r["n"]) for r in est["urgencia"]], "")
    _titulo_secao(pdf, "Por tipo de midia")
    _barra_tabela(pdf, [(ROT_TIPO.get(r["label"], r["label"]), r["n"]) for r in est["tipo"] if r["n"]], "")
    _titulo_secao(pdf, "Itens por grupo")
    _barra_tabela(pdf, [(r["label"], r["n"]) for r in est["por_grupo"]], "")
    return bytes(pdf.output())


def historico(resultados: list[dict], subtitulo: str) -> bytes:
    pdf = _novo("Historico de mensagens", subtitulo)
    _titulo_secao(pdf, f"Registros ({len(resultados)})")
    if not resultados:
        pdf.set_font("helvetica", "I", 10)
        pdf.cell(0, 6, _s("Nenhum registro."))
    for r in resultados:
        meta = f"{r['grupo_nome'] or 'grupo'}"
        if r.get("remetente"):
            meta += f"  -  {r['remetente']}"
        meta += f"  -  {ROT_TIPO.get(r['tipo'], r['tipo'])}  -  {r['enviada_em']:%d/%m/%Y %H:%M}"
        pdf.set_font("helvetica", "", 10)
        pdf.set_text_color(*TINTA)
        pdf.multi_cell(0, 5, _s(r["texto"] or "(sem texto)"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "", 8)
        pdf.set_text_color(*CINZA)
        pdf.multi_cell(0, 4.5, _s(meta), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*TINTA)
        pdf.ln(2)
    return bytes(pdf.output())
