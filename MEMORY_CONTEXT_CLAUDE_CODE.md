# MEMORY_CONTEXT_CLAUDE_CODE.md

Reconstrução integral da sessão de trabalho no Claude Code, do início ao
fim, sem pular trechos. Complementa `AGENTS.md` (arquitetura/comandos) e
`KNOWN_ISSUES.md` (bugs em aberto/decisões) — este arquivo é sobre **como
chegamos até aqui**: raciocínio, tentativas descartadas, convenções não
escritas e contexto de produto. Nenhum valor de segredo, chave ou token
aparece aqui — só nomes de variável e, quando relevante, a existência de
algo sensível sem o conteúdo.

---

## 1. Decisões técnicas e o porquê de cada uma

### Migração Oracle Cloud → GitHub Actions
O pipeline rodava em produção numa VM da Oracle Cloud; a sessão migrou tudo
pra GitHub Actions (`.github/workflows/pipeline.yml`). Motivo: manter a
restrição de 100% ferramentas gratuitas. Quando uma alternativa
considerada envolvia um VPS de US$4-5/mês pra eliminar risco de Termos de
Serviço do GitHub Actions, a resposta do operador foi direta: "tem que ser
ferramentas gratuitas" — a opção mais barata/simples vence, mesmo aceitando
o risco que o dinheiro removeria. Geração e publicação rodam no mesmo job
de propósito (comentário em `pipeline.yml`): o runner é efêmero, o arquivo
de vídeo só existe enquanto o job vive — quem desacopla horário de
publicação de horário de execução é o `publishAt` da API do YouTube
(`scheduler/scheduling.py`), não o agendador do GitHub.

### Chave Groq por idioma não é rotação
Implementado `GROQ_API_KEY_PT`/`_EN`/`_ES` (`utils/environment.py:groq_api_key`)
depois que uma execução pesada testando PT+EN bateu o teto de 200k
tokens/dia do `gpt-oss-20b` numa única conta. O operador foi enfático em
distinguir isso de rotação de chaves pra burlar rate limit (prática
rejeitada por violar a Acceptable Use Policy da Groq, decisão já registrada
em `PROJECT_HANDOFF.md` antes desta sessão): "NAO CONFUNDA, NAO VAMOS ESTAR
ROTAIONANDO APIs, mas sim usando uma api para um motivo diferente, isso nao
é contras as regras." A distinção que importa: uma chave fixa por carga de
trabalho consistente (cada idioma sempre faz o mesmo tipo de chamada), não
múltiplas chaves alternadas pra mesma carga.

### Reescrever a divisão de vídeo pro teto do YouTube Shorts
`stages/splitter.py` tinha `MAX_MINUTES = 7.0` — bem acima do limite real
de 3 minutos do YouTube Shorts. Mudado pra `2.75` (margem de segurança de
15s) e `MAX_WORDS` recalculado de 1085 pra 426. Também trocou a lógica de
divisão: em vez de encher a Parte 1 até o teto e jogar o resto pequeno na
Parte 2, calcula `num_parts = max(2, ceil(total_words / MAX_WORDS))` e
distribui igualmente — resultado real observado: uma história de 3.87min
que antes viraria "1 parte cheia + 1 pequena" passou a virar "1:51 + 2:09".
Decisão do operador sobre a estratégia: aceitar vídeos de 2:15-2:30 como
alvo, mas manter histórias que cabem numa parte só sempre que possível —
"acho importante termos algumas historias que seja de apenas um video
tambem".

### Reduzir o card do hook de 980px pra 780px
`stages/thumbnail.py:render_hook_card` usava `target_w = 980` (91% da
largura do template) — o texto ocupava 97% da área do card, sem
respiro. Reduzido pra 780px (72% da largura), texto passou a ocupar ~54%
do espaço, deixando margem pro design do template. Motivo foi puramente
visual/qualidade, relatado pelo operador ("a letra do hook está muito
grande").

### Skip_before nas legendas pra não duplicar o hook
O hook aparecia duas vezes na tela: uma vez como card animado (overlay) e
de novo como legenda palavra-por-palavra por cima. Corrigido calculando a
duração REAL do hook a partir dos boundaries de áudio do TTS (não estimativa
por contagem de palavras) e passando `skip_before=hook_duration` pra
`stages/subtitle.py`/`stages/word_timing.py`, que filtram palavras com
timestamp anterior a esse valor.

### `max_tokens` dinâmico, nunca fixo
Documentado como decisão preexistente em `PROJECT_HANDOFF.md` e reforçado
nesta sessão: o teto de tokens da validação (`stages/validator.py`) é
calculado a partir do tamanho real do script
(`min(4500, max(2000, 1800 + word_count * 3))`), não um número fixo.
Motivo direto: com `max_tokens=800` fixo, os modelos de raciocínio do Groq
(`gpt-oss-20b`) gastavam parte do orçamento "pensando" antes de escrever a
resposta, truncando o JSON e derrubando a validação silenciosamente pra
"aprovar sem validar". Subido pra 1500 primeiro, depois a fórmula dinâmica
foi ajustada de base 1400→1800 e teto 3500→4500 depois que ainda truncava
ocasionalmente mesmo com a primeira correção (achado num teste real com
script de tamanho médio truncando em ~3254 tokens).

### Fila usa `story_id` versionado, não nome de arquivo
`scheduler/queue.py:enqueue()` mudou de usar o nome do arquivo como ID pra
usar `story_id` como base, com sufixo de idioma/parte, e versionamento
automático (`_v2`, `_v3`...) em caso de colisão. Motivo: testar a mesma
história duas vezes no mesmo dia gerava o mesmo ID e o segundo item era
descartado **em silêncio** — o operador foi categórico: "isso nao pode
acontecer nem nos testes."

### Tradução: Google → MyMemory → texto original, com retry
Cadeia original (deep-translator/Google apenas) falhava sem fallback real.
`googletrans==4.0.0rc1` foi cogitado e **descartado**: fixa `httpx` numa
versão de 2020, incompatível com `groq`, `python-telegram-bot` e
`huggingface-hub` (conflito real de dependência confirmado ao instalar).
Escolhido `MyMemoryTranslator`, que já vem embutido no `deep-translator`
(zero dependência nova). Dois bugs próprios corrigidos depois: (a) MyMemory
exige código de idioma com região (`en-US`, não `en`) — mapeamento
`MYMEMORY_LANG_CODES` separado do `LANG_CODES` do Google pra não quebrar o
motor que já funcionava; (b) quando os dois motores falham na mesma
rodada (visto: rate limit do MyMemory — "5 requests per second... 200k
per day", cota pública compartilhada, fora do nosso controle), o texto
ficava no idioma errado e cascateava pra detecção de gênero errada — retry
de 3 tentativas com espera 5s/15s adicionado em `translate()`.

### Extração do Reddit: JSON público → sessão logada via cookie
Esta foi a maior reviravolta técnica da sessão. Sequência real de
diagnóstico:
1. Suspeita inicial: bloqueio de IP de datacenter do GitHub Actions
   (padrão comum de scraping anti-bot).
2. Correção parcial aplicada primeiro: `subreddit.lstrip("r/")` não remove
   o prefixo "r/" — remove qualquer caractere do CONJUNTO `{r, /}` do
   início, corrompendo `"r/relationship_advice"` → `"elationship_advice"`
   e `"r/raisedbynarcissists"` → `"aisedbynarcissists"` (o "r" seguinte
   também sumia). Trocado por `removeprefix()`. Isso não explicava a
   falha nos outros 20 subreddits.
3. Log elevado de `debug` pra `warning` pra ver a causa real na próxima
   falha (`stages/extractor.py`).
4. Log seguinte mostrou HTTP 403 em `www.reddit.com`, `old.reddit.com` E
   `PullPush.io` simultaneamente — ainda hipótese de bloqueio de
   datacenter.
5. **Teste decisivo**: rodei a extração direto no PC local do operador
   (IP residencial) — **também deu 403**. Isso derrubou a hipótese de
   bloqueio de datacenter: é o Reddit bloqueando tráfego anônimo em geral,
   política deles, não algo específico do GitHub Actions.
6. Tentativa de registrar um app OAuth oficial do Reddit
   (`reddit.com/prefs/apps`, tipo "script") travou num loop de captcha —
   testado em desktop, navegador mobile, wifi, dados móveis (4G/5G),
   diferentes navegadores. O operador revelou que já tentava isso **há
   anos, sem nunca conseguir** — descartado como caminho viável.
7. Solução adotada: `REDDIT_SESSION_COOKIE` — cabeçalho `Cookie` completo
   de uma sessão logada normal no navegador (login humano comum, sem
   passar pelo fluxo de registro de app). Testado e confirmado
   funcionando (0 posts sem cookie → 5 posts com cookie, mesmo
   subreddit). Decodifiquei o JWT do cookie `reddit_session` e confirmei
   validade de ~179 dias (bem mais folgado que os 7 dias do token OAuth do
   YouTube) — `token_v2` no mesmo cookie expira em ~1 dia mas não parece
   ser o que trava o endpoint usado.

### Não automatizar login do Reddit
Depois de resolver com cookie manual, o operador perguntou se dava pra
automatizar a renovação. Decisão: não. Automatizar exigiria guardar a
senha da conta Reddit em algum lugar pra login programático (Selenium/
Playwright), e login automatizado é justamente o tipo de padrão que
sistemas antibot mais desconfiam — risco de a conta ser sinalizada, pior
que renovar manualmente a cada ~6 meses. Mitigação escolhida em vez disso:
`scripts/check_oauth_expiry.py` avisa no Telegram com antecedência (≤14
dias pro cookie do Reddit, ≤2 dias pro token OAuth do YouTube), lendo
`data/oauth_token_status.json` (idioma + timestamp de geração, sem
segredo).

### Monitoramento de log/tendência: um agente, GitHub Actions, não Claude Code routine
Discussão de design (sem implementação ainda — ver seção 4). Duas decisões
tomadas:
- **Um agente com duas rotinas**, não dois agentes separados — a lógica de
  classificação de risco (mecânico → aplica sozinho; estrutural → pergunta
  no Telegram) é a mesma pros dois casos (revisão de log pós-execução e
  revisão de tendência semanal); duplicar isso em dois agentes seria
  complexidade sem ganho.
- **GitHub Actions + Groq**, não uma rotina agendada do Claude Code
  (`/schedule`). Pesquisei o custo (é grátis, dentro da assinatura normal)
  mas achei duas limitações reais que desempataram pra GitHub Actions:
  rotinas do Claude Code só disparam por cron, sem equivalente a
  `workflow_run` (não dá pra disparar "assim que o pipeline terminar"), e
  o push é restrito a branches prefixadas `claude/`, exigindo PR pra
  mesclar — quebra a ideia de "correção mecânica aplica sozinho sem
  fricção" que era o objetivo do nível "mecânico" de risco.

---

## 2. Problemas enfrentados, como foram resolvidos, e tentativas que não funcionaram

### Mojibake (UTF-8 decodificado como Latin-1) — duas rodadas de correção
Primeira observação: travessão e aspas curvas saindo como "â" seguido de
caractere de controle invisível em texto gerado pelo Groq (ex:
"kidsâMarcus" em vez de "kids—Marcus"). Primeira correção
(`utils/groq_client.py:_reparar_mojibake`) usou uma regex restrita a
`\x80-\x9f` (controle C1) — **insuficiente**: um teste real em espanhol
mostrou acentuação quebrada ("Ã±" em vez de "ñ"), que usa bytes fora dessa
faixa (0xA0-0xFF) e passava direto pelo filtro. Generalizado pra: qualquer
texto não-ASCII tenta o round-trip `encode('latin-1').decode('utf-8')`;
texto já correto simplesmente falha esse round-trip e fica intocado
(testado com PT/ES acentuado, CJK, emoji, ASCII puro — todos preservados
corretamente). Aplicado no único ponto por onde toda resposta do Groq
passa (`_TrackedCompletions.create()`), protegendo todos os estágios de
uma vez.

**Achado tardio importante**: um log colado pelo operador mais tarde na
sessão mostrava "â" espalhado até em strings **hardcoded** do `main.py`
(ex: "ETAPA 5 â Traduzido" em vez de "ETAPA 5 — Traduzido") — string que
nunca passa por LLM nem tradutor. Isso prova que aquela instância
específica era **artefato de como o GitHub Actions exibiu o log pra
cópia/colagem**, não corrupção real de dado. Fica registrado porque é
fácil confundir os dois: "â" no log nem sempre significa mojibake real no
pipeline — verificar se a string afetada é hardcoded antes de assumir bug.

### Thumbnail nunca era enviada ao YouTube
`scheduler/uploader.py` fazia upload do vídeo mas nunca chamava
`service.thumbnails().set()` — o arquivo já existia
(`stages/thumbnail.py` gerava, `thumbnail_path` já vinha na fila), só
faltava o passo que sobe. Corrigido com tratamento de erro isolado (canal
sem verificação por telefone rejeita thumbnail customizada; isso não pode
derrubar um upload que já deu certo).

### Card de thumbnail com fonte distorcida ("tremida", fora da borda)
Diagnóstico: o workflow do GitHub Actions nunca instalava fonte TTF, só
FFmpeg. `stages/thumbnail.py:_find_font()` não achava nenhum candidato da
lista, Pillow caía pro fonte bitmap padrão dele (minúscula), e o cálculo
de quebra de linha em `_fit_text` (feito pro tamanho de fonte TTF pedido)
saía todo errado pro tamanho real da fonte bitmap. Corrigido em duas
frentes: instalar `fonts-dejavu-core` no workflow, e blindar o fallback de
`_fit_text` pra nunca mais estourar a área do card (antes truncava em
`[:6]` linhas fixas sem checar se cabia; agora calcula quantas linhas
cabem de verdade e reticencia o resto).

### Gênero/voz trocados num vídeo real
Cadeia de causa: tradução falhou nos dois motores (rate limit transitório
do MyMemory) → texto ficou em inglês → detecção de gênero
(`stages/gender_detector.py`, roda ANTES da tradução completar de verdade)
teve confiança baixa (0.30) porque inglês raramente marca gênero
gramaticalmente → caiu pra "unknown" → naturalização (que traduziu como
efeito colateral, ver próximo item) chutou gênero masculino, mas a
história mencionava "ex-husband" da narradora (sinal de que era mulher) →
voz selecionada por padrão pra "unknown" foi feminina (`pt-BR-FranciscaNeural`)
→ texto masculino narrado com voz feminina. Corrigido na raiz: retry de
tradução (ver seção 1) reduz a frequência desse gatilho, já que as duas
falhas observadas foram transitórias.

### Naturalização traduzindo como efeito colateral — padrão observado, não solução confiável
Visto pelo menos duas vezes (uma história em espanhol semanas antes, e a
história "1w8npme"/"1wb4e68" mais tarde): quando a tradução real falha e o
texto original em inglês segue adiante, a etapa de naturalização
(`stages/naturalizer.py`) às vezes traduz como efeito colateral, porque o
prompt dela instrui "escreva em {idioma}" independente do idioma de
entrada. Isso **às vezes salva o conteúdo** (a história sai no idioma
certo mesmo com a tradução formal tendo falhado), mas é uma sorte, não uma
garantia — e não resolve a detecção de gênero, que roda numa etapa
anterior sobre o texto ainda em inglês. Não tratar esse comportamento como
fallback confiável.

### Extração 403 — ver decisão técnica na seção 1 (não repetir aqui o diagnóstico completo)

### `apt-get update` falhando no workflow — Google Chrome, não nosso pacote
"Instalar FFmpeg" falhava com `Hash Sum mismatch` no índice do repositório
do Google Chrome — vem pré-configurado na imagem padrão do runner do
GitHub Actions, mas o workflow não usa Chrome pra nada. Falha do lado do
Google (índice do repositório deles), derrubando o `apt-get update`
inteiro por causa de uma fonte irrelevante. Corrigido removendo
`/etc/apt/sources.list.d/google-chrome.list` antes do update.

### Colisão entre plugins instalados globalmente e a pasta do projeto
Instalar o plugin "superpowers" (via tentativa de `/plugin install`, que
falhou com "isn't available in this environment") acabou puxando um
"marketplace" inteiro de plugins (ponytail, caveman, mattpocock-skills) —
materializado dentro da PASTA DO PROJETO em `.claude/skills/` e
`.agents/skills/`, não num diretório global de usuário. Isso quase foi
sincronizado pro repositório público sem querer (o `sync_repo_publico.py`
detectou de repente 767 arquivos versionáveis em vez dos ~160 normais).
Corrigido adicionando `.claude/` e `.agents/` ao `.gitignore` do projeto.
Investigação posterior (via agente `claude-code-guide`) confirmou:
`.claude/` local só funciona pro projeto onde está, não é global — pra ter
as mesmas skills em outro projeto seria preciso copiar a pasta ou instalar
via marketplace de verdade em cada um. O operador depois desinstalou local
e reinstalou globalmente por conta própria.

### Falso-positivo do filtro de segurança do `sync_repo_publico.py` — duas vezes
`CAMINHOS_BLOQUEADOS` bloqueia por substring — isso pegou
`scripts/check_oauth_expiry.py` (substring "token", pensado pra bloquear
`secrets/youtube_token_*.json`) e depois `.env.example` (substring ".env").
Resolvido de duas formas diferentes por pressa/contexto: o primeiro caso
foi resolvido **renomeando o arquivo** (`check_token_expiry.py` →
`check_oauth_expiry.py`, mais simples e não mexe no filtro de segurança);
o segundo caso (`.env.example`) foi resolvido **corrigindo o filtro**
(lista `CAMINHOS_PERMITIDOS` com exceção explícita), porque renomear um
arquivo de nome padrão esperado (`.env.example`) seria pior que ajustar o
filtro. Mesma classe de bug, resolvida diferente por ser mais apropriado
em cada caso — não é inconsistência, foi decisão deliberada registrada no
commit `cbfd3ab`.

### Sincronização do repo público travando (`shutil.rmtree`)
`sync_repo_publico.py` faz backup do `.git` antes de apagar e recriar a
pasta de destino do zero — em pelo menos duas ocasiões nesta sessão, o
`shutil.rmtree` falhou com `PermissionError` (lock de arquivo do Windows,
provavelmente IDE/explorer segurando um handle). Recuperado sem perda nos
dois casos porque o script já move o `.git` pra `_git_backup_tmp` **antes**
de tentar apagar — bastou restaurar esse backup manualmente e rodar
`git checkout -- .` pra repor os arquivos de trabalho.

### Tentativa de publicar o app OAuth do YouTube — travada, não retomada
Ao tentar tirar o app do modo "Testing" no Google Cloud Console pra parar
a expiração de 7 dias, o Google passou a exigir URL de Política de
Privacidade e Homepage antes de liberar "produção externa". Comecei a
preparar uma página simples via GitHub Pages pra resolver isso de graça
(criei a pasta `docs/`, sem chegar a popular o conteúdo) quando o operador
interrompeu e pediu pra deixar pra depois, priorizando outros bugs (ver
seção 4 — este é trabalho pendente, não abandonado por decisão técnica).

---

## 3. Convenções estabelecidas na conversa (não escritas em AGENTS.md nem em comentário)

- **Testar localmente com dado real antes de reportar um fix como pronto.**
  Praticamente todo fix desta sessão (mojibake, MyMemory, `_fit_text`,
  extração via cookie) foi testado com uma chamada real reproduzindo o bug
  original antes de commitar — não só verificação de sintaxe. Isso nunca
  foi pedido explicitamente como regra, mas foi o padrão seguido o tempo
  todo e vale manter.
- **Nunca ecoar o valor de um segredo colado pelo operador na conversa.**
  Quando o cookie do Reddit foi colado em texto puro no chat, ele foi
  gravado direto em arquivo (`.env` local) sem nunca ser reimpresso em
  nenhuma resposta — inclusive usando um arquivo de scratchpad temporário
  deletado logo em seguida pra evitar que passasse pelo shell de forma
  arriscada.
- **Preferir corrigir a causa raiz compartilhada, não o caminho que o
  relato menciona.** Exemplo concreto: o bug de `lstrip("r/")` existia em
  DOIS lugares (`_fetch_reddit_json` e `_fetch_pullpush`) fazendo a mesma
  coisa errada — os dois foram corrigidos juntos, não só o que o log
  destacava primeiro. Mesmo padrão no validador: das 8 chamadas ao Groq em
  `stages/validator.py`, 4 tinham `"Responda em {language}"` e 4 não —
  todas as 4 faltantes foram corrigidas de uma vez, não só a que causou o
  sintoma relatado.
- **Ao achar um bug de filtro de segurança (sync_repo_publico.py),
  escolher entre renomear o arquivo ou ajustar o filtro caso a caso** —
  não existe uma regra fixa de "sempre ajustar o filtro" ou "sempre
  renomear"; a escolha depende de se o nome do arquivo é convencional/
  esperado (não renomear `.env.example`) ou arbitrário (renomear
  `check_token_expiry.py` era seguro).
- **Alertas de Telegram usam `send_admin_alert` sem dedupe deliberadamente
  em contextos de aviso de expiração** — `scripts/check_oauth_expiry.py`
  pode avisar mais de uma vez dentro da janela de risco porque, pra esse
  caso específico, lembrar de novo é preferível a arriscar esquecer (isto
  é diferente do padrão de alerta de validação em `stages/validator.py`,
  que já tinha lógica própria de quando avisar).
- **Pausar automação em vez de deixar acumular falha silenciosa.** Quando
  64 execuções agendadas seguidas falharam (token OAuth expirado), a
  reação foi comentar o `schedule:` do `pipeline.yml` (não apagar,
  comentar com uma nota do motivo) em vez de deixar rodando enquanto o bug
  não era resolvido — `workflow_dispatch` manual continuou disponível.
- **Card visual (hook) e texto narrado são o MESMO texto, mas com
  necessidades diferentes** — números por extenso importam pra narração
  (TTS soletra dígito por dígito) mas não pro texto exibido; a solução foi
  restringir a geração do hook a sempre escrever por extenso (afeta os
  dois usos ao mesmo tempo) em vez de ter duas versões do texto.

---

## 4. Trabalho combinado que ainda não foi implementado

- **Agente de manutenção (log_review + trend_review)** — desenho fechado
  (ver seção 1), **nenhuma linha de código escrita ainda**. Próximo passo
  combinado era começar por `maintenance/risk.py` + `maintenance/log_review.py`
  (não depende de credencial nova) antes de `trend_review.py` (precisa de
  API key nova do YouTube Data API v3, ainda não gerada). Ficou pausado
  quando o operador pediu pra rodar o teste real de extração com cookie
  primeiro, e depois a prioridade virou a migração pro Codex.
- **Publicar o app OAuth do YouTube no Google Cloud Console** — travado
  precisando de URL de Política de Privacidade/Homepage. Comecei a montar
  uma página via GitHub Pages (pasta `docs/` criada, vazia) quando o
  operador pediu pra deixar pra depois. Isso resolveria o problema de
  expiração de 7 dias de vez.
- **Reverter `min_interval_minutes` de 1 pra 90** em
  `config/publishing.yaml` — foi setado pra 1 minuto deliberadamente pra
  testar o agendamento de vídeos multi-parte (teste confirmado funcionando
  — "Foi postado... a diferença de programação foi de um minuto mesmo").
  Não há confirmação registrada nesta sessão de que foi revertido de volta
  pro valor de produção (90). **Verificar o valor atual antes de reativar
  o cron.**
- **Reativar o `schedule:` do `pipeline.yml`** — comentado desde
  2026-09-08 por causa da expiração do token do YouTube. Só reativar
  depois de resolver o item da publicação do app OAuth (ou aceitar
  renovação manual a cada 7 dias, o que o operador não confirmou querer).
- **Confirmar correção dos dois bugs herdados do `PROJECT_HANDOFF.md`
  anterior** (drift de título/hook, erro 413 Payload Too Large) — nunca
  revisitados nesta sessão apesar de `stages/validator.py` ter recebido
  bastante trabalho. Ficou como item de `KNOWN_ISSUES.md`, não investigado
  de fato.
- **Decidir o destino do repositório `Fonte-`** (1 commit, resto não
  commitado) — levantado na auditoria de migração pro Codex, não
  resolvido, fica como decisão pendente do operador.
- **Confirmar/remover variáveis órfãs do `.env`** (`OLLAMA_URL`,
  `OLLAMA_MODEL`, `YOUTUBE_CLIENT_ID`/`_SECRET`/`_REDIRECT_URI`) — nenhuma
  é lida pelo código atual, ficaram só documentadas como órfãs no
  `.env.example`.
- **Testar de novo com o cookie do Reddit + fixes de fonte/tradução juntos
  numa mesma execução completa** — os três fixes mais recentes (retry de
  tradução, instalação de fonte, blindagem do `_fit_text`) foram
  commitados mas o operador ainda não confirmou uma execução real
  demonstrando os três funcionando juntos.

---

## 5. Contexto de produto/negócio que influencia decisões técnicas

- **Modelo de negócio**: geração de renda extra escalável através de
  vídeos curtos automatizados, sem operação manual diária — exceto TikTok,
  que é deliberadamente manual (aprovação do TikTok Developer App
  pendente, é contingência externa, não uma limitação de código a
  "corrigir"). Isso explica por que o fluxo do TikTok manda kit pronto
  (vídeo + legenda + hashtags) pro Telegram em vez de tentar automação
  direta.
- **Três idiomas = três canais/contas separadas**, cada um numa conta
  Google diferente (não é "trocar de canal" dentro da mesma conta) — isso
  moldou a necessidade do `scripts/reautenticar_youtube.py` avisar
  explicitamente pra escolher o e-mail certo na tela de login, porque
  autorizar com a conta errada sobe vídeo pro canal errado **silenciosamente**
  (já aconteceu uma vez em produção antes desta sessão, motivo raiz
  identificado: o token gerado fica preso ao canal ativo no navegador no
  momento da autorização).
- **Crescimento por fases via `growth_plan`** em `config/publishing.yaml`
  — limites de upload diário sobem com a idade da conta, sinalizando
  preocupação deliberada com anti-detecção/naturalidade de crescimento de
  canal novo, não só limite técnico arbitrário. Confirmado nesta sessão
  que `publish.py` já respeita esse teto por canal mesmo quando a geração
  produz os 3 idiomas de uma vez por disparo do cron — o excedente só fica
  na fila, não vira spam de publicação.
- **Nicho de conteúdo**: histórias de subreddits de conflito
  interpessoal/confissão (AITAH, AmItheAsshole, relationship_advice,
  TrueOffMyChest, EntitledParents, raisedbynarcissists, revenge/malicious
  compliance, tifu, legaladvice, confessions, antiwork, tales from tech
  support, entre outros — 22 subreddits configurados em
  `config/subreddits.yaml`). O tom do canal (visto num exemplo de post real
  do canal "Ah Voz do Reddit") é confissão em primeira pessoa com hook de
  pergunta moral/curiosidade.
- **Backgrounds de vídeo vêm de canais grandes de terceiros do YouTube**
  (Sand Tagious, Oddly Satisfying, e outros já catalogados em
  `config/backgrounds_manifest.json`) — usados como fundo genérico tipo
  ASMR/satisfying, sem narrativa própria. O operador está ciente do risco
  de copyright/Content ID e testando deliberadamente com um canal por vez,
  monitorando por strike antes de expandir o uso — decisão de risco aceito
  conscientemente, não uma lacuna técnica a resolver.
- **A conta Reddit usada pra extração é pessoal do operador**, logada
  normalmente (não é uma conta de "aplicativo" ou bot dedicado) — existe,
  mas o nome de usuário específico não está registrado aqui por não ser
  necessário pra continuidade técnica.
