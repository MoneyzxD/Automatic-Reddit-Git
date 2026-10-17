# Gemini gratuito — provedor padrão do pipeline

Decisão atual do operador em 16/10/2026: usar Gemini no lugar do Groq em todas
as etapas de IA. Essa instrução substitui a condição anterior de manter Groq
como padrão até o aceite completo. O Secret GEMINI_API_KEY já está cadastrado;
seu valor não é impresso. A geração completa ainda precisa de prova real.

## Implementação e reversão

PIPELINE_LLM_PROVIDER seleciona groq ou gemini uma vez por execução. O default
é gemini, inclusive quando a variável está vazia. O workflow manual/agendado
fixa Gemini e não injeta Secrets Groq nem aceita seleção de outro provedor.
A camada utils/llm_client.py
encaminha os clientes de adaptação, perfil, correção de gênero, naturalização,
título/hook/encerramento, metadados e validação. Métodos privados com nomes
históricos groq são preservados para manter compatibilidade e testes existentes.
A tradução também usa Gemini quando selecionado. A seleção Groq preserva
Google/MyMemory. Cache legado de tradução não conta como tradução Gemini.

Gemini usa REST nativo com requests já instalado. GEMINI_MODEL começa em
gemini-3.8-flash, que tem modalidade gratuita documentada e consta no catálogo
autenticado. Modelos fixos permitidos também incluem gemini-2.5-flash e
gemini-2.5-flash-lite. Não há alternância por
rate limit, contratação, ativação de faturamento, grounding ou ferramenta paga.
O projeto Google deve continuar sem faturamento: o endpoint não informa o plano
de cobrança da chave e uma chave de projeto pago pode cobrar pelo mesmo modelo.

Prompts e gates locais permanecem; o schema completo de fatos/patches é enviado
em responseJsonSchema. Só uma resposta STOP com texto final pode ser consumida.
Resposta bloqueada, truncada, vazia ou inválida não aprova conteúdo. O perfil,
evidências literais, rechecagem LanguageTool e quarentena continuam obrigatórios.
Falha Gemini nas etapas de geração interrompe o lote, sem acionar Ollama,
regras ou templates como substitutos. Limpeza determinística explícita e perfil
imutável permanecem. Tradução retorna indisponibilidade tipificada sem Google.
O guardião controla as três tentativas; o cliente não adiciona retries nesse
caminho. Geração tem no máximo duas tentativas em 429/503/timeout/conexão,
com teto de espera 30s. Timeout e payload são iguais nas duas tentativas.
Cadência padrão 13s entre chamadas/etapas/idiomas no mesmo processo não garante
crédito diário nem coordena outros consumidores do projeto Google.

Erros armazenam só código/status/espera numérica. RetryInfo é lido sem preservar
mensagens livres. Chaves ficam no cabeçalho HTTPS, sem query string/redirect.
Consumo registra o modelo efetivamente usado, inclusive respostas incompletas.

## Aceite operacional

1. Suíte local e testes de encaminhamento, schema, truncamento, erros e credenciais.
2. Main no Actions usa Gemini fixo. Para teste sintético isolado, usar
   idiomas=pt en es, historia_teste=true e apenas_gerar=true; namespace validation-*.
   Para retomar produção sem publicar, usar state_action=generate, sem história
   de teste ou namespace de validação. Rejeitados não são reabertos.
3. Conferir roteiro/perfil nos três idiomas, MP4/voz/legendas/cards e checkpoint.
   Um workflow verde com conteúdo rejeitado ou sem mídia não basta.
4. Restaurar/verificar a mídia em outro runner antes de liberar produção.
5. Validar Gemini já selecionado no fluxo normal. Preservar
   estado production, IDs confirmados, filas, tokens OAuth e meta diária.

O código legado permite reversão local explícita com PIPELINE_LLM_PROVIDER=groq;
o Actions exige alteração revisada para isso. Não existe reversão automática
por erro ou cota. Nenhuma reversão apaga snapshots, fontes ou perfil.
Uma aprovação antiga reutilizável não conta como revisão nova pelo Gemini.
Nenhum teste sintético deve ser publicado. Falha de cota ou gate mantém o
aceite pendente; não reduzir validações nem ativar cobrança para fazê-lo passar.

## Fontes oficiais

- [REST e configuração](https://ai.google.dev/api/generate-content)
- [Saídas estruturadas](https://ai.google.dev/gemini-api/docs/structured-output)
- [Modalidade gratuita e uso dos dados](https://ai.google.dev/gemini-api/docs/pricing)
- [Cotas efetivas por projeto](https://ai.google.dev/gemini-api/docs/rate-limits)

Na modalidade gratuita, conteúdo pode ser usado para melhorar produtos Google.
Limites efetivos dependem da conta/projeto e são conferidos no AI Studio.

## Evidência local em 13/10/2026

Baseline: 1.116 testes. Cliente ainda ausente: 20 testes novos falharam antes
da implementação. Suíte após integração: 1.146 passes/63,13s; checks adicionais
de cadência/workflow e interfaces: 119 passes/10,60s. compileall e diff check
passaram. Esses testes usam transporte falso, não o Secret do Actions.

Revisão independente sem Critical/Important aprovou somente validação isolada.
O único achado menor era o alerta genérico recomendar diagnóstico Groq mesmo
com Gemini; o texto foi corrigido para o provedor configurado. Qualidade real,
cotas/faturamento da conta, inspeção de mídia/restore e liberação de produção
continuam pendentes. Checkpoints antigos não são prova do novo provedor.

## Execução real iniciada

Commit d614352 na branch gemini-provider. Run
[38479275207](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38479275207)
iniciado com llm_provider=gemini, PT/EN/ES, história sintética, apenas geração e
namespace validation-gemini-20261013. Main/production não foram alterados.
Terminou failure na adaptação EN: HTTP404 no modelo configurado, uma tentativa
do guardião, zero mídia; upload foi pulado. Isso não comprova erro de cota nem
autoriza substituir produção. Consulta autenticada de catálogo foi adicionada
para confirmar modelos disponíveis antes de outra geração; somente nomes públicos
de modelos aptos a generateContent são exibidos, sem corpos de erro/credenciais.
Revisão do delta reproduziu uma combinação publish+catalog-only que pulava a
verificação tardia; o resolver inicial agora rejeita essa combinação e qualquer
consulta fora de normal/apenas-gerar/validation. Regressão RED/GREEN antes do
disparo de catálogo, sem qualquer upload executado.

A consulta [38480502108](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38480502108)
terminou success: 1.157 testes/22,47s, LanguageTool real, restore/save privados e
GET autenticado passaram. Tanto 2.5 Flash quanto 3.8 Flash constam no catálogo;
isso não explica retrospectivamente o HTTP404 nem garante acesso à inferência.
Nenhuma chamada de geração ou mídia ocorreu nesse modo. Modelo fixo candidato
agora 3.8 Flash, com thinkingLevel=low e os mesmos caps/schema/gates; não é
alternância por cota nem aceite para produção.

Validação de geração retomada no
[38491356526](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38491356526),
commit a43aafb, modelo fixo Gemini 3.8 Flash. Mesma fonte/perfil/namespace de teste,
PT/EN/ES sintéticos e sem upload. Check específico do modelo/schema e gates:
150 testes locais passaram. Resultado terminal registrado abaixo.

O run 38491356526 terminou failure: adaptação EN aprovada com Gemini 3.8; tradução
Google bloqueada e fallback MyMemory precisou de reparos gramaticais. O guardião
fez revisões reais e depois recebeu HTTP503 em chunk/PT, três tentativas, contexto
15.240 caracteres. Nenhum HTTP429 Gemini está comprovado nesse resultado.
Zero mídia/upload; checkpoint de teste seq14 conserva adaptação e fonte/perfil.
O 503 é indisponibilidade do serviço, não reprovação factual comprovada.

Para validar o fluxo selecionado sem o tradutor Google instável, tradução Gemini
usa blocos lossless de 4.500 caracteres, sentinelas/glossário e detector local.
Inglês residual, marcador perdido, saída bloqueada/truncada/vazia ou indisponível
continuam recusados, sem devolver a fonte como português. O guardião continua
revisando tradução contra fonte antes de naturalização/TTS. Provider/cache são
identificados; source/hash/perfil e passos aprovados de recuperação permanecem.
Essa revisão ainda exige prova real PT/EN/ES, sem alterar produção.

O delta de tradução/HTTP503 passou 133 testes focados e a suíte completa:
1.166 passes/68,67s. Revisão independente não encontrou Critical/Important;
o cabeçalho desatualizado do tradutor foi corrigido. São provas locais com
transporte falso, sem demonstrar disponibilidade ou qualidade do serviço.

Commit a8c580a enviado na mesma branch. Run
[38493851915](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38493851915)
retoma PT/EN/ES no mesmo namespace, com modelo fixo 3.8 Flash, tradução Gemini,
história sintética e apenas geração. Produção continua no Groq até cumprir
os critérios de aceite acima.

O run 38493851915 terminou failure na primeira tradução EN→PT: TimeoutError
após 60s, uma tentativa, sem resposta candidata. Testes/LT/restore/save passaram;
checkpoint seq21 mantém fonte/perfil/adaptação EN e zero mídia/upload.
Não houve HTTP429 Gemini comprovado; a causa interna do timeout é desconhecida.

A investigação usou [troubleshooting oficial](https://ai.google.dev/gemini-api/docs/troubleshooting):
retries transitórios de timeout/conexão são recomendados, e Gemini 3.6+ ignora
temperatura, com rejeição futura anunciada. O cliente agora permite um único
retry de transporte dentro do mesmo teto de duas tentativas de geração,
sem aumentar timeout/caps nem trocar chave/modelo. O guardião mantém uma tentativa
interna. Temperatura permanece no 2.5 e é omitida no 3.8. Quatro regressões RED,
287 testes focados GREEN e suíte 1.170 passes/73,19s; revisão independente sem
Critical/Important. Uma nova validação isolada deve conferir o serviço real,
sem considerar esses testes como aprovação de tradução ou disponibilidade.

## Bloqueio atual e próxima retomada

Run [38494779551](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38494779551),
commit d240287, terminou failure. A tradução Gemini EN→PT respondeu STOP
com 2.024 tokens contabilizados e passou o detector local. Isso não é aceite
semântico: o guardião falhou na coleta factual da tradução PT com HTTP429,
resource_exhausted, uma tentativa, contexto 4.801 caracteres e RetryInfo
81.609 segundos (22h40m09s). O subtipo de cota não foi capturado, portanto não
afirmar RPD/TPD/RPM; ausência de achado semântico não aprova os problemas LT.

Testes/LanguageTool/restore/save passaram; publicação foi pulada. Checkpoint
final seq28 conserva fonte/perfil/adaptação EN aprovada, zero mídia. EN/ES
não chegaram às etapas localizadas desta rodada. Não substituir produção nem
repetir chamadas enquanto o projeto indicar cota esgotada. Espera sugerida
não garante disponibilidade posterior. Limites reais do projeto/modelo são
conferidos no AI Studio; número de chaves não aumenta a cota por projeto.

A integração permanece somente na branch gemini-provider. Próxima sessão:
conferir renovação/capacidade gratuita, retomar o mesmo namespace com Gemini
3.8 e a mesma fonte/perfil, sem publicar história sintética. Faltam gates
PT/EN/ES, mídia/inspeção e restore em outro runner. Não apagar checkpoints,
enfraquecer gates, rotacionar modelos/chaves por cota ou ativar cobrança.

## Retomada em 14/10/2026

A branch `gemini-recovery` combina a integração existente com `ebb6ca0` de
produção: expansão EN AITA/AITAH antes da revisão, JSON estruturalmente compacto
e ação `generate` sem upload. A combinação não altera o provedor padrão nem
libera Gemini em produção. Revisão independente aprovou somente teste isolado;
fonte, perfil e adaptações aprovadas do namespace de teste permanecem intactos.
O RetryInfo anterior termina aproximadamente às 21h de 14/10 no fuso de São Paulo;
isso permite nova tentativa limitada, mas não garante renovação/disponibilidade.
Os [limites oficiais](https://ai.google.dev/gemini-api/docs/rate-limits) são por
projeto e RPD renova à meia-noite do Pacífico, não necessariamente nesse prazo.

O [run38657422977](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38657422977)
retomou o namespace sintético após o prazo: tradução PT respondeu STOP/2.012
tokens e cinco respostas do guardião foram concluídas. A revisão chegou à
terceira rodada e terminou503/chunk após três tentativas, contexto15.226
caracteres; nenhum429 nesta rodada. Snapshot seq35 conserva adaptação EN,
fonte/perfil, três idiomas unavailable e zero mídia/upload. Não há aceite Gemini.

Um ciclo concreto antecedeu essa falha: LT mudou `todas as vezes` para
`todas às vezes`; a revisão semântica desfez a crase, e LT voltou a apontar erro.
A [regra oficial6.6 AS_VEZES_BR](https://github.com/languagetool-org/languagetool/blob/v6.6/languagetool-language-modules/pt/src/main/resources/org/languagetool/rules/pt/pt-BR/grammar.xml#L821)
não verifica o contexto anterior. O cliente agora reconhece esse falso positivo
somente em pt-BR, na regra exata e no span `as vezes` imediatamente precedido
por `todas`. Erros adverbiais reais (`Eu as vezes...`), outras regras e idiomas
permanecem exigidos. O guardião continua revisando fatos, bloco e global.

Três regressões falharam antes da correção; sete casos contextuais passaram,
mais uma prova do guardião mantendo a frase intacta sem reparo. Dois testes
adicionais só executam com o runtime LanguageTool configurado, como no Actions;
skip local não comprova o serviço. A próxima validação limitada deve executar
esses testes reais e retomar os idiomas, sem trocar modelo por quota, alterar
caps/retries ou promover Gemini para produção antes do aceite completo.

O [run38659167207](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38659167207),
commit23a0334, passou1.190 testes no Actions, incluindo as duas provas com
LanguageTool6.6 real, sem skip. Tradução PT e três respostas semânticas foram
concluídas; a segunda rodada do gate recebeu429/resource_exhausted em chunk,
uma tentativa, contexto15.492 e RetryInfo85.047s. Snapshot final seq42 mantém
zero mídia e PT/EN/ES unavailable; nenhuma publicação. Não repetir Gemini antes
do prazo (aproximadamente21h de15/10, São Paulo), nem presumir qual cota terminou.
O filtro contextual isolado recebeu aprovação para produção após essa prova;
isso não libera a integração Gemini. A geração completa continua sem aceite.

## Troca definitiva solicitada em 16/10/2026

Main/57d7ed7 aplica a decisão atual do operador: Gemini em todas as etapas de IA,
inclusive tradução, com credencial própria e sem injetar Secrets Groq no fluxo
manual/agendado. Cota/erro Gemini não aciona Groq, Ollama, regras ou templates de
geração. Limpeza determinística e aprovações reutilizáveis continuam preservadas.

Suíte local:1.274 passes e dois skips exclusivos do runtime LanguageTool.
Revisão independente sem bloqueios após corrigir os fallbacks. A seleção
Groq das regressões antigas é explícita na fixture; novos testes retiram a
variável para comprovar o default Gemini, sem consumir nenhuma API real.

O [run38983801654](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38983801654)
foi iniciado na main com state_action=generate, idiomas=pt e apenas_gerar=true.
Retomou estado de produção, sem upload; não foi teste sintético. Passou1.276
testes no Actions, inclusive LanguageTool real, sem skips. Gemini completou a
tradução e nove chamadas semânticas, sem429/503 ou falha de schema. O roteiro PT
foi rejeitado após dois reparos. Encerramento assistido durante filtragem da
próxima fonte permitiu inspecionar os logs; checkpoint final production/seq120
preserva91IDs, três vídeos pendentes EN2/ES1 e12 estados rejeitados. Comparação
seq115/119 confirmou45arquivos imutáveis iguais e os11rejeitados anteriores
preservados. Nenhuma mídia Gemini nova. Cron permanece desabilitado.

Checagem somente leitura dos tokens OAuth locais em16/10 retornou invalid_grant
em PT/EN/ES. O registro versionado indica geração em09/10. Isso evidencia um
bloqueio de autenticação local além da geração LLM; não compara nem comprova
os Secrets do GitHub. Renovação exige login interativo do operador e não foi
feita. Nenhum token foi impresso, salvo ou enviado por essa checagem.

### Causa do ciclo de reparos identificada

O guardião aplicava cegamente a primeira sugestão LanguageTool antes da
rechecagem: parentalidade→parental idade em três ocorrências; Gemini desfazia
a separação e o LT repetia o achado. Também introduziu vê-las→as vês, reparado
depois pelo Gemini. Ao final, depois de→após foi tratado como erro crítico.

A regra oficial6.6 [DEPOIS_DE_APÓS](https://github.com/languagetool-org/languagetool/blob/v6.6/languagetool-language-modules/pt/src/main/resources/org/languagetool/rules/pt/style.xml#L4262)
pertence à categoria FORMAL, tipo style. O cliente descartava esse tipo e o
guardião não reconhecia essa categoria como estilo. Agora preserva issueType;
somente estilo explicitamente identificado avisa sem impor formalização.

[Parentalidade é dicionarizada](https://dicionario.priberam.org/parentalidade).
A exceção do léxico é limitada à palavra inteira exata, locale pt-BR e regra
MORFOLOGIK_RULE_PT_BR; grafias próximas, outros idiomas e regras continuam
bloqueados. Sugestões LT vão ao Gemini como hipóteses, sem aplicação automática
da primeira opção. Críticos não resolvidos continuam rejeitando; não se apagam
achados porque o Gemini aprovou. Sem alterar fatos/perfis ou reabrir rejeitados.

Suíte completa local do reparo:1.283passes e cinco skips do backend. O
[run38985741179](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38985741179)
terminou success, com1.288passes e zero skips, incluindo o LanguageTool6.6 real:
confirmou a regra spelling, preservou o vocábulo e o estilo sem ciclo, e manteve
erros próximos bloqueados. Somente testes/catálogo, namespace isolado, nenhuma
chamada generateContent nem mídia/publicação. A prova de mídia completa continua
pendente. Revisão independente aprovou o diff, sem Critical/Important.

### Teste de vídeo após integrar o reparo

Main/5ced683; [run38986158416](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38986158416)
retomou somente PT no namespace sintético validation-gemini-20261013. Passou
1.288testes reais, sem skips. A tradução Gemini passou o gate depois de um
reparo; o ciclo LT anterior não se repetiu. A naturalização também respondeu
completamente. Sua revisão global posterior recebeu429/resource_exhausted,
uma tentativa, contexto16.325caracteres e RetryInfo84.537s.

O prazo informado corresponde aproximadamente a17/10 às21h de São Paulo
(18/10 00hUTC); não prova qual subtipo de cota terminou nem garante liberação
nesse horário. Não repetir chamadas Gemini antes dele nem alternar modelo,
chave ou provedor para contornar a recusa. Gemini continua selecionado.

Checkpoint final seq47 mantém a fonte, o perfil e a adaptação EN, acrescenta
a tradução PT aprovada e conserva PT/EN/ES unavailable para retomada. Nenhuma
mídia ou publicação. O teste isolado não mudou production/seq120, os91IDs ou
os três vídeos reais pendentes. Publicação continua também dependente da
renovação OAuth interativa indicada acima. Cronfalse confirmado ao final.

## Renovação YouTube concluída após o teste

O operador concluiu os três logins em16/10, entre21h55 e21h57 de São Paulo
(17/10 00h55–00h57UTC). Os novos tokens passaram refresh e leitura da API.
O canal de cada token foi comparado aos IDs de canal dos vídeos já confirmados
na fila do respectivo idioma: PT Ah Voz do Reddit, EN The Voice of Reddit,
ES La voz de Reddit. As três comparações coincidiram antes de gravar Secrets.

YOUTUBE_TOKEN_PT, YOUTUBE_TOKEN_EN e YOUTUBE_TOKEN_ES atualizados no repositório
MoneyzxD/Automatic-Reddit-Git por stdin, sem imprimir tokens. Cópias locais
da produção e da raiz sincronizadas; datas de geração atualizadas. A falha
OAuth local anterior está resolvida. A checagem não publicou vídeos e não
executou nova chamada Gemini; o prazo de RetryInfo e o cron pausado permanecem.

## Retomada automática autorizada

O operador pediu restabelecer publicação automática após renovar os logins.
A fila real restaurada isoladamente de production/seq120 contém três vídeos
aprovados: EN duas partes de 50,784s e 92,793s; ES um vídeo de 154,233s. FFprobe
confirmou H264 1080×1920 e áudio AAC; três frames por vídeo permitiram conferir
cards e legendas legíveis. Isso não prova nova geração Gemini nem análise de
retenção. PT rejeitado permanece bloqueado.

O workflow permite publicar a fila aprovada quando geração falha, com testes,
restore e novo checkpoint de estado antes de efeitos externos. Uma janela por
`GEMINI_RETRY_NOT_BEFORE` impede chamadas de geração antes de
2026-10-18T00:00:05Z. A automação pode escoar estoque nesse intervalo. Provar
upload e ativação do cron continua distinto de provar nova geração completa.
