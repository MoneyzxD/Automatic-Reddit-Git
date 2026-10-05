# PROJECT_HANDOFF.md

## Continuação atual — 2026-10-05

Diagnóstico estrutural aprovado pelo operador e enviado em `6930e5f`, só na
branch isolada. Suíte 856 passed/30 warnings/50.11s, 200 testes do guardião,
compilação/diff check e revisão independente passaram. Registra campos/tipos/
regras sem valores ou chaves desconhecidas; não altera schema, prompt ou gates.
Run `37331951705` passou testes/LT/estado, mas falhou PT/tradução por HTTP429/TPM,
três tentativas/Retry-After21s. Nenhuma mídia/upload; campo da recusa anterior ainda
desconhecido. Diagnóstico também passa a reter recusas JSON intermediárias, antes
sobrescritas por sucesso/cota; 859 testes e revisão independente passaram.
Retomar pelo resultado em [RELIABILITY_STATUS](docs/RELIABILITY_STATUS.md);
não repetir correções anteriores nem inferir qual campo falhou sem captura.

Operador confirmou nenhuma postagem manual. OwnerAPIread-only conferiu81/84IDs
e0títulos dos7incertos. Relatório privado reconciliado aplicado sóemstaging;
snapshot e restauração local passaram:30histórias/91partes/84IDs mantidos,
7pendentes,91kits/56capas encerrados na cópia. Original intocado, sem head remoto.
89testes state/snapshot passaram. Run 37320307156 falhou global EN por evidência
não literal/3, não cota. Código a3b7f3a corrige retry sem feedback, mantendo gate;
812 testes locais e revisão independente passaram. Run 37322711750 terminou
verde, mas sem vídeo: estilo LT tratado como gramática crítica gerou ciclo.
12a48bf corrige classificação/sugestões mecânicas; 823 testes locais e revisão
passaram. Run 37324808064 aprovou adaptação EN e falhou PT/tradução por HTTP400
json_validate_failed/1, sem mídia. 484a912 permite somente esse retry no orçamento
atual; 832 testes/revisão passaram. Run 37326768456 passou 832 testes/17.14s,
LT e restore/save, mas falhou PT/tradução por HTTP400/json_validate_failed
após três tentativas. JSON válido/693 caracteres, campo incompatível desconhecido;
sem mídia/upload. Retry limitado não resolveu a recusa. Antes de outro remendo
ou geração, discutir contrato/diagnóstico estrutural sanitizado; gates intactos.
tokenfine de estado disponível no Actions, não no.env local. Configuração
solicitada; nenhum gh amplo usado. Continuar pelo status/ledger, não reiniciarT1–6.

## Retomada prioritária — 2026-10-04 à noite

Leia [RELIABILITY_STATUS](docs/RELIABILITY_STATUS.md) antes de continuar T7.
Investigação revelou perda do histórico DB por cache salvo após teste falho
antes de restore; candidatos antigo/atual preservados privados, sem bootstrap.
Há84IDs conservados, sete itens sem ID e mídia legada recuperada. O contrato
de evidência aprovado usa IDs lossless e copia citações pelo código; probe da
fonte preservada1wfduc8 passou13fatos/1chamada. FullPTENES ainda interrompido
por429; diagnóstico sanitizado confirmou TPD no run37244100764. Após respeitar
430s, run37244757274 voltou a falhar por TPD, espera647s. Não repetir chamadas
sob cota nem confundir Retry-After com garantia de rodada completa.
Suíte fresh809pass não é vídeo real aprovado. Encerrar91kits/56capas autorizado,
propostas privadas preparadas; sete possíveis uploads manuais seguem bloqueados.
Não repetir remendos de prompt/modelo, trocar chave nem liberar main sem gates.
Verify37244536054 passou em outro runner:809testes19.15s/7arquivos/mídiazero.
Não houve bootstrap production, rodada normal, upload ou implementação de agentes.

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

### Revisão e retomada — 2026-10-04

A revisão independente da porção de código foi concluída. Seus quatro
achados importantes foram reproduzidos antes de corrigir: WAL residual no
restore, fila legada ausente tratada como vazia, paths equivalentes no Windows
e continuação de upload após resultado incerto. Regressões e suíte completa
passaram: **745 testes**, 29 avisos de depreciação, 90.80s; `compileall` e
`git diff --check` passaram. Isso é evidência local, não execução de serviços.

A variable `PIPELINE_STATE_REPO` já aponta ao repositório privado; consulta
apenas de nomes dos Secrets em 2026-10-04 confirmou `PIPELINE_STATE_TOKEN`
ausente. O operador precisa criar a credencial limitada e cadastrá-la no
repositório de produção, sem enviar o valor no chat. Depois vêm importação
reconciliada, geração real isolada e restore no segundo runner; só então
liberação. Main, cron, tokens YouTube e meta diária não foram alterados.

O registro local para continuar sem repetir tarefas fica em
`.superpowers/sdd/2026-10-03-pipeline-reliability/progress.md`, na worktree
acima; revisão e prova da suíte ficam no mesmo diretório. Tarefas 1–6 estão
completas; a tarefa 7 continua pendente dos gates operacionais. Esse diretório
de retomada permanece preservado enquanto a implantação não terminar.

O operador cadastrou `PIPELINE_STATE_TOKEN`; consulta de nomes confirmou sua
existência em 2026-10-04 às 16:20:22 UTC, sem ler o valor. Autorizou enviar a
branch e iniciar validação isolada no Actions. A permissão efetiva da credencial
e a persistência remota serão verificadas nessa execução. A investigação das
falhas atuais de produção foi priorizada para depois destes ajustes em
[BACKLOG](docs/BACKLOG.md), com os runs de referência e critério de aceite.

O primeiro run isolado, [37216781914](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/37216781914),
aqueceu LanguageTool e passou 745 testes, mas o bootstrap bloqueou por DB
presente. O teste de CLI em subprocesso executava dry-run e criava/migrava o
SQLite da raiz de código. Dois testes reproduziram esse efeito; o dry-run
agora usa filtro/organizer sem DB, sem apagar estado para contornar o bloqueio.
Geração e publicação não chegaram a executar nesse run. A validação seguinte
precisa comprovar também escrita/restauração privada e geração real.

A segunda validação, [37217438115](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/37217438115),
passou 747 testes, bootstrap/restauração privada e checkpoint final, comprovando
o acesso real do Secret ao armazenamento. A geração parou antes de mídia:
`invalid_json`, HTTP 400, `json_validate_failed`, modo facts, 4002 caracteres,
uma tentativa, revisão da adaptação EN de `test_male_001`. Publicação foi pulada.
O adaptador do guardião foi ajustado para JSON schema estrito nos modelos
GPT-OSS já usados; parser e gates de fidelidade/gênero continuam obrigatórios.
Regressões locais não substituem a próxima chamada real do Groq no Actions.

A terceira validação, [37218385352](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/37218385352),
passou 754 testes e restore/save privados, mas repetiu HTTP 400
`json_validate_failed` no modo facts mesmo com schema estrito. O ajuste não
resolveu a chamada real. Diagnóstico adicional classifica somente sintaxe,
tamanho e posição da geração recusada; nunca persiste sua resposta ou mensagem
bruta. A causa permanece em investigação, sem liberar main ou publicar vídeos.

O diagnóstico do run 37219383922 mostrou JSON válido, 4677 caracteres. Probe
local real, com a chave EN configurada, encontrou três rótulos kind fora do
enum em 14 fatos. Schema/parser foram preservados; o prompt agora explicita
categorias e cópia literal, e retry factual recebe a citação recusada como dado
sem aumentar o orçamento. Uma citação também alterava capitalização; o gate
continua rejeitando esse caso. O último probe encontrou 429 com espera acima
do orçamento, portanto a correção completa ainda precisa de prova no Actions.
Fixture de integração foi isolada do Groq real; ela não pode consumir a chave
presente no ambiente. Suíte interrompida durante essa investigação não é prova.

Run [37221057489](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/37221057489),
commit c36554a: 763 testes, LanguageTool real, restore e save privados passaram;
geração encontrou `rate_limit`, HTTP429, modo facts, uma tentativa (espera
do serviço acima do orçamento). Sem mídia/publicação. Não repetir geração
enquanto a cota não renovar nem trocar chave para contorná-la. A correção de
prompt/feedback ainda NÃO tem aceite real; falta geração PT/EN/ES, inspeção
de mídia e bootstrap reconciliado antes de liberar main. Verify separado pode
comprovar o estado de controle/fonte/perfil, mas não mídia que não foi gerada.

Verify [37221464481](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/37221464481)
concluído com sucesso em outro runner, commit c36554a, mesmo namespace:
restore e verificação passaram; geração/publicação/checkpoint final foram
pulados conforme o modo. Isso comprova a recuperação do estado salvo de
controle/fonte/perfil, NÃO geração de mídia ou upload. Retomar quando a cota
permitir a prova semântica real; não reiniciar tarefas 1–6 nem descartar heads.
