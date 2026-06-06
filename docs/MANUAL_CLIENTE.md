# Manual do cliente — Monitoramento de Grupos de Obras

Guia simples de uso e operação do sistema, em linguagem não técnica. Para
detalhes de instalação/servidor, ver `DEPLOY.md`; para a entrega/propriedade,
ver `HANDOVER.md`.

---

## 1. O que o sistema faz

O sistema acompanha sozinho os grupos de WhatsApp das obras e transforma a
conversa em informação organizada para a gestão:

- **Captura tudo** o que circula nos grupos (texto, áudio, foto, documento, vídeo).
- **Identifica o que importa** com IA: pendências, dúvidas e decisões.
- **Entrega de três formas:**
  - **Relatório diário** com tudo do dia, separado por categoria.
  - **Consulta de histórico** para responder dúvidas recorrentes.
  - **Alertas imediatos** quando algo crítico/urgente aparece.

A equipe de campo **não muda nada** na forma de usar o WhatsApp. A única
observação é que o número de monitoramento aparece como mais um participante
do grupo.

---

## 2. O painel

Acesse o painel pelo navegador no endereço informado na entrega (ex.:
`http://SEU-SERVIDOR:8000`). Menu:

| Página | Para quê |
|--------|----------|
| **Relatório do dia** | Ver pendências, dúvidas e decisões do dia. Dá para escolher a data e o grupo. |
| **Histórico** | Buscar no que já foi dito (ex.: "medição", "cimento 3º andar"). |
| **Grupos** | Ativar/desativar o monitoramento de cada grupo. |
| **Saúde** | Ver se o sistema está funcionando (captura, processamento, banco). |

---

## 3. Como adicionar um novo grupo ao monitoramento

1. Abra o grupo de WhatsApp da obra no celular.
2. Adicione o **número de monitoramento** como participante (como faria com
   qualquer pessoa da equipe).
3. Pronto. Assim que a primeira mensagem circular, o grupo aparece na página
   **Grupos** do painel, já ativo.

Para **parar** de monitorar um grupo, vá em **Grupos** e clique em *Desativar*
(ou remova o número de monitoramento do grupo no WhatsApp).

> Não é preciso mexer em código nem chamar o desenvolvedor para adicionar grupos.

---

## 4. Como trocar membros / quem recebe alertas e relatórios

- **Quem aparece nos grupos:** é a equipe da obra, gerida normalmente no
  próprio WhatsApp. O sistema só lê.
- **Quem recebe os alertas e o relatório diário:** é um canal do **Telegram**
  configurado na entrega. Para mudar o destinatário, ajusta-se a configuração
  do Telegram (ver `DEPLOY.md` → variáveis `TELEGRAM_*`). Peça ao responsável
  técnico se precisar trocar.

---

## 5. Relatório diário e alertas

- O **relatório diário** é enviado automaticamente todo dia no horário
  configurado (padrão 18:00) pelo Telegram, e também fica disponível no painel.
- Os **alertas** são enviados na hora quando a IA detecta algo **crítico ou
  urgente**, sem esperar o fim do dia.

---

## 6. Se o número de monitoramento cair (Plano B)

Pode acontecer de o WhatsApp bloquear/desconectar o número (não há como garantir
100% — qualquer fornecedor honesto dirá o mesmo). O sistema mitiga e tem plano:

- **Você recebe um aviso imediato** no Telegram informando a desconexão.
- **Nenhum dado é perdido** — tudo que já foi capturado fica salvo no banco.
- A recuperação é: adicionar o **número de backup** aos grupos e reconectar.
  O responsável técnico faz isso rapidamente (ver `DEPLOY.md` → Plano B).

---

## 7. Privacidade (LGPD)

O sistema captura todo o conteúdo dos grupos. Recomenda-se alinhar com a equipe
que a comunicação dos grupos é monitorada para fins de gestão da obra, e definir
por quanto tempo os dados/mídias ficam guardados (a mídia pesada é descartada
automaticamente após o prazo de retenção configurado; o texto e as análises
permanecem).
