#!/usr/bin/env python3
"""Injeta uma mensagem de texto e publica na fila (Nível 3) para exercitar o
pipeline ponta a ponta SEM WhatsApp.

Pré-requisito: Postgres + Redis + pipeline no ar.
    docker compose up -d postgres redis api pipeline

Uso:
    set -a; source .env; set +a
    python3 scripts/injetar_mensagem.py "Falta cimento no 3º andar, parou tudo"
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime

import psycopg
import redis

DSN = (
    f"host={os.environ.get('SEED_DB_HOST', 'localhost')} "
    f"port={os.environ.get('POSTGRES_PORT', '5432')} "
    f"user={os.environ['POSTGRES_USER']} "
    f"password={os.environ['POSTGRES_PASSWORD']} "
    f"dbname={os.environ['POSTGRES_DB']}"
)
REDIS_HOST = os.environ.get("SEED_REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_STREAM = os.environ.get("REDIS_STREAM", "captura:eventos")


def main() -> None:
    texto = sys.argv[1] if len(sys.argv) > 1 else "Falta cimento no 3º andar, parou tudo"

    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO grupos (wa_jid, nome, is_active)
               VALUES ('demo-001@g.us', 'Obra Demo — Edifício Central', true)
               ON CONFLICT (wa_jid) DO UPDATE SET nome = EXCLUDED.nome
               RETURNING id""",
        )
        grupo_id = cur.fetchone()[0]
        wa_id = f"inj-{int(time.time())}"
        cur.execute(
            """INSERT INTO mensagens
                 (grupo_id, wa_message_id, tipo, enviada_em, texto, texto_origem,
                  status, payload_bruto)
               VALUES (%s, %s, 'texto', %s, %s, 'original', 'capturada', %s)
               RETURNING id""",
            (grupo_id, wa_id, datetime.now(), texto, json.dumps({"injetado": True})),
        )
        mensagem_id = cur.fetchone()[0]
        conn.commit()

    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
    r.xadd(REDIS_STREAM, {"mensagem_id": str(mensagem_id)})

    print(f"OK — mensagem {mensagem_id} injetada e publicada na fila.")
    print('Acompanhe: docker compose logs -f pipeline')
    print("Depois veja em http://localhost:8000")


if __name__ == "__main__":
    main()
