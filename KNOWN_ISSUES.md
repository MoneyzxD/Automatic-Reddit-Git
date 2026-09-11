# KNOWN_ISSUES.md

Bugs, decisões deliberadas e contexto que só existiam em conversa/memória
antes desta migração. Gerado na migração Claude Code → Codex CLI
(2026-09-11) a partir do histórico real de trabalho, não de suposição.

## Em aberto — precisam de ação

### 1. Token OAuth do YouTube expira a cada 7 dias
O app OAuth no Google Cloud Console está em modo **"Testing"**, não
publicado. Nesse modo, todo token de refresh expira sozinho em 7 dias,
sem aviso da API — a falha só aparece quando um upload dá
`invalid_grant: Token has been expired or revoked`.

- **Correção definitiva**: publicar o app (Google Cloud Console → APIs &
  Services → OAuth consent screen → aba "Público"/Audience → "Publicar
  app"). Isso trava porque o Google exige um campo "E-mail de contato do
  desenvolvedor" preenchido na página de Branding, e depois de preenchido
  ainda pediu **URL de Política de Privacidade e Homepage** pra liberar o
  modo de produção externa — não resolvido ainda, ficou pendente.
- **Mitigação já implementada**: `scripts/check_oauth_expiry.py` avisa no
  Telegram quando faltarem ≤2 dias pro limite, lendo
  `data/oauth_token_status.json` (gravado por
  `scripts/reautenticar_youtube.py` a cada renovação manual).
- **Por causa disso o cron do `pipeline.yml` está pausado** (comentado,
  não deletado) desde 2026-09-08 — reative só depois de resolver isto,
  senão toda execução agendada falha sozinha sem gerar nada.

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

### 4. Drift de título/hook (herdado, status não confirmado)
Do `PROJECT_HANDOFF.md` anterior: em algum ponto, cada tentativa de
correção de título/hook sobrescrevia `current_title`/`current_hook`
incondicionalmente, mesmo quando a nova versão era pior que a anterior —
podendo alucinar detalhes que não existem na história original. Não há
confirmação, nesta migração, de que isso foi corrigido — `stages/validator.py`
recebeu bastante trabalho nesta sessão (níveis de idioma explícitos,
aumento de `max_tokens`), mas esse bug específico não foi verificado.
**Ação**: ler `validate_title_hook`/`apply_title_hook_fix` em
`stages/validator.py` e confirmar se há guarda condicional (só substitui
se o novo score for ≥ ao anterior).

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

## Decisões deliberadas — não reverter sem entender o motivo

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
- **"Roda em produção via Oracle Cloud"** — desatualizado. O projeto foi
  migrado para GitHub Actions como ambiente de produção ao longo desta
  sessão (ver `.github/workflows/pipeline.yml`). Oracle Cloud não é mais
  usado.
