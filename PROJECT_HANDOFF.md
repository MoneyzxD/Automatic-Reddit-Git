# PROJECT_HANDOFF.md

## Estado integrado

Esta atualização substitui o handoff reconstruído de memória do Claude Code.
Arquitetura e convenções ficam em `AGENTS.md`; execução e instalação ficam em
`README.md`. O código é a autoridade de comportamento, e `KNOWN_ISSUES.md`
preserva limitações e decisões anteriores.

O perfil único de narrador e os gates de roteiro estão integrados. A etapa 3.5
resolve fonte/título completos e trava o perfil para PT, EN, ES e todas as
partes. `source_gender` pode continuar desconhecido; `narration_gender` é
binário, escolhido por evidência positiva ou hash estável, sem estereótipos.
Naturalização, metadados e TTS usam esse perfil, sem redetecção por idioma.

O guardião revisa texto e fatos com patches verificáveis; corrigir o narrador
não autoriza trocar o gênero de outros personagens. A versão de maior nota
não contorna reprovação. Falhas de conteúdo geram quarentena sanitizada e
pulam história/idioma; indisponibilidade obrigatória interrompe o lote com
código 2. Há gate final por parte antes da voz, e exportação/enfileiramento
esperam concluir todas as partes do idioma. gTTS sem controle de gênero está
bloqueado por padrão.

LanguageTool 6.6/Temurin 17, cache com SHA verificado e saúde dos três locales
fazem parte do workflow. O manifesto `config/languagetool_runtime.env` é a
autoridade de URL/versão/hash. Produção continua no GitHub Actions. O instalador
Oracle/Linux é suportado, mas sua execução em host real não foi realizada nesta
etapa. Veja os comandos e distribuições suportadas no README.

## Decisões preservadas

- Stack integralmente gratuita; sem rotação de contas/chaves Groq para burlar
  rate limit. Cada idioma mantém sua chave fixa, com fallback à genérica.
- Sessão logada Reddit via cookie e renovação manual; não retomar registro
  OAuth sem pedido do operador.
- OAuth YouTube em Testing, renovado manualmente a cada sete dias com alertas.
- Cron 09:00 UTC, meta inicial de três vídeos por idioma e uma parte excedente
  possível para o dia seguinte; progressão da meta depende de decisão manual.
- TikTok com kit Telegram e postagem manual, condicionado à aprovação externa
  para uma eventual API automática.
- Normalização de idioma no ponto de entrada; correções cirúrgicas sustentadas
  pela fonte, em vez de reescrita global ou promoção automática de regras.

## Retomada

Use `data/logs/script_quality.jsonl` e os JSONs de quarentena para investigar
reprovações, sem expor segredos. O artifact `logs-<run_id>` os preserva por
14 dias. Propostas de glossário exigem teste e revisão humana antes de entrar
em `config/contextual_glossary.yaml`.

Revisão independente de toda a branch, fast-forward/push e verificação do
runner real são passos de release posteriores à documentação/regressão local.
Não interpretar teste unitário verde como execução do LanguageTool real nem
como publicação bem-sucedida. O erro 413 legado continua sem confirmação
operacional específica (ver `KNOWN_ISSUES.md`); análise de TPM usa telemetria
existente antes de justificar outro provedor ou mudança de orçamento.
