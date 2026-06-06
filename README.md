# Monitoramento Inteligente de Grupos de WhatsApp de Obras

Sistema que captura, em tempo real, o conteúdo de grupos de WhatsApp de obras
(texto, áudio, foto, documento e vídeo), usa **Whisper** para transcrever áudio
e a **API Claude** para classificar **pendências, dúvidas e decisões**, e entrega
valor por três canais: relatório diário, consulta de histórico e alertas
proativos — sem mudar o fluxo de trabalho da equipe de campo.

> Cliente: Monreal (Cassiano) · Desenvolvedor: James · Plataforma: Workana
> Documentos de referência: `analise_requisitos.txt`,
> `stack_e_plano_desenvolvimento.txt`, `plano_diario_de_trabalho.txt`.

---

## Estado atual do desenvolvimento

Este repositório corresponde ao **scaffold das Etapas 0–2** do plano diário:

| Etapa | Item | Estado |
|-------|------|--------|
| 0 | Repo, Docker Compose, Postgres + Redis, `.env`, schema do banco | ✅ scaffold |
| 1 | Worker de captura (Node.js + Baileys) | ✅ esqueleto funcional |
| 2 | Pipeline (Whisper + ffmpeg + docs + Claude) | ✅ esqueleto funcional |
| 3 | Relatório diário + consulta de histórico + painel (FastAPI) | ✅ esqueleto funcional |
| 4 | Alertas proativos (Telegram) + notificação de bloqueio (Plano B) | ✅ esqueleto funcional |
| 5 | Painel de grupos (RF-08), escala, documentação, handover | ⏳ a fazer |

Ações externas pendentes (não são código): provisionar o VPS, o número
dedicado + número de backup, a chave da API Claude e o bot de alertas. Ver
**Pendências bloqueadoras (P-01..P-08)** no `plano_diario_de_trabalho.txt`.

---

## Arquitetura

```
[WhatsApp]
   │ (Baileys / multi-device)
   ▼
capture-worker (Node.js + TypeScript)  ── grava ──▶ PostgreSQL
   │  publica evento {mensagem_id}                    ▲
   ▼                                                  │
Redis Stream  ──consumido por──▶  pipeline (Python)   │
                                   ├─ faster-whisper (áudio)
                                   ├─ ffmpeg (frames + áudio de vídeo)
                                   ├─ pdfplumber / python-docx (docs)
                                   └─ API Claude (classificação) ──grava──┘
```

- **Captura é somente leitura** — o número nunca envia mensagens (mitiga bloqueio).
- **Redis Stream** com grupo de consumidores garante entrega confiável (sem perda).
- **Postgres é a fonte da verdade**; o stream carrega apenas o `mensagem_id`.

Detalhes em [docs/ARQUITETURA.md](docs/ARQUITETURA.md).

---

## Como rodar (desenvolvimento)

Pré-requisitos: Docker + Docker Compose.

```bash
# 1. Configurar segredos
cp .env.example .env
#    Edite .env: senha do Postgres, ANTHROPIC_API_KEY, WA_PHONE_NUMBER (número
#    dedicado em formato internacional só com dígitos, ex.: 5511999998888).

# 2. Subir o ambiente (Postgres, Redis, captura, pipeline)
docker compose up -d --build

# 3. Parear o número dedicado (primeira vez) — ler o PAIRING CODE nos logs:
docker compose logs -f capture
#    No celular do número dedicado: WhatsApp > Aparelhos conectados >
#    Conectar aparelho > Conectar com número de telefone > digitar o código.

# 4. Ativar o(s) grupo(s) a monitorar (RF-08).
#    Por enquanto via SQL (o painel chega na Etapa 5). O grupo é criado
#    automaticamente na primeira mensagem capturada; para garantir que está ativo:
docker compose exec postgres psql -U obras -d obras_monitor \
  -c "UPDATE grupos SET is_active = true;"
```

Acompanhar o processamento:

```bash
docker compose logs -f pipeline
```

### Painel e relatórios (Etapa 3)

Com o ambiente no ar, o painel fica em **http://localhost:8000**:

- `/` — relatório do dia (pendências, dúvidas, decisões), filtrável por data e grupo.
- `/historico?q=...` — consulta de histórico por busca full-text (RF-04).
- `/grupos` — ativar/desativar grupos monitorados (RF-08, base do painel da Etapa 5).

O relatório diário é disparado automaticamente pelo APScheduler no horário
`RELATORIO_HORA:RELATORIO_MINUTO` (padrão 18:00) e entregue pelo Telegram.
Para gerar/entregar sob demanda (teste/DEMO):

```bash
curl -X POST "http://localhost:8000/api/relatorio/enviar"
```

### Alertas proativos (Etapa 4)

Itens classificados como **crítica/alta** (configurável em `ALERTA_URGENCIAS`)
disparam um alerta imediato no Telegram, sem esperar o relatório diário (RF-05).
A tabela `alertas` garante dedup — cada situação é notificada uma única vez.

Se o número de monitoramento for deslogado/bloqueado, o worker de captura envia
uma **notificação de bloqueio** (Plano B / RF-09) para acionar o número de backup.
Configure `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` no `.env`.

---

## Estrutura do repositório

```
.
├── docker-compose.yml         # sobe todo o sistema
├── .env.example               # modelo de configuração
├── db/migrations/             # schema SQL (roda no initdb do Postgres)
├── capture-worker/            # Etapa 1 — Node.js + Baileys
│   └── src/
│       ├── index.ts           # entrypoint
│       ├── whatsapp.ts        # conexão Baileys, captura, reconexão
│       ├── db.ts              # gravação + dedup
│       ├── redis.ts           # publicação no stream
│       ├── config.ts          # configuração
│       └── logger.ts
├── pipeline/                  # Etapa 2 — Python
│   └── app/
│       ├── worker.py          # orquestra o processamento por mensagem
│       ├── queue.py           # consumo confiável do Redis Stream
│       ├── transcribe.py      # faster-whisper
│       ├── video.py           # ffmpeg (frames + áudio)
│       ├── documents.py       # pdfplumber / python-docx
│       ├── classify.py        # API Claude (classificação)
│       ├── db.py              # leitura/escrita no Postgres
│       └── config.py
├── api/                       # Etapa 3 — FastAPI (relatório, histórico, painel)
│   └── app/
│       ├── main.py            # endpoints HTML + JSON
│       ├── reports.py         # geração + entrega do relatório diário
│       ├── scheduler.py       # APScheduler (relatório diário agendado)
│       ├── db.py              # consultas (relatório, busca full-text)
│       ├── config.py
│       └── templates/         # painel (Jinja: relatório, histórico, grupos)
├── media/                     # mídia capturada (NÃO versionada — LGPD)
└── docs/                      # documentação
```

## Custos mensais recorrentes (estimados)

- **Servidor (VPS):** ~US$ 10–30/mês conforme escala.
- **API Claude:** variável conforme volume de mensagens/áudio/vídeo (P-02/P-04).
- **Whisper:** roda no servidor, **sem custo de API**.
- **Licenças:** nenhuma (ferramentas open source).

## Propriedade

Todo o código-fonte e a documentação são de propriedade do cliente (Monreal).
