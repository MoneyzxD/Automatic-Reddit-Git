# Backlog operacional

Ordem definida pelo operador em 2026-10-04.

## 1. Concluir a implantação da confiabilidade — em andamento

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

## 2. Investigar por que o pipeline de produção está falhando — pendente

Executar depois dos ajustes de confiabilidade, antes dos agentes de manutenção
e crescimento. Preservar logs/artifacts recentes enquanto estiverem disponíveis.
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
