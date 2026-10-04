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

## Confiabilidade em implementação — 2026-10-03

Worktree isolada: `_export_repo_publico/.worktrees/pipeline-reliability`, branch
`pipeline-reliability`, base `23f7f9c`. Documentos pendentes do checkout main
permanecem intactos; integrar preservando suas edições, sem usar o sync legado.
Tarefas 1–6 registradas em commits locais: classificação/retry, DB aditivo,
retomada por fonte/perfil/idioma, snapshots verificáveis, transporte privado
e confirmação de upload antes dos demais efeitos. Suíte dessa etapa: **703
passed**, 23 warnings. Integração inicial de modos/checkpoints/workflow: **97
passed**, 12 warnings em áreas afetadas. Ambos usam serviços falsos.

`MoneyzxD/Automatic-Reddit-State` foi criado e verificado PRIVATE com a conta
MoneyzxD. Não foram criados tokens nem enviados Secrets, snapshots, vídeos ou
alterações ao main. O fluxo novo ainda não foi exercitado no Actions/Groq real.
[PIPELINE_STATE](docs/PIPELINE_STATE.md) registra pré-requisitos e bloqueios.

Retomar pela tarefa 7 do plano de confiabilidade: terminar revisão/testes,
obter Secret limitado pelo operador, reconciliar/importar estado existente,
validar geração PT/EN/ES sem upload e restaurar no segundo runner. Só depois
liberar main e confirmar uma rodada dentro da meta normal. Agentes de
manutenção/crescimento ficam fora desta entrega. O incidente semântico anterior
continua sem causa operacional comprovada; a classificação nova não é prova
retroativa de cota.
