#!/usr/bin/env python3
"""Injeta uma mensagem de MÍDIA (áudio/imagem/vídeo/documento) e publica na fila,
para testar o pipeline de mídia ponta a ponta SEM WhatsApp (Nível 3+).

Simula o que a captura faz: cria a mensagem + a mídia (apontando para um arquivo
em MEDIA_DIR) e publica o evento no Redis para o pipeline processar
(transcrição/extração/visão -> classificação Claude).

Pré-requisito: Postgres + Redis + pipeline no ar, e o arquivo já dentro de
./media (montado como /media no contêiner).

Uso (caminho é o do contêiner, ex.: /media/audio/teste.wav):
    docker compose run --rm -e SEED_DB_HOST=postgres -e SEED_REDIS_HOST=redis \
        -v "$PWD/scripts:/scripts:ro" pipeline \
        python /scripts/injetar_midia.py audio /media/audio/teste.wav
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime

import psycopg
import redis

MIME = {
    "audio": "audio/wav",
    "imagem": "image/jpeg",
    "video": "video/mp4",
    "documento": "application/pdf",
}

DSN = (
    f"host={os.environ.get('SEED_DB_HOST', 'localhost')} "
    f"port={os.environ.get('POSTGRES_PORT', '5432')} "
    f"user={os.environ['POSTGRES_USER']} "
    f"password={os.environ['POSTGRES_PASSWORD']} "
    f"dbname={os.environ['POSTGRES_DB']}"
)


def main() -> None:
    if len(sys.argv) < 3:
        print("uso: injetar_midia.py <tipo> <caminho> [legenda]")
        print("  tipo: audio | imagem | video | documento")
        sys.exit(1)
    tipo, caminho = sys.argv[1], sys.argv[2]
    legenda = sys.argv[3] if len(sys.argv) > 3 else None

    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO grupos (wa_jid, nome, is_active)
               VALUES ('demo-001@g.us', 'Obra Demo — Edifício Central', true)
               ON CONFLICT (wa_jid) DO UPDATE SET nome = EXCLUDED.nome
               RETURNING id""",
        )
        grupo_id = cur.fetchone()[0]

        wa_id = f"inj-midia-{int(time.time())}"
        cur.execute(
            """INSERT INTO mensagens
                 (grupo_id, wa_message_id, tipo, enviada_em, texto, texto_origem,
                  status, payload_bruto)
               VALUES (%s, %s, %s, %s, %s, %s, 'capturada', %s)
               RETURNING id""",
            (grupo_id, wa_id, tipo, datetime.now(), legenda,
             "original" if legenda else None, json.dumps({"injetado": True, "midia": True})),
        )
        mensagem_id = cur.fetchone()[0]

        cur.execute(
            """INSERT INTO midias (mensagem_id, tipo, mime_type, caminho)
               VALUES (%s, %s, %s, %s)""",
            (mensagem_id, tipo, MIME.get(tipo), caminho),
        )
        conn.commit()

    r = redis.Redis(
        host=os.environ.get("SEED_REDIS_HOST", "localhost"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
    )
    r.xadd(os.environ.get("REDIS_STREAM", "captura:eventos"), {"mensagem_id": str(mensagem_id)})

    print(f"OK — mensagem {mensagem_id} ({tipo}) injetada com mídia {caminho} e publicada.")


if __name__ == "__main__":
    main()
