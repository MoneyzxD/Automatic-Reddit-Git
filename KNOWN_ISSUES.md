# KNOWN_ISSUES.md

Bugs, decisões deliberadas e contexto que só existiam em conversa/memória
antes desta migração. Gerado na migração Claude Code → Codex CLI
(2026-09-11) a partir do histórico real de trabalho, não de suposição.

## Em aberto — precisam de ação

### Recuperação privada — implementação local, rollout pendente (2026-10-03)

Na branch `pipeline-reliability`, estados aditivos por idioma e fonte/checkpoints
privados corrigem o dedupe prematuro; uploads incertos bloqueiam reenvio e a
confirmação precede capa/limpeza. Não confundir isso com implantação concluída.
O repositório `MoneyzxD/Automatic-Reddit-State` foi criado e verificado privado.
Faltam credencial limitada, bootstrap reconciliado e validação real do Actions.
Leia [PIPELINE_STATE](docs/PIPELINE_STATE.md) para recuperar sem apagar histórico.

Revisão de código e correções locais verificadas em 2026-10-04: 745 testes
passando. Restore conserva e bloqueia sidecars SQLite residuais; aliases de
paths entre Linux/Windows são rejeitados antes de mutar o destino. Fila ausente
em estado obrigatório bloqueia snapshot em vez de virar vazia. Upload incerto
interrompe a rodada e bloqueia novos envios do mesmo idioma até reconciliação.
Essas proteções ainda não foram liberadas em produção.

A validação isolada 37217438115 confirmou armazenamento/restauração privados,
mas a geração parou no Groq: HTTP 400, `json_validate_failed`, modo facts,
contexto de 4002 caracteres, uma tentativa. É falha real do formato de saída
JSON, sem evidência de 429 nesse teste. O guardião agora usa schema estrito
nos modelos GPT-OSS 20B/120B, mantendo as verificações locais de citação literal,
gênero e fatos. O run 37218385352 repetiu a mesma rejeição mesmo com schema
estrito; portanto esse ajuste não comprovou resolução. Diagnóstico sanitizado
da geração recusada identifica sintaxe/tamanho/posição sem salvar seu conteúdo.
Run 37219383922 confirmou sintaxe válida. Probe local encontrou kind fora do
enum e citação com capitalização alterada. Prompt e feedback de retry foram
ajustados, sem relaxar schema/parser/citação literal ou aumentar orçamento.
Último probe local recebeu 429 com espera acima do permitido; não contornar
cota com troca de chaves nem tratar testes falsos como prova da correção real.
O Actions 37221057489 também encontrou HTTP429 no facts; restore/save e 763
testes passaram, sem gerar/publicar. Aceite real do ajuste continua bloqueado
pela cota; não liberar main por teste unitário verde. Isso não diagnostica
retroativamente os runs antigos de produção, ainda listados no backlog.
Outros modelos configurados conservam JSON object e podem ter a mesma limitação;
não há troca automática de modelo, chave ou aprovação por fallback.

O run 37128480329 não preservou a classe da indisponibilidade semântica de
`1wfduc8`; retries não comprovam 429. Novas chamadas classificam HTTP/timeout,
JSON/schema e evidência literal sem body bruto. Sem fonte original íntegra,
essa história legada não pode ser reconstruída da quarentena redigida.
Processing abandonado e head incerto ainda exigem recuperação assistida;
não há CLI de edição automática de heads nem cleanup de releases habilitado.

### 1. Token OAuth do YouTube expira a cada 7 dias
O app OAuth no Google Cloud Console está em modo **"Testing"**, não
publicado. Nesse modo, todo token de refresh expira sozinho em 7 dias,
sem aviso da API — a falha só aparece quando um upload dá
`invalid_grant: Token has been expired or revoked`.

- **Correção definitiva**: publicar o app (Google Cloud Console → Google Auth
  Platform → Audience → "Publish app") e depois gerar novamente os três
  tokens. Para uso pessoal com menos de 100 usuários, a documentação do
  Google dispensa a verificação completa; permanece a tela de app não
  verificado e o limite vitalício de 100 novos usuários.
- **Mitigação já implementada**: `scripts/check_oauth_expiry.py` avisa no
  Telegram quando faltarem ≤2 dias pro limite, lendo
  `data/oauth_token_status.json` (gravado por
  `scripts/reautenticar_youtube.py` a cada renovação manual).
- O gatilho diário está ativo com `PIPELINE_AUTOMATION_ENABLED=true`, mesmo
  enquanto o OAuth está em Testing, por decisão do operador. Renove os três
  tokens manualmente a cada sete dias (ou quando chegar o alerta do Telegram)
  e envie-os aos Secrets do repositório. `YOUTUBE_OAUTH_PUBLISHING_STATUS`
  permanece `testing` até o app ser publicado.

### 2. App OAuth do Reddit — não insista em tentar de novo
Anos de tentativa de criar um app tipo "script" em `reddit.com/prefs/apps`
falharam num loop de captcha — testado em desktop, mobile, wifi, 4G/5G,
diferentes navegadores. **Sem confirmação de causa exata** (pode ser
restrição da conta Reddit específica, não do processo em si). A solução
em produção é sessão logada via cookie (ver `AGENTS.md`), que já funciona
e dura ~6 meses. Não proponha "vamos tentar de novo o registro OAuth" sem
o operador pedir explicitamente — já foi tentado exaustivamente.

### 3. Repositório principal (`Fonte-`) nunca foi commitado de verdade
A pasta raiz do projeto é ela mesma um repositório git
(`origin: github.com/MoneyzxD/Fonte-`, branch `clean_branch`), com **um
único commit** (`9533f07 feat: pipeline limpo sem videos`) e praticamente
todo o código atual como mudança não commitada. O repositório que
realmente recebeu todo o trabalho desta sessão é
`_export_repo_publico/` → `github.com/MoneyzxD/Automatic-Reddit-Git`
(branch `main`), sincronizado manualmente via `python sync_repo_publico.py`
+ commit/push dentro daquela pasta.

Isso significa: **`Fonte-` não é uma cópia de segurança confiável** — se
a pasta de trabalho for perdida, o único histórico real de código está no
`Automatic-Reddit-Git`. Decida antes de prosseguir: (a) commitar o estado
atual do `Fonte-` como está, (b) abandonar o `Fonte-` e tratar
`Automatic-Reddit-Git` como o único repositório oficial, ou (c) outra
estrutura. Isto **não foi decidido nesta migração** — só documentado.

### 5. Erro 413 Payload Too Large (herdado, status não confirmado)
Do `PROJECT_HANDOFF.md` anterior: erro 413 quebrando loops de correção
cirúrgica de forma silenciosa (sem confirmação de correção). Não foi
revisitado nesta sessão. **Ação**: procurar tratamento de exceção em torno
das chamadas de `apply_surgical_fix`/`apply_title_hook_fix`/
`apply_metadata_fix` em `stages/validator.py` e confirmar se um payload
grande é tratado (chunking, redução de contexto) ou só falha.

### 6. MyMemoryTranslator tem rate limit público apertado
Visto em produção: `Server Error: You made too many requests... 5
requests per second and up to 200k requests per day`. É a cota
**compartilhada globalmente** da API gratuita do MyMemory, não algo sob
nosso controle direto. Mitigado com retry (3 tentativas, 5s/15s) em
`stages/translator.py`, mas pode voltar a acontecer em dias de pico da
API. Se isso continuar sendo problema recorrente, considerar outro motor
de fallback gratuito.

### 7. YouTube recusa thumbnail com 403 mesmo após upload do vídeo

Confirmado no run `34920391659` (15/09/2026): vídeo `0VpyD1Vms60`
publicado, JPG gerado, mas `thumbnails.set` devolveu falta de permissão para
miniaturas personalizadas. A recusa ocorre depois da autenticação/upload;
renovar tokens não habilita esse recurso do canal.

Conferir no YouTube Studio a elegibilidade do canal e a verificação exigida
para miniaturas. A disponibilidade de upload de capas para Shorts depende
do canal. A documentação atual permite capa personalizada pelo Studio no
computador; não assumir que Shorts nunca aceita JPG.

- [Ajuda oficial e requisitos](https://support.google.com/youtube/answer/72431?hl=pt-BR)
- [Erro 403 da API](https://developers.google.com/youtube/v3/docs/thumbnails/set)

Mitigação: resultado da thumbnail fica separado na fila, com erro e link do
Studio; o vídeo continua `uploaded` para evitar duplicação. Em falha da capa,
MP4/JPG são preservados. O artifact `video-<run_id>` inclui capas e vídeos
preservados por 7 dias, também em execuções que publicam. Corrigir a capa do
vídeo existente no Studio após habilitar o recurso; não reenviar o vídeo.

### Qualidade do card revisada (15/09/2026)

Inter SemiBold acompanha o projeto com licença OFL (`assets/fonts/Inter.ttf`),
inclusive no Linux. Texto escuro sólido, renderização em 2x, medição real das
letras e linhas equilibradas substituem fonte dependente do sistema, contorno
grosso e estimativa por caracteres. Card mantém 780px e margens para avatar e
rodapé. A capa é 1080x1920, com o card centralizado sem deformar o template.

## Resolvido nesta sessão (contexto, não reabrir sem evidência nova)

Para não retrabalhar o que já foi investigado e corrigido:

- Extração 403 do Reddit (JSON público morreu, cookie de sessão resolveu)
- `subreddit.lstrip("r/")` corrompia nomes que começam com "r" após o
  prefixo (`relationship_advice` → `elationship_advice`) — trocado por
  `removeprefix()`
- Thumbnail nunca era setada no YouTube (upload sem thumbnail) —
  `thumbnails().set()` nunca era chamado, só o upload do vídeo
- Card de thumbnail com fonte distorcida — runner sem fonte TTF instalada,
  Pillow caindo pro bitmap padrão; corrigido instalando `fonts-dejavu-core`
  no workflow + blindado o fallback de quebra de linha em
  `stages/thumbnail.py` pra nunca estourar a área do card
- Mojibake (UTF-8 decodificado como Latin-1) em respostas do Groq —
  reparo automático em `utils/groq_client.py`, cobre acentuação PT/ES e
  travessão/aspas curvas EN
- Validador não dizia ao Groq em qual idioma responder (4 de 8 chamadas em
  `stages/validator.py` sem `"Responda em {language}"`) — causava
  contaminação cruzada de idioma em scripts
- Colisão de ID na fila (`scheduler/queue.py`) descartava item duplicado em
  silêncio — agora versiona (`_v2`, `_v3`)
- `googletrans==4.0.0rc1` **não deve ser reinstalado** — fixa `httpx` numa
  versão de 2020, incompatível com `groq`/`python-telegram-bot`. O
  fallback de tradução usa `MyMemoryTranslator` (já embutido no
  `deep-translator`, sem dependência nova)
- Hook narrado lendo números em dígito soletrado ("um, cinco, zero...") em
  vez de por extenso — instrução explícita nos prompts de hook +
  verificação no validador
- Título/hook formado por duas frases coladas com hífen/travessão — prompts
  PT/EN/ES agora exigem uma frase coesa e uma trava determinística normaliza
  qualquer separador que escape do LLM. O validador preserva a versão com
  melhor score em vez de devolver incondicionalmente a última tentativa.

## Decisões deliberadas — não reverter sem entender o motivo

### Gates de roteiro e implantação suportada

O narrador é resolvido uma vez antes da adaptação: `source_gender` pode ficar
`unknown`, mas `narration_gender` é binário e imutável entre idiomas, partes,
metadados e voz. Sem evidência suficiente, o hash estável de `story_id` decide,
sem recorrer a nomes, profissão, roupa ou outros estereótipos. gTTS sem controle
de gênero permanece desabilitado por padrão. Reprovação do guardião gera
quarentena sanitizada e pula história/idioma; indisponibilidade obrigatória
interrompe o lote com código 2. `fail_closed: false` não libera o gate final.

LanguageTool 6.6 com Temurin 17 roda localmente no GitHub Actions, ambiente de
produção ativo. O instalador Oracle Linux é suportado, mas não foi executado
em host Oracle nesta entrega. O ZIP tem SHA fixado no manifesto, conferido
também em cache hit. Falha de saúde nos locales PT/EN/ES impede geração.
O artifact de logs e quarentena retém evidências sanitizadas por 14 dias.
Achados do glossário só viram regras após teste e revisão humana. A execução
real no runner e no host Oracle é verificação operacional distinta dos testes
locais.

| Decisão | Por quê |
|---|---|
| Chave Groq por idioma (`GROQ_API_KEY_PT`/`_EN`/`_ES`) não é rotação | Rotação de múltiplas chaves pra burlar rate limit da mesma carga de trabalho viola a AUP da Groq e foi rejeitada. Isto é diferente: uma chave fixa por carga de trabalho consistente (cada idioma sempre faz o mesmo tipo de chamada) |
| Normalização de idioma (`pt-br` → `pt`) só no ponto de entrada | Espalhar essa normalização por múltiplos módulos já causou um incidente de falha em cascata, documentado no handoff anterior |
| Validação em duas camadas (substituição direta / LLM) | Controle de custo de token em pipeline batch — perder isso reintroduz gasto desnecessário |
| TikTok semi-automático (Telegram + postagem manual) | API direta bloqueada por aprovação pendente do TikTok Developer App — contingência externa, não uma limitação de código |
| Julgamento semântico via LLM em vez de regex/listas fixas (gênero, título/hook, validação) | Regras rígidas performaram pior nesses três pontos, testado empiricamente |
| Retries esgotam tentativas em vez de cortar cedo por similaridade | Casos reais precisaram de até 6 tentativas pra convergir |
| `max_tokens`/temperatura/retries dinâmicos, nunca hardcoded | Escala com o tamanho real do script; hardcoding quebrava em casos fora da média |
| Tempo de processamento por história não é métrica relevante | Workflow é batch + publicação agendada pro dia seguinte, não tempo real |
| 100% ferramentas gratuitas, sem exceção | Restrição dura do operador — nunca proponha alternativa paga, mesmo de custo irrisório |

Exceção estreita em validação de confiabilidade (2026-10-06): o JSON de revisão
pontual do guardião tem teto **configurável** `semantic_max_completion_tokens`
(2.048 nesta prova), não o orçamento de geração de um roteiro inteiro. Resposta
`length` nunca é aceita, mesmo parseável; torna indisponível sem retry sob o
mesmo teto. Qwen da revisão usa `none` explicitamente; os demais modelos/etapas
mantêm seu esforço. Essa mudança não garante suficiência para qualquer tamanho
nem identifica o subtipo do 429. História maior pode exigir ajuste medido do
orçamento/divisão lossless antes de passar os mesmos gates, nunca truncamento
de fonte/fatos para publicar. Veja [evidência](docs/RELIABILITY_STATUS.md).

## Correções ao CLAUDE.md anterior (agora refletidas no AGENTS.md)

Coisas que o `CLAUDE.md` antigo dizia e que não batem mais com o código real:

- **"Reddit's public JSON endpoints (no API key)"** — desatualizado. Requer
  `REDDIT_SESSION_COOKIE` (sessão logada) desde que o Reddit passou a
  bloquear tráfego anônimo até de IP residencial.
- **"Ollama... expected at `OLLAMA_URL` from `.env`"** — nunca foi verdade
  no código: a URL vem hardcoded em `config/settings.yaml`
  (`ollama_url: http://localhost:11434/api/generate`). As chaves
  `OLLAMA_URL`/`OLLAMA_MODEL` existem no `.env` local mas não são lidas em
  nenhum lugar do código — órfãs.
- **"YouTube OAuth creds" via `.env`** — o `.env` local tem
  `YOUTUBE_CLIENT_ID`/`YOUTUBE_CLIENT_SECRET`/`YOUTUBE_REDIRECT_URI`, mas o
  mecanismo real usado pelo código é `YOUTUBE_CREDENTIALS` (o JSON inteiro
  do `client_secret.json` como uma única variável, usado no runner) +
  `secrets/youtube_credentials.json` localmente. Os três primeiros parecem
  órfãos de uma implementação anterior — confirmar antes de removê-los do
  `.env`, mas não documentá-los como se fossem o mecanismo ativo.
- **"Roda em produção via Oracle Cloud"** — desatualizado. GitHub Actions
  é o ambiente de produção ativo (ver `.github/workflows/pipeline.yml`).
  Oracle Linux tem instalador suportado, ainda sem implantação ativa
  verificada nesta entrega.
