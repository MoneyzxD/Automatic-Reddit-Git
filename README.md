# Reddit Stories Automation Pipeline

Pipeline 100% gratuito que transforma histórias do Reddit em vídeos verticais
narrados em português (BR), inglês e espanhol. GitHub Actions é o ambiente de
produção atual; Oracle Cloud é um destino suportado pelo instalador, sem
implantação ativa ou execução do instalador alegada nesta entrega.

## Instalação e execução

Instale as dependências de `requirements.txt`, FFmpeg e o runtime local abaixo.
No Linux, instale também `fonts-dejavu-core`. Copie `.env.example` para `.env`
e configure a sessão logada do Reddit e as chaves Groq. A extração usa o cookie
completo `REDDIT_SESSION_COOKIE`, não JSON público anônimo. A renovação é manual;
o registro OAuth do Reddit já foi descartado após tentativas repetidas.

```bash
pip install -r requirements.txt
cp .env.example .env
python main.py --lang pt en es
python main.py --test-story --lang pt
python main.py --dry-run
python publish.py --lang pt
```

`--test-story` troca a extração por uma história fixa e mantém os gates reais.
`--dry-run` pula extração, LLM e mídia. Groq é o provedor principal das etapas
de geração, com Ollama local/regras como fallback onde implementado. Ollama é
opcional e sua URL/modelo vêm de `config/settings.yaml`. Chaves Groq por idioma
são fixas por carga de trabalho, com fallback à chave genérica; não há rotação.

## Perfil do narrador e gates de qualidade

A sequência completa está na tabela de `AGENTS.md` e no docstring de `main.py`.
Na etapa 3.5, `NarratorProfileResolver` examina título e fonte completos em
blocos sem truncar o final. O perfil é imutável e persistido em
`data/scripts/profiles/{story_id}_narrator_profile.json`. Todos os idiomas,
etapas e partes recebem o mesmo `profile_id`; não há redetecção sobre traduções.

`source_gender` registra `male`, `female` ou `unknown` conforme a evidência.
`narration_gender` sempre é binário e fica travado para concordância e TTS.
Autoidentificação explícita prevalece. Evidência semântica aceita exige trecho
literal e atribuição ao narrador. Baixa confiança pode manter `source_gender`
como `unknown` e escolher a evidência positiva de maior peso para narração;
empate, conflito explícito ou ausência de evidência usam SHA-256 estável de
`story_id`. Ambiguidade permite continuar com essa escolha registrada.
Parceiro, orientação, cabelo, nome, profissão, hobby, roupa e emoção não
determinam gênero.

O TTS exige `male` ou `female` explicitamente. A voz edge-tts alternativa deve
pertencer ao mesmo gênero. `allow_uncontrolled_gender_fallback: false` bloqueia
gTTS por padrão, pois ele não garante o gênero da voz. O campo legado
`fallback: gtts` não libera esse caminho; só a permissão explícita o habilita.

`ScriptGuardian` combina glossário contextual, LanguageTool local e revisão
semântica Groq. Revisa adaptação, tradução, naturalização, título/hooks,
hook injetado, todas as partes completas e descrições localizadas. Um gate
final recebe exatamente cada parte com hook e encerramento antes do TTS.
Todas as partes e descrições passam pelos checks prévios à mídia; exportação
e enfileiramento só ocorrem após concluir todas as partes do idioma.

Patches pontuais precisam de trecho exato, posição inequívoca e suporte na
fonte/perfil. Correções de gênero só podem atingir o narrador, sem substituição
global das flexões de outros personagens. Falhas de tradução são resultados
tipados e bloqueiam a sequência, em vez de reinserir inglês como sucesso.
Achados de estilo sem severidade crítica são aviso; idioma, fatos, terminologia,
gramática ou atribuição restantes bloqueiam a aprovação. A maior nota entre
tentativas não autoriza publicar conteúdo reprovado.

Reprovação põe o candidato em
`data/quarantine/{story_id}/{language}_{stage}[_partN].json`, com sanitização,
perfil, hashes e relatório, e avisa no Telegram. Falha da adaptação pula a
história; falha posterior pula o idioma. O lote tenta outra história para
completar a meta. Dependência obrigatória indisponível interrompe o lote;
`main.py` retorna código **2**, distinguindo indisponibilidade de reprovação.
O preflight de LanguageTool ocorre antes da extração, exceto em dry-run.

Em `config/settings.yaml`, `script_quality.enabled: false` causa
indisponibilidade, não aprovação. `fail_closed: false` apenas permite que a
interface do guardião devolva um relatório não aprovado fora do gate final;
`main.py` ainda bloqueia relatórios não aprovados. O gate final sempre bloqueia.
LanguageTool é obrigatório no runner/Oracle, com `LANGUAGETOOL_REQUIRED=true`
ou com `languagetool_required: true` (padrão). Definir a variável como `false`
não sobrepõe a configuração obrigatória. O guardião não aprova por fallback
Ollama/regras quando falta revisão semântica.

`config/contextual_glossary.yaml` é o arquivo versionado de regras contextuais.
Por exemplo, Pokémon/trading card usa "carta", enquanto credit/debit card
preserva "cartão". `card` isolado é ambíguo e bloqueia a tradução. Achados nos
relatórios são material para revisão humana: novas regras exigem contexto,
teste de regressão, atualização de versão e revisão humana antes de promoção.
Nenhuma saída LLM altera automaticamente o glossário.

## LanguageTool local

A autoridade única de versão, URL e checksum é
[`config/languagetool_runtime.env`](config/languagetool_runtime.env):
LanguageTool **6.6**, Java **Eclipse Temurin 17**, ZIP oficial
`https://languagetool.org/download/LanguageTool-6.6.zip`, SHA-256
`53600506b399bb5ffe1e4c8dec794fd378212f14aaf38ccef9b6f89314d11631`.
Atualizações devem partir desse manifesto, compartilhado por CI e instalador.

O endpoint padrão é `http://127.0.0.1:8081/v2/check`. Cliente e health check
aceitam somente HTTP loopback (`127.0.0.1`, `localhost`, `::1`), recusam
redirecionamentos e ignoram proxies de ambiente. Não há fallback à API pública.
O health check usa apenas a biblioteca padrão e exige Python **3.9+**:

```bash
python scripts/check_languagetool.py --url http://127.0.0.1:8081/v2/check --expected-version 6.6 --required-locales pt-BR en-US es --timeout-seconds 120
```

Esse comando obrigatório confirma `/v2/languages`, versão e aquecimento de
`/v2/check` nos três locales. Falha de download, SHA, inicialização, versão
ou locale impede geração no workflow. O GitHub Actions usa cache imutável
do ZIP em `.cache/languagetool`, com chave por SO/arquitetura/hash do manifesto;
confere SHA inclusive em cache hit e extrai no diretório temporário do runner.

Para um host Linux suportado, execute `sudo bash scripts/install_languagetool.sh`
no repositório. Suporte: Ubuntu 22.04/24.04, Debian 12/13, Oracle Linux/RHEL
8/9. EL8 exige AppStream de **8.8+** para `python3.11`; EL9 usa `python3`
**3.9+**. O instalador valida Temurin 17, SHA e saúde, guarda o ZIP em
`/var/cache/languagetool`, instala em `/opt/languagetool` e habilita a unidade
`deploy/languagetool/languagetool.service`. Ela usa usuário sem privilégios,
`Restart=on-failure` e acesso de rede limitado a loopback. Não exponha a porta
8081 publicamente. Testes locais cobrem o contrato; a execução real no host
Oracle permanece uma verificação operacional separada.

## Operação e evidências

Cada história gera uma ou mais partes de até 2:45 por idioma solicitado.
Vídeos finais usam
`data/exports/{lang}/{slug}_{YYYYMMDD}_{lang}[_ptNofM].mp4`, com thumbnail e
metadados. Legendas são ASS animado palavra a palavra. Publicação automática
é no YouTube; TikTok recebe kit no Telegram para postagem manual.

`data/logs/script_quality.jsonl` registra decisões, versões, contagens e
resumos de patches, sem copiar trechos sensíveis. O artifact existente
`logs-<run_id>` inclui logs de qualidade e JSONs sanitizados de quarentena,
com retenção de **14 dias**, inclusive em falha.

O cron diário das 09:00 UTC continua condicionado a
`PIPELINE_AUTOMATION_ENABLED=true`. `generate_daily_batch.py` completa a meta
inicial de três vídeos por idioma; `DAILY_VIDEO_TARGET` tem teto 10 e mudanças
da progressão exigem decisão manual. Uma parte excedente pode ser agendada
para o dia seguinte. OAuth YouTube continua em Testing por decisão do operador,
com renovação manual a cada sete dias e alertas Telegram. Detalhes de filas,
dedupe e segredos: `AGENTS.md`; limitações e decisões: `KNOWN_ISSUES.md`.

```bash
python -m pytest tests -q
```

Os testes unitários usam adaptadores locais/falsos; passar a suíte não comprova
serviço real ou publicação. O workflow executa a saúde real antes dos testes.

## Recuperação privada (implantação pendente)

A branch `pipeline-reliability` acrescenta retomada por idioma, diagnóstico
seguro do guardião e snapshots privados de DB/fila/mídia. Confira
[PIPELINE_STATE](docs/PIPELINE_STATE.md) para credencial limitada, bootstrap
reconciliado, validação isolada e tratamento de uploads incertos.

O destino `MoneyzxD/Automatic-Reddit-State` foi criado privado. A liberação
exige Secret de acesso específico, importação revisada do histórico e dois
runs reais de geração/restauração antes da publicação normal. Testes locais
não substituem esses passos. Meta, janelas e OAuth manual permanecem iguais.
