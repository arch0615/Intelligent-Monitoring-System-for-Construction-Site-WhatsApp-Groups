# Arquitetura técnica

Documento de apoio à manutenção (RNF-04). Explica como as peças se conectam e
por que cada escolha foi feita.

## Visão geral

Dois processos principais ligados por uma fronteira limpa (Redis):

1. **capture-worker** (Node.js + Baileys) — conecta ao número dedicado como
   dispositivo vinculado, lê mensagens em tempo real, baixa e descriptografa
   mídia, normaliza e grava no Postgres, e publica um evento no Redis.
2. **pipeline** (Python) — consome o evento, deriva texto (Whisper para áudio,
   ffmpeg+Whisper para vídeo, extração para documentos), classifica com a Claude
   e grava as análises.

## Por que estas escolhas

- **Baileys (multi-device):** biblioteca madura, sem necessidade de Chromium,
  baixo consumo de memória, login por pairing code. Sessão persistida em disco
  (`auth_state/`) permite reconexão automática e troca rápida de número (Plano B).
- **Somente leitura:** o número nunca envia mensagens nem marca presença online,
  reduzindo o risco de bloqueio pelo WhatsApp.
- **Redis Stream (não pub/sub):** entrega confiável com grupo de consumidores e
  ACK. Se o pipeline cair, os eventos não processados são reentregues — sem perda
  de dados (RNF-05).
- **Postgres como fonte da verdade:** o stream carrega só o `mensagem_id`; o
  conteúdo é lido do banco. Mantém o stream leve e evita duplicar dados.
- **Whisper local (faster-whisper, int8):** transcrição sem custo de API.
- **Claude com saída estruturada:** `output_config.format` garante JSON válido
  para gravar direto nas tabelas, sem parsing frágil.

## Fluxo de dados (uma mensagem)

```
messages.upsert (Baileys)
  └─ determinarTipo + extrairTexto
  └─ baixarMidia -> MEDIA_DIR (se houver)
  └─ salvarMensagem (transação, dedup por grupo+wa_message_id)
  └─ publicarEvento(mensagem_id) -> Redis Stream
        │
        ▼ (pipeline)
  consumir() -> processar(mensagem_id)
     ├─ carregar_mensagem (texto + mídias)
     ├─ derivar texto:
     │    audio     -> transcrever
     │    video     -> extrair_audio->transcrever + extrair_frames
     │    documento -> extrair_texto
     │    imagem    -> (imagem vai para a análise visual)
     ├─ classificar(texto, imagens) -> [itens]
     ├─ gravar_analises
     ├─ marcar_status('processada')
     └─ confirmar(evento_id)  # ACK
```

## Modelo de dados

| Tabela | Papel |
|--------|-------|
| `grupos` | grupos monitorados; `is_active` controla captura (RF-08) |
| `remetentes` | participantes (autoria das mensagens) |
| `mensagens` | uma linha por mensagem; `busca` (tsvector) para histórico (RF-04) |
| `midias` | metadados dos arquivos; binário fica no filesystem |
| `analises` | itens classificados pela Claude (0..N por mensagem) |
| `alertas` | registro do que já foi notificado (RF-05) |

`status` em `mensagens` (`capturada → processando → processada/erro`) torna o
pipeline idempotente e auditável.

## Pontos de atenção para manutenção

- **Custo de vídeo (RF-06):** frames analisados pela Claude escalam custo. O
  intervalo é configurável (`VIDEO_FRAME_INTERVAL_SECONDS`). Confirmar volume
  (P-04) antes de habilitar em escala.
- **Prompt caching:** ativa de fato só quando o system prompt atinge o mínimo do
  modelo (~4096 tokens no Opus). Para volumes altos, engrossar com few-shot.
- **Retenção de mídia (Etapa 5):** prever política de arquivamento para não
  encher o disco do VPS.
- **LGPD (R-07):** todo o conteúdo dos grupos é capturado. Prever consentimento
  e política de retenção/eliminação na documentação ao cliente.
- **Dependência de biblioteca não-oficial (Baileys):** fixar versão estável;
  mudanças da plataforma WhatsApp podem exigir atualização.
