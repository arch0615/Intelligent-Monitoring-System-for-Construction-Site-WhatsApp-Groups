#!/usr/bin/env python3
"""Semeia dados de exemplo (Nível 2) para ver o painel/relatório/histórico
funcionando SEM WhatsApp.

Pré-requisito: Postgres no ar (docker compose up -d postgres).
Conecta em localhost:5432 (ajuste SEED_DB_HOST se necessário).

Uso:
    cd whatsapp-obras-monitor
    docker compose up -d postgres
    set -a; source .env; set +a
    python3 scripts/semear_demo.py
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

import psycopg

DSN = (
    f"host={os.environ.get('SEED_DB_HOST', 'localhost')} "
    f"port={os.environ.get('POSTGRES_PORT', '5432')} "
    f"user={os.environ['POSTGRES_USER']} "
    f"password={os.environ['POSTGRES_PASSWORD']} "
    f"dbname={os.environ['POSTGRES_DB']}"
)

# (texto, tipo, [(categoria, urgencia, resumo, confianca), ...])
EXEMPLOS = [
    ("Falta cimento no 3º andar, o pedreiro está parado.", "texto",
     [("pendencia", "alta", "Falta cimento no 3º andar — pedreiro parado", 0.9)]),
    ("Qual cor de tinta foi aprovada para a fachada?", "texto",
     [("duvida", "media", "Dúvida sobre a cor de tinta da fachada", 0.85)]),
    ("Decidido: entrega da laje fica para sexta.", "texto",
     [("decisao", "baixa", "Entrega da laje definida para sexta-feira", 0.92)]),
    ("Vazamento de gás na obra, evacuar agora!", "texto",
     [("pendencia", "critica", "Vazamento de gás — evacuação imediata", 0.97)]),
    ("Áudio: precisamos de mais 2 serventes amanhã.", "audio",
     [("pendencia", "media", "Solicitação de 2 serventes para amanhã", 0.8)]),
    ("Bom dia, pessoal!", "texto", []),
]


def main() -> None:
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO grupos (wa_jid, nome, is_active)
               VALUES ('demo-001@g.us', 'Obra Demo — Edifício Central', true)
               ON CONFLICT (wa_jid) DO UPDATE SET nome = EXCLUDED.nome
               RETURNING id""",
        )
        grupo_id = cur.fetchone()[0]

        cur.execute(
            """INSERT INTO remetentes (wa_jid, nome_push)
               VALUES ('5541999990000@s.whatsapp.net', 'Mestre de Obras')
               ON CONFLICT (wa_jid) DO UPDATE SET nome_push = EXCLUDED.nome_push
               RETURNING id""",
        )
        remetente_id = cur.fetchone()[0]

        base = datetime.now()
        criadas = 0
        for i, (texto, tipo, analises) in enumerate(EXEMPLOS):
            cur.execute(
                """INSERT INTO mensagens
                     (grupo_id, remetente_id, wa_message_id, tipo, enviada_em,
                      texto, texto_origem, status, payload_bruto)
                   VALUES (%s, %s, %s, %s, %s, %s, 'original', 'processada', %s)
                   ON CONFLICT (grupo_id, wa_message_id) DO NOTHING
                   RETURNING id""",
                (grupo_id, remetente_id, f"demo-msg-{i}", tipo,
                 base - timedelta(minutes=10 * i), texto, json.dumps({"demo": True})),
            )
            row = cur.fetchone()
            if row is None:
                continue
            mensagem_id = row[0]
            criadas += 1
            for categoria, urgencia, resumo, conf in analises:
                cur.execute(
                    """INSERT INTO analises
                         (mensagem_id, categoria, urgencia, resumo, confianca, modelo)
                       VALUES (%s, %s, %s, %s, %s, 'demo')""",
                    (mensagem_id, categoria, urgencia, resumo, conf),
                )
        conn.commit()

    print(f"OK — {criadas} mensagem(ns) de exemplo inseridas no grupo demo.")
    print("Abra http://localhost:8000 para ver o relatório do dia.")


if __name__ == "__main__":
    main()
