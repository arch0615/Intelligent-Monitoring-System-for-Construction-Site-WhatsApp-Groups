"""Classificação de conteúdo com a API Claude (RF-02).

Recebe o texto de uma mensagem (original, transcrito ou extraído) e, opcionalmente,
imagens (fotos ou frames de vídeo), e identifica PENDÊNCIAS, DÚVIDAS e DECISÕES,
marcando o nível de urgência de cada item.

Decisões de implementação (alinhadas ao SDK oficial `anthropic`):
- Modelo padrão: claude-opus-4-8 (configurável via CLAUDE_MODEL).
- Adaptive thinking + effort "medium": bom equilíbrio custo/qualidade para
  classificação (projeto é sensível a custo — RF/condições comerciais).
- Saída estruturada via output_config.format (json_schema) -> JSON validado,
  sem prefill (removido nos modelos 4.x).
- Prompt caching no system prompt (estável entre todas as mensagens). Observação:
  o cache só ativa de fato se o prefixo atingir o mínimo do modelo (~4096 tokens
  no Opus); para volumes altos, vale engrossar o system com exemplos few-shot.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import anthropic

from .config import config, logger

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

# System prompt estável (bom candidato a cache). Descreve a tarefa e as regras
# de classificação para o contexto de obras.
SYSTEM_PROMPT = """\
Você é um assistente que analisa mensagens trocadas em grupos de WhatsApp de \
obras de construção. Sua função é transformar conversa solta em informação \
estruturada para a equipe de gestão.

A partir do conteúdo de UMA mensagem (que pode ser texto, transcrição de áudio/\
vídeo, texto extraído de documento e/ou imagens), identifique itens relevantes e \
classifique cada um em exatamente uma categoria:

- "pendencia": algo que precisa ser feito, resolvido ou providenciado; uma tarefa \
  em aberto, falta de material, atraso, solicitação não atendida.
- "duvida": uma pergunta ou incerteza que aguarda resposta/esclarecimento.
- "decisao": uma definição, aprovação ou combinado que foi tomado.

Para cada item, atribua a urgência:
- "critica": risco imediato (segurança, parada de obra, prazo estourando hoje).
- "alta": precisa de atenção no mesmo dia.
- "media": importante, mas pode aguardar o relatório diário.
- "baixa": informativo.

Regras:
- Uma mensagem pode conter 0, 1 ou vários itens. Se não houver nada relevante \
  (ex.: "bom dia", figurinha, conversa social), retorne uma lista vazia.
- "resumo" deve ser uma frase curta, objetiva e em português, pronta para um \
  relatório de gestão (ex.: "Falta cimento no 3º andar — pedreiro aguardando").
- "confianca" é sua confiança (0.0 a 1.0) de que a classificação está correta.
- Não invente informação que não esteja na mensagem.
"""

# Esquema da saída estruturada. additionalProperties:false é obrigatório.
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "itens": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "categoria": {"type": "string", "enum": ["pendencia", "duvida", "decisao"]},
                    "urgencia": {"type": "string", "enum": ["baixa", "media", "alta", "critica"]},
                    "resumo": {"type": "string"},
                    "confianca": {"type": "number"},
                },
                "required": ["categoria", "urgencia", "resumo", "confianca"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["itens"],
    "additionalProperties": False,
}

_MEDIA_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def _bloco_imagem(caminho: str) -> dict[str, Any] | None:
    """Monta um content block de imagem (base64) para a Claude (visão)."""
    ext = Path(caminho).suffix.lower()
    media_type = _MEDIA_TYPES.get(ext)
    if media_type is None:
        return None
    dados = base64.standard_b64encode(Path(caminho).read_bytes()).decode("utf-8")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": dados},
    }


def classificar(texto: str | None, imagens: list[str] | None = None) -> list[dict[str, Any]]:
    """Classifica o conteúdo de uma mensagem. Retorna a lista de itens (pode ser vazia)."""
    conteudo: list[dict[str, Any]] = []

    # Imagens primeiro (fotos enviadas no grupo ou frames extraídos de vídeo).
    for caminho in imagens or []:
        bloco = _bloco_imagem(caminho)
        if bloco is not None:
            conteudo.append(bloco)

    instrucao = texto.strip() if texto else "(mensagem sem texto — analise as imagens, se houver)"
    conteudo.append({"type": "text", "text": f"Conteúdo da mensagem:\n{instrucao}"})

    if not conteudo:
        return []

    response = _client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=2000,
        thinking={"type": "adaptive"},
        output_config={
            "effort": "medium",
            "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
        },
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": conteudo}],
    )

    # Com output_config.format, o primeiro bloco de texto é JSON válido.
    texto_resposta = next((b.text for b in response.content if b.type == "text"), "")
    try:
        dados = json.loads(texto_resposta)
    except json.JSONDecodeError:
        logger.error("Resposta da Claude não é JSON válido: %r", texto_resposta[:200])
        return []

    itens = dados.get("itens", [])
    logger.debug(
        "Claude classificou %d item(ns) | cache_read=%s",
        len(itens),
        getattr(response.usage, "cache_read_input_tokens", 0),
    )
    return itens
