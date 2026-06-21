"""Worker do pipeline (Etapa 2) — orquestra o processamento de cada mensagem.

Fluxo por mensagem (consumida do Redis):
  1. Carrega a mensagem + mídias do Postgres.
  2. Deriva o texto:
       - áudio          -> faster-whisper
       - vídeo          -> ffmpeg (áudio -> Whisper) + frames -> Claude (visão)
       - documento      -> pdfplumber / python-docx
       - imagem/texto   -> usa legenda/corpo (+ imagem na análise)
  3. Classifica com a Claude (pendência/dúvida/decisão + urgência).
  4. Grava resultados e marca a mensagem como processada.
  5. ACK no stream.

Erros em uma mensagem não derrubam o worker: marcamos status 'erro' e seguimos.
"""
from __future__ import annotations

import threading
import time

from . import alerts, classify, db, documents, transcribe, video
from .config import logger
from .queue import confirmar, consumir, registrar_saude


def _derivar_texto_e_imagens(msg: db.Mensagem) -> tuple[str | None, list[str]]:
    """Retorna (texto_para_analise, lista_de_imagens) conforme o tipo da mensagem."""
    imagens: list[str] = []
    texto = msg.texto  # legenda/corpo, quando houver

    for midia in msg.midias:
        caminho = midia["caminho"]
        tipo = midia["tipo"]

        if tipo == "audio":
            transcricao = transcribe.transcrever(caminho)
            if transcricao:
                db.gravar_texto(msg.id, transcricao, "transcricao")
                texto = transcricao

        elif tipo == "video":
            # Áudio do vídeo -> Whisper
            try:
                wav = video.extrair_audio(caminho)
                transcricao = transcribe.transcrever(wav)
                if transcricao:
                    db.gravar_texto(msg.id, transcricao, "transcricao")
                    texto = transcricao
            except Exception:  # noqa: BLE001
                logger.exception("Falha na trilha de áudio do vídeo %s", caminho)
            # Frames -> análise visual da Claude
            try:
                imagens.extend(video.extrair_frames(caminho))
            except Exception:  # noqa: BLE001
                logger.exception("Falha ao extrair frames de %s", caminho)

        elif tipo == "documento":
            extraido = documents.extrair_texto(caminho, midia.get("mime_type"))
            if extraido:
                db.gravar_texto(msg.id, extraido, "ocr_extracao")
                texto = extraido

        elif tipo == "imagem":
            imagens.append(caminho)

    return texto, imagens


def processar(mensagem_id: int) -> None:
    msg = db.carregar_mensagem(mensagem_id)
    if msg is None:
        logger.warning("Mensagem %s não encontrada — ignorando", mensagem_id)
        return

    db.marcar_status(mensagem_id, "processando")
    try:
        texto, imagens = _derivar_texto_e_imagens(msg)
        itens = classify.classificar(texto, imagens)
        db.gravar_analises(mensagem_id, itens, classify.config.CLAUDE_MODEL)
        # Alertas proativos (RF-05): dispara imediatamente para itens urgentes.
        enviados = alerts.processar_alertas(mensagem_id)
        db.marcar_status(mensagem_id, "processada")
        logger.info(
            "Mensagem %s processada (%d item(ns), %d alerta(s))", mensagem_id, len(itens), enviados
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Erro ao processar mensagem %s", mensagem_id)
        db.marcar_status(mensagem_id, "erro", str(exc))


def _heartbeat_loop() -> None:
    """Atualiza o heartbeat de saúde a cada 30s, independentemente de o consumidor
    estar bloqueado esperando mensagens (consumidor ocioso = saudável)."""
    while True:
        try:
            registrar_saude()
        except Exception:  # noqa: BLE001 — heartbeat nunca derruba o worker
            logger.exception("Falha ao registrar heartbeat")
        time.sleep(30)


def main() -> None:
    logger.info("Pipeline de processamento iniciado — aguardando eventos")
    threading.Thread(target=_heartbeat_loop, daemon=True).start()
    for evento_id, mensagem_id in consumir():
        try:
            processar(mensagem_id)
        finally:
            # ACK mesmo em erro: o status 'erro' fica registrado no banco e evita
            # reprocessar em loop. Reprocessamento manual via painel (Etapa 3+).
            confirmar(evento_id)


if __name__ == "__main__":
    main()
