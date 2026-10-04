# Backlog operacional

Ordem definida pelo operador em 2026-10-04.

## 1. Investigar falhas anteriores — evidência histórica limitada

Logs preservados dos runs 37128480329 e 37209564422: ambos interromperam a
revisão da adaptação EN antes de tradução/mídia/publicação. O primeiro registrou
cinco chamadas semânticas e seis retries SDK; o segundo três chamadas e dois
retries SDK. O HTTP/body original não foi preservado: não é possível atribuir
a mesma causa, nem afirmar cota/OAuth retroativamente. No segundo houve também
timeout do alerta Telegram, posterior ao gate, não causa da falha de geração.
403 de alguns subreddits não impediu selecionar história nos dois runs.
Fontes completas desses incidentes não estão no artifact sanitizado; não
reconstruir texto por substituição de [REDACTED] nem resetar dedupe.

Validação nova 37237857551, branch 12dd591: LanguageTool/testes/restore passaram;
geração falhou por HTTP400 json_validate_failed, facts, tentativa 2. Separada
do HTTP429 do run anterior. Probe único posterior com chave fixa EN retornou
JSON válido, 23 fatos e uma citação não literal. A coleta/revisão semântica
ainda não é operacionalmente confiável: discutir o contrato/modelo antes de
novo remendo de prompt ou enfraquecimento do gate. Main não liberado.

## 2. Validar geração, reconciliar e liberar confiabilidade — em andamento

Plano: `superpowers/plans/2026-10-03-pipeline-reliability.md`. Código revisado
com 763 testes locais passando. Secret `PIPELINE_STATE_TOKEN` cadastrado e
acesso real ao armazenamento privado comprovado. A revisão de roteiro real
ainda está em validação: JSON recusado, categorias/citações e cota Groq são
registrados separadamente, sem inferir a causa das falhas antigas. Próximos gates:
geração isolada no Actions, restauração em outro runner e bootstrap
reconciliado de produção antes de liberar main.
Run 37221057489 terminou por HTTP429 da Groq; escrita/restauração e testes
passaram, mas nenhuma mídia foi gerada. Revalidar geração somente quando
a cota permitir; não usar outra chave para contornar esse bloqueio.
Verify 37221464481 passou em outro runner, sem geração/publicação. Confirma
estado de controle/fonte/perfil restaurado, não mídias que não foram geradas.

### Referências e critério de conclusão

Investigar antes de liberar main, conforme pedido mais recente do operador.
Preservar logs/artifacts recentes enquanto estiverem disponíveis.
Runs de referência:

- 2026-10-04: [37209564422](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/37209564422), failure em main/30a0a0c.
- 2026-10-03: [37128480329](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/37128480329), failure em main/30a0a0c; revisão da adaptação EN de 1wfduc8 indisponível, classe original não preservada.

Identificar etapa e mecanismo com logs sanitizados e diagnóstico real do novo
código. Não concluir 429, token expirado ou erro de conteúdo apenas por retries
ou mensagem genérica. Reproduzir o mecanismo identificado, corrigir o menor
ponto compartilhado e verificar no Actions. Aceite: causa demonstrada e rodada
normal bem-sucedida nos idiomas afetados, com IDs/agendamentos e estado
preservados, sem duplicação de uploads.

## 3. Agentes de manutenção e crescimento — fase posterior

Começar após confiabilidade e diagnóstico operacional. Crescimento segue a
proposta já preparada no checkout de produção; esta lista não autoriza mudança
editorial nem implementação antecipada desses agentes.
