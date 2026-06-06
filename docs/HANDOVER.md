# Entrega e handover

Documento de transferência do sistema para o cliente (Monreal).

---

## 1. Propriedade

Todo o código-fonte e a documentação são de **propriedade da Monreal**. O cliente
pode levar o projeto para outro desenvolvedor manter no futuro, sem dependência
exclusiva do desenvolvedor original.

---

## 2. O que está sendo entregue

- **Repositório Git** completo (este projeto), com histórico de commits por etapa.
- **Documentação:**
  - `README.md` — visão geral e como rodar.
  - `docs/ARQUITETURA.md` — arquitetura técnica e decisões.
  - `docs/MANUAL_CLIENTE.md` — uso do painel, adicionar grupos, trocar membros.
  - `docs/DEPLOY.md` — instalação no VPS, configuração, operação, Plano B.
  - `docs/HANDOVER.md` — este documento.
- **Código organizado e comentado** (RNF-04), em português, para manutenção por
  qualquer desenvolvedor.

---

## 3. Componentes do sistema

| Componente | Tecnologia | Pasta |
|------------|------------|-------|
| Captura | Node.js + Baileys | `capture-worker/` |
| Processamento/IA | Python (faster-whisper, ffmpeg, Claude) | `pipeline/` |
| API / Painel / Relatórios | FastAPI + APScheduler | `api/` |
| Banco de dados | PostgreSQL | `db/migrations/` |
| Fila/buffer | Redis | (contêiner) |
| Orquestração | Docker Compose | `docker-compose.yml` |

---

## 4. Credenciais a transferir (checklist)

Entregar ao cliente, de forma segura (nunca no Git):

- [ ] Acesso ao VPS (SSH).
- [ ] `.env` de produção (senhas, `ANTHROPIC_API_KEY`, tokens do Telegram).
- [ ] Acesso à conta da API Claude (Anthropic) — billing no nome do cliente.
- [ ] Números de WhatsApp: monitoramento + backup.
- [ ] Bot do Telegram (token) e canal/chat de destino.
- [ ] Acesso ao repositório Git.

---

## 5. Custos mensais recorrentes (fora do desenvolvimento)

- **VPS:** ~US$ 10–30/mês conforme escala.
- **API Claude:** variável conforme volume de mensagens/áudio/vídeo.
- **Whisper:** roda no servidor, **sem custo de API**.
- **Licenças:** nenhuma (ferramentas open source).

---

## 6. Suporte pós-entrega

Conforme acordado no Workana. Toda comunicação formal (decisões, aprovações,
entregas, pagamentos) registrada no Workana; WhatsApp apenas para agilidade.

> Itens comerciais a formalizar no Workano (ver `analise_requisitos.txt`):
> prazo final de suporte gratuito (P-06) e o impacto de preço do escopo de
> vídeo (P-04/P-07).

---

## 7. Pendências conhecidas / próximos passos

- **Validação em ambiente real:** as Etapas 1–5 precisam ser validadas com um
  grupo real (DEMOs) usando o número, a chave Claude e o bot do Telegram reais.
- **Definições em aberto (P-01..P-08):** número de grupos/volume, número de
  monitoramento, volume de vídeo e intervalo de frames, prazo de suporte.
- **Evolução futura prevista (não no escopo atual):** busca semântica com
  pgvector; storage de mídia em MinIO/S3 ao escalar; testes automatizados.
