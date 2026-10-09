# Confiabilidade — evidência operacional 2026-10-04

## Retomada prioritária de publicação — 2026-10-09

[Run 37953540179](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/37953540179)
agendado em main/30a0a0c falhou na revisão da adaptação EN após três chamadas;
HTTP original não foi preservado pela versão antiga. Publicação foi pulada.
Os runs agendados de 06–09/10 ainda usam main anterior, não a branch de reparo.
Não atribuir essas falhas ao OAuth nem inferir 429 sem diagnóstico.

Refresh dos três tokens locais foi conferido com o Google, sem salvar arquivos:
PT/EN/ES retornaram invalid_grant. Secrets YOUTUBE_TOKEN_* não atualizados desde
30/09; valores não acessados. Operador orientado a renovar pelo script da raiz
com --all --github --repo MoneyzxD/Automatic-Reddit-Git, confirmando cada canal.
Status OAuth só pode mudar após renovação efetiva, nunca pela data da investigação.

Validação 37486166670/28ff32b cancelada em 06/10 após cerca de dez minutos
na preparação FFmpeg, antes de Python/LT/restore/geração. Não identifica qual
comando interno parou. Correção estreita limita comandos e step, registra fase
e código, mantém FFmpeg/DejaVu e não mata APT ativo. Teste de fonte ausente também
impede preparação verde sem DejaVu. Testes de shell são isolados, não instalação
real. Próximo teste reutiliza validation-reliability-20261006-completion, que
não chegou a receber estado/gates nesse run; sem upload de histórias de teste.
Histórico reconciliado e 84 IDs permanecem preservados. Production sem checkpoint
completo, main não integrado e retorno à publicação ainda não comprovado.

## Conclusão parcial detectada — 2026-10-06

[Run 37479460583](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/37479460583)
em `b8c9da9` terminou failure após 16m42s. Adaptação EN e tradução PT foram
aprovadas; naturalização PT ficou unavailable por HTTP429/chunk/três tentativas.
Diagnóstico novo foi preservado: payload 21.917 bytes/21.559 caracteres,
sem teto explícito de saída, TPM 8.000/restante 8.000, RPD 1.000/restante 991.
Subtipo/Retry-After ausentes. Isso não demonstra RPM/TPD/OTPM disponíveis nem
comprova que o tamanho seja a causa. ES e mídia não foram alcançados; upload
pulado. Estado isolado íntegro: sequência 13, nove controles, zero mídia.

Sonda única confirmou outro defeito, separado do 429: extração factual PT
retornou JSON válido com `finish_reason=length`, que o guardião não verificava.
Fonte foi conferida offline como exatamente a fixture pública TEST_STORY_MALE;
nenhuma história privada do Reddit foi usada na sonda. A comparação na mesma
chave/modelo, saída limitada a 2.048 e `reasoning_effort=none`, terminou em
`stop`, com 993 tokens de saída em vez de 2.048. Contagem/JSON não comprovam
cobertura factual nem qualidade editorial; não é replay do 429 do Actions.

Correção na branch: só `stop` com conteúdo permite continuar aos parsers/gates;
JSON válido parcial também falha. `incomplete_response` encerra imediatamente,
sem repetir sob o mesmo teto. Retry de HTTP429/transporte/schema é preservado.
Teto de JSON configurável `semantic_max_completion_tokens: 2048`, somente do
guardião; geração do roteiro inteiro mantém seu orçamento anterior. `none`
explícito só no Qwen ativo; modelo/chave, schema, fontes e gates não alternam.
É um limite deliberado, não garantia de caber na cota ou atender qualquer história.

RED independente: 45 falhas/26 passes; foco 331 passes; suíte fresh **1.047
passes**, 33 avisos legados. A próxima prova deve executar os gates atuais desde
o início em namespace novo isolado, preservando o anterior: aprovações obtidas
antes da checagem de conclusão não demonstram aceite desta correção. Production,
main, mídia, rodada normal e agentes continuam pendentes do backlog.

## Instrumentação anterior — 2026-10-06

Instrumentação autorizada após capturas Usage/Limits do operador: o consumo
Qwen mostrado não demonstra cota diária esgotada; o subtipo do último 429
continua desconhecido. Captura nova mede bytes/caracteres do HTTP real do SDK,
tetos explícitos de saída, limites/restantes/reset numéricos e consumo em sucesso.
Falha carrega apenas números allowlisted no relatório; nenhum texto/chave/header
livre. Modelo, payload enviado, gates, retries e cadência permanecem iguais.
Guardião registra cada tentativa (SDK retry desativado); estágios legados veem
somente o desfecho do SDK e streaming permanece sem consumo pelo diagnóstico.

Prova local: 9 testes RED pela captura ausente; overflow adversarial reproduzido
e corrigido; 262 testes focados passaram e revisão independente ficou sem
achados pendentes. Suíte completa pós-ajuste: 976 testes, 33 avisos legados.
A captura acima comprovou os metadados no Actions; esses testes não
declaram causa da recusa nem aceitam mídia/main. Avaliação do Plus concluída em
[OPENAI_PLUS_FEASIBILITY](OPENAI_PLUS_FEASIBILITY.md): alternativa condicional,
não migração implementada. O namespace `validation-reliability-20261006-anchors`
foi preservado; a próxima validação segue a decisão de conclusão descrita acima.

[Run 37408357221](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/37408357221)
em `1947aee4` terminou **failure em 4m36s**. Os **959 testes passaram em
18,93s**, LanguageTool e restore isolado passaram. A geração interrompeu na
revisão da adaptação EN: `rate_limit`, **HTTP429**, modo `chunk`, três tentativas,
contexto de 16.695 caracteres. Subtipo de limite e Retry-After não vieram no
diagnóstico; nenhuma falha JSON foi registrada nessa amostra. Não atribuir
esse 429 ao token de estado, OAuth YouTube, erro de ancoragem ou a todos os
incidentes anteriores. PT/EN/ES não chegaram à geração de mídia.

Upload foi pulado, checkpoint final passou e logs foram preservados. Head do
namespace `validation-reliability-20261006-anchors` confirmado, com cópia
local verificada por hash e schema: sete checkpoints completos, sequência seis,
sete arquivos de controle, zero mídia/etapas aprovadas. Sem restore de produção,
reset de estados anteriores ou alteração de fonte/perfil. Watch encerrado.
Namespace production reconferido: zero checkpoints completos.

Uma consulta **sintética curta local EN**, sem retries, recebeu HTTP200:
teto TPM 8.000, restante TPM 6.960, teto RPD 1.000, restante RPD 999,
319 tokens de uso. É diagnóstico dessa credencial local e dessa chamada,
não prova de igualdade com o Secret do Actions, suficiência para contexto
longo, limite diário atingido ou aprovação pelo guardião completo. Secrets
GROQ por idioma existem; seus valores não foram lidos/trocados. A
[documentação oficial](https://console.groq.com/docs/rate-limits) distingue
limites por minuto/dia e orienta conferir a cota efetiva na organização.

Próximo diagnóstico: confirmar Usage/Limits da conta EN efetivamente usada no
Actions e, se necessário, coletar somente metadados numéricos do transporte.
Captura sem chave API solicitada ao operador. Sem novo dispatch automático,
rotação de credenciais/modelo ou afrouxamento dos gates. Bootstrap production,
main, rodada normal e agentes permanecem pendentes dos aceites reais.

## Credencial e restauração real — 2026-10-06

Credencial limitada local configurada e acesso ao destino privado aprovado
comprovado, sem expor token ou alterar o Secret existente. A cópia reconciliada
conserva 30 histórias, 91 partes, 84 IDs confirmados e sete vídeos pendentes
(PT: 3, EN: 2, ES: 2). Inventário e digest aprovados continuam idênticos.

Cópia privada completa no namespace `validation-reconciliation-20261006`:
11 blobs de mídia, 488.459.531 bytes. O
[run verify 37407149313](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/37407149313)
em `af2f6f4` passou: **955 testes em 17,90s**, restore e verificação no runner
Linux, cinco arquivos de controle e 11 blobs íntegros. Geração, publicação e
checkpoint final foram pulados. LanguageTool foi encerrado na limpeza normal.
Foco local de recuperação: 133 testes, dez avisos, 40,91s.

Isso comprova transporte e recuperação da cópia legada entre Windows e Actions,
não a qualidade editorial dos vídeos legados nem geração nova. Namespace
production continua sem head; main, caches, original e IDs externos intactos.
A decisão foi provar esta etapa independente em cópia isolada antes de ativar
produção; nenhum bootstrap production foi antecipado.

Uma única consulta sintética ES às 03:08 UTC recebeu resposta JSON com dois
fatos, sem repetir HTTP429. É disponibilidade nessa amostra curta, não prova
de contexto longo ou orçamento para um lote. Continuam pendentes: investigar
reparos PT, geração completa PT/EN/ES, inspeção da nova mídia, bootstrap
reconciliado, integração main e rodada normal. Agentes permanecem posteriores.
Os registros abaixo são antecedentes; a ausência local do token foi resolvida.

Diagnóstico estreito de ancoragem distingue trecho ausente no chunk de offset
incorreto por enum sanitizado; ambos continuam rejeitados. Schema, parser,
prompts, modelos, chaves, cadência e gates não mudaram. TDD e foco de 225 testes
passaram; suíte **959 passed**, 33 avisos legados, 83,07s; compile/diff check
passaram. Revisão independente: 225 testes, nenhum Critical/Important/Minor.
Não identifica retroativamente o ramo do reparo PT antigo nem libera main.

## Retomada verificada — 2026-10-05 / 06 UTC

Run `37379031931`/`ac74819` terminou failure em 2026-10-05 22:15:58 UTC.
Testes, LanguageTool e restore/save privados passaram; publicação foi pulada.
Tradução PT aprovada após 13 chamadas semânticas; naturalização PT rejeitada
por alteração na sequência da cena do mercado, além de avisos/omissões.
Tradução ES ficou unavailable: HTTP429/global, três tentativas, subtipo e
Retry-After não informados. Nenhuma falha JSON registrada nesta amostra.
Isso não comprova recuperação completa, estabilidade universal ou cota diária.

Checkpoint final `complete-14` capturado em cópia privada, SHA-256 do payload
conferido. Nove arquivos de controle, incluindo adaptação EN e tradução PT,
sem mídia. API de artifacts confirma somente logs; nenhum MP4/JPG novo.
Consulta sintética única ES em 2026-10-06 também recebeu HTTP429, sem subtipo
ou Retry-After. Não redisparar o lote nem trocar chave/modelo para contornar isso.
Não existe monitor de dispatch ativo; sessões antigas não sobrevivem à retomada.

Revisão independente completa de `23f7f9c..ac74819`: três achados Important
reproduzidos e corrigidos, só na branch isolada:

- Comandos do kit TikTok não alteram mais YouTube; lookup encontra `pt`.
- Snapshot aceita basenames Unicode do organizer. JSON editorial com palavra
  tokens/credentials exige MP4 associado à fila/manifesto, título compatível
  e ausência de campos OAuth/credenciais, inclusive aninhados. IDs, diretórios,
  hashes, travessia, links e colisões continuam protegidos.
- Namespace explícito não-production bloqueia upload mesmo sem flag required;
  o modo local legado sem namespace permanece compatível.

RED/GREEN reproduzidos; suíte fresh **955 passed**, 33 avisos de depreciação,
89.36s. Compile/diff check passaram. Revisor pós-delta: 134 testes/26.92s,
quatro avisos, nenhum Critical/Important novo. Aprovação técnica do delta,
não de main/produção. Detalhes privados no ledger da worktree.

Próximos gates: investigar os reparos PT rejeitados sem relaxar fidelidade,
restabelecer serviço ES, gerar/inspecionar os três idiomas e restaurar mídia em
outro runner. Depois bootstrap reconciliado, main e rodada normal. Terminal
rejected não é reaberto automaticamente. Token limitado de estado ainda ausente
no ambiente local; o Secret Actions não fornece seu valor de volta. Não usar
a credencial ampla do gh para essa importação. Agentes permanecem posteriores.
Os blocos abaixo são antecedentes, não instruções para repetir dispatches.

## Próxima validação: guardião Qwen fixo — 2026-10-05

Branch isolada passa a configurar `qwen/qwen3.8-27b` somente para o guardião.
Modelo listado pela conta e compatível com schema estrito segundo as
[documentações Groq](https://console.groq.com/docs/structured-outputs) e
[limites gratuitos](https://console.groq.com/docs/rate-limits). Não é rotação
por cota: chave fixa por idioma, schema, parser, gates, LanguageTool, cadência
e orçamento permanecem iguais. Modelos das etapas de geração não mudaram.

Sondas reais: fatos sintéticos com referências literais; frase correta aprovada;
valor inventado rejeitado como amount:critical. Contexto longo autorizado,
fonte com SHA conferido e candidato/ledger sanitizados: três grammar:warning,
sem falha JSON registrada. Nova sonda pelo código alterado, sem alias de modelo,
também retornou esses três avisos, em três chamadas semânticas, sem falha JSON.
Não é replay exato nem aprovação completa: os avisos ainda exigem julgamento,
inclusive o possível falso positivo de estilo em “explicar por si mesmo”.
Não afirmar superioridade semântica, ausência universal de HTTP400 ou mídia pronta.

TDD: cinco falhas esperadas antes do allowlist; foco 286 passed/15 avisos/10.77s;
suíte completa 896 passed/33 avisos/51.37s; compile e diff check passaram.
Revisor independente: 14 casos HTTP/schema passaram, nenhum Critical/Important/
Minor novo. Aprovação restrita à validação, não à liberação de main.

Próximo gate: aguardar recuperação do incidente Actions e disparar PT/EN/ES
sem upload, retomando `validation-reliability-20261005-source`. Monitor de
status ativo; nenhum novo dispatch enquanto houver indisponibilidade de runners.
Depois: mídia, restore em segundo runner, bootstrap reconciliado e main.
Os antecedentes abaixo descrevem a configuração anterior, não a próxima rodada.

## Fonte narrativa separada do ledger — 2026-10-05

Retomada atual: run `37370371919`/`b030bd6`, mesmo namespace de validação,
PT/EN/ES sem upload, terminou failure antes de iniciar o pipeline: job cancelled
em15m1s, runner_id0, nome vazio, steps[]. Anotação oficial: o job não foi
adquirido por runner hosted após várias tentativas. [GitHub Status](https://www.githubstatus.com/)
registra incidente desde19:11UTC; API indica major_outage/investigating,
atualizado20:47:22UTC. Nenhuma geração, restore/save, mídia ou upload nesse run;
aguardar recuperação externa antes de novo dispatch. Duas chamadas posteriores ao probe
comparativo, com os mesmos dados sanitizados e 20B, deram HTTP400/reason ausente
e depois approved/sem achados pelo `_request` atual. Variabilidade observada,
sem motivo factual específico recuperado. Código/configuração permanecem iguais;
aguardar a prova completa, sem aprovar conteúdo por contagem ou por esse probe.

Envelope alternativo de função foi testado só em sonda descartável: mesmo schema,
sem executar função. Frases sintéticas correta/inventada tiveram emissão válida
e decisões esperadas. No contexto longo autorizado, primeiro retorno passou pelo
gate literal, mas o resumo se perdeu por codificação cp1252 do terminal; a chamada
seguinte teve HTTP400/providerother. Não demonstra estabilidade/superioridade;
nenhuma integração desse mecanismo nem fallback novo. Manter código atual.

Run `37363161214`/`8628ed9`, namespace novo isolado, terminou failure/10m11s.
Adaptação EN aprovada; tradução PT corrigiu cinco achados gramaticais, depois
ficou unavailable por três HTTP400/json_validate_failed no modo chunk, com
failed_generation string vazia/0 caracteres, contexto12735–12767. Nenhum HTTP429
registrado, nenhuma mídia/upload. Não alcançou os gates derivados: este teste
não prova o efeito real da separação de fonte nem resolução do falso positivo ES.
Testes/LT/restore/save passaram; a adaptação aprovada está preservada.

Diagnóstico adicional, sem mudança de produção: transporte HTTP sintético com
SDK real comprova strict:true, required completo, objetos fechados, start nullable,
sem tools/stream nos três modos. 15 testes de cadência/0.62s passaram. Schema
confere com os requisitos da [Groq](https://console.groq.com/docs/structured-outputs).
Prova curta real com conteúdo sintético e chave fixa PT passou: dois fatos
com referências literais, chunk/global approved na sequência empréstimo inicial
e recusa posterior. Não é replay do incidente nem prova de roteiro completo.
Primeira execução do probe local não carregou o .env correto e não fez chamadas;
caminho corrigido antes da prova real. Essa falha local não era erro do serviço.

A comparação longa foi inicialmente bloqueada pelo auto-review. O operador
autorizou explicitamente a transmissão e o probe foi executado: fonte íntegra
com SHA conferido, candidato/ledger SANITIZADOS, contexto12797, mesma chave PT,
duas chamadas e nenhuma alteração de produção. GPT-OSS20B retornou rejected com
um factual:critical; GPT-OSS120B retornou rejected com um factual:critical e um
style:warning. Ambos forneceram JSON parseável; o HTTP400 não se reproduziu
nessa amostra. O probe reteve somente status/contagens, não os motivos dos
achados: não atribuir a rejeição a uma frase específica nem confirmar erro real
do original a partir do candidato sanitizado. Não é replay exato, teste dos
gates completos ou demonstração de superioridade do 120B. Próximo diagnóstico:
comparar o achado concreto à fonte, preservando privacidade; não repetir o
pipeline completo ou mudar modelo/prompt apenas por essas contagens.
Suíte final de diagnóstico: 891 passed/33 avisos/50.95s; compile/diff check
passaram. Revisão independente aprovou apenas o commit de caracterização,
sem Critical/Important. Minor: required/properties iguais não detectam remoção
simultânea de um campo no schema. Outros testes verificam os campos esperados,
mas o teste HTTP novo não fixa todos os nomes; não afirmar essa cobertura.

Diagnóstico independente dos candidatos do run `37341313520`: ES/meta2 contém
a recusa **depois** da descoberta, sustentada pela fonte; o achado citava apenas
o empréstimo anterior e foi falso positivo temporal. PT/título é impreciso
(perder versus faltar ao jantar), sem contradição factual demonstrada. Não
aprovar automaticamente nenhuma dessas frases nem dispensar nova revisão.

Defeito de código comprovado: `derived_source` juntava roteiro aprovado e JSON
do ledger. A reextração no primeiro gate derivado passou a citar esse JSON como
fonte: 15/33 citações PT e 10/28 ES continham chaves JSON no artifact sanitizado.
Agora os gates recebem só a narrativa localizada aprovada; o ledger continua
separado na geração. O cache existente reaproveita os fatos dessa narrativa.
Isso corrige a autoridade da evidência, mas não comprova sozinho a recuperação
do julgamento temporal nem explica retroativamente a referência inválida EN.

`source_reference_error` identifica somente enums locais (tipo, vazio, ID
desconhecido/repetido, ordem, lacuna, citação não literal). Retry recebe esse
subtipo, sem valores/IDs recusados. Schema, aceitação, orçamento e gates iguais.
TDD: nove falhas esperadas antes da implementação; suíte completa 888 passed,
33 avisos legados de datetime.utcnow, 45.19s; compile/diff check passaram.
Revisão independente aprovou a próxima validação isolada. Limite de teste:
o ramo de citação não literal conserva a condição anterior, sem caso novo
específico; adaptadores sintéticos não comprovam a Groq real.

Compatibilidade: prepared.json antigo tem hash da fonte concatenada; retomada
através desta revisão bloqueia para reconciliação explícita. Não apagar ou
promover esse checkpoint automaticamente. A validação anterior não chegou a
salvar prepared, porém PT/ES ficaram rejected: usar namespace novo isolado
para provar os três idiomas, preservando os anteriores e produção.

Run recente `37349810900` de main/`30a0a0c` também falhou antes de mídia, na
adaptação EN de `1w8npme`. Testes/LT passaram, publicação foi pulada; relatório
antigo não preservou SemanticFailure/HTTP. Não atribuir a mesma causa por
suposição. Artifact privado preservado; main/bootstrap/rodada normal/agentes
continuam pendentes de aceite real.

## Correção de emissão e cadência — 2026-10-05

Operador autorizou corrigir os dois bloqueios capturados. Código `5aea94b`
enviado somente à branch `pipeline-reliability`. A instrução de revisão agora
exige todos os campos, explica `reason` e inclui `start: null` no exemplo;
severity usa um valor válido. Schema, parser e gates permanecem estritos.

O wrapper lê a recarga TPM pelo SDK público `with_raw_response`/`parse` e
espaça chamadas por modelo entre etapas/clientes, inclusive após recusa. O
cabeçalho diário de requests não é confundido com RPM. Resets de 0–120s têm
margem de 1s, piso de 2,1s para 30 RPM e teto de 120s; esperas são divididas
em blocos de até 60s. Sem cabeçalho confiável, espera 61s após a tentativa.
Chaves continuam fixas, sem aumento de tentativas/orçamento do guardião.

Limites: estado só deste processo e conservador entre chaves, pois a quota é
por organização. Não coordena outros consumidores/processos/namespaces;
retries internos do SDK legado ficam fora da cadência individual. O guardião
continua com SDK retry zero. Cabeçalhos fora da faixa/formato aceitos não
comprovam recarga em 61s; TPD e pedidos maiores que TPM continuam sujeitos ao
erro do provedor e gates obrigatórios. Cadência não cria cota nem garante lote.
Referências: [limites Groq](https://console.groq.com/docs/rate-limits) e
[SDK público](https://github.com/groq/groq-python#accessing-raw-response-data-eg-headers).

TDD reproduziu omissão no exemplo, chamadas sem espaçamento e os limites
RPM/recarga de 90s. Suíte completa final: 873 passed/30 warnings/50.12s;
warnings legados de `datetime.utcnow`. Revisão independente aprovou os deltas,
incluindo 12 testes de cadência/0.41s com transporte HTTP sintético. Isso não
comprova emissão/fidelidade da Groq real. Run `37338112115` passou 873 testes/22.49s,
LanguageTool e restore/save; terminou failure/15m15s. Tradução PT aprovada após
oito chamadas e naturalização PT após cinco. Cadência real registrada, esperas
16–57s, nenhum HTTP429 registrado nos relatórios. Isso não garante cota futura.
HTTP400 ainda ocorreu: tradução omitiu `reason` em três achados, depois recuperou;
título omitiu `reason` nas três tentativas e bloqueou o lote. `start` não teve
omissão registrada nessa amostra. Nenhuma mídia/upload, EN/ES não concluídos.

Gap reproduzido: diagnóstico sabia quais campos faltavam, mas retry recebia só
`invalid_json`. Código `3d65d84` acrescenta `missing_issue_fields`, deduplicados
e restritos a `reason`/`start`, apenas de violações required no path exato de
issue. Valores/índices/nomes extras não são reenviados e a geração recusada
continua descartada. Nenhum motivo é fabricado localmente; parser/schema/gates
e orçamento continuam iguais. Outros campos permanecem no feedback genérico
até evidência e regressão justificarem ampliação. TDD seis falhas esperadas;
211 testes do guardião/1.12s, suíte completa 879/30warnings/49.69s,
compile/diff check e revisão independente (211/1.14s, sem achados) passaram.
Run `37341313520`/`3d65d84` passou 879 testes/18.09s, LanguageTool e restore/save;
terminou failure/34m20s, sem mídia/upload. As recusas JSON intermediárias foram
recuperadas dentro do orçamento: PT/título saiu de unavailable para rejected;
ES aprovou tradução, naturalização, título/hooks, duas partes e metadados da
parte 1. Nenhum HTTP429 registrado nos relatórios. Ainda houve omissão de
`reason` em respostas iniciais e uma geração JSON vazia no título ES: o ajuste
recupera falhas, não garante que o provedor nunca emita resposta inválida.

Bloqueios distintos preservados: PT/título foi rejeitado por diferença entre
perder o jantar e não ir ao jantar; ES/metadados da parte 2 descreviam recusa
de empréstimo, enquanto o guardião apontou empréstimo já realizado. Esses
achados são evidência do guardião, não conclusão independente sobre seus
candidatos ou prova de defeito no código. EN aprovou tradução/naturalização,
mas a coleta factual do título terminou `invalid_source_reference` após três
tentativas (HTTP ausente, contexto4737). A resposta/IDs inválidos não foram
preservados; não é possível dizer se foram vazios, desconhecidos, repetidos,
fora de ordem ou não contíguos. Isso não foi quota/OAuth/schema `reason`.

Próximo diagnóstico: comparar os candidatos de título/metadados com a fonte
e scripts aprovados; identificar de forma sanitizada o subtipo da referência
inválida antes de corrigir esse contrato. Não repetir dispatch, enfraquecer
evidência ou reescrever etapas por suposição. Main/bootstrap/rodada normal e
agentes continuam pendentes. Os registros abaixo são antecedentes.

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
também (três testes/0.27s, sem achados).

Captura real `37333981612`/`d173dd2`: 859 testes/19.52s, LanguageTool,
restore e save final passaram. PT/tradução repairing1 (quatro chamadas),
unavailable2 (sete chamadas). Na chamada6/tentativa2, HTTP400/json_validate_failed
com JSON válido/1601 caracteres: cinco achados sem os campos obrigatórios
`reason` e `start` (dez violações de required), sem truncamento do diagnóstico.
Tentativa3 terminou HTTP429/TPM, Retry-After18s/contexto15872; a recusa anterior
foi preservada no relatório. Nenhuma mídia/publicação. O mascaramento global de PII
mascarou um índice numérico do path; não restaurar conteúdo livre para desfazer isso.

O diagnóstico autorizado está comprovado em serviço real. Próxima correção:
alinhar instrução/exemplo de revisão ao contrato obrigatório (`start` aparece
como opcional e falta no exemplo atual; `reason` já está no exemplo). Não
atribuir toda a recusa apenas ao prompt: geração recusada omitiu ambos. A cota
TPM é bloqueio separado a tratar mantendo a chave fixa e orçamento acordado.
Schema/gates continuam intactos; não houve correção desses dois bloqueios nem
geração PT/EN/ES completa, bootstrap de produção ou liberação de main.

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

1. Com campos ausentes agora identificados, corrigir o contrato de emissão e
   tratar TPM sem rotação de chaves; comprovar no serviço real antes de liberar.
2. Gerar PT/EN/ES completos, conferir roteiro/voz/ASS/card e restore da mídia.
3. Importar o candidato reconciliado após aceite real e credencial específica disponível.
4. Bootstrap, verify independente, integração em main e rodada dentro da meta.

Cron legado permanece habilitado (`PIPELINE_AUTOMATION_ENABLED=true`), sem
alteração neste trabalho; isso não significa que a branch nova foi liberada.
Agentes de manutenção/crescimento ficam após esses gates. Nenhum Secret
YouTube/Groq/Reddit, cron, meta, vídeo remoto ou estado production foi alterado.
