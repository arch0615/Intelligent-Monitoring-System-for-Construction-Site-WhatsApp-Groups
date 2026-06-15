# Guia de testes

Como validar o sistema em camadas, do mais barato/rápido para o mais completo.
A ideia é **desacoplar**: testar a IA e o painel sem depender do WhatsApp (que
é a parte mais lenta de preparar). Deixe o pareamento do número para o fim.

```
Nível 1  IA (Claude)        -> não precisa de WhatsApp nem VPS  (roda HOJE)
Nível 2  Banco + Painel     -> precisa do Postgres no ar
Nível 3  Pipeline ponta a ponta -> Postgres + Redis
Nível 4  Captura real (E2E) -> número pareado + grupo de teste
```

---

## Nível 1 — A IA está classificando? (roda agora, só precisa da chave)

Prova que a chave da API funciona e que a Claude separa pendência/dúvida/
decisão + urgência, sem subir nada.

```bash
# instale só o necessário (leve — sem Whisper/ffmpeg)
pip install anthropic python-dotenv

# carregue a chave do .env e rode o teste
set -a; source whatsapp-obras-monitor/.env; set +a
python3 whatsapp-obras-monitor/scripts/testar_classificacao.py
```

Esperado: para cada frase de exemplo, o script imprime os itens classificados.
Frases neutras ("bom dia") devem retornar lista vazia.

---

## Nível 2 — Painel, relatório e histórico (com dados de exemplo)

Sobe só o banco, popula com dados realistas e abre a API/painel — sem WhatsApp.

```bash
cd whatsapp-obras-monitor
docker compose up -d postgres          # sobe só o Postgres (migrations rodam)
set -a; source .env; set +a
python3 scripts/semear_demo.py         # insere grupo + mensagens + análises

docker compose up -d api               # sobe a API/painel
```

Depois, no navegador:
- http://localhost:8000/         -> relatório do dia (deve mostrar os exemplos)
- http://localhost:8000/historico?q=cimento  -> busca de histórico
- http://localhost:8000/grupos    -> ativar/desativar
- http://localhost:8000/saude     -> saúde (Postgres OK; captura/pipeline
                                     aparecem "fora" porque não foram subidos)
- http://localhost:8000/health    -> JSON do health check

---

## Nível 3 — Pipeline ponta a ponta (sem WhatsApp)

Sobe tudo, menos a captura, e injeta um evento na fila para o pipeline
processar (classifica + grava + alerta, se configurado).

```bash
cd whatsapp-obras-monitor
docker compose up -d postgres redis api pipeline
# injeta uma mensagem de teste e publica no Redis (o pipeline consome):
python3 scripts/injetar_mensagem.py "Falta cimento no 3º andar, parou o serviço"

docker compose logs -f pipeline    # acompanhe a classificação acontecendo
```

Confira no painel (http://localhost:8000) que a mensagem virou item analisado.
Se o Telegram estiver configurado e o item for urgente, deve chegar um alerta.

---

## Nível 4 — Captura real (end-to-end com grupo de WhatsApp)

Último nível, com o número dedicado. Ideal: um **grupo de teste** seu antes do
grupo real da obra.

```bash
cd whatsapp-obras-monitor
docker compose up -d --build           # sobe tudo, incluindo a captura
docker compose logs -f capture         # leia o PAIRING CODE e pareie o número
```

1. Pareie o número principal (ver README/DEPLOY).
2. Adicione o número a um grupo de teste.
3. Mande no grupo: um texto, um áudio, uma foto, um PDF e um vídeo curto.
4. Verifique:
   - `docker compose logs -f capture`   -> "Mensagem capturada"
   - `docker compose logs -f pipeline`  -> transcrição/classificação
   - http://localhost:8000/             -> itens no relatório do dia
   - alerta no Telegram para algo urgente

---

## Checklist rápido do que cada nível prova

| Nível | Prova que... |
|------|--------------|
| 1 | A chave da API funciona e a classificação está correta |
| 2 | Banco, relatório, histórico e painel funcionam |
| 3 | A fila + pipeline processam e gravam ponta a ponta |
| 4 | A captura real do WhatsApp funciona (texto, áudio, foto, doc, vídeo) |

> Dica: rode os níveis 1 e 2 antes da DEMO com o cliente. Assim você já chega
> na demonstração com a IA e o painel comprovadamente funcionando, e o único
> "ao vivo" é a captura do grupo real.
