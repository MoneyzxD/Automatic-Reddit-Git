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
Fontes completas desses incidentes não estavam no artifact sanitizado. Elas
foram recuperadas do Reddit e seus hashes coincidiram com os perfis dos
incidentes; cópias privadas estão no workspace de investigação. Isso não
recupera o HTTP antigo nem autoriza reset de dedupe/replay de produção.

Validação nova 37237857551, branch 12dd591: LanguageTool/testes/restore passaram;
geração falhou por HTTP400 json_validate_failed, facts, tentativa 2. Separada
do HTTP429 do run anterior. Probe único posterior com chave fixa EN retornou
JSON válido, 23 fatos e uma citação não literal. A coleta/revisão semântica
ainda não é operacionalmente confiável: discutir o contrato/modelo antes de
novo remendo de prompt ou enfraquecimento do gate. Main não liberado.

Reprodução factual com fontes verificadas: 1wf0he0 passou em três chamadas;
1wfduc8 falhou por nonliteral_evidence após três. Comparação com GPT-OSS120B
na mesma chave EN também rejeitou evidência não literal na primeira chamada.
Trocar apenas o modelo não resolveu. O operador aprovou referências de trechos:
a coleta agora recebe unidades lossless, retorna IDs válidos/contíguos e o
código copia a citação literal da fonte. O contrato público e os gates são
preservados. Revisão independente aprovou o ajuste; probe real da história
sintética confirmou dez fatos literais em duas chamadas. Isso não comprova
roteiro/mídia completos. Após autorização de continuação, probe da fonte
preservada 1wfduc8 passou: 13 fatos literais em uma chamada. Não é aceite de vídeo.

Falha de estado demonstrada separadamente: run37063586921 falhou nos testes
antes do restore e salvou DB cache mesmo assim. Run37064703594 restaurou esse
DB e fila de outro run. Capturas privadas comprovaram a perda de 28 histórias
e 91 partes no DB recente. A cópia anterior conserva 30 histórias/91 partes,
com filas byte-identical às atuais. Veja [status](RELIABILITY_STATUS.md) para
pendências de reconciliação; nenhum candidato foi importado.

## 2. Validar geração, reconciliar e liberar confiabilidade — em andamento

Última validação, commit dc87c02/run37241728126: coleta factual avançou,
adaptação entrou em repairing e a revisão global parou por HTTP429/cota.
Nenhum vídeo/upload; checkpoint salvo. Verify37242044138 passou em outro runner,
786 testes/17.33s, sete arquivos de controle e mídia zero, sem Groq.
Suíte local786 passou; não repetir geração para burlar cota nem trocar chave.
Rascunho de reconciliação privado preserva84IDs,91itens/7incertos e originais;
nenhuma decisão aplicada ou bootstrap production. Autorizações específicas
de ausência manual dos sete sem ID continuam pendentes; agentes ainda posteriores.
Operador autorizou encerrar 91 kits TikTok e 56 tentativas antigas de capa.
Suporte aditivo de cancelamento de capa failed/missing implementado e revisado,
sem alterar IDs/erros; ainda não aplicado ao estado de produção. Run37243243200
parou antes da coleta factual por HTTP429. Diagnóstico seguro adicional está
em validação para distinguir cota diária/minuto, sem trocar chave ou fallback.
Run37244100764/ec15619 confirmou TPD, Retry-After430s, facts429/1tentativa.
Testes/LT/restore/save passaram; sem mídia. Respeitar intervalo antes de nova
validação. Novas propostas privadas preservam inventário e bloqueiam sete
sem confirmação manual. Watch visual parcial dos vídeos legados não valida
roteiro/voz da branch nova nem autoriza publicação.
Verify37244536054 passou:809tests19.15s/7arquivoscontrole/mídia0. Mesmo após
respeitar Retry-After, run37244757274 parou em facts por TPD/espera647s;
sem mídia/upload, save preservado. Não fazer novas chamadas enquanto a cota
permanecer indisponível. Propostasv2 conservam datas históricas com fuso.

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
