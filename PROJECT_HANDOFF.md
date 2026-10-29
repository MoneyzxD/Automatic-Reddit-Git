# PROJECT_HANDOFF.md

## Retomada — 29/10/2026, 14h de São Paulo

As duas rodadas anteriores terminaram: manual40797660200 (head4777aa2) e
cron40866173891 (headfe9390f). Geração falhou, mas publicação e save passaram.
Foram cinco uploads novos, todos confirmados pela API proprietária como
processados e no canal correto: PT2, EN3, ES0. Em29/10 às13h55, três estavam
públicos e dois agendados. Não repetir nenhum dos102IDs confirmados.
O checkpoint de entrada da nova rodada é40866173891-1-430.

Os relatórios finalmente registraram causa concreta da cota: OTPM com limite
1000 e pedido1024 em PT/tradução/chunk e EN/hook injetado/global. Teto de revisão
Groq reduzido para900; fatos/Gemini mantêm2048 e length continua bloqueado.
ES recusou título sem achados: recuperação opt-in também em título/hooks, dentro
das três candidatas já previstas; recusa vazia persistente continua unavailable.
Metadados continuam com uma candidata adicional.429/5xx/conexão/timeout da
geração não podem virar fallback e depois outra chamada; proteção compartilhada
em utils/llm_client.py para metadados e os três geradores públicos.

Outro incidente confirmado: o cron enviou EN às16h15UTC entre horários já
confirmados16h09 e17h40. A agenda agora considera os instantes existentes,
revalida janela e preserva90min entre publicações. O publicador limita o
resultado a hoje e a uma vaga excedente amanhã; o resto permanece pendente.
Não houve alteração de vídeos/horários já enviados ao YouTube.

Prova:24REDs novos (quota, recuperação, falha de geração e agenda),339testes
próximos e **1.581 completos** com LanguageTool real em84,71s; revisão sem achados.
Replay isolado do estado real mudou16h15 para19h10UTC, com90min de distância.
Auditoria:140arquivos com conteúdo imutável preservado (três só reserializados),
43idiomas encerrados inalterados e zero processing. Evidências privadas em
data/state/restauracao_20261027/{control_integrity_40866173891,
new_uploads_owner_check_20261029,schedule_replay_20261029}.json.

Correções implantadas em0720fc8. [Run40918218668](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/40918218668)
iniciado às14h07 de29/10, produção normal PT/EN/ES, meta3, Groq e publicação.
É o único gravador. EN já alcançou a meta e deve ser pulado pelo contador.
Monitor somente leitura na sessão exec **47988**, via write_stdin; encerra ao
concluir o run. Inicialmente passou FFmpeg e iniciou o aquecimento do LT.
Confirmar PT e ES reais; não declarar aceite integral só pelos testes.
Checkpoint434 às14h16: ES retomou1x5ugmy (metadados da parte2 pendentes),
EN continua com a meta3,102IDs preservados. Nenhum upload novo nesta rodada.

Correção adicional do tradutor pronta para a próxima rodada:1wybqga/PT no run
40797660200 retornou HTTP200, completion2048/teto2048 e length. O SDK enviava low
ao Qwen3.8; agora somente esse modelo Groq recebe none, como o guardião.
Cap2048, modelos/chaves, prompts, marcadores, idioma e rejeição de truncamento
preservados. Dois REDs de wire; seis casos de SDK (outros modelos e stop/length),
222testes próximos e **1.587 completos** com LT real em82,14s passaram. Revisão
sem achados. Raciocínio é hipótese causal apoiada no incidente do guardião;
eficácia real no tradutor ainda pendente. O run ativo0720fc8 não recebe o ajuste.
A sessão antiga de monitor41675 terminou com a interrupção; não existe mais.
Os registros abaixo são históricos e esta seção prevalece.

## Execução ativa — 28/10/2026, noite de São Paulo

[Run 40797660200](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/40797660200),
head **4777aa2**, iniciado pelo agente após o operador pedir novamente a retomada.
É produção real, PT/EN/ES, meta normal de três vídeos, Groq fixo e publicação habilitada.
Não iniciar outro gravador ou chamada avulsa de IA enquanto este run estiver ativo.
O bloqueio de revisão automática foi resolvido; commit/push e dispatch passaram.
O diagnóstico da chamada única ES já foi consumido com HTTP200; não repeti-lo.
Os 1.535 testes completos e a revisão anteriores correspondem ao código implantado.
Conferir progresso com o monitor abaixo, trocando o runID por 40797660200.
O último estado antes desta rodada é o checkpoint354, com 97 IDs preservados.
Ainda não há aceite desta execução. As seções seguintes registram o histórico.
Checkpoint **378**, conferido às00h25 de São Paulo em29/10: `1x5ugmy/PT`
está **exported**, com dois vídeos na fila; ES da mesma fonte está unavailable
por unexplained_rejection, com metadata_part1 aprovada e metadata_part2 pendente.
`1x9nddb/EN`, `1x9vb4m/EN` e `1x9w7n2/EN` foram rejected por qualidade;
`1wvcl31/EN` processa, com tradução/naturalização aprovadas.
Ainda sem upload novo; publicação ocorre após o lote.
Os97IDs anteriores continuam preservados. Monitor contínuo somente leitura
está na sessão exec **41675**; usar write_stdin para acompanhar, sem iniciar
outro monitor/gravação. Ele para quando o run termina. Main já inclui o novo
cron e a prioridade abaixo; o run ativo permanece em **4777aa2**.

Retomada parcial de metadados corrigida: a factory de descrição agora só roda
depois de consultar o checkpoint. Blocos são recompostos localmente quando
fonte/perfil/entrada/parte coincidem com a descrição aprovada. Antes, havia
chamada remota desnecessária para a parte1 antes de retomar a parte2. Um RED
reproduziu duas chamadas em vez de uma; a contraprova de entrada incompatível
continua exigindo duas gerações/revisões. Gate final, Gemini e indisponibilidade
preservados.182testes próximos e **1.541 completos** com LanguageTool real
passaram em78,05s; revisão independente sem achados. Não é prova de upload.

Recuperação estreita adicionada só às descrições: uma candidata extra da mesma
parte após rejeição fundamentada ou unexplained_rejection esgotado, com feedback
e nova revisão integral. Recusa vazia persistente continua unavailable. Falhas
do guardião por quota/timeout/503/LT/JSON e StateError não acionam regeneração.
Na geração de metadados Groq,429/5xx/conexão/timeout reconhecidos agora propagam
LLMUnavailable antes de template; isso evita repetir a geração após falha real.
Fallback por truncamento/sem chave e Gemini permanecem. Quatro RED de recuperação
e quatro RED de falhas da geração;188testes próximos e **1.556 completos** em
79,42s com LanguageTool real, revisão independente sem achados. Nenhuma chamada
real de IA foi executada nesses testes. Esta alteração só afeta a próxima rodada.

Auditoria de controle no snapshot377:43idiomas encerrados preservados;140arquivos
anteriores de fonte/perfil/etapas com conteúdo intacto.139idênticos em bytes e
um perfil apenas reserializado (JSON canônico idêntico, mesmo profile_id/fonte).
Prova: data/state/restauracao_20261027/live_control_integrity_40797660200.json.

Cron seguinte antecipado para 05h17 UTC (02h17 de São Paulo), minuto17 para evitar
hora cheia; mesma meta, janelas e concorrência. Oito disparos sob 09h UTC começaram
entre 13h e 15h39 UTC. Os 74 testes próximos passaram; conferência de fusos em julho/outubro/
novembro/janeiro preserva o mesmo dia nos três canais. Os rascunhos locais do
operador em AGENTS/README mantêm suas alterações e não integram este commit;
o horário vigente está no workflow e em docs/RESTORATION_20261027.md.
A revisão independente não encontrou bloqueios. O ajuste atinge o próximo cron;
a execução manual atual continua usando seu head 4777aa2.

Prioridade de retomada corrigida nesta continuação: linhas solicitadas já
pending/unavailable primeiro; depois idiomas ausentes de fontes com algum
exported; por último demais ausentes. Mantém datas das retomadas explícitas
sem antecipá-las pela data de extração de um idioma ausente. No snapshot367,
1x4uvxk/EN estava em8º, além do orçamento de seis; na cópia isolada corrigida
fica em1º, enquanto PT retoma1xf3poe e ES retoma1x6sq3x. A consulta não escreve
estado nem reabre terminais. Quatro RED antes;113testes próximos e **1.539
completos** passaram com LanguageTool real em79,42s; revisão sem achados.
Prova local: data/state/restauracao_20261027/selector_priority_probe_20261029.json.
O run ativo não recebe essa alteração; valerá na próxima retomada.

## Retomada — 28/10/2026

O [run 40772331493](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/40772331493),
head `c36770f`, foi cancelado pelo agente após os bloqueios de PT e ES, antes
de qualquer upload novo. Save final e logs passaram. Checkpoint **354**:
97 IDs e todas as rejeições anteriores preservados, 132 arquivos imutáveis
idênticos à baseline e zero linhas `processing`. Nenhum gravador está ativo.

PT/tradução/chunk e ES/título/global falharam por HTTP429/OTPM, mesmo com cap
1024. ES passou a naturalização, antes bloqueada. EN ficou sem matéria-prima
após 36 respostas 502/503 do arquivo gratuito. Não é falha OAuth: todos os
tokens foram renovados e validados em 28/10. Ainda não há aceite dos três idiomas.

Correção nova: `retry_candidates` inclui idioma ausente em fonte gerenciada,
como já faz `processing_languages`. Assim a retomada usa `source.json` sem raw.
Legado e estados existentes `rejected`/`exported`/`processing` seguem excluídos
no idioma solicitado. A consulta não altera estado ou perfil. Oito casos RED;
163 testes próximos e **1.517 testes completos** passaram com LanguageTool real.
Revisão independente sem achados. Implantado em **c6faba7**; o
[run 40779021584](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/40779021584)
terminou **success** em modo `verify`, com 1.517 testes em 28,89s, restauração e
verificação privada aprovadas. Não gerou, publicou ou escreveu checkpoint.
Automação continua habilitada, Groq fixo e meta3; isso não comprova disponibilidade
do provedor nem recuperação integral. Não há execução em andamento desta rodada.

O operador autorizou a chamada única Groq ES de `1x6sq3x`, após o bloqueio da
revisão automática. Executada uma vez, sem retries: HTTP200, resposta completa,
1,52s e cap1024. Título/fonte conferidos por SHA; ledger do checkpoint aprovado
de naturalização. Prova sem conteúdo/credenciais em
`data/state/restauracao_20261027/single_es_otpm_diagnostic.json`. A autorização
desse diagnóstico foi consumida; não o repetir. Sucesso isolado não confirma
continuidade nem informa números de OTPM, pois não houve recusa.

Diagnóstico numérico passivo no SemanticFailure pronto para a rodada normal:
apenas limite/uso/pedido/espera da mensagem 429 reconhecida, sem texto livre ou
alteração de retries. Valores finitos limitados; formatos parciais/ambíguos são
descartados. Um RED inicial e quatro RED de parsing; 345 testes próximos e
**1.535 completos** passaram com LanguageTool real em 74,87s. Revisão independente
confirmou fechamento dos achados. Próximo passo: implantar e executar a rodada
normal, aproveitando também a retomada de idiomas ausentes de `c6faba7`.

Implantação deste diagnóstico ficou bloqueada: a revisão automática de
permissões falhou por limite de uso antes de executar diff/add/commit/push.
Não classificou a ação como insegura. Não contornar a revisão por outro meio.
As mudanças estão locais, sem commit; HEAD remoto permanece `e4d666a`.
A chamada ES autorizada já foi executada uma vez e não deve ser repetida.
Nenhuma nova rodada foi disparada após o run verify 40779021584.

Monitor somente leitura, da raiz:

```powershell
& ".\.venv\Scripts\python.exe" "_export_repo_publico/data/state/restauracao_20261027/monitor_run.py" 40772331493
```

Computer Use foi interrompido pela ferramenta por não validar URL; não emitir
novas ações de UI nesta mesma rodada. Acompanhamento continua só por APIs/CLI.

## Reparos dos incidentes reais — 28/10/2026

Run40761430663 foi cancelado pelo agente para liberar os relatórios de três
recusas, antes de qualquer upload novo. Cleanup/save e artifacts passaram.
Checkpoint**40761430663-1-344** verificado:97IDs preservados, zero IDs novos.
1xg5u87/PT e1xfuywi/PT permanecem rejected(adaptation);1x9een7/PT permanece
rejected(translation), sem repetir seu upload EN. A quarta fonte1xf3poe/PT
terminou unavailable/dependency_unavailable quando LT parou no cancelamento;
retomável normalmente, sem reconciliação manual ou estado processing pendente.

Causas concretas: COMMA_COMPOUND_SENTENCE sinalizava " or" e a candidata local
só cobria a regra_2 com and/but/so. Agora testa a vírgula dessa regra exata+or,
sem mudar palavras e exigindo nova revisão LT/chunk/global. Em PT, TU_TI_EU_MIM
sugeria mim em "para eu nem precisar subir", apesar de eu ser sujeito do
infinitivo. Exceção estritamente pt-BR/regra/span/prefixo/sufixo desse caso;
erros reais da mesma regra permanecem, inclusive no mesmo texto. Não mudou
glossário, perfil, fonte, limites de revisão nem aprovação semântica.

Seis testes falharam antes da correção. Native6.6 confirmou o falso positivo
e a candidata EN; contraprovas preservam rejeição/indisponibilidade semântica.
Suíte final**1.506 aprovados em78,34s**, LanguageTool obrigatório real. Revisão
independente sem achados. Próxima rodada deve usar estas correções junto deD36.

## Rodada anterior — histórico de28/10/2026

Ajuste integrado/revisado emd36ae8a: o lote fixa
`PIPELINE_GROQ_WORKLOAD_LANGUAGE` no ambiente de cada filho único. Assim perfil,
adapter e revisão EN da fonte também usam a chave fixa PT/EN/ES da execução,
sem concentrar etapas comuns na chave EN. Não troca por cota; Gemini e fallback
genérico preservados. Sem override, comportamento legado mantém-se. Em empate
de vagas, o lote tenta quem teve menos tentativas: recusa PT dá vez a EN/ES.
**1.493 testes aprovados**, LanguageTool real obrigatório,74,98s; revisão sem
achados. O run abaixo usa9cdfc83 e não recebe esses dois deltas enquanto roda.

**Run40761430663**, head9cdfc83, executou produção com PT/EN/ES,
meta normal3, Groq, extração real e publicação habilitada. Não é dry-run nem
validacao_groq/meta1. Foi encerrado conforme o registro acima. O workflow usou
os três Secrets renovados em28/10. Link:
https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/40761430663

Run40760967107 passou no modo verify, com o código novo, suíte e restauração
privada reais. Não gerou ou publicou. O último snapshot conferido antes da
rodada preserva97IDs; monitor somente leitura em
data/state/restauracao_20261027/monitor_run.py aceita o runID e confere payload,
estados, progresso e preservação dos97IDs sem baixar mídia. Nenhum gravador
local de estado está ativo. A pasta é ignorada pelo Git.

## Retomada — 28/10/2026

Run**40596712855** concluiu coleta, geração e upload EN no Actions, com fonte
real **1x9een7**: https://youtu.be/U4WtiENWvjg. Confirmado em28/10 por API
autenticada: public/processed, canal EN esperado e oEmbed anônimo200. Não repetir
esse upload. O snapshot do run40718225099 preserva**97 IDs**, incluindo esse
vídeo e o PT H2XqpcQM_50. O estado partial da fila não invalida YouTube uploaded.

O cron**40718225099** falhou em ES/naturalization, fonte1x6sq3x, com429/OTPM
em três tentativas, mesmo com cabeçalho TPM geral indicando8000. PT/EN dessa fonte já estão
rejected e continuam fechados; ES está unavailable/retomável. Revisão de controle
da tradução ES aprovada, após recomposição da cota, passou em três chamadas com
cap2048; isso não prova que2048seja sempre impossível nem uma falha do YouTube.

Correção: lote executa um idioma por vez e pausa só a dependência afetada,
continuando os demais. Flag interna opcional --isolar-idioma distingue serviço
indisponível(código4) de StateError(código2, parada global). A CLI padrão e a
saída final do lote preservam código2 de indisponibilidade. Não tenta nova fonte
no idioma sem serviço. Meta3, excedente1, perfil/dedupe/gates seguem iguais.
Revisões Groq reservam1024tokens; fatos e Gemini conservam2048. Resposta truncada
continua bloqueada. Suíte completa**1.481 testes**, LanguageTool real obrigatório,
em79,48s; revisão independente sem achados. Implantação/teste real em andamento.

Operador renovou os três tokens da raiz com:
python scripts/reautenticar_youtube.py --all --github. Secrets atualizados em
28/10 às20:08–20:09UTC. Refresh real e channels.list confirmaram PT, EN e ES
nos canais esperados, inclusive ES comparado aos vídeos históricos. As datas
públicas foram sincronizadas para produção. Não precisa iniciar outro OAuth.
Prova local sem segredo: data/state/restauracao_20261027/renewed_tokens_check.json.

## Retomada automática em validação — 27/10/2026

O operador autorizou integrar as correções e restaurar a rotina dos três idiomas.
Veja [registro de implantação](docs/RESTORATION_20261027.md) para configuração,
provas e pendências atuais. Groq passa a ser seleção explícita da rotina via
`PIPELINE_LLM_PROVIDER`; Gemini continua disponível. A meta normal permanece3.
O fallback gratuito Arctic Shift recuperou20posts reais localmente após o403;
não recebe cookie, não inventa métricas e mantém filtros/perfil/dedupe/gates.
Suíte completa com LanguageTool obrigatório:1.472aprovados em75,02s.
Revisão independente sem Critical/Important. Ainda validar no runner.
PT/EN OAuth válidos; ES aguarda login do operador. Nenhuma fonte rejeitada
ou upload confirmado foi reaberto nesta implantação.

## Teste PT concluído — 27/10/2026

Vídeo público: **https://youtu.be/H2XqpcQM_50**, publicado às **18h57 de São Paulo**.
A API autenticada confirmou `public/processed` no canal PT esperado, e o oEmbed
anônimo retornou HTTP200. Foi enviado um único arquivo; para cumprir a decisão
do operador de publicar imediatamente, o mesmo ID foi antecipado do horário
calculado de 19h17. Não gerar nem enviar novamente esta história.

Execução93277 terminou com código0. Pasta:
`data/state/testes_pipeline_completo_pt/20261027_180920`. Fonte real **1x4uvxk**,
282 palavras, filtro85,30, coletada pelo Chrome autenticado com recibo e SHA.
Perfil preservou `source_gender=unknown` e voz feminina pelo desempate estável;
gravidez e relacionamento não foram usados para declarar identidade.

O MP4 final tem1080×1920 e92,276s. Whisper small local reconheceu280/286 palavras
correspondentes: diferença mediana43ms e p90 de110ms em relação aos tempos nativos.
Os270 eventos ASS não se sobrepõem e seus inícios correspondem às palavras nativas.
O corpo passou por reparos e revisão integral; a descrição usou template após
truncamento do Groq e também foi aprovada. Consumo registrado:94.247 tokens em42 chamadas.

Checkpoint privado **40351541446-1-305** confirmado. O payload foi baixado e lido
independentemente: preserva os95 IDs anteriores e acrescenta somente este, total96,
com horário real `2026-10-27T21:57:22Z`. A reconciliação95883 terminou com código0.
Workflow `pipeline.yml` está `active`; `PIPELINE_AUTOMATION_ENABLED=true` foi
conferido após o término. O aviso de fila parcial corresponde à outra plataforma,
não a falha do YouTube; seu estado é `uploaded` e o ID confirmado deve ser preservado.

Provas locais em `data/logs/` desta pasta: `resultado_publicacao.json`,
`comparacao_mp4_final.json`, `publicacao_imediata.json` e
`confirmacao_estado_publicacao.json`. O MP4 permanece em
`data/exports/pt/1x4uvxk_38c7b54483c2_1cea9f22756a/`.

Correções preparadas incluem recuperação de leitura privada, tradução Groq opt-in,
reparos de vírgula com nova revisão, exceção contextual de `valia`, regeneração
limitada da naturalização, identidade plural e correção de `Im15` confundido com
marcador masculino. Revisões independentes concluídas. A validação conjunta final
das áreas alteradas passou: **887 testes em47,41s**, sem falhas; `git diff --check`
também passou. Sessões93277,95883 e36478 encerradas com código0; nenhum teste
de geração/publicação desta rodada permanece em andamento.

**Limites:** alterações continuam locais, sem commit/push. Este aceite é de um
vídeo PT local com Groq; não comprova EN/ES nem a rodada agendada do Actions.
A coleta HTTP do Reddit ainda retorna403, inclusive na sonda com o cabeçalho
padrão. Gemini permanece configurado; sua última sonda retornou503. O aumento
do timeout de instalação FFmpeg ainda precisa de prova no runner. O próximo
trabalho é integrar/validar esses deltas no Actions e resolver a coleta automática.

As seções abaixo são histórico: as execuções de geração nelas citadas já terminaram.

## Teste ativo — 27/10/2026, 17h52 (São Paulo)

**Exec18519 em andamento**, pasta `data/state/testes_pipeline_completo_pt/20261027_175152`.
Comando da raiz: python testar_pipeline_completo_local.py --publicar --provider groq
--reddit-post _export_repo_publico/data/state/teste_publicacao_pt/reddit_browser_20261027_1800/post_1wv6wzv.json
--fora-da-janela. Acompanhar18519 antes de qualquer outro gravador. Autorização
pública imediata mantém-se; token/canal PT e estado privado já conferidos.
Fonte real1wv6wzv,263palavras, filtro71,97; autoidentificação me(26f) foi
conferida offline antes de persistir. Captura nova do JSON100 autenticado noChrome1,
íntegra com SHA e recibo; HTTP automático ainda não restaurado.

Reconciliação51571 terminou com sucesso: checkpoint**290**,1wvm7u7/PT
processing→rejected por assisted_profile_conflict, perfiloriginal/dedupe95IDs
intactos,sem partes/filas/upload. Workflow/var foram reativados antes do teste
atual,que pausa novamente enquanto escreve. Nunca retomar essa fonte rejeitada.
Revisão encontrou2P2 e ambos foram corrigidos: say/saying também são discurso
indireto,135testesperfilpassaram; script de reconciliação recusa Python-O antes
de imports/estado,provaexecutada. Revisão independente confirmou fechamento.
As demais correções/testes abaixo seguem válidos; nenhum commit/push nesta rodada.

## Retomada — 27/10/2026, 17h45 (São Paulo)

**64522 não está mais em execução**: interrupção da sessão às00h54 encerrou
o processo sem finally. ConferênciaCIM não encontrou Python/Java deste teste.
Último checkpoint local289; workflow continua disabled_manually/varfalse.
Nenhum MP4/upload novo.1wvm7u7/PT permanece processing; perfil persistido
unknown/female é incompatível com `we're two dudes both44m` na fonte.
Não retomar essa fonte com o perfil incorreto nem substituir o perfil imutável.

Correção no resolver: autoidentificação plural we are/we're two/both
men/women/dudes, fora de citação/hipóteses/discursoindireto.7casos novos,
2redantes;214testes perfil/voz/gates passaram. Perfis existentes intactos.
Revisão independente pedida a public_text_review, junto da reconciliação.

Preparado script único `data/state/teste_publicacao_pt/encerrar_tentativa_1wvm7u7.py`:
semflag sóconfere; --aplicar pretende processing→rejected por assisted_profile_conflict,
conservando fonte/perfil/95IDs e sem batch/upload, checkpoint antes de reativar
workflow/var originais. Primeira leitura67504 passou as provas anteriores e
falhou SQL por nome da tabela; corrigido para pipeline_parts, nenhuma mutação feita.
**Ainda não executar --aplicar sem concluir revisão e conferir resultados.**

Sonda mínima Gemini agora retornou503 (sem história/credencial na saída).
Próximo teste permanece Groq, com outra fonte íntegra e perfil conferido antes
de persistir. As correções anteriores continuam locais, semcommit/push.

## Execução atual — 27/10/2026, 00h52 (São Paulo)

**Exec64522 em andamento**, pasta `data/state/testes_pipeline_completo_pt/20261027_005135`.
Fonte real **1wvm7u7**,273palavras, filtro81,21, captura original Chrome/recibo
em `data/state/teste_publicacao_pt/reddit_browser_20261027_0047/post_1wvm7u7.json`.
Comando da raiz: python testar_pipeline_completo_local.py --publicar --provider groq
--reddit-post _export_repo_publico/data/state/teste_publicacao_pt/reddit_browser_20261027_0047/post_1wvm7u7.json
--fora-da-janela. Acompanhar64522; não iniciar outro gravador. Operador mantém
autorização de publicação pública assim que pronta. Helper permite agora
150–300palavras somente para a amostra local; filtros/limites de produção intactos.

96190 terminou sem mídia/upload, checkpoint287 confirmado;1x70tea/PT rejected
e permanece fechado, como1wvcl31/1xebjyt. Tradução PT foi aprovada na retomada,
mas naturalização bloqueou por LT GENERAL_GENDER_AGREEMENT_ERRORS em
`cada um valia150dólares`:6.6 lê valia como substantivo feminino e sugere
uma valia/um, valia; Groq chunk/global/language não propôs mudança.
Probe com instrução de reformular também devolveu no-op; prompt não foi alterado.

Correção contextual restrita no cliente LT: somente essa regra, pt-BR, span
um valia, precedente cada e subsequente número+dólares.415testes passaram,
2redantes, revisão limpa. LT6.6 real confirma achado bruto e filtro contextual.
Adicionada regeneração da naturalização em main/naturalizer: reutiliza o
checkpoint de3gerações já existente nos títulos, feedback da candidata/achados,
mesma tradução/perfil, cache somente após revisão integral aprovada. Indisponibilidade
não regenera.166testes quality/guardian/naturalizer/Gemini e9controles dohelper
passaram;2redantes; revisão independente limpa. Tudo ainda local/semcommit/push.

Conferência adicional preparada em `data/state/teste_publicacao_pt/conferir_mp4_final.py`:
quando houver MP4, chama Whisper small CPU local_files_only, compara fala do
MP4 com tempos nativos/ASS e escreve comparacao_mp4_final.json. Ainda não foi
executada nesta fonte porque a mídia não existe. OAuth PT válido,95IDs preservados.
Coleta HTTP automática continua403; amostra veio do navegador autenticado.
Correção timeoutFFmpeg está só local, não comprovada em CI.

## Retomada atual — 27/10/2026, 00h20 (São Paulo)

Exec **96190 em andamento** (retomada de7238), pasta `data/state/testes_pipeline_completo_pt/20261027_002017`.
Fonte real1x70tea,183palavras, filtro75,48, captura íntegra do Chrome autenticado
em `data/state/teste_publicacao_pt/reddit_browser_20261027_0020/post_1x70tea.json`.
Comando da raiz: python testar_pipeline_completo_local.py --publicar --provider groq
--reddit-post _export_repo_publico/data/state/teste_publicacao_pt/reddit_browser_20261027_0020/post_1x70tea.json
--fora-da-janela --resume20261027_002017. Acompanhar96190 primeiro; nunca iniciar outro gravador.
Este teste usa semantic_max_completion_tokens1024 só em memória; produção2048 intacta.

A tentativa6679 terminou sem mídia/upload: tradução PT real Groq200, mas LT
VERB_COMMA_CONJUNCTION exigiu `dela,` em `despesas dela quando formos para Nova York`.
Revisões chunk/global/language devolveram vazio, e o crítico do LT bloqueou.
Checkpoint277 confirmado; workflow/var active/true conferidos antes do teste atual.
95IDs preservados;1wvcl31/PT e1xebjyt/PT continuam rejected, não reabrir.

Correção estreita no guardião: quando LLM/glossário não propõem patches, só PT
e só essa regra podem testar a sugestão literal original+vírgula como candidata.
Orçamento existente e nova checagem LT+chunk+global obrigatórios; nenhum gate
ou regra desativado.409testes passaram,2falhas red antes, revisão independente limpa.
LT6.6 real confirmou remoção do crítico no candidato do incidente; isso ainda
não prova geração/publicação real. A fonte1x65oqv foi recusada pelo filtro57,8
somente no diagnóstico, não registrada. Nada commitado/enviado nesta rodada.

Correção CI local posterior: instalação FFmpeg180→300s, step8→10min, após
timeout124 real no download do mirror; lock/rede/retries/traps preservados.
8testes do shell/controlador passaram,1red antes, revisão independente limpa.
Não foi enviado nem comprovado no runner. Na execução7238, adaptação e fatos
EN responderam200 com teto semântico1024. A chamada facts da tradução PT
recebeu429OTPM nas3tentativas a61s;7238 terminou QualityUnavailable semmídia/upload.
Uma sonda mínima respondeu200 e a reprodução exata facts com os mesmos
source_units/modelo/chave/teto também respondeu200. Sem números de quota na
falha original, não presumir limite específico.96190 retoma a mesma fonte
unavailable com a adaptação aprovada; não reabre rejected nem reinicia fonte.

## Teste real atual — 26/10/2026, 23h55 (São Paulo)

Sessão exec **6679 em andamento**, pasta
`data/state/testes_pipeline_completo_pt/20261026_235446`, fonte real **1xebjyt**
(208 palavras, filtros72,22). Primeiro acompanhar essa sessão; não iniciar outra.
Comando da raiz: python testar_pipeline_completo_local.py --publicar --provider groq
--reddit-post _export_repo_publico/data/state/teste_publicacao_pt/reddit_browser_20261026_2353/post_1xebjyt.json
--fora-da-janela. Token PT confirmado; operador autorizou publicação pública
assim que pronta, fora da janela. Cron/workflow ficam pausados durante o teste.

Tentativa anterior47749 terminou na tradução PT: rejected,1grammar crítico,
nenhum batch/upload. Checkpoint272 preserva95IDs e essa rejeição permanece fechada.
Quarentena detalhada não chegou a ser escrita porque o checkpoint de rejeição
falhou antes da notificação; relatório de qualidade preserva contagem/reparos.
A pilha mostrou requests.RequestException no GET do recibo privado, não Groq/YT.
Workflow e variável voltaram a active/true ao terminar a tentativa anterior.

Correção local produtiva: PrivateStateStore repete só GET após falha de
transporte, até3tentativas, esperas2/4s e log só da classe; POST/TLS/allowlist/
hashes intactos.126testes state/snapshot/checkpoints passaram, red antes.
Modo Groq ainda traduzia por Google/MyMemory; Google falhou e a candidata
legada foi reprovada. ScriptTranslator ganhou opt-in groq_translation=True,
ligado só pelo helper real --provider groq; usa o mesmo cliente/prompt com
modelo fixo, bloqueia truncamento e mantém idioma/sentinelas/gates/cache.
Gemini e legado sem opt-in preservados.137testes translator/Gemini passaram,
duas regressões red antes; revisão independente limpa das duas correções.

Nova captura veio de JSON real de100posts no Chrome autenticado; arquivo/recibo
preservam texto/metadados e hash, sem modhash/cookie. HTTP Python continua403.
Outra candidata1x9rm0q ficou só em diagnóstico, recusada pelo filtro59,3;
não foi registrada no DB. Não reduzir filtros para usá-la.
Controles do helper:9provas passaram novamente com DB congelado no payload267,
pois o banco da primeira pasta avançou para rejected. Nenhum vídeo novo até aqui.
Mudanças ainda locais; nada foi commitado/enviado nesta restauração atual.

## Teste real em andamento — 26/10/2026, 23h17 (São Paulo)

PT renovado às 22h58: refresh e channels.list confirmaram o canal esperado;
metadado do Secret YOUTUBE_TOKEN_PT confirma atualização às 01h58Z de 27/10.
Token novo também foi copiado para secrets/ de produção, que continua ignorado;
data/oauth_token_status.json recebeu só a data PT e ainda não foi enviado ao Git.

Operador autorizou explicitamente publicar este teste assim que pronto, fora
da janela normal. Helper da raiz agora aceita --reddit-post com captura/recibo
e hash, mantendo texto, filtros e estados rejeitados; --fora-da-janela altera
só a janela em memória, preservando teto, intervalo e antecedência. Plano de
cada transporte registra horário/opções efetivos e proveniência do recibo.
Quatro provas locais passaram; revisão independente sem achados pendentes.

Execução real iniciada: pasta data/state/testes_pipeline_completo_pt/20261026_230559,
sessão exec 32171. **Primeiro acompanhar essa sessão; não iniciar outra em paralelo.**
Comando usado na raiz: python testar_pipeline_completo_local.py --publicar
--provider groq --reddit-post _export_repo_publico/data/state/teste_publicacao_pt/reddit_browser_20261026_2242/post_1wvcl31.json
--fora-da-janela. Se precisar retomar, acrescentar --resume 20261026_230559 somente
depois de conferir término, estado privado e ausência de envio incerto.

Workflow pipeline.yml está disabled_manually e variável de automação false
durante este teste para excluir concorrência. O finally do helper restaura
ambos após checkpoint seguro; se houver estado/envio incerto, reconciliar antes.
Restaurou os 95 IDs e o primeiro checkpoint já foi confirmado na release do
run40351541446/attempt1. Fonte real 1wvcl31, coleta assistida pelo Chrome;
coleta HTTP automática continua403. Groq confirmou perfil e adaptação com200;
revisões recebem429 intermitente e recuperam com200. Cadência existente de61s.
Atualização às 23h31: sessão32171 terminou com StateError após adaptação EN
aprovada. Finally confirmou checkpoint267 e reativou workflow/automação.
Head remoto267 confere com last_saved local, 95IDs, zero batch da fonte e
zero uploading. Só 1wvcl31/PT ficou processing; não tratar como rejected.
Helper ganhou diagnóstico seguro da localização/etapa do erro e recuperação
assistida --recuperar-processamento, somente junto de --resume/captura original.
Confere raw original/hash, fonte/perfil/cache, único processing e ausência de
batch/upload antes da transição processing→unavailable; checkpoint guardado
antes de retomar. Nove provas isoladas com cópias reais passaram; revisão limpa.
Às 23h33 a flag foi executada junto das opções anteriores e --resume20261026_230559:
sessão exec **47749 em andamento**. Recuperação confirmada e fonte/perfil
retomados. O workflow volta a estar pausado durante essa sessão. Primeiro
acompanhar47749, não repetir a execução. Nenhum vídeo novo gerado/publicado.

Log real do Actions40351541446 foi conferido: update do apt terminou, mas
install de ffmpeg/fonts atingiu timeout de180s, exit124. Tentava baixar94,1MB
do mirror azure.archive.ubuntu.com. Não foi erro de chave/API nessa execução.
Nenhuma correção de CI foi aplicada ainda; manter separado do teste local.

## Teste local até publicação solicitado — 2026-10-26

O operador confirmou a sincronização e pediu o teste real até publicação
pública. A preparação não publicou nem alterou a automação: variable continua
`true` e workflow `active`. OAuth PT ainda retorna `invalid_grant`; foi solicitado
login pelo helper **da raiz** `scripts/reautenticar_youtube.py --lang pt --github`.

Estado mais recente conferido: production/run40197727209/attempt1/seq264,
95 IDs confirmados, zero pendentes/incertos, 13 blobs. PT tem 11 estados
rejeitados e nenhuma retomada elegível; não reabri-los. Controle/recibo privados
estão em `data/state/teste_publicacao_pt/20261026_173735`.
Reddit real devolveu403 nos dois hosts, com bloqueio por segurança da rede;
PullPush devolveu429. Cookie da raiz presente e com expiração em08/03/2027;
validade do cookie não comprovou acesso. Foi perguntado se o navegador local
consegue abrir o Reddit com a conta conectada. Sonda curta GroqPT respondeu200;
Gemini3.8 respondeu503. Isso não comprova chamadas longas do guardião.

Helper local preparado na raiz: `testar_pipeline_completo_local.py`.
`--preflight --provider groq` para no OAuth antes de qualquer efeito externo.
`--publicar --provider groq` foi preparado, mas **ainda não foi executado**.
Usa fonte real curta íntegra, filtros/gates normais, estado privado verificado,
fila e Uploader; verifica o ID público/processado no canal PT. Para excluir
o gravador Actions durante o teste, desabilita temporariamente o workflow,
confere que os runs anteriores terminaram e restaura o estado anterior após
checkpoint seguro. Cada checkpoint também verifica exclusão e head remoto.
Retomadas preservam a fonte/hash e IDs enviados, sem repetir o transporte.
Revisão independente e verificações offline dos controles passaram; não são
prova de geração/publicação real. O teste aguarda OAuth PT e acesso ao Reddit.

Comparação local às 22h43: após renovar o cookie da raiz, página comum e JSON
continuaram com HTTP 403 pelo Python. No Chrome já autenticado, a página e **o mesmo
endpoint JSON** abriram sem desafio. Isso localiza a diferença no acesso do
cliente, mas ainda não comprova a causa exata nem restaura a coleta automática.
Uma fonte pública íntegra foi preservada por leitura do JSON exibido no navegador:
`data/state/teste_publicacao_pt/reddit_browser_20261026_2242/post_1wvcl31.json`.
São 165 palavras, score 73,48 nos filtros normais, sem ocorrência no baseline
das 17h37. `diagnostico.json` registra hash, método e limites desta evidência;
nenhum modhash/cookie foi salvo na captura. O helper completo ainda usa coleta
HTTP; essa captura é uma entrada assistida preservada, não integração concluída.
Às 22h45 o token PT ainda era o arquivo de 16/10; operador disse que fará a
renovação agora. Nenhum vídeo publicado ou estado remoto alterado nesta comparação.

A falha agendada40351541446 de26/10 ocorreu em **Instalar FFmpeg**, antes de
Python/restore/geração. Por isso não há release privada desse run; não atribuir
essa falha específica ao LLM ou YouTube. Nenhuma correção do workflow foi feita
nesta preparação local.

## Validação local de mídia — 2026-10-26

As correções abaixo ainda são locais; não comprovam recuperação do cron.
O teste EN gerou MP4, mas descartava os tempos nativos do Edge e estimava as
legendas após falha CUDA por `cublas64_12.dll` ausente. Agora conserva
`WordBoundary` do próprio áudio; Whisper repete em CPU se CUDA falhar durante
a transcrição. Sem tempos reais, a voz falha, inclusive no gTTS autorizado.
`edge-tts>=7.3.1` também corrige o HTTP403 reproduzido na versão 7.2.8.

EN corrigido: `data/state/testes_sincronia/en_20261026_141524/video_en_sincronizado.mp4`.
Transcrição independente em CPU do MP4 final encontrou 98,8% das palavras e
diferença mediana de 36 ms nos inícios (p90=77 ms). São medidas de alinhamento,
não revisão humana; um frame em 25,45 s também confirmou a legenda esperada.
O helper da raiz `testar_video_en_local.py` aceita `--lang pt`, usa estado
isolado e não publica. A primeira tentativa PT parou na tradução: a revisão
apontou concordância sem propor patch. O reparo dirigido existente agora recebe
também achados semânticos gramaticais literais únicos sem proposta, dentro do
mesmo orçamento e com revisão completa posterior. 328 testes dos gates, 151 dos
contratos semânticos e 23 de voz/tempos passaram; revisão independente sem achados.
O teste completo PT em `data/state/testes_locais_pt/20261026_143207_255391`
terminou indisponível na revisão global da tradução, após três HTTP429 do Groq.
Não alcançou áudio; o reparo gramatical ainda não tem aceite real desse fluxo.
Uma sonda pública Gemini3.8 em seguida terminou em timeout de 30 s.

O helper da raiz `testar_sincronia_pt_local.py` verifica somente mídia com texto
fixo público, sem LLM/DB/fila/upload. MP4 PT real gerado em
`data/state/testes_sincronia/pt_20261026_144316/video_pt_sincronizado.mp4`.
Whisper em CPU no MP4 encontrou 48/48 palavras, mediana de 32 ms e p90 de 98 ms;
os 40 eventos ASS estão alinhados aos tempos nativos e não se sobrepõem.
Isso comprova a sincronização da amostra, não a geração completa do roteiro PT.

O operador autorizou teste público posterior, mas pediu continuar só os testes
locais e renovar o token PT depois; refresh PT retornou `invalid_grant`.
Não publicar a história sintética nem alterar namespace para contornar esse gate.
Os resultados históricos abaixo não substituem este estado atual.

## Publicação restabelecida — 2026-10-13

Confiabilidade integrada em main. Run
[38344600714](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38344600714)
terminou success: sete vídeos recuperados enviados, zero falhas de upload
(PT3/EN2/ES2). Owner API conferiu todos os IDs processados nos canais corretos
e os publishAt; quatro já estavam públicos. Checkpoint final preserva 91 IDs
confirmados e nenhuma pendência de upload. Os 84 IDs anteriores foram mantidos.
EN/ES continuam com thumbnail403, com mídia preservada para ajuste sem reenvio.

Run normal [38425392437](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38425392437)
restaurou esse estado, mas não gerou mídia: quatro fontes foram rejeitadas nos
oito estados EN/ES. Cancelamento assistido após esse limite terminal preservou
o checkpoint final production/seq47, os 91 IDs e zero pendências de upload.
Não confundir a publicação recuperada com geração normal resolvida. Cron09UTC,
workflow ativo e PIPELINE_AUTOMATION_ENABLED=true conferidos. OAuth09/10 segue
Testing com renovação manual; não gerar novamente os tokens antes de necessário.
Main/0ad6654 também impede gTTS interno de ignorar a permissão de fallback:
VoiceGenerator controla exclusivamente as alternativas e o gênero. 1.104 testes
passaram; detalhes/evidência atual em [RELIABILITY_STATUS](docs/RELIABILITY_STATUS.md).
Operação, incluindo publish somente, em [PIPELINE_STATE](docs/PIPELINE_STATE.md).

Reparo seguinte corrige ancoragem de patches semânticos com offsets estimados
quando o trecho literal é único; ambiguidades continuam bloqueadas. Achados
gramaticais do LT sem sugestões chegam à revisão semântica, sem enfraquecer gates.
Expansões novas preservam parênteses de idade; retomadas conservam fonte/hash,
perfil e etapas antigas. Falhas falsas de fidelidade/gênero recebem instruções
mais precisas, não uma aprovação automática. Ainda exige rodada real verde antes
dos agentes de crescimento/manutenção.

Antecedentes abaixo são históricos e não substituem esta seção.
## Nota local preservada — 2026-10-13, antes do reparo do guardião

Código de confiabilidade integrado em main/0838bfd. Bootstrap e restauração de
production confirmados, com 84 IDs históricos preservados e 31 histórias/91 partes.
Run [38344600714](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38344600714)
terminou success: sete vídeos enviados (PT3/EN2/ES2), zero falhas de upload.
Owner API confirmou os sete IDs processados nos canais corretos e os horários;
quatro já estavam públicos na conferência. EN/ES mantêm pendência de capa403.
Run normal [38425392437](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38425392437)
foi disparado para completar a meta3/idioma, com restauração de estado pós-upload.
Resultado em acompanhamento. Cron09UTC e automação continuam habilitados.
Status/evidências atuais: [RELIABILITY_STATUS](docs/RELIABILITY_STATUS.md).
Operação de restore/publicar somente: [PIPELINE_STATE](docs/PIPELINE_STATE.md).

As retomadas e notas locais abaixo foram preservadas como histórico; suas
declarações de implantação/OAuth pendentes não substituem o estado atual acima.

## Retomada prioritária — 2026-10-09

Produção ainda não liberada. Fonte de status: [RELIABILITY_STATUS](docs/RELIABILITY_STATUS.md).
Main30a0a0c continua falhando antes do upload; HTTP antigo não permite atribuir
todos os incidentes à mesma causa. Refresh local dos três tokens YouTube
confirmado invalid_grant; operador deve renovar pelo script da raiz com
`--all --github --repo MoneyzxD/Automatic-Reddit-Git`. Não usar --github-only
com os tokens expirados, nem mudar datas de OAuth antes da renovação real.

Branchpipeline-reliability/2def796 contém preparoFFmpeg limitado/com diagnóstico
(provado no runner) e contexto semântico compactado sem perda de evidências
(1.064 testes/revisão independente; não prova editorial completa).
Run37965391481 isolado/test-story/PTENES/no-upload ainda em execução em17:39UTC:
EN/adaptação e PT/tradução/naturalização aprovadas; zero mídia. Monitor28534,
namespacevalidation-reliability-20261006-completion. Conferir seu resultado
antes de qualquer novo dispatch; não publicar histórias de teste.

Captura privada37962565002 do cache exato37953540179 preserva84IDs/7semID;
filas idênticas04/10, DB recente7histórias/0partes. Todos sete IDs seen atuais
já estão no candidato reconciliado30histórias/91partes, cujo digest permanece
igual. Não importar DB recente vazio de partes, apagar cache/IDs ou bootstrap
às cegas. Geração/inspeção/verify reais, bootstrap aprovado, main e rodada
normal ainda pendentes. Agentes/Plus ficam depois da recuperação operacional.

## Continuação atual — 2026-10-05

Atualização mais recente: run 37408357221/1947aee4 falhou na adaptação EN por
HTTP429, chunk, três tentativas e contexto de 16.695 caracteres. 959 testes
em 18,93s, LanguageTool, restore e save passaram. Sem mídia/upload; snapshot
privado verificado e production intacto. Consulta curta local EN, HTTP200/TPM
8.000, não prova igualdade com o Secret do Actions. Usage/Limits da conta EN
do runner solicitado ao operador; sem novo
dispatch ou troca de chaves/modelo. Consulte a seção inicial do status.
Monitores encerrados; produção ainda não foi liberada.

Atualização 2026-10-06: credencial limitada local funcionando. Cópia reconciliada
conserva84IDs/7pendentes; verify37407149313/af2f6f4 passou no Actions,955testes/
17.90s e restoreLinux/5arquivos/11blobs. Nenhuma geração/publicação/bootstrap
production/main. Sonda sintética ES única recebeu2fatos sem429; não comprova
lote. Status é a autoridade atual, inclusive para o diagnóstico dos reparosPT.
Registros abaixo são antecedentes; tokenlocalausente foi resolvido.

Retomada: run37379031931/ac74819 falhou na geração; PT tradução aprovada,
naturalização rejeitada por sequência de evento e ES revisão HTTP429.
Infra/testes/estado passaram, publicação pulada e checkpoint final sem mídia
preservado. Consulta sintética ES única em 2026-10-06 repetiu HTTP429, sem
subtipo/Retry-After. Sem novo dispatch, monitor ativo ou liberação main.
Revisão completa identificou três bugs corrigidos na branch: comandos TikTok
isolados de YouTube, filenames editoriais recuperáveis com proteção de
credenciais e upload bloqueado em namespace de teste independentemente de flag.
955 testes/33 avisos/89.36s, compile/diff e revisão pós-delta passaram. Ainda
não é prova de roteiro/mídia completos. Fonte/perfil/histórico conservados;
tokenfine local continua ausente. Consulte a seção inicial de
[RELIABILITY_STATUS](docs/RELIABILITY_STATUS.md) e o ledger antes de continuar.
Main/bootstrap/rodada normal/agentes aguardam os gates reais. Antecedentes abaixo.

Próxima versão isolada configura Qwen3.8 fixo só no guardião, com schema/gates/
chaves/cadência intactos. Suíte 896 passed/33 avisos/51.37s, compile/diff e
revisão independente passaram. Sonda longa pelo código real retornou três
grammar:warning, três chamadas semânticas, sem falha JSON; não é aceite completo
nem prova de superioridade. Actions segue em incidente: aguardar recuperação
antes de dispatch PT/EN/ES no namespace existente, sem upload. Main/bootstrap/
mídia/rodada normal/agentes permanecem pendentes; seção inicial de
[RELIABILITY_STATUS](docs/RELIABILITY_STATUS.md) é a autoridade do próximo gate.

Run atual `37370371919`/`b030bd6` retoma o namespace de validação anterior,
PT/EN/ES sem upload. Terminou failure sem runner ou etapas: anotação oficial
de hosted runner não adquirido. Actions major_outage/investigating20:47UTC;
aguardar recuperação antes de novo dispatch. Sonda de envelope alternativo
também falhou no contexto longo; não incorporada, sem fallback novo.
Probes adicionais 20B alternaram HTTP400/reason ausente e approved/sem achados;
nenhuma correção adicional ou causa factual isolada. Status/ledger são a
autoridade da retomada; produção/main permanecem intactos.

Run `37363161214`/`8628ed9` falhou em 10m11s: adaptação EN aprovada,
tradução PT indisponível após três HTTP400/json_validate_failed com geração
vazia. Sem mídia/upload; separação da fonte não chegou aos gates derivados.
Transporte SDK comprova strict/required/closed corretos; prova curta real
sintética passou em facts/chunk/global. Após autorização explícita, comparação
longa sanitizada executou duas chamadas, mesma chave PT: 20B rejected com um
factual:critical; 120B rejected com um factual:critical e um style:warning.
Ambos retornaram JSON parseável, sem reproduzir HTTP400. Só status/contagens
foram retidos; não concluir erro factual do original ou superioridade de modelo.
Não houve troca de modelo/Secret/gate nem integração main. Próximo diagnóstico
é conferir o achado concreto contra a fonte; limites no status/ledger.

Continuação: separação fonte/ledger corrigida após comprovar citações de JSON
nos gates derivados. Diagnóstico de referência agora tem subtipo enum, sem IDs
ou valores. 888 testes/33 avisos/45.19s, compile/diff check e revisão independente
passaram; falta validação real, não liberar main. Prepared antigo exige
reconciliação explícita; PT/ES rejected anteriores não são retomáveis. Próxima
rodada usa namespace novo isolado, sem upload/reset de produção. Detalhes e
limites na seção inicial de [RELIABILITY_STATUS](docs/RELIABILITY_STATUS.md).
Run main37349810900 também falhou na adaptação EN antes de mídia, sem classe
HTTP preservada; não diagnosticar por analogia. Antecedentes abaixo.

Correção autorizada de emissão e TPM enviada em `5aea94b`, só na branch isolada:
exemplo com todos os campos e cadência por recarga TPM entre etapas/clientes.
Schema/gates/chaves/orçamento preservados. 873 testes locais e revisão
independente passaram. Run `37338112115` aprovou tradução/naturalização PT,
sem HTTP429 registrado; título falhou por `reason` ausente em três tentativas.
Nenhuma mídia/upload. Gap de feedback reproduzido e corrigido em `3d65d84`:
retry agora recebe somente os nomes reason/start ausentes, sem valores/índices
ou preenchimento automático. 879 testes locais e revisão independente passaram.
Run `37341313520` passou 879 testes/18.09s, LT e restore/save; terminou failure
34m20s sem mídia/upload. Recusas JSON recuperadas; nenhum HTTP429 registrado.
PT/título e ES/metadados parte2 foram rejeitados por achados factuais. ES chegou
à divisão/metadados; EN aprovou tradução/naturalização e parou na coleta factual
do título, invalid_source_reference/3, HTTP ausente. Subtipo/IDs não capturados;
investigar antes de novo dispatch ou correção. Não chamar esses achados de
mesma causa anterior nem de defeito comprovado no código.
Consulte a seção inicial do
[status](docs/RELIABILITY_STATUS.md) para limites e aceite real. Bootstrap,
main, rodada normal e agentes permanecem posteriores à validação completa.
Os parágrafos abaixo preservam os antecedentes, não o próximo passo atual.

Diagnóstico estrutural aprovado pelo operador e enviado em `d173dd2`, só na
branch isolada. Suíte 856 passed/30 warnings/50.11s, 200 testes do guardião,
compilação/diff check e revisão independente passaram. Registra campos/tipos/
regras sem valores ou chaves desconhecidas; não altera schema, prompt ou gates.
Run `37331951705` passou testes/LT/estado, mas falhou PT/tradução por HTTP429/TPM,
três tentativas/Retry-After21s. Nenhuma mídia/upload; campo da recusa anterior ainda
desconhecido naquele run. Diagnóstico também retém recusas JSON intermediárias, antes
sobrescritas por sucesso/cota; 859 testes e revisão independente passaram.
Run `37333981612` comprovou a captura: revisão PT recebeu cinco achados sem
`reason`/`start` obrigatórios; HTTP400 preservado antes do HTTP429/TPM final.
859 testes/19.52s, LT e estado passaram; nenhuma mídia/upload. Próximo passo é
alinhar emissão ao schema e tratar cota separadamente, não enfraquecer gates.
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
### Notas locais preservadas

## Continuação atual — 2026-10-05

Atualização2026-10-06: run37408357221/1947aee4 falhou por HTTP429 na revisão da
adaptaçãoEN/chunk/trêstentativas/contexto16695. 959testes18.93s/LT/restore/save
passaram, semmídia/upload. Cópia privada verificada; production intacto.
Consulta curta localEN HTTP200/TPM8000 não prova igualdade com SecretActions.
Usage/Limits da conta EN do runner solicitado ao operador; watch encerrado,
sem novo dispatch/troca de chave/main. Status da worktree orienta continuação.

Rodada real Qwen `37379031931`/`ac74819` terminou failure22:15:58UTC;
API reconferida em 2026-10-06. Tradução PT aprovada, naturalização PT rejeitada
por alteração da sequência de evento e ES revisão HTTP429. Sem mídia/upload;
checkpoint final preservado. Reconciliação local conserva 84 IDs/7 pendentes;
credencial limitada local configurada em2026-10-06. Verify37407149313/af2f6f4
passou no Actions:955testes/restoreLinux/11blobs, sem geração/publicação ou
headproduction. Consulte status/ledger da worktree para validação corrente;
os monitores e a ausência da credencial nos antecedentes já foram encerrados.
Correções e evidências atuais estão na worktree `pipeline-reliability`, em
`docs/RELIABILITY_STATUS.md` e no ledger do plano. Main/bootstrap/rodada normal/
agentes continuam posteriores aos gates reais. Não usar gh amplo no bootstrap.
Os parágrafos abaixo são antecedentes, inclusive os monitores já encerrados.

Próxima candidata enviada: `ac74819`, branch/worktree `pipeline-reliability`.
Qwen3.8 fixo apenas no guardião, schema/gates/chaves/cadência preservados.
896 testes/33 avisos/50.94s na reconferência; compile/diff e revisão independente
passaram. Sonda longa real retornou três avisos gramaticais em três chamadas,
sem erro JSON registrado; não comprova geração completa. Actions permanece em
incidente: monitor ativo e dispatch PT/EN/ES sem upload somente após recuperação,
namespace `validation-reliability-20261005-source`. Espera condicional sessão
86228: confere SHA ac74819 antes de um único dispatch e acompanha com gh watch;
nenhum outro dispatch enquanto ativa. Consulte status/ledger da
worktree; mídia/bootstrap/main/rodada normal/agentes ainda não concluídos.

Retomada posterior: run37370371919/b030bd6 terminou failure sem qualquer etapa
ou runner (runner_id0): hosted runner não adquirido após várias tentativas.
GitHub Status API indica Actions major_outage/investigating20:47UTC. Aguardar
recuperação antes de outro dispatch; não atribuir esse resultado ao pipeline.
Sonda alternativa de saída também não comprovou estabilidade no trecho longo,
portanto não incorporada. Código/gates/modelo/produção preservados.

Última continuação: código `8628ed9` enviado só em `pipeline-reliability`;
separa narrativa do JSON factual nos gates derivados e diagnostica referências
recusadas com subtipo enum, sem valores/IDs. 888 testes/33 avisos/45.19s,
compile/diff check e revisão independente passaram. Run `37363161214` iniciou
PT/EN/ES real sem upload, namespace novo `validation-reliability-20261005-source`.
Terminou failure/10m11s: adaptação aprovada, tradução PT com três HTTP400 de
JSON/geração vazia; sem mídia/upload, gates derivados não exercitados. Prova
curta real passou. Comparação longa sanitizada posteriormente autorizada e
executada: 20B/120B retornaram JSON parseável e rejeição factual, sem reproduzir
HTTP400. Somente status/contagens retidos; não comprova erro do original nem
vantagem do 120B. Consultar ledger/status da worktree para próximo diagnóstico;
não liberar main/bootstrap/agentes. Prepared antigo exige reconciliação.
Run main37349810900 falhou na adaptação EN; diagnóstico antigo não preservou HTTP.
Os registros abaixo são antecedentes.

Retome na worktree `.worktrees/pipeline-reliability`; código enviado `3d65d84`.
Operador aprovou diagnóstico estrutural de JSON recusado, sem conteúdo privado
ou mudança de schema/gates. 859 testes e revisão independente passaram. Run
`37331951705` falhou por TPM/429; o diagnóstico agora preserva recusas JSON
intermediárias mesmo após sucesso/cota. Run `37333981612` comprovou a captura:
cinco achados sem `reason`/`start` obrigatórios, HTTP400 preservado antes de
HTTP429/TPM final. 859 testes/19.52s, LT/restore/save passaram. Nenhuma mídia,
publicação/reset ou integração em main. Correção autorizada alinhou o exemplo
de emissão ao schema e adicionou cadência por recarga TPM entre etapas/clientes;
schema/gates/chaves/orçamento intactos. 873 testes locais e revisão independente
passaram. Run `37338112115` aprovou tradução/naturalização PT, sem HTTP429
registrado; título falhou por reason ausente nas três tentativas. Nenhuma mídia.
Retry agora recebe nomes reason/start ausentes, sem valores/índices ou fabricação
de motivos. 879 testes locais e revisão independente passaram. Run `37341313520`
terminou failure/34m20s: 879 testes/18.09s, LT e estado passaram; recusas JSON
recuperadas, nenhum HTTP429 registrado. Sem mídia/upload. PT/título e ES/meta2
rejeitados por achados factuais; EN/título parou em invalid_source_reference/3,
HTTP ausente e subtipo não capturado. Investigar esses bloqueios antes de novo
dispatch/remendo. Testes não são aceite real; main/bootstrap/agentes pendentes.
Resultado e limites ficam no `docs/RELIABILITY_STATUS.md` dessa worktree.
Operador confirmou nenhuma publicação manual. Consulta ownerAPI e logs
anteriores sustentam reconciliação: 84 IDs históricos mantidos, sete pendentes,
91 kits e 56 tentativas de capa encerrados somente na cópia local. Snapshot e
restauração local passaram com 30 histórias/91 partes; originais preservados.
Nenhum head/importação production, integração main ou agente novo.

Run 37320307156 passou testes/LT/restore/save final; geração global EN falhou
por nonliteral_evidence/3, não HTTP429. Código a3b7f3a corrige o retry sem
feedback mantendo os gates; 812 testes locais e revisão independente passaram.
Run 37322711750 terminou verde, sem vídeo: repetição estilística LT tratada
como erro gramatical gerou ciclo. 12a48bf corrige categoria/avisos mecânicos;
823 testes locais e revisão passaram. Run 37324808064 aprovou adaptação EN,
mas PT/tradução falhou por HTTP400 json_validate_failed/1, sem mídia. 484a912
permite somente esse retry no orçamento atual; 832 testes/revisão passaram.
Run 37326768456 passou 832 testes/17.14s, LT e restore/save, mas falhou
PT/tradução: HTTP400/json_validate_failed após três tentativas. JSON válido/693
caracteres, campo incompatível desconhecido; nenhum vídeo/upload. Retry limitado
não resolveu a recusa. Retomar pela discussão do contrato e diagnóstico
estrutural sanitizado, antes de outro remendo/dispatch; manter gates intactos.
Token específico de estado está no Actions, não no .env local; configuração
solicitada sem segredo no chat ou uso da credencial ampla gh. Cron legado
continua habilitado; isso não libera a branch nova. Para resultado e próximos
gates, leia `docs/RELIABILITY_STATUS.md` e o ledger dessa worktree.

## Última retomada — 2026-10-04 à noite

Continue na worktree `.worktrees/pipeline-reliability`, branch enviada `6d59557`
(código da captura em `8be51cb`). Leia seu
`docs/RELIABILITY_STATUS.md` e ledger antes de agir. Capturas privadas
37238541263/37238543218 comprovaram perda de 28 histórias/91 partes no DB cache
recente; filas/84 IDs preservados, sete MP4 pendentes recuperados. Fontes dos
dois incidentes também recuperadas com hash original conferido. Validação nova
37237857551 ainda falhou antes de mídia por HTTP400; reprodução de uma fonte
falhou por citação não literal, inclusive com modelo maior. Suíte: 773 testes passaram.
Contrato factual precisa de revisão aprovada; nenhuma integração em main,
bootstrap production ou rodada normal nova foi realizada. Documentos dirty
deste checkout continuam pertencendo ao operador e devem ser preservados.

## Trabalho atual não integrado — retomada 2026-10-04

O plano de confiabilidade foi aprovado e está implementado na branch local
`pipeline-reliability`, worktree `.worktrees/pipeline-reliability`, base
`23f7f9c`, último commit enviado `12dd591` (código validado: `c36554a`). Retome nessa worktree pelo ledger
`.superpowers/sdd/2026-10-03-pipeline-reliability/progress.md`; tarefas 1–6
estão completas e a tarefa 7 ainda tem gates operacionais pendentes. Não
recomeçar o plano nem sobrescrever os documentos pendentes deste checkout.

A revisão independente apontou quatro falhas, reproduzidas e corrigidas:
sidecars SQLite no restore, fila legada sumida virando vazia, aliases de paths
Windows e continuação após upload incerto. Suíte final local: **745 testes
passando**, 29 avisos de depreciação, 90.80s; compilação e diff check passaram.
Nenhum teste novo equivale a geração/Groq/YouTube real.

`MoneyzxD/Automatic-Reddit-State` foi criado privado, e a variable
`PIPELINE_STATE_REPO` foi configurada em `Automatic-Reddit-Git`. Consulta apenas
de nomes dos Secrets em 2026-10-04 confirmou `PIPELINE_STATE_TOKEN` ausente.
O operador precisa cadastrar um token fine-grained limitado ao repo privado,
Contents read/write, como esse Secret no repo de produção; nunca enviar o
valor no chat. Depois: bootstrap reconciliado, geração PT/EN/ES isolada sem
upload, segundo run de restore/verify e somente então liberação de main.
Em seguida, o operador cadastrou o Secret e autorizou push/validação. Consulta
de nomes confirmou seu cadastro às 16:20:22 UTC; valor não acessado. A branch
`pipeline-reliability` foi enviada com commit `a91f475`, e o run `37216781914`
iniciou validação PT/EN/ES no namespace `validation-reliability-20261004`, com
história de teste e publicação desativada. A investigação das falhas atuais
foi registrada no backlog dessa branch, para depois destes ajustes.
Não houve merge em main nem mudança da automação de produção. Os agentes
de manutenção/crescimento permanecem fora da entrega. Leia as instruções
operacionais em `.worktrees/pipeline-reliability/docs/PIPELINE_STATE.md`.

Atualização operacional: o Secret limitado comprovou escrita/restauração real
nos runs 37217438115 e 37218385352; testes e LanguageTool passaram. Geração
parou antes de mídia por Groq HTTP400/json_validate_failed, modo facts, uma
tentativa. Schema estrito não resolveu a chamada real. Suíte local atual:
759 testes passando. Run 37219383922 está validando diagnóstico sanitizado
adicional, sem resposta bruta nos logs nem publicação. Produção/main continuam
intactos; bootstrap reconciliado e geração/verify reais ainda são pendências.

O run 37219383922 confirmou JSON válido, não erro de sintaxe. Probe isolado
mostrou rótulos fora do enum e uma citação com capitalização alterada. Prompt
de fatos/feedback agora pedem categorias válidas e cópia exata; schema e gate
não foram flexibilizados. Fixture de integração agora impede Groq real em
testes, mesmo com chave no ambiente. Suíte isolada: 763 passed/30 warnings em
49.76s. Último probe local recebeu 429 acima do orçamento de espera; chamadas
locais pararam. Run 37221057489 verifica a correção real no Actions, sem upload.

Resultado 37221057489: testes/LT/restore/save passaram, mas Groq respondeu
rate_limit/HTTP429 em facts após uma tentativa. Nenhuma mídia ou publicação.
Não repetir geração até a cota permitir. Run 37221464481 está verificando
somente o estado privado em outro runner, sem Groq/geração/upload. T7 ainda
não concluída; ajuste semântico, mídia e bootstrap reconciliado de produção
seguem pendentes. Falhas antigas de main permanecem no backlog da branch.

Verify 37221464481 concluído com sucesso em outro runner, commit c36554a:
estado de controle/fonte/perfil restaurado/verificado, sem Groq ou publicação.
Não é prova de mídia/upload. Retomada: esperar cota permitir geração real,
depois inspecionar mídia PT/EN/ES e reconciliar bootstrap de produção. T7
continua pendente; não repetir tarefas concluídas nem apagar heads/caches.

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
- TikTok mantém o desenho de kit Telegram/postagem manual, atualmente
  desabilitado por configuração; uma API automática depende de aprovação externa.
- Normalização de idioma no ponto de entrada; correções cirúrgicas sustentadas
  pela fonte, em vez de reescrita global ou promoção automática de regras.

## Retomada

Use `data/logs/script_quality.jsonl` e os JSONs de quarentena para investigar
reprovações, sem expor segredos. O artifact `logs-<run_id>` os preserva por
14 dias. Propostas de glossário exigem teste e revisão humana antes de entrar
em `config/contextual_glossary.yaml`.

## Release concluído e evidência

Em 2026-10-02, a revisão/correção final e integração/push foram concluídos;
`main` recebeu `30a0a0c7fdae31610099816b802c4d49f3041740`. A
[validação no Actions](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/37064703594)
terminou com sucesso: LanguageTool 6.6 real aquecido em PT-BR/en-US/es,
533 testes passando e dry-run PT/ES/EN. Publicação foi pulada deliberadamente;
o processo de fundo foi encerrado pelo passo de limpeza.
Resultado/logs desse run foram reconferidos em leitura em 2026-10-03.

Isso comprova infraestrutura/testes e simulação, não uma nova renderização
com revisão semântica real nem upload nessa validação. Oracle continua sem
execução real verificada. O erro 413 legado continua sem confirmação
operacional específica (ver `KNOWN_ISSUES.md`); análise de TPM usa telemetria
existente antes de justificar outro provedor ou mudança de orçamento.

## Antecedentes da recuperação

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
## Próxima fase: preparação de crescimento (2026-10-03)

Foram preparados [AI_WORKFLOW](docs/AI_WORKFLOW.md) e
[YOUTUBE_GROWTH_AGENT](docs/YOUTUBE_GROWTH_AGENT.md), com roteamento de skills,
baseline informado pelo operador, pontos de observação e proposta de coleta,
memória privada e experimentos independentes por idioma.
É preparação documental: nenhum coletor/agente, workflow novo, dependência
ou mudança editorial foi implementado. O próximo passo é revisar a arquitetura
com o operador, depois obter dados reais dos canais e especificar o MVP.
Não reiniciar o plano de narrador já integrado para realizar essa fase.

## Incidente real e prioridade de confiabilidade (2026-10-03)

O [run agendado 37128480329](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/37128480329)
falhou em `30a0a0c`: 533 testes e LanguageTool passaram, mas a revisão da
adaptação EN de `1wfduc8` terminou `unavailable`. Publicação foi pulada.
O relatório não preserva a classe da falha; retries do SDK não comprovam 429.

Reprodução isolada confirmou que HTTP 429 e JSON inválido produzem a mesma
mensagem genérica e que uma história inserida sem partes exportadas já é
considerada duplicada. Baseline local: 89 testes passando nas áreas de
guardião, lote diário e fila. Nenhum serviço Groq, render ou upload foi
testado nessa reprodução.

O operador autorizou avançar primeiro em confiabilidade e depois nos agentes.
A [spec de confiabilidade](docs/superpowers/specs/2026-10-03-pipeline-reliability-design.md)
registra diagnóstico/retry, retomada por idioma e recuperação privada de estado.
O desenho e a criação de `MoneyzxD/Automatic-Reddit-State` privado foram
aprovados. O [plano de implementação](docs/superpowers/plans/2026-10-03-pipeline-reliability.md)
está preparado e aguarda revisão/confirmação do método de execução. Nenhuma
correção de código nem criação externa foi realizada nessa preparação.
A credencial limitada ao armazenamento privado será fornecida pelo operador
na implantação; não reutilizar implicitamente a credencial ampla do gh.
Depois vêm implementação/regressões, bootstrap reconciliado e validação real
sem publicação antes da liberação normal.
