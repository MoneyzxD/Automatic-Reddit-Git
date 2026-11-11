# Desenvolvimento no desktop e no notebook

Auditoria: 10/11/2026. Projeto: `MoneyzxD/Automatic-Reddit-Git`.
Decisão confirmada: notebook para edição, conversa com Codex e operação do
GitHub; testes/execução na nuvem. Desktop permite trabalho local e remoto.
O projeto bancário citado em outro editor não pertence a este workspace.

## 1. Visão geral e fontes de verdade

Python transforma histórias Reddit em Shorts PT/EN/ES: extração autenticada,
adaptação/tradução, perfil de narrador, ScriptGuardian, revisão LanguageTool,
TTS, legendas, FFmpeg/Pillow, metadados e publicação YouTube. TikTok está
desabilitado na configuração atual. Estado: SQLite, filas JSON, fontes e mídia
em snapshots privados. Skills auxiliam o desenvolvimento; não rodam no pipeline.

| Repositório | Papel e acesso |
|---|---|
| `MoneyzxD/Automatic-Reddit-Git` | Público; código de produção, `main` |
| `MoneyzxD/Automatic-Reddit-Intelligence` | Privado; coleta e relatórios, `reports/en/latest.md` |
| `MoneyzxD/Automatic-Reddit-State` | Privado; estado operacional; consulta só quando a tarefa exigir |

No desktop, produção está em `_export_repo_publico/`; a pasta acima é legada.
No notebook, o clone de `Automatic-Reddit-Git` já é a raiz de produção.
Use caminhos relativos ao clone. `sync_repo_publico.py` da raiz legada não é
um procedimento de atualização. O runtime de produção permanece no Actions.

Leia [AGENTS](../AGENTS.md), [handoff](../PROJECT_HANDOFF.md) e,
para incidentes recentes, [recuperação diária](DAILY_RECOVERY.md).
Restauração/upload incerto exige [contrato de estado](PIPELINE_STATE.md).

## 2. Pré-requisitos por computador

| Componente | Notebook | Desktop/runner |
|---|---|---|
| Git, GitHub CLI e VS Code/Codex | Necessários para o fluxo por IDE/terminal | Usados também |
| Conta ChatGPT existente | Login próprio no novo dispositivo | Já utilizada |
| GitHub MoneyzxD | Autenticação de leitura/escrita conforme tarefa | Verificar conta ativa |
| Python | Dispensado | Runner usa 3.11 |
| `requirements.txt` | Não instalar por padrão | Fonte única; versões `>=`, ainda sem lock |
| FFmpeg, libx264, filtro ASS, DejaVu | Dispensados | Necessários para testes de mídia/runtime |
| Eclipse Temurin 17, LanguageTool 6.6 | Dispensados | Manifesto e SHA em `config/languagetool_runtime.env` |
| Ollama | Dispensado | Opcional no desktop; ausente no Actions |

Versões observadas no desktop: Git 2.53.0.windows.1, gh 2.100.0,
VS Code 1.145.2; são inventário, não versões mínimas obrigatórias.
O notebook ainda não foi inspecionado. SO, permissões, ferramentas e conexão
serão validados nele. A consulta de versão do VS Code funcionou, mas houve
aviso de acesso negado do crashpad no sandbox; isso não valida a extensão.

## 3. Configuração inicial leve

1. Identificar SO e verificar `git --version`, `gh --version` e `code --version`.
2. Instalar apenas ferramentas ausentes pelos instaladores oficiais/gerenciador
   disponível, respeitando permissões. Abrir VS Code, instalar a extensão
   oficial Codex e entrar com a conta ChatGPT já contratada.
3. Executar `gh auth login`, autenticar como MoneyzxD e conferir `gh auth status`.
   Completar login humano no navegador; não copiar caches de autenticação.
4. Configurar identidade Git por repositório se necessário; obter o endereço
   de commit escolhido pelo operador, sem inferi-lo dos Gmail dos canais.
5. Clonar em pasta própria, com os comandos abaixo. Nenhuma conta Gmail do
   YouTube precisa estar logada para edição e testes sem serviços reais.

```powershell
gh repo clone MoneyzxD/Automatic-Reddit-Git
Set-Location Automatic-Reddit-Git
git remote -v
git status --short
gh repo view --json nameWithOwner,viewerPermission
```

Opcional para tarefas da inteligência, em pasta irmã:
`gh repo clone MoneyzxD/Automatic-Reddit-Intelligence`.
Não recriar worktrees do desktop copiando suas pastas `.git`.

## 4. VS Code, Codex, agentes, skills e MCPs

Não há `.vscode`, `.codex` ou `.mcp.json` versionado no código de produção
auditado. As instruções portáveis são `AGENTS.md` e os documentos do projeto.
O login em outro computador não deve ser tratado como sincronização das
conversas, skills, plugins, permissões ou servidores locais.

No desktop foram encontrados:

- Skills pessoais `yt-audit`, `yt-seo`, `yt-package`, `yt-script`, `yt-edit`,
  `yt-plan`, `yt-viral`, `yt-shorts`, `yt-comment`, `yt-chapters`, `yt-retention`.
- Procedimentos de investigação, revisão, planejamento, Superpowers e Ponytail.
  Há também skills locais na raiz legada; `.agents/` é ignorada na produção.
- Configuração pessoal Codex com plugins de navegador/computer use,
  visualização/documentos e Ponytail; MCP `node_repl` declarado. Existência
  de configuração não comprova conexão nem funcionamento no notebook.

Para tarefas Git, o caminho mínimo é Git + gh; nenhum MCP é obrigatório.
No novo computador, inventarie as ferramentas efetivamente expostas ao Codex.
Reinstale somente as skills usadas pela tarefa a partir da origem verificável,
incluindo recursos referenciados; leia seu SKILL.md e valide o carregamento.
Não copiar toda a configuração pessoal, hooks com paths do desktop, tokens
ou servidores que não existam no notebook. Não inventar MCP de YouTube: a
coleta existente é código autenticado na nuvem, não skill com acesso implícito.

Acesso por IDE e autenticação: documentação oficial consultada:
[Codex IDE](https://learn.chatgpt.com/docs/codex/ide) e
[autenticação](https://learn.chatgpt.com/docs/auth).

## 5. Sincronização Git e continuidade

Antes de começar em qualquer máquina:

```powershell
git status --short
git fetch origin
git switch main
git pull --ff-only
git switch -c trabalho/descricao-curta
```

Execute a troca/pull somente com alterações preservadas; diretório sujo exige
inspeção, não reset/clean/stash automático. Confira sempre remote e conta.
Edite em branch, revise o diff, faça commit/push e abra PR. Registre no PR
o SHA testado, run, resultado e limitações. Não confundir testes de uma branch
com aprovação de outro commit. Ao trocar de computador, deixe o trabalho em
branch remota e registre a tarefa/pendências; só commits enviados são sincronizados.

Foi observada autenticação de duas contas gh no desktop: Henri-fernandes ativa
e MoneyzxD também autenticada. Não mudar identidade global por reflexo. Para
MoneyzxD, validar permissão e usar credencial adequada à operação, sem exibi-la.

## 6. Variáveis, arquivos locais e integrações

Notebook de edição não precisa de `.env`. Secrets operacionais permanecem no
GitHub; não é necessário lê-los/copiar para disparar workflows autorizados.
Nomes estão em [.env.example](../.env.example), sem valores reais.

| Integração | Configuração existente, quando realmente necessária |
|---|---|
| Reddit | `REDDIT_SESSION_COOKIE`, `REDDIT_USER_AGENT`; sessão manual |
| Groq | `GROQ_API_KEY_PT/EN/ES`, chave genérica como fallback; carga fixa por idioma |
| Gemini | `PIPELINE_LLM_PROVIDER`, `GEMINI_API_KEY`, configuração do modelo; alternativa implementada, disponibilidade não garantida |
| YouTube | `YOUTUBE_CREDENTIALS`, `YOUTUBE_TOKEN_PT/EN/ES`; publicação separada do OAuth readonly da inteligência |
| Telegram | Bot, admin e chat por idioma; nunca imprimir valores |
| Estado privado | `PIPELINE_STATE_TOKEN/REPO/NAMESPACE/REQUIRED`; só workflow operacional autorizado |
| Mídia | Manifesto e `BACKGROUND_BASE_URL/SOURCE`; downloads apenas no runtime |
| LanguageTool | HTTP loopback no runner; não apontar o notebook para localhost do desktop |

Versionar código, testes, configurações sem segredos, manifesto e documentos.
Manter locais/privados: `.env`, `secrets/`, credenciais, DB, filas, perfis,
fontes privadas, quarentena, snapshots, mídia e logs. O `.gitignore` existente
cobre esses caminhos; `data/scripts/` tem arquivos rastreados, portanto revisar
conteúdo antes de adicionar qualquer saída nova. Não usar `git add .` às cegas.

## 7. Testes e execução na nuvem

O workflow `testes.yml` desta preparação executa `python -m pytest tests -q`
em Ubuntu24.04/Python3.11, com FFmpeg/fontes e LanguageTool6.6 local ao runner.
Usa `requirements.txt` e o manifesto existentes. Não restaura estado privado,
não usa Secrets de produção e não invoca geração/publicação. Testes com mocks
comprovam contratos, não acesso real a Groq/YouTube/Reddit.

```powershell
gh workflow run testes.yml --ref NOME_DA_BRANCH
gh run list --workflow testes.yml --limit 5
gh run view ID_DO_RUN
gh run view ID_DO_RUN --log-failed
```

Substitua branch/ID por valores reais. Workflow novo precisa estar registrado
na branch padrão para o disparo manual; o PR pode validar sua introdução.
PRs acionam testes sem Secrets. Não usar `pipeline.yml` como botão de testes:
ele também pode gerar mídia e publicar. Operação de produção requer escopo
explícito e leitura de suas entradas; `--test-story` não é simulação de serviços.

No desktop, após configurar o runtime, o comando equivalente é
`python -m pytest tests -q`. Rodar o pipeline local exige configuração própria
e não faz parte da preparação do notebook. Não fixar todas as dependências
com `pip freeze` do desktop; o projeto ainda carece de lock validado no Linux.

## 8. Checklist de validação do notebook

- [ ] SO, Git, gh, VS Code e Codex identificados e utilizáveis.
- [ ] Login próprio ChatGPT; gh com acesso correto a MoneyzxD.
- [ ] Clone correto, branch/SHA conhecidos e `git status` entendido.
- [ ] Leitura das instruções e dos relatórios privados necessários comprovada.
- [ ] Skills da tarefa carregadas; MCPs opcionais testados ou marcados ausentes.
- [ ] Branch remota/PR acessível; testes Actions do SHA esperado concluídos.
- [ ] Nenhum token/configuração do desktop copiado por conveniência.
- [ ] Pendências registradas com evidência; teste falso separado de serviço real.

Desktop desligado não impede GitHub Actions. Ele impede apenas o acesso a
arquivos/testes que continuem exclusivos daquela máquina. Sessão no notebook
não dá acesso remoto automático ao desktop.

## 9. Pendências da auditoria e problemas conhecidos

Auditoria do desktop encontrou alterações preexistentes não publicadas em
AGENTS/README/KNOWN_ISSUES/memória e diagnóstico Groq; documentos
`docs/AI_WORKFLOW.md` e `docs/YOUTUBE_GROWTH_AGENT.md` também estavam sem
versionamento. Foram preservados: não fazem parte desta entrega nem estarão
num clone até serem revisados e enviados em trabalho separado.

A worktree `youtube-intelligence` tem branch local `youtube-intelligence-mvp`
e alteração na spec de30/10. A branch não constava no remoto público consultado;
não publicar sua história indiscriminadamente. O runtime privado já existe em
`Automatic-Reddit-Intelligence`; reconciliar diferenças no destino privado antes
de migrar material. Worktrees/artefatos privados não são backup por clone público.

O helper OAuth Windows validado com seletor de conta está na raiz legada do
desktop (`scripts/reautenticar_youtube.py --all --github`), não no clone puro.
Isso é uma dependência operacional do desktop ainda não portada; renovação não
é necessária para preparar o notebook. Não usar o script homônimo do clone
como substituto sem conferir diferenças. App em Testing exige renovação manual.

Em09/11, run42583106880 confirmou limite TPD Groq de200000tokens por carga:
EN199531, ES199063, PT199859 usados. Houve um upload PT confirmado e checkpoint
salvo; conclusão failure não significa ausência de envios. Redução de consumo
e espera persistente ainda pendentes. Não trocar chaves para contornar cota.
Correções atuais em main/0faa52f incluem isolar contexto local excedido;
história fica em quarentena, sem aprovação automática. Detalhes em DAILY_RECOVERY.

GitHub Actions pode parar por limites/quota/permissões. Manter orçamento extra
zero; confirmar novamente no painel da conta ao mudar plano/runner. Não ativar
runner pago, Codespaces ou APIs cobradas como solução. O ambiente de testes
exige rede para pacotes e LanguageTool; falha de download não prova defeito no
código. As versões `>=` e diferenças Windows/Linux limitam reprodução exata.

## 10. Retomada e registro

Ao encerrar trabalho, atualizar o documento pertinente com decisão, branch/SHA,
run e resultado, limitações e próximo passo concreto. Usar dados sensíveis só
no repositório privado apropriado. A documentação histórica pode estar antiga:
validar o estado remoto e os logs antes de retomar uma pendência.

## PROMPT PARA EXECUTAR NO NOTEBOOK

```text
Prepare este notebook para trabalhar no pipeline MoneyzxD/Automatic-Reddit-Git.
Ele serve para conversar com Codex, editar código e operar GitHub. Testes,
renderização e execução devem ocorrer no GitHub Actions; uso local completo
permanece opcional no desktop. Custo adicional zero.

Leia integralmente docs/CONFIGURACAO_NOTEBOOK.md e AGENTS.md. Leia
PROJECT_HANDOFF.md e docs/DAILY_RECOVERY.md para retomar; consulte README,
KNOWN_ISSUES.md e docs/PIPELINE_STATE.md conforme a tarefa. Confira remote,
branch/SHA, arquivos modificados e estado remoto. Não reutilize instruções
do projeto bancário ou da raiz legada como se fossem deste clone.

Identifique SO e ferramentas disponíveis. Instale/configure apenas Git,
GitHub CLI, VS Code e Codex ausentes, dentro das permissões. Peça minha
intervenção só para login, autorização necessária ou ação manual. Confirme
conta GitHub correta e acesso aos repositórios; não exponha credenciais.
Não instale Python/FFmpeg/LanguageTool nem copie .env/secrets no notebook.

Inventarie skills/plugins/MCPs realmente disponíveis. Configure apenas os
necessários a partir de origem verificável; leia SKILL.md, valide carregamento
e registre ausências. Preserve configurações pessoais existentes.

Use branches e PRs. Execute testes pelo workflow testes.yml no SHA correto
e leia resultados; mantenha separado o pipeline de geração/publicação.
Se o workflow não existir no remoto, registre a pendência e examine a branch
de preparação antes de criar duplicata. Não declare serviço real validado
por mocks. Não publique vídeos nem altere Secrets para testar acesso.

Preserve trabalho local/remoto e dados privados, sem reset/clean ou publicação
indiscriminada de worktrees. Ao terminar, relate verificações e evidências,
funcionalidades prontas, bloqueios, mudanças realizadas e próximo passo.
Atualize documentação relevante para continuar em outra sessão sem este chat.
```
