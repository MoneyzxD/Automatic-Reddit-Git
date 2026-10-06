# OpenAI pelo Plus — avaliação de viabilidade

Avaliado em 2026-10-06. Não é integração implementada nem liberação de produção.

## Conclusão

Viável condicionalmente para uma prova com **Sign in with ChatGPT (SIWC)**,
especialmente em VM própria. Ainda não comprovado como substituto da Groq no
GitHub Actions. A API tradicional com chave continua tendo cobrança separada;
a seleção de modelo desta conversa não altera a configuração do pipeline.
[Cobrança oficial](https://learn.chatgpt.com/docs/pricing).

## Fatos documentados

- Plus elegível pode autorizar apps de código aberto a usar a franquia do plano
  via OAuth. Elegibilidade do app/conta precisa ser confirmada; repo público
  não equivale automaticamente a enquadramento OSS. Nenhuma licença foi alterada.
  [Quickstart](https://developers.openai.com/siwc/quickstart).
- VM própria tem procedimento oficial: OAuth local, transferência protegida,
  host ID persistente e renovação pela VM. Não encontramos orientação específica
  de SIWC para runner efêmero do Actions; não afirmar que é permitido ou proibido.
  [VM](https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms),
  [cliente e host](https://developers.openai.com/siwc/token-sharing-open-source).
- A rota usa Responses com `store=false`, `stream=true` e contexto em `input`.
  Exige adaptar `system`/`temperature` e tratar conclusão, falha, resposta
  incompleta e stream interrompido. `max_output_tokens` não é suportado nessa
  rota; JSON/schema estrito e o modelo disponível precisam de prova real.
  Só `response.completed` permite sucesso, inclusive após receber deltas.
  [Limitações](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations),
  [inferência](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference).
- Apps compartilham a franquia existente de Codex/ChatGPT Work. O teto por app
  não reserva cota nem cria uma nova. Não há orçamento comprovado para nove
  vídeos/dia neste pipeline; contar mensagens não resolve essa estimativa.
  [Uso compartilhado](https://learn.chatgpt.com/docs/sign-in-with-chatgpt).

## Próxima prova e limites

Antes de integrar: consentimento OAuth próprio do app, catálogo real da conta,
credenciais protegidas e renovação durável/serializada no ambiente escolhido.
Não reutilizar a sessão da extensão Codex nem endpoints internos do ChatGPT.
Para custo adicional zero, manter créditos externos desativados, sem API paga
de fallback e parar ao atingir a franquia.

A menor prova útil é sintética: coleta factual e revisão PT/EN/ES com os schemas
atuais; medir conclusão, formato, duração e consumo, sem fonte Reddit privada,
mídia, fila ou upload. Depois seriam necessários roteiro completo, gates atuais,
renovação/restart e capacidade para o lote no host real. A avaliação não autoriza
enviar histórias/credenciais à OpenAI nem antecipar migração Oracle.

O diagnóstico Groq e os gates operacionais do [backlog](BACKLOG.md) continuam
primeiro. Esta avaliação não mudou provedor, modelo, chave ou cron.
