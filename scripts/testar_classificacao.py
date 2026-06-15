#!/usr/bin/env python3
"""Teste de fumaça (Nível 1) — a IA da Claude está classificando?

Roda sem WhatsApp, sem VPS e sem banco. Só precisa da chave da API
(ANTHROPIC_API_KEY) carregada no ambiente. Usa o MESMO prompt e schema do
sistema real (pipeline/app/classify.py).

Uso:
    pip install anthropic python-dotenv
    set -a; source whatsapp-obras-monitor/.env; set +a
    python3 whatsapp-obras-monitor/scripts/testar_classificacao.py
"""
from __future__ import annotations

import os
import sys

# O config do pipeline exige algumas variáveis (Postgres) que NÃO são usadas
# por este teste — definimos valores de preenchimento só para o import funcionar.
os.environ.setdefault("POSTGRES_USER", "teste")
os.environ.setdefault("POSTGRES_PASSWORD", "teste")
os.environ.setdefault("POSTGRES_DB", "teste")

# Permite importar o pacote `app` do pipeline (prompt/schema reais).
_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RAIZ, "pipeline"))

if not os.environ.get("ANTHROPIC_API_KEY"):
    print("ERRO: ANTHROPIC_API_KEY não está definida. Carregue o .env primeiro:")
    print("  set -a; source whatsapp-obras-monitor/.env; set +a")
    sys.exit(1)

from app.classify import classificar  # noqa: E402

# Mensagens de exemplo no estilo de um grupo de obra.
EXEMPLOS = [
    "Falta cimento no 3º andar, o pedreiro está parado esperando.",
    "Qual cor de tinta foi aprovada para a fachada?",
    "Decidido: a entrega da laje fica para sexta-feira.",
    "ATENÇÃO: vazamento de gás na obra, evacuar agora!",
    "Bom dia, pessoal 👍",
]


def main() -> None:
    print("Testando classificação com a Claude...\n")
    for texto in EXEMPLOS:
        itens = classificar(texto)
        print(f"» {texto}")
        if not itens:
            print("   (nada relevante)\n")
            continue
        for item in itens:
            print(
                f"   - [{item['categoria']}/{item['urgencia']}] {item['resumo']}"
                f"  (confiança {item.get('confianca')})"
            )
        print()
    print("OK — se os itens acima fazem sentido, a IA está funcionando.")


if __name__ == "__main__":
    main()
