# Guia de deploy e operação

Para o responsável técnico. Cobre instalação no VPS, configuração, operação do
dia a dia e o Plano B.

---

## 1. Requisitos

- VPS Ubuntu LTS (22.04/24.04). Sugestão: 4 vCPU / 8 GB RAM / 160 GB SSD,
  IPv4 estático, snapshots/backup habilitados. Provedores de bom custo:
  Hetzner, Contabo, DigitalOcean, Vultr.
- Docker + Docker Compose.
- Um número de WhatsApp **dedicado** (nunca pessoal) para monitoramento, e um
  segundo número de **backup**.
- Chave da API Claude (Anthropic) e um bot do Telegram (token + chat_id).

---

## 2. Instalação

```bash
# No VPS:
git clone <repositorio> obras-monitor && cd obras-monitor
cp .env.example .env
nano .env        # preencher segredos (ver seção 3)

docker compose up -d --build
```

As migrations do banco rodam automaticamente na primeira subida (pasta
`db/migrations` é executada pelo Postgres no initdb).

---

## 3. Configuração (`.env`)

| Variável | O que é |
|----------|---------|
| `POSTGRES_*` | Credenciais do banco. Troque a senha. |
| `ANTHROPIC_API_KEY` | Chave da API Claude. |
| `CLAUDE_MODEL` | Modelo (padrão `claude-opus-4-8`). |
| `WA_PHONE_NUMBER` | Número de monitoramento (internacional, só dígitos). |
| `WA_BACKUP_PHONE_NUMBER` | Número de backup (Plano B). |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Canal de alertas e relatórios. |
| `RELATORIO_HORA` / `RELATORIO_MINUTO` | Horário do relatório diário. |
| `ALERTA_URGENCIAS` | Urgências que disparam alerta imediato (padrão `critica,alta`). |
| `VIDEO_FRAME_INTERVAL_SECONDS` | Intervalo de frames de vídeo (custo!). |
| `RETENCAO_MIDIA_DIAS` | Dias até remover o binário de mídia do disco. |

---

## 4. Primeira conexão (pareamento do número)

```bash
docker compose logs -f capture
```

Aparece um **PAIRING CODE** nos logs. No celular do número de monitoramento:
*WhatsApp > Aparelhos conectados > Conectar aparelho > Conectar com número de
telefone* e digite o código. A sessão fica salva em `capture-worker/auth_state/`
(reconecta sozinho depois disso).

---

## 5. Operação do dia a dia

- **Painel:** `http://SEU-SERVIDOR:8000`.
- **Saúde:** página *Saúde* no painel, ou `GET /health` (JSON) — checa Postgres,
  Redis e os heartbeats de captura e pipeline.
- **Logs:** `docker compose logs -f capture` / `pipeline` / `api`.
- **Relatório sob demanda:** `curl -X POST http://localhost:8000/api/relatorio/enviar`
- **Retenção de mídia sob demanda:** `curl -X POST http://localhost:8000/api/manutencao/retencao`
  (também roda automático às 03:30).

### Backup do banco

```bash
docker compose exec postgres pg_dump -U obras obras_monitor > backup_$(date +%F).sql
```

Agende isto no cron do VPS + use os snapshots do provedor.

---

## 6. Escala (1 → N grupos)

Não exige reengenharia: basta adicionar o número de monitoramento a mais grupos
(ver `MANUAL_CLIENTE.md` §3). A captura processa todos os grupos ativos.
Acompanhe o uso de CPU/RAM e o tamanho do disco (`media/`) ao crescer; ajuste
`RETENCAO_MIDIA_DIAS` e o tier do VPS conforme o volume real.

---

## 7. Plano B — número bloqueado/desconectado

Quando o número de monitoramento cai, chega um alerta no Telegram. Recuperação:

1. Confirme no painel *Saúde* que a captura está fora.
2. Ajuste `WA_PHONE_NUMBER` para o número de backup (`WA_BACKUP_PHONE_NUMBER`).
3. Limpe a sessão antiga e reconecte:
   ```bash
   rm -rf capture-worker/auth_state/*
   docker compose restart capture
   docker compose logs -f capture   # novo PAIRING CODE para o número de backup
   ```
4. Adicione o número de backup aos grupos no WhatsApp.

Os dados capturados continuam íntegros no banco — nada se perde na troca.

---

## 8. Atualização do sistema

```bash
git pull
docker compose up -d --build
```

Novas migrations em `db/migrations` rodam apenas no initdb do Postgres; para
aplicar uma migration nova a um banco já existente, execute o arquivo `.sql`
manualmente via `docker compose exec postgres psql -U obras -d obras_monitor -f ...`
(ou use uma ferramenta de migração ao evoluir o projeto).
