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

Continuação2026-10-06: diagnóstico numérico do HTTP real implementado e revisado;
976 testes locais passaram. Próximo gate é validar a captura e a geração no
Actions, sem upload, mantendo o namespace atual. Não inferir TPM/TPD somente
pelos gráficos. [Status](RELIABILITY_STATUS.md) detalha prova e limites.
Avaliação de substituir Groq pelo Plus concluída: ver
[OPENAI_PLUS_FEASIBILITY](OPENAI_PLUS_FEASIBILITY.md); elegibilidade/capacidade
e runner efêmero não comprovados, nenhuma migração/API paga configurada.

Run37408357221/1947aee4: 959testes18.93s/LT/restore/save passaram; adaptaçãoEN
interrompida por HTTP429/chunk após3tentativas. Sem subtipo/Retry-After ou mídia.
Consulta curta localEN respondeu200/TPM8000; não comprova igualdade com Secret
do Actions ou capacidade para lote. Conferir Usage/Limits da conta EN do runner
antes de novos disparos/remendos. Snapshot verificado, production intacto;
detalhes na seção inicial do status. Agentes ainda aguardam os aceites.

Credencial local resolvida em2026-10-06. Verify37407149313/af2f6f4 passou:
955testes e restore da cópia reconciliada no runnerLinux/11blobs. Preserva84IDs/
7pendentes, sem headproduction/main ou publicação. Sonda curta ES recebeu2fatos
sem429; geração completa e reparosPT ainda não validados. Seção inicial do
status orienta a retomada; tokenlocalausente abaixo é antecedente resolvido.

Retomada atual: run37379031931 terminou failure, sem mídia/upload; PT tradução
aprovada, naturalização rejeitada por evento e ES revisão HTTP429. Consulta
sintética única posterior ainda recebeu429; subtipo/espera desconhecidos.
Revisão completa da branch encontrou três bugs de código, corrigidos com
RED/GREEN: comandos TikTok cruzavam YouTube/ignoravampt; snapshot recusava
filenames editoriais; namespace de teste podia publicar sem flag required.
955 testes locais e revisão pós-delta passaram. Serviços/mídia/bootstrap/main
ainda não aprovados; autoridade de retomada é a primeira seção do status.

Próxima candidata isolada usa Qwen3.8 fixo no guardião, mantendo contratos,
gates e chaves. 896 testes e revisão independente passaram; sonda longa pelo
código real teve três avisos gramaticais, sem falha JSON registrada. Isso não
comprova geração completa. Aguardar recuperação Actions antes de nova validação
PT/EN/ES sem upload, retomando o namespace atual. Detalhes/limites no status.

Run atual37370371919/b030bd6 retoma checkpoint de validação, sem publicação.
Terminou failure antes de qualquer etapa: runner hosted não adquirido. Actions
em major_outage; acompanhar recuperação antes de nova rodada. Sonda alternativa
de envelope não comprovou estabilidade no contexto longo e não foi integrada.
Diagnóstico adicional e limites estão na seção inicial do status.

Run37363161214 falhou antes dos gates derivados: adaptação aprovada, tradução
PT com três HTTP400/json_validate_failed e geração vazia. Sem mídia/upload.
Prova sintética curta real passou; wire SDK comprova schema estrito correto.
Comparação longa sanitizada autorizada explicitamente e executada: 20B e 120B
retornaram JSON parseável e rejeição factual, sem reproduzir HTTP400. Somente
status/contagens retidos, sem prova de defeito factual no original ou vantagem
do 120B. Próximo diagnóstico é conferir o achado concreto contra a fonte;
consultar status/ledger antes de nova ação. Não está restaurado operacionalmente.

Fonte narrativa separada do JSON do ledger após evidência de contaminação
das citações. Falso positivo temporal ES comprovado; PT é imprecisão, não
contradição demonstrada. Subtipo de referência inválida agora é diagnosticado
sem IDs/valores. 888 testes e revisão passaram; próximo gate é nova validação
isolada dos três idiomas, sem upload. Prepared antigo bloqueia por hash e exige
reconciliação, não limpeza automática. Run main37349810900 falhou na adaptação
EN com diagnóstico antigo genérico; evidência privada preservada. Consulte a
seção inicial do status para limites; ainda não há aceite operacional.

Correção de emissão/cadência autorizada enviada em `5aea94b` à branch isolada.
873 testes locais e revisão independente passaram; run `37338112115` aprovou
tradução/naturalização PT, sem HTTP429 registrado. Título falhou por `reason`
ausente em três tentativas; nenhuma mídia/upload. `3d65d84` corrige feedback
que não informava os campos ausentes, sem preencher valores ou relaxar schema.
879 testes locais/revisão passaram; run `37341313520` passou 879 testes/18.09s,
LT e restore/save, mas terminou failure/34m20s sem mídia/upload. Recusas JSON
recuperadas, nenhum HTTP429 registrado. PT/título e ES/metadados parte2 tiveram
rejeições factuais; EN/título terminou invalid_source_reference/3, HTTP ausente.
O subtipo não foi capturado. Antes de nova rodada: conferir candidatos contra
fonte/script aprovado e diagnosticar referência inválida de modo sanitizado,
mantendo evidência/gates. Isso não prova defeito no código nem mesma causa
dos incidentes antigos. Limites e evidência atual estão na seção inicial de
[RELIABILITY_STATUS](RELIABILITY_STATUS.md). Agentes/main/bootstrap aguardam
aceite completo; a cronologia abaixo não autoriza repetir correções antigas.

Diagnóstico estrutural autorizado implementado em `6930e5f`, só na branch
isolada: 856 testes passaram e revisão independente aprovou. Run `37331951705`
falhou por HTTP429/TPM, não comprovou o campo recusado e não gerou mídia/upload.
Registro adicional conserva recusas intermediárias mesmo após sucesso/cota;
859 testes e revisão independente passaram. Run `37333981612` comprovou o
diagnóstico real: cinco achados sem `reason`/`start`, HTTP400 preservado antes
de HTTP429/TPM. Nenhuma mídia/upload. Diagnóstico concluído; próximos passos são
alinhar emissão ao contrato e tratar TPM sem rotação ou relaxamento dos gates.
Evidência e limites em [RELIABILITY_STATUS](RELIABILITY_STATUS.md).

Atualização2026-10-05: operador confirmou nenhuma postagem manual; ownerAPI
reconfirmou81/84IDs e0títulos dos7incertos. Candidato reconciliado e restaurado
localmente:30histórias/91partes/84IDs/7pendentes/91kits e56capas encerrados só
na cópia, sem mudar originais ou estado remoto. 89 testes state/snapshot passaram.
Bootstrap ainda depende do aceite completo e tokenfine local (solicitado; não
usar gh amplo). Run 37320307156 passou testes/LT/estado, mas falhou global EN
por nonliteral_evidence/3, não HTTP429. Correção estreita do retry sem feedback
enviada em a3b7f3a, gates preservados; 812 testes locais e revisão passaram.
Run 37322711750 terminou verde mas sem vídeo: repetição estilística do LT foi
tratada como gramática crítica e entrou em ciclo de correções. 12a48bf corrige
classificação/avisos sem alterações mecânicas de estilo; 823 testes e revisão
passaram. Run 37324808064 aprovou adaptação EN, mas PT/tradução falhou por
HTTP400 json_validate_failed/1, sem mídia. 484a912 permite apenas esse retry
tipificado no orçamento existente; 832 testes/revisão passaram. Run 37326768456
passou 832 testes/17.14s, LT e restore/save, mas voltou a falhar PT/tradução:
repairing1, unavailable2, chunk HTTP400/json_validate_failed/3 tentativas,
JSON sintaticamente válido/693 caracteres. Sem mídia/upload; campo incompatível
desconhecido. Retry limitado não resolveu a recusa. Próximo passo: discussão do
contrato e diagnóstico estrutural sanitizado, antes de outro remendo/dispatch.
Importação/main/agentes seguem posteriores ao aceite real. Os parágrafos abaixo
registram antecedentes.

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

## Pendências legadas TikTok — antes de reabilitar o kit

TikTok continua desabilitado. Revisão confirmou problemas distintos que não
causam a falha atual de geração YouTube: `/status` rotula resumo/contadores
YouTube como TikTok; `/fail` promete reenvio mas grava failed, fora da seleção
pending; notify_job consulta fila YouTube, não `get_pending_tiktok`; comandos
para ID ausente confirmam uma alteração inexistente. Corrigir com filas
isoladas antes de reabilitar, sem tocar IDs/agendamentos YouTube. Esta anotação
não habilita TikTok, não descarta kits nem altera política de publicação.
