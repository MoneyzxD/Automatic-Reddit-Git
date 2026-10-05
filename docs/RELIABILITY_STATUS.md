# Confiabilidade — evidência operacional 2026-10-04

## Diagnóstico estrutural autorizado — 2026-10-05

Operador aprovou identificar o campo recusado sem armazenar a resposta. O
diagnóstico de `json_validate_failed` agora compara o JSON sintaticamente válido
com o schema do modelo/modo configurado. Registra somente caminhos de campos
conhecidos, regras e tipos; chaves extras e valores livres não são expostos.
Limites: 20 achados, 4096 nós e o teto sintático existente de 131072 caracteres.
O leitor cobre apenas o subconjunto usado pelo schema atual; uma ampliação desse
schema exige ampliar o diagnóstico. Números são lidos pelo parser Python; valores
extremos de `start` podem sofrer arredondamento/overflow no diagnóstico. Isso
não muda o gate de offsets. `matches_schema` não aprova conteúdo nem
explica sozinho a recusa do provedor; inspeção incompleta é indicada explicitamente.
Schema, prompt, modelos, chaves, retries e gates permanecem iguais.

TDD: 23 falhas reproduzidas antes da implementação; 200 testes do guardião e
suíte completa 856 passed/30 warnings/50.11s passaram. Compilação e diff check
passaram. Fixtures de nomes longos e profundidade foram ajustadas ao comportamento
real do Python/Windows, sem alterar o parser de produção. Revisão independente
aprovou: 24 testes/0.28s, sem achados Critical/Important; precisão numérica é
limitação Minor documentada.

Run `37331951705` passou 856 testes/17.88s, LanguageTool, restore e save final;
PT/tradução entrou em repairing e depois unavailable: HTTP429/TPM, três tentativas,
Retry-After21s, contexto16111. Nenhuma mídia/upload. O relatório final não teve
HTTP400; isso não prova que não houve recusa intermediária, pois o código antigo
guardava só a última falha. Não equiparar a cota atual à recusa de schema anterior.

Lacuna de observabilidade reproduzida com três testes RED: sucesso/429 posterior
apagava o diagnóstico anterior. Registro agora retém até 20 recusas JSON sanitizadas
por revisão, com contador de chamada e aviso de truncamento; reinicia entre
revisões. Não altera fluxo/retries. 203 testes do guardião e suíte completa
859 passed/30 warnings/50.24s passaram, compilação/diff check e revisão independente
também (três testes/0.27s, sem achados). Uma captura real com esse registro continua
pendente; não afirmar qual campo foi recusado sem ela.

## Atualização 2026-10-05 — candidato reconciliado localmente

Operador confirmou que não há publicações manuais. Consulta ownerAPI de leitura
reconfirmou 81/84 IDs históricos e nenhum título dos sete incertos; tokens locais
não foram alterados. Com os logs anteriores de falha antes do transporte, foram
preparadas 91 decisões: preservar84IDs/datas, reter7pendentes, encerrar91kits e
56tentativas de capa. Conferência é via API do proprietário, não UI simulada.
Três IDs históricos ausentes continuam preservados, sem recriação.

Decisões aplicadas somente em staging privado. Snapshot e restauração local em
outra pasta passaram:30histórias/91partes/84IDs/7pendentes, erros/datas mantidos,
11blobs de mídia únicos; original intacto. Testes state/snapshot:89pass/19.00s.
Ainda não há head production/importação nem liberação de main. Token específico
de estado está no Actions, mas não no .env local; configuração local solicitada,
sem pedir segredo no chat nem usar credencial ampla gh como substituta.
Run 37320307156 passou 809 testes/26.58s, LanguageTool e restore/save final;
geração falhou em adaptação EN/global: nonliteral_evidence, três tentativas,
HTTP ausente/contexto 16181. Nenhuma mídia/upload. Não foi HTTP429; a resposta
inválida não foi preservada, portanto a citação exata não é conhecida. O
candidato sanitizado difere do hash original e não foi usado como replay exato.

Defeito comprovado no código: somente facts enviava o motivo da recusa no retry.
Commit a3b7f3a estende feedback enum-only a chunk/global e explicita o contrato
literal no prompt, mantendo gates, fonte, perfil, modelo e orçamento. TDD:
três falhas reproduzidas, 156 testes do guardião e suíte 812/30warnings/54.05s
passaram; compile/diff check e revisão independente aprovados. Isso não prova
fidelidade do modelo nem conclusão de T7. Run 37322711750 passou 812 testes/23.64s,
LanguageTool, restore/save final e revisão semântica; job terminou verde, porém
adaptação foi rejeitada por achado gramatical persistente, sem mídia/upload.

Quarentena revelou causa distinta: repetição de início de frase é regra de
estilo oficial do LanguageTool 6.6 (`REPETITIONS_STYLE`), mas o código a tratava
como gramática crítica. Sugestões mecânicas trocaram I → Furthermore, I → Besides
e criaram novas repetições. Commit 12a48bf reconhece essa categoria como aviso
e registra sugestões de estilo sem aplicá-las automaticamente. Gramática real,
ortografia, categorias desconhecidas e gates semânticos continuam bloqueantes.
TDD: oito falhas reproduzidas, 207 testes focados e suíte 823/30warnings/49.38s
passaram; compile/diff check e revisão independente aprovados.

Run 37324808064 passou 823 testes/21.73s e aprovou a adaptação EN após uma
correção gramatical, com três avisos de estilo mantidos. Isso comprova avanço
real desse gate, não renderização. PT/tradução parou em chunk por HTTP400
json_validate_failed, uma tentativa/contexto15972; geração recusada era JSON
sintaticamente válido/353 caracteres, campo incompatível desconhecido. Restore/
save final passaram; nenhuma mídia/upload. Google também limitou a tradução;
MyMemory alcançou o guardião pelo caminho existente, sem fallback local.

484a912 permite retry somente de HTTP400 + código explícito json_validate_failed,
descartando a geração recusada e enviando feedback enum-only. Mesmos orçamento,
espera, esquema estrito e gates; outros erros permanentes não repetem. Suíte
832/30warnings/49.68s, compile/diff check e revisão independente passaram.
Não afirmar que o erro do provedor é necessariamente transitório. A documentação
Groq discute retry de falhas de schema em best-effort e pede repro de HTTP400
inesperado em strict; aqui o esquema estrito foi preservado.

Run 37326768456 falhou sem mídia/publicação; 832 testes/17.14s, LanguageTool,
restore e save final passaram. A adaptação aprovada foi preservada. Tradução PT
entrou em repairing (quatro chamadas, cinco achados gramaticais críticos), mas
a segunda revisão ficou indisponível após sete chamadas acumuladas: chunk,
HTTP400/json_validate_failed, três tentativas/contexto16263. A geração recusada
era JSON sintaticamente válido/693 caracteres; o campo incompatível continua
desconhecido. O retry limitado funcionou, mas não resolveu a recusa do provedor.
Antes de outro remendo ou dispatch, discutir o contrato de saída e definir
diagnóstico estrutural sanitizado que identifique a incompatibilidade sem
armazenar conteúdo livre. Não inferir qual campo falhou nem relaxar o esquema.
Namespace `validation-reliability-20261005-style`
foi criado para a amostra após rejeição terminal no anterior, que permanece
intacto. Nenhum head anterior/produção foi resetado.
Os registros de 2026-10-04 abaixo são antecedentes, não pendências já resolvidas.

Main permanece em 30a0a0c; não houve integração/publicação nesta validação.
Branch de trabalho: pipeline-reliability. Retomada técnica e rulings ficam no
ledger privado `.superpowers/sdd/2026-10-03-pipeline-reliability/progress.md`.

## Continuação: referências factuais aprovadas

Implementação limitada: unidades lossless de 200 caracteres com IDs locais,
seleção ordenada/contígua/única; evidência copiada da fonte pelo código.
Referências inválidas bloqueiam, e revisão de value/fidelidade/gênero/gramática
permanece obrigatória. Revisão independente aprovou. Probe Groq da história
sintética: dez fatos literais em duas chamadas. Ainda não é aceite de vídeo.
Após autorização do operador para continuar, probe da fonte preservada
1wfduc8 passou: 13 fatos, uma chamada, todas as citações literais. Isso valida
a coleta factual, não o roteiro completo. O encerramento de 91 kits TikTok
e 56 tentativas de capa antigas foi autorizado. A autorização não confirma
a ausência de publicação manual dos sete vídeos sem ID; esses ficam bloqueados.

Commit de código `dc87c02`, suíte local 786 passed/30 warnings/53.57s,
compileall e diff check passaram. Run37241728126 passou testes, LanguageTool
e restore; coleta factual avançou, adaptação entrou em repairing. Revisão
global interrompida por rate_limit/HTTP429, uma tentativa, contexto14265.
Checkpoint final foi salvo; nenhum MP4 ou upload. LT background aparece
cancelled no encerramento, mas seu health/warmup passaram; não atribuir a ele
a falha de geração. Verify37242044138 passou em outro runner, sem Groq/geração/
publicação: 786 testes/17.33s, sete arquivos de controle restaurados, mídia zero.
Confirma recuperação de fonte/perfil/controle, não renderização nem upload.

Run37243243200, no mesmo namespace isolado: geração interrompida por HTTP429
em facts, uma tentativa, contexto4794; sem mídia/publicação. Ainda não havia
diagnóstico do tipo de cota. Não atribuir esse limite aos incidentes antigos
nem concluir que a credencial local é idêntica à do runner. Ajuste aditivo
registra somente enumeração de limite declarada e Retry-After numérico finito;
não guarda mensagem livre, não muda retry e não alterna chaves.
Suíte local atual: 809 passed, 30 warnings, 54.89s; compilação e diff check
passaram. Revisão independente do diagnóstico aprovou o escopo, não o rollout.

Run37244100764, código ec15619: HTTP429 em facts confirmou limite de tokens
por dia (TPD), Retry-After430s, uma tentativa, contexto4794. Testes/LanguageTool/
restore/save final passaram; sem mídia/upload. O cancelamento do processo LT
ocorreu no encerramento, após health/warmup bem-sucedidos. Respeitar a espera
indicada antes de novo teste; não inferir renovação completa da cota diária.
Verify37244536054 passou em outro runner: 809 testes/19.15s, restore confirmado,
sete arquivos de controle/mídia zero, sem Groq/geração/publicação. Após a espera,
run37244757274 (dispatch23:43:03UTC) voltou a falhar em facts por TPD às23:46:15,
Retry-After647s, uma tentativa/contexto4794. Sem mídia/upload; save final passou.
Não continuar repetindo geração sob cota: a espera informada não garantiu
disponibilidade para essa chamada. FullPTENES permanece não validado.

Rascunho privado de reconciliação preparado em cópia local separada:
84 IDs/91 itens legados/7 incertos, 14 arquivos de mídia copiados com hash,
112 referências ainda sem bytes. Originais conferidos antes/depois, preservados.
Paths rebased só na cópia; nenhuma decisão aprovada, head ou importação.
Snapshot candidato continua inválido por necessidade de reconciliação.
Propostas adicionais privadas: 84 IDs, 7 desconhecidos bloqueados, 91 kits e
56 capas; inventário original intacto, nenhuma decisão aplicada. As propostas
não declaram Studio conferido nem constituem aprovação para bootstrap.
Versão2 das propostas preserva os horários reais do campo legado YouTube,
com fuso explícito, para não contabilizar 84 envios históricos como feitos hoje.

## Investigação e validação

- Runs antigos 37128480329/37209564422: revisão de adaptação EN indisponível;
  classe HTTP original não preservada. Mesma causa não comprovada.
- Fontes 1wfduc8/1wf0he0 recuperadas do Reddit com hashes originais conferidos;
  conteúdo e logs preservados apenas no workspace privado de investigação.
- Run37237857551: HTTP400/json_validate_failed facts tentativa2, sem mídia.
  Distinto do rate_limit429 registrado anteriormente.
- Probe da coleta com fontes conferidas: 1wf0he0 aprovado em três chamadas;
  1wfduc8 nonliteral_evidence após três. GPT-OSS120B também falhou com essa
  fonte, na mesma chave EN. Probes não testaram o roteiro completo/voz/card.
- Suíte local: 773 testes passaram, 30 avisos, 83.30s. Os dois runs de captura
  passaram 773 testes e LanguageTool real; isso não é aceite de geração.

## Estado preservado, ainda não importado

Capturas somente privadas, sem marker/head production:

| Candidato cache | Run de captura | Histórias DB | Partes DB |
|---|---|---:|---:|
| 37209564422 | 37238541263 | 2 | 0 |
| 37025408714 | 37238543218 | 30 | 91 |

ZIPs e arquivos conferidos por SHA-256. Filas PT/EN/ES são iguais byte a byte
nas duas cópias; a cópia anterior inclui as duas histórias dos incidentes.
Run37063586921 salvou cache de DB após falha dos testes antes de restaurar;
run37064703594 o combinou com fila37025408714. O workflow novo remove essa
autoridade de cache e exige restore confirmado para save final. Dry-run agora
não abre/migra DB persistente. Essas correções ainda não estão em main.

Filas: PT 31 itens/28 IDs, EN 31/29 IDs, ES 29/27 IDs. Total de 84 IDs confirmados,
preservados sem alteração. Consulta autenticada de leitura aos canais confirmou
81 IDs. Três PT não foram encontrados em playlist nem videos.list:
2kj7o4kuHrw, ay5u5p8f3mw, kMH9jjv8XQo. Preservar histórico; ausência atual
não autoriza recriar vídeos nem apagar registros.

Sete itens sem ID (global uploading, YouTube failed): 1wtjwq4_pt e as duas
partes de 1wqijcl em cada idioma. Logs36737131418 mostram invalid_grant antes
de iniciar envio; os runs36887596133/37025408714 não os tentaram novamente.
Playlist atual não encontrou título exato. Isso não exclui upload manual com
outro título: operador precisa conferir e aprovar a decisão antes de reenvio.

Mídias desses sete itens recuperadas de video-36737131418: 7 MP4 + 14 JPG,
490246562 bytes. ffprobe: todos 1080x1920, durações 77.30–137.54s. Não foram
aprovados semanticamente nesta etapa; são mídia legada para reconciliação,
não prova da renderização da branch nova. Skill watch conferiu três amostras
locais (PT casa, EN/ES irmão, parte1) em 00:01/00:03/00:15. Cards legíveis e
sem corte nos dois primeiros quadros de cada vídeo; legendas visíveis em PT/EN
aos15s, não no quadro ES. Sem transcrição/áudio, não distinguir pausa de fala
de problema de legenda nem aprovar voz/sincronização. Nenhum upload externo.

Todos os 91 kits TikTok continuam pending no original. EN/ES têm 56 tentativas
de capa failed. Encerramento autorizado, mas ainda não aplicado ao estado
production. Código de reconciliação aceita cancelamento explícito de capa
failed/missing somente junto de upload confirmado, conservando ID/erros e
auditando estados anteriores. Testes reais de clone/fila passaram e revisão
independente aprovou. Não fingir postagem TikTok nem sucesso de capa.
Bootstrap exige relatório aprovado e candidato
íntegro; ele não foi executado. Não substituir faltantes por fila vazia.

## Gates restantes

1. Revisar o contrato de saída após a recusa persistente de schema e obter
   diagnóstico seguro antes de outra correção/geração; job verde sem mídia não é aceite.
2. Gerar PT/EN/ES completos, conferir roteiro/voz/ASS/card e restore da mídia.
3. Importar o candidato reconciliado após aceite real e credencial específica disponível.
4. Bootstrap, verify independente, integração em main e rodada dentro da meta.

Cron legado permanece habilitado (`PIPELINE_AUTOMATION_ENABLED=true`), sem
alteração neste trabalho; isso não significa que a branch nova foi liberada.
Agentes de manutenção/crescimento ficam após esses gates. Nenhum Secret
YouTube/Groq/Reddit, cron, meta, vídeo remoto ou estado production foi alterado.
