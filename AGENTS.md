# AGENTS.md

Instruções para agentes de codificação (Codex CLI e equivalentes) trabalhando neste
repositório. Substitui o `CLAUDE.md` anterior (específico do Claude Code) — o
conteúdo técnico foi conferido contra o código real nesta migração, não copiado
às cegas; onde o `CLAUDE.md` estava desatualizado, está corrigido aqui e a
divergência está anotada em `KNOWN_ISSUES.md`.

## O que é este projeto

Pipeline que transforma histórias do Reddit em vídeos curtos verticais (9:16)
narrados e legendados, em três idiomas (português, inglês, espanhol), e os
enfileira para publicação no YouTube/TikTok. Construído para rodar 100% em
stack gratuita — isso é uma restrição dura do operador, não uma preferência:
nunca proponha um serviço pago, mesmo de custo irrisório, como solução.

Stack: Reddit (sessão logada, ver seção "Autenticação do Reddit" abaixo),
edge-tts para voz (gTTS só com permissão explícita), Whisper para legendas, FFmpeg para renderização,
Groq (com fallback Ollama local/regras hardcoded) para as etapas de LLM, e
SQLite para estado.

Todos os comentários de código e mensagens de log são em português — mantenha
esse padrão em qualquer linha nova, a menos que instruído o contrário.

## Comandos

```bash
# Pipeline completo pra um idioma (default: pt)
python main.py --lang pt
python main.py --lang pt en es

# Dry run — pula extração, LLM, áudio e vídeo; só loga o que faria
python main.py --dry-run

# Pula extração+filtragem, usa história de teste fixa (TEST_STORY em main.py)
python main.py --test-story --lang pt

# Scheduler em segundo plano (cron-like: geração + uploads + aviso TikTok)
python -m scheduler.runner

# Publica o que já está na fila (sem gerar nada novo)
python publish.py --lang pt

# Renova o cookie de sessão do Reddit (ver seção de autenticação)
python scripts/reautenticar_youtube.py --lang pt   # idem pra token OAuth do YouTube

# Testes
pytest
pytest tests/test_queue_tiktok.py
pytest tests/test_queue_tiktok.py::test_enqueue_creates_pending_item
```

Não há linter/formatter configurado neste repo — não assuma `black`/`ruff`
sem antes conferir `requirements.txt`.

FFmpeg precisa estar instalado e no PATH. No GitHub Actions, o workflow
também instala `fonts-dejavu-core` explicitamente — sem isso, o Pillow usa
a fonte bitmap padrão dele e o card de thumbnail sai com texto distorcido
(bug real já visto em produção, corrigido adicionando o pacote no runner).

## Autenticação do Reddit (mudança importante, pós-CLAUDE.md)

O `CLAUDE.md` antigo dizia "JSON público, sem API key" — isso **não é mais
verdade**. Em 2026 o Reddit passou a devolver 403 no endpoint JSON público
mesmo para tráfego anônimo de IP residencial (mudança de política deles,
não um bloqueio específico de datacenter). A extração real depende de uma
sessão logada:

- Variável `REDDIT_SESSION_COOKIE`: cabeçalho `Cookie` completo, copiado do
  DevTools do navegador (aba Network → qualquer requisição a reddit.com →
  Request Headers → `cookie:`) de uma conta Reddit logada.
- Tentativa de registrar um app OAuth oficial do Reddit (`reddit.com/prefs/apps`)
  **falhou repetidamente** (loop de captcha, anos de tentativa sem sucesso,
  independente de rede/dispositivo) — não insista nesse caminho sem que o
  operador peça explicitamente.
- O cookie dura ~6 meses (bem mais que o token OAuth do YouTube enquanto o
  app está em Testing, que dura só 7 dias — ver `KNOWN_ISSUES.md`).
  `scripts/check_oauth_expiry.py` avisa no
  Telegram quando faltarem ≤14 dias, lendo o campo `exp` do JWT
  `reddit_session` embutido no cookie.
- Quando expirar: repetir o processo manual de login+DevTools. Não existe
  forma seguRA de automatizar isso sem guardar a senha da conta Reddit em
  algum lugar — avaliado e descartado deliberadamente (risco de a conta ser
  sinalizada por login automatizado, um problema pior que renovar manual a
  cada 6 meses).

## Arquitetura

### Fluxo completo (`main.py`) — 1 história por execução

`main.py` orquestra uma história por vez (`run_pipeline`). Instancia uma
classe por etapa (`stages/` e `scheduler/notifier.py`) e percorre os passos
abaixo. A lista numerada no docstring de `main.py` é a fonte de verdade —
mantenha as duas em sincronia sempre que a ordem mudar.

| # | Etapa | Módulo/detalhe |
|---|------|-----------------|
| 0 | Preflight | `ScriptGuardian.assert_ready()` antes da extração; indisponibilidade obrigatória encerra o lote (exceto dry-run) |
| 1 | Extração | `stages/extractor.py` — Reddit via sessão logada (pulado com `--test-story`) |
| 2 | Filtragem | `stages/filter.py` — score 0-100 |
| 3 | Siglas EN | Expande abreviações no texto original (`(28F)` → "28-year-old woman", `AITA`, `MIL` etc. — `expand_age_gender_en`/`REDDIT_ACRONYMS` em `main.py`) |
| 3.5 | Perfil | `NarratorProfileResolver` resolve e trava uma identidade para os três idiomas antes de adaptar; não há redetecção por idioma |
| 4 | Adaptação | `stages/adapter.py` — limpeza narrativa via Groq (fallback: regras) |
| 4.5 | Validação | Valida o script adaptado (EN) antes de traduzir |
| 5 | Tradução | `stages/translator.py` — Google → MyMemory, com até 3 tentativas; resultado tipificado, sem usar inglês quando a tradução falha |
| 5.5 | Validação | Valida o script traduzido (por idioma) |
| 6 | Siglas PT/ES | Expande abreviações no texto já traduzido (`expand_acronyms_translated`) |
| 8 | Naturalização | `stages/naturalizer.py` — LLM, já com o gênero correto |
| 9.5 | Guardião | Revisa a naturalização contra a tradução aprovada, com o perfil imutável |
| 10 | Título | `stages/titler.py` — gerador viral a partir do título original do Reddit |
| 10.5 | Guardião | Revisa título, hook inicial e encerramento contra história/fatos validados |
| 11 | Hook | Título injetado como primeira fala narrada |
| 12 | Divisão | `stages/splitter.py` — partes de até 2:45 (teto do YouTube Shorts com margem de segurança), cada uma repete o hook e tem seu próprio encerramento |
| 12.5 | Guardião | Revisa todas as partes completas antes de qualquer geração de mídia |
| 12.6 | Metadados | `stages/metadata.py` — SEO por parte com script localizado e fatos validados |
| 12.7 | Guardião | Revisa descrições localizadas antes da voz/renderização |
| 12.9 | Gate final | Revisa exatamente a parte narrada, incluindo hook e encerramento, imediatamente antes de TTS |
| 13 | Voz | `stages/voice.py` — edge-tts, com a voz do gênero correto |
| 14 | Legendas | `stages/subtitle.py` — ASS animado palavra-a-palavra |
| 15 | Vídeo | `stages/video.py` — FFmpeg 1080x1920 + ASS + background automático |
| 16 | Thumbnail | `stages/thumbnail.py` — Pillow (JPG estático + card .mov animado com fade) |
| 18 | Organização | `stages/organizer.py` — exporta e enfileira só depois de concluir todas as partes do idioma |

No fim, `scheduler/notifier.py` manda um resumo no Telegram (sucesso/parcial/
falha) e uma mensagem por vídeo pra postagem manual no TikTok.

**Validação corre o tempo todo, não só no fim.** `stages/script_guardian.py`
(`ScriptGuardian`) revisa adaptação, tradução, naturalização, textos públicos,
hook injetado, partes e descrições, e aplica só patches pontuais sustentados.
Reprovação põe o conteúdo em `data/quarantine/` e pula a história/idioma;
indisponibilidade obrigatória avisa no Telegram e retorna código 2 na CLI.
O guardião não usa fallback local para aprovar conteúdo sem revisão.

`source_gender` guarda a conclusão da fonte (`male`, `female` ou `unknown`);
`narration_gender` escolhe `male` ou `female` uma vez, por evidência atribuída
ao narrador ou hash estável de `story_id` quando não há decisão confiável.
O perfil persiste em `data/scripts/profiles/` e alimenta naturalização,
metadados, todas as partes e a voz sem inferir gênero por estereótipos.
O glossário contextual versionado em `config/contextual_glossary.yaml` só recebe
novas regras após teste e revisão humana. Veja `README.md` para operação dos
gates e do LanguageTool local.

### Cadeia de fallback de LLM

Etapas legadas de geração podem usar Groq → Ollama local → regras/templates.
O perfil usa evidência da fonte e hash estável como desempate; o
`ScriptGuardian` exige revisão semântica Groq e LanguageTool local, sem
aprovação por fallback Ollama/regras. Modelos e limites estão em
`config/settings.yaml`.

**Chaves Groq por idioma**: `GROQ_API_KEY_PT`/`_EN`/`_ES` dão a cada idioma
seu próprio orçamento de tokens (por minuto e por dia) em vez de PT/EN/ES
disputarem o teto de uma única conta — resolvido por
`utils/environment.py:groq_api_key(language)`, caindo pra `GROQ_API_KEY`
genérica se a chave do idioma não estiver definida. **Isto não é rotação de
chaves para burlar rate limit** (prática que o operador rejeitou
explicitamente por violar a Acceptable Use Policy da Groq — ver
`KNOWN_ISSUES.md`) — é uma chave fixa por carga de trabalho, cada uma
sempre fazendo o mesmo tipo de tarefa. Não confunda os dois ao propor
mudanças nessa área.

**Ollama é opcional e não está configurado por variável de ambiente** —
apesar do que documentação antiga possa sugerir, a URL vem hardcoded em
`config/settings.yaml` (`ollama_url: http://localhost:11434/api/generate`,
chave `ollama_model`), sem leitura de `OLLAMA_URL`/`OLLAMA_MODEL` do
ambiente em lugar nenhum do código. No runner do GitHub Actions não existe
servidor Ollama — esse fallback é inatingível ali por design, só é
relevante em desenvolvimento local com Ollama rodando de verdade.

### Layout de configuração

- `config/settings.yaml` — ajuste por etapa (modelos de voz, dimensões de
  vídeo, nomes de modelo LLM, `ollama_url`/`ollama_model` hardcoded,
  limiares de filtragem). Lido por `load_config()` em `main.py`.
- `config/subreddits.yaml` — lista de subreddits fonte por categoria,
  achatada por `get_subreddits()`.
- `config/publishing.yaml` — tudo pro `scheduler/runner.py`: meta diária de
  vídeos por canal/idioma (`daily_video_plan`), excedente máximo de uma parte
  pre-agendada para o dia seguinte, janelas de postagem por dia
  da semana+fuso, growth-plan legado, janelas de
  notificação do TikTok, jitter/pausa anti-detecção. Usa placeholders
  `${VAR}` resolvidos a partir do ambiente (ex: `${TELEGRAM_CHAT_ID_PTBR}`).
- `config/voice_profiles.yaml` — detalhe de seleção de voz TTS além do que
  está em `settings.yaml`.
- `config/languagetool_runtime.env` — versão 6.6, URL e SHA-256 do ZIP oficial;
  CI e instalador Linux usam o mesmo manifesto com Eclipse Temurin 17.
- `config/contextual_glossary.yaml` — termos dependentes de contexto;
  promoção de regras exige teste e revisão humana.
- `config/backgrounds_manifest.json` — lista de nomes de arquivo de vídeo
  de fundo hospedados fora do repo (GitHub Release) — regenerar com
  `python -m stages.backgrounds --gerar-manifesto-remoto` sempre que a
  release de backgrounds mudar (o GitHub sanitiza nomes com espaço/símbolo
  no upload; o manifesto tem que bater com o nome real do asset).
- `.env` (não versionado) — ver seção "Variáveis de ambiente".

### Scheduler / publicação (`scheduler/`)

`scheduler/runner.py` é um processo de longa duração (APScheduler), separado
de `main.py` — não renderiza vídeo, dispara `main.py` num cron e gerencia
filas de upload:

- `pipeline_job` — roda `main.py --lang <lang>` por idioma configurado num
  cron diário.
- `upload_job` — vasculha a fila do YouTube (`scheduler/queue.py`) e dispara
  `scheduler/uploader.py` quando `_can_upload()` permite (canal habilitado,
  dentro da janela de postagem, abaixo do limite diário, intervalo mínimo
  respeitado, growth-plan, jitter/pausa anti-detecção aleatórios).
- `tiktok_notify_job` — sem upload automático pro TikTok; manda uma
  mensagem no Telegram com o kit pronto (vídeo + legenda + hashtags) pra um
  humano postar manualmente. Operador responde `/ok <id>`, `/fail <id>` ou
  `/skip <id>` no Telegram pra resolver itens da fila (ver
  `build_kit_message` em `scheduler/notifier.py`).
- `reset_daily_counters` — job de meia-noite UTC zerando contadores diários
  por idioma.
- Estado da fila fica em arquivos JSON (um por idioma), gerenciado só por
  funções em `scheduler/queue.py` (`enqueue`, `get_pending`, `update_status`,
  `count_uploads_today` etc.) — sem classe de fila separada, tudo sobre
  `_QUEUE_DIR_PATHS`. Testes fazem monkeypatch desse path (ver
  `tests/test_queue_tiktok.py`) — siga o mesmo padrão pra testes novos.
- `enqueue()` usa `story_id` como base do ID (não o nome do arquivo) e
  versiona (`_v2`, `_v3`...) em caso de colisão — bug real já corrigido
  (colisão descartava o item em silêncio antes).

### Banco de dados

`utils/db.py` (`PipelineDB`) — SQLite único em `db/pipeline.db`, rastreia
dedupe de história (`story_exists`/`insert_story`) e status de
processamento por idioma/parte (`update_status`/`get_pending`). Estado
separado das filas JSON de `scheduler/queue.py`.

### Convenção de diretório `data/`

Artefatos organizados por subpasta de idioma dentro de cada etapa:
`data/raw/`, `data/scripts/{lang}/`, `data/audio/{lang}/`,
`data/subtitles/{lang}/`, `data/videos/{lang}/`, `data/thumbnails/{lang}/`,
`data/exports/{lang}/`. Nome final segue
`{slug}_{YYYYMMDD}_{lang}[_pt{N}of{M}].mp4`. A maior parte de `data/` é
gitignorada, exceto `data/scripts/` (scripts finais + metadados JSON ficam
versionados).

## CI/CD — GitHub Actions

`.github/workflows/pipeline.yml` roda geração E publicação no mesmo job
(de propósito: o runner é efêmero, o arquivo de vídeo só existe enquanto o
job vive). Cache via `actions/cache` restaura/salva `db/pipeline.db` e
`data/queue/` entre execuções (senão o dedupe nasceria vazio a cada run).
O mesmo workflow instala Temurin 17, verifica SHA-256 do ZIP 6.6 inclusive
após cache hit, aquece os três locales do LanguageTool em loopback antes de
gerar e preserva logs/quarentena sanitizada por 14 dias. Oracle Linux tem
instalador suportado, mas GitHub Actions segue como produção ativa.
O gatilho diário das 09:00 UTC chama `scripts/generate_daily_batch.py`, que
gera histórias adicionais até completar a meta de vídeos de cada idioma. Se
uma história ultrapassar a meta em uma parte, o mesmo job envia essa parte ao
YouTube com `publishAt` do dia seguinte; excedentes maiores são recusados. A
meta começa em 3 e pode ser alterada
pela variável `DAILY_VIDEO_TARGET` (teto 10); a progressão planejada é
3 → 4 → 5 → 6 → 8 → 10 e exige decisão manual após avaliar desempenho. O job
agendado só executa quando a variável de repositório
`PIPELINE_AUTOMATION_ENABLED=true` estiver definida. O operador decidiu
permitir OAuth em modo Testing: os tokens expiram em sete dias e devem ser
renovados manualmente quando o alerta do Telegram avisar. Defina
`YOUTUBE_OAUTH_PUBLISHING_STATUS=production` apenas quando o app for
publicado; o `workflow_dispatch` manual continua disponível independentemente
da variável de automação.

## Testes

Testes em `tests/`, usam `pytest`; `conftest.py` só adiciona a raiz do repo
ao `sys.path`. `tests/test_queue_tiktok.py` isola estado de fila por teste
via fixture `use_temp_queue` (autouse) — siga esse padrão (monkeypatch
`_QUEUE_DIR_PATHS`) pra qualquer teste novo que toque `scheduler/queue.py`
em vez de apontar pros arquivos reais de `data/queue/`.

## Convenções de código e processo de trabalho

Estas regras vieram de duas fontes que não existem mais como "plugin" fora
do Claude Code (Ponytail e Superpowers) — o comportamento funcional delas
foi preservado aqui como texto simples, já que o Codex não tem sistema de
skill/plugin equivalente. Ficou como seção deste arquivo (não como script
separado) porque é pura instrução de estilo/processo, sem nada executável.

**Estilo de código (equivalente ao "Ponytail")**:
- Prefira a menor mudança que resolve o problema de verdade — biblioteca
  padrão/já instalada antes de dependência nova, uma função pequena antes
  de uma classe, edição cirúrgica antes de reescrita.
- Bug relatado é sintoma, não a causa — antes de editar, encontre e corrija
  na função compartilhada por todos os chamadores, não só no caminho que o
  relato menciona (visto neste projeto: o bug de `subreddit.lstrip("r/")`
  corrompia nomes de subreddit em duas funções diferentes que faziam a
  mesma coisa errada).
- Não adicione abstração para um caso hipotético futuro. Três linhas
  parecidas são melhores que uma abstração prematura.
- Marque atalhos deliberados que cortam um canto real com um comentário
  nomeando o teto e o caminho de melhoria (ex: "sem dedupe aqui, aceitável
  porque X — Y seria a versão robusta").

**Processo (equivalente ao "Superpowers")**:
- Para mudanças de escopo maior ou ambíguas, primeiro alinhe o objetivo
  antes de implementar (o que o Superpowers chamava de "brainstorming") —
  não pule direto pra código quando o pedido admite mais de uma
  interpretação razoável.
- Para bugs "difíceis" (comportamento inesperado, causa não óbvia),
  diagnostique a causa raiz com evidência (logs, teste isolado reproduzindo
  o problema) antes de propor a correção — não corrija por tentativa.
- Antes de declarar um fix pronto, rode uma verificação concreta que prove
  isso: um teste isolado, uma chamada real da função corrigida com dado que
  reproduzia o bug, ou os dois. Este projeto tem o hábito de testar cada
  fix localmente (com dado real que reproduzia o problema) antes de
  commitar — mantenha esse hábito.

## Dependências

`requirements.txt` é a única fonte de dependências Python (sem
`pyproject.toml`/`package.json` neste projeto). Está comentado por seção
com o motivo de cada pacote — leia os comentários antes de remover algo,
vários existem por causa de uma falha silenciosa já vivida em produção
(ex: sem `faster-whisper` as legendas dessincronizam sem erro visível; sem
`python-telegram-bot` todo alerta vira no-op silencioso).

**Atenção**: as versões usam `>=`, não estão travadas em versão exata
(`==`). Isso não foi alterado nesta migração — decida se quer travar com
`pip freeze` antes de depender de reprodutibilidade estrita.

Dependências de sistema fora do gerenciador de pacotes Python:

- **FFmpeg** — precisa estar instalado e no PATH. Comandos de instalação
  por SO estão comentados no `requirements.txt`; no GitHub Actions, o
  workflow instala via `apt-get`.
- **fonts-dejavu-core** (Linux/runner) — sem isso, `stages/thumbnail.py`
  não acha fonte TTF e o Pillow usa um fallback bitmap que quebra o
  cálculo de quebra de linha do card (bug real já corrigido instalando o
  pacote no workflow — ver `KNOWN_ISSUES.md`).
- **Ollama** (opcional, só dev local) — precisa estar rodando em
  `localhost:11434` se você quiser esse fallback funcionando; não é
  necessário no runner de produção nem nos gates novos.
- **LanguageTool 6.6 / Eclipse Temurin 17** — serviço local obrigatório para
  geração; cliente e health check só aceitam HTTP loopback, sem proxy ou
  redirecionamento. `scripts/check_languagetool.py` usa Python 3.9+;
  `scripts/install_languagetool.sh` suporta Ubuntu 22.04/24.04, Debian 12/13,
  Oracle Linux/RHEL 8 (AppStream 8.8+ e Python 3.11) e 9 (Python 3.9+).

## Estado entre execuções e como reiniciar do zero

O pipeline mantém estado em três lugares independentes:

1. **`db/pipeline.db`** (SQLite, gitignorado) — dedupe de histórias já
   processadas e status por idioma/parte (`utils/db.py`). No GitHub
   Actions é restaurado/salvo via `actions/cache` entre execuções (chave
   `pipeline-db-*`) — sem isso, cada execução reprocessaria as mesmas
   histórias do zero.
2. **`data/queue/{lang}.json`** (gitignorado) — fila de upload pendente
   por idioma (`scheduler/queue.py`). Também cacheado no GitHub Actions
   (chave `pipeline-queue-*`).
3. **`data/oauth_token_status.json`** (versionado, sem segredo) — data de
   geração de cada token OAuth do YouTube, usado só pra calcular quando
   avisar de expiração (`scripts/check_oauth_expiry.py`).

**Para reiniciar do zero com segurança**:
- Local: apague `db/pipeline.db` e os arquivos em `data/queue/` — o
  código recria ambos automaticamente na próxima execução. Isso faz o
  pipeline "esquecer" quais histórias já processou, então histórias
  antigas podem ser reprocessadas.
- GitHub Actions: apague os caches (Settings → Actions → Caches no repo,
  ou `gh cache delete` via CLI) com as chaves `pipeline-db-*` e
  `pipeline-queue-*`. Sem apagar o cache, um `git rm`/reset local não tem
  efeito nenhum no runner — ele restaura do cache, não do repositório.
- `data/oauth_token_status.json` não precisa ser resetado — só reflete
  quando cada token foi gerado; apagá-lo só faz o aviso de expiração
  parar de disparar até a próxima renovação manual.

Nada disso é necessário pra rodar o pipeline pela primeira vez — só é
relevante se algo ficar em estado inconsistente e você quiser garantir um
recomeço limpo.

## Segredos e variáveis de ambiente

Ver `.env.example` pra lista completa de nomes (sem valores). `.env`,
`secrets/`, `*_credentials.json`, `*_token*.json` e `db/pipeline.db` estão
no `.gitignore` — confirme que continuam lá antes de qualquer commit que
toque configuração.

## Problemas conhecidos e decisões não óbvias

Ver `KNOWN_ISSUES.md` — cobre o que só existia em memória de conversa
antes desta migração (bugs abertos, decisões deliberadas que não devem ser
revertidas sem entender o motivo, e limitações aceitas conscientemente).
