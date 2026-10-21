# Recuperação privada do pipeline

Status: integrado em main; bootstrap e publicação recuperada confirmados em 13/10.
Teste unitário/fake HTTP não comprova persistência no GitHub nem upload real.

## Incidente de upload incompleto em 20/10/2026

Run39435225675 falhou antes da geração e novamente no checkpoint final com
`Asset incompleto ou divergente`. A API privada confirmou um blob de179222bytes
em `state=starter`, sem digest, desde14:05:14UTC. Reutilizar esse nome fazia
todos os checkpoints seguintes da mesma release falharem. Não foi erro OAuth
do YouTube. O GitHub documenta esse resíduo de upload no
[endpoint de assets](https://docs.github.com/en/rest/releases/assets#upload-a-release-asset).

Mídia e payload agora admitem até três nomes determinísticos por blob, mantendo
o arquivo incompleto e todos os checkpoints anteriores. Só `uploaded` com
tamanho e SHA-256 conferidos entra no recibo. HTTP502/503/504 e interrupção de
rede também têm esse limite. Uma cópia `uploaded` divergente continua bloqueada;
não é contornada como se fosse upload incompleto. Não há DELETE nem alteração
de IDs já confirmados no YouTube. Três cópias incompletas exigem reconciliação.
Markers `complete-N.json` mantêm o protocolo original: marker incompleto ou
corrompido continua bloqueando, sem ignorar um possível head mais recente.

Regressões locais reproduziram o erro antes da correção. A sonda real abaixo
confirmou checkpoint, repetição idempotente, restauração e upload/download de
179222bytes em `validation-storage-b4adf264be6b`, com dados sintéticos:

```powershell
python scripts/probe_state_storage.py --env-file ..\.env
python -m pytest tests/test_pipeline_state.py -q
```

O caminho de `--env-file` deve apontar para o arquivo local que contém
`PIPELINE_STATE_TOKEN`. O script cria namespace `validation-storage-*` exclusivo,
nunca escreve em production nem publica vídeo. A sonda real não força uma
falha upstream; o estado starter é reproduzido no transporte dos testes.
Essas provas são de armazenamento, não de recuperação editorial/publicação.

Integração: main/2527f53. Run39483244524 terminou success, com1.371testes
sem skips e restauração/validação real de production (86arquivos,13mídias).
A comparação da seq201 com a seq187 preservou72arquivos imutáveis,95IDs
confirmados e19rejeições. Isso valida o armazenamento, não geração nova.

Run39483902319 executou somente PT, com Gemini e publicação habilitada. O
checkpoint final chegou à seq207 sem o erro de persistência, preservando95IDs,
19rejeições e zero vídeos novos na fila. Encerramento e hook injetado foram
aprovados e preservados, mas split_part/parte1 terminou unavailable por timeout
Gemini em três tentativas (contexto8411chars). Nenhum upload foi feito. Não
classificar a persistência corrigida como publicação restaurada.

O marcador PT que o splitter inseria, `[Continua na Parte 2 de 2...]`, também
produz DIACRITICS crítico no LanguageTool6.6. A reprodução real falhou antes
do reparo. A frase `[A história continua na parte 2 de 2.]` passa sem achados,
mantendo número/próxima parte e sem alterar filtros ou regras gramaticais.
Suíte completa após esse reparo:1.372testes aprovados, sem skips, usando o
backend real local. Comparação seq207/seq201:77arquivos imutáveis,95IDs e
19rejeições anteriores preservados; nenhuma rejeição nova.

Timeout da revisão continua60s: o teste de180s não confirmou essa hipótese.
Após autorização explícita para uma chamada com a primeira parte PT de1x6sq3x,
o diagnóstico39490154464 retornou HTTP503 em9,11s, sem resposta completa.
Não repetiu a chamada e não alterou estado operacional nem usou YouTube.
Isso comprova indisponibilidade nessa chamada, não esgotamento de cota nem
falha OAuth; aumentar timeout não elimina HTTP503.

A preparação local conferiu exatamente8411chars e o hash original. Não
enviou chamadas porque a chave Gemini existe só no Secret do Actions. O
workflow diagnose_gemini_review fixa asset/SHA privados, modelo e namespace,
faz uma chamada sem retry e só publica códigos/contagens/latência no log.
A revisão automática inicialmente bloqueou a transmissão avulsa; o operador
autorizou especificamente esse conteúdo/destino antes da única chamada real.
Sonda/transporte:68testes passaram; revisão independente sem bloqueios.

Run39490485301 validou manualmente PT/Groq com publicação habilitada. A
primeira parte passou e foi preservada; a descrição recebeu recusas vazias
chunk/global (approved=false, issues vazias), que o código tratava como erros
factuais e rejeição terminal. Workflow success, mas sem mídia ou upload: não
é recuperação. Seq213 tem95IDs,20rejeições,13mídias, zero pendências. Os79
arquivos imutáveis da seq207 e as19rejeições anteriores foram preservados.
Essa vigésima rejeição também permanece fechada; não reabrir para testar.
O único429 nesse run recuperou na tentativa seguinte; a recusa vazia foi o
bloqueio final, não erro OAuth nem a advertência anterior do Google Translate.

Recusa vazia em chunk/global agora recebe `unexplained_rejection`, pede motivo
no mesmo orçamento de três tentativas e termina unavailable se persistir.
Não transforma a recusa em aprovação nem inventa um achado factual. A resposta
nova ainda precisa passar todos os gates. O modo language continua aceitando
false/lista vazia como ausência de proposta segura, sem aprovar o roteiro.
Três regressões falharam antes;382testes próximos e1.380da suíte completa
passaram com LanguageTool real. A fixture de reprovação agora fornece um
crítico explícito sem patch; expectativas de bloqueio/fila permanecem iguais.

Gemini continua padrão do cron. Uma validação Groq não prova disponibilidade
do Gemini nem continuidade automática nos três idiomas.

Run39493219101 não publicou: a fonte nova1x9nddb foi rejeitada na adaptação EN
por COMMA_COMPOUND_SENTENCE persistente após reparo parcial. Não houve falha de
API/schema nem patch recusado; não há bug de contexto comprovado nessa recusa.
Seq217 preserva80arquivos imutáveis da seq213,95IDs e20rejeições anteriores;
há21rejeições fechadas agora. Não reabrir essa fonte para forçar aceite.

A validação manual Groq usava main.py uma vez e podia terminar success sem
vídeo após recusa normal. Agora reutiliza generate_daily_batch.py --target1:
até seis histórias com a configuração atual, pulando conteúdo rejeitado e
parando imediatamente em indisponibilidade/código2. A meta é absoluta do dia,
inclui pendentes/agendados existentes e admite uma parte excedente; pode não
gerar nada se já satisfeita. Confirmar artefatos/IDs novos separadamente antes
de afirmar geração ou publicação nova. Cron/meta diária3/Gemini e todos os
gates permanecem iguais. Historia fixa/dry-run continuam uma única simulação.
Dois testes falharam antes do ajuste no comando manual. Depois:70testes
próximos e1.383da suíte completa passaram, sem skips, com LanguageTool real;
revisão independente sem Critical/Important. Isso ainda não prova vídeo novo.

Run39497046104 completou as seis tentativas e falhou corretamente com pt=0/1.
As seis fontes foram recusadas na adaptação EN ou tradução PT por gramática,
termos/tradução e gênero pendentes após reparos; não houve indisponibilidade
semântica terminal nesse lote. Seq239 mantém95IDs,27rejeições fechadas,
13mídias históricas e zero pendências. Comparação seq239/seq217:82arquivos
imutáveis,95IDs e21rejeições anteriores preservados. Nenhum vídeo PT novo.
OAuth local PT também renovou e channels.list confirmou o canal correto com
HTTP200 em20/10; isso não confirma o Secret usado pelo runner nem um upload.

Compatibilidade adicional: gemini-3.5-flash-lite entrou na allowlist, mantendo
default/cron3.8. A documentação oficial confirma modalidade gratuita e saída
estruturada ([modelo](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite),
[gratuidade](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.5-flash-lite)).
diagnose_gemini_public usa uma única chamada com exemplo sintético fixo de
jantar/agradecimento, sem fonte real, estado privado ou credencial YouTube.
Não repete a sonda autorizada de1x6sq3x. Disponibilidade/JSON de exemplo não
equivalem à qualidade do guardião nem autorizam migração automática do cron.
Teste do endpoint falhou antes da expansão;71testes de transporte/sondas
passaram, incluindo HTTP503 com uma única chamada e logs sem conteúdo/chave.
Após reiniciar/aquecer o LanguageTool local que estava desligado, a suíte
completa passou1.386testes sem skips em242,31s; revisão sem Critical/Important.
Run39534880373 confirmou uma chamada sintética real em20/10 às23h46 de
São Paulo: gemini-3.5-flash-lite, HTTP200,0,84s, JSON completo, approved e
zero achados. Não confirma disponibilidade contínua nem roteiro real, mídia
ou upload. O modelo do cron continua3.8; próximo gate é geração PT isolada.

O erro final da CLI agora inclui apenas code/http/mode/attempts tipificados
quando disponíveis; outras indisponibilidades registram o tipo da exceção.
Preserva código de saída2 e nunca imprime roteiro, contexto ou erro bruto.
Regressões timeout/503 reproduziram RED com o log genérico anterior;
98testes próximos e a suíte completa1.376testes passaram com LanguageTool real.

As falhas dos dias18 e19 são distintas: Gemini429/resource_exhausted no
encerramento PT e Gemini503 na tradução do título PT, respectivamente. O sucesso EN de
17/10 não prova continuidade nem funcionamento dos três idiomas. Registros
anteriores abaixo são históricos.

Atualização em 16/10: Gemini substitui Groq em todas as etapas de IA por decisão
explícita do operador. Fluxo manual/agendado fixa Gemini, sem Secrets Groq nem
fallback de geração para Ollama/regras/templates. Veja [migração](GEMINI_MIGRATION.md).
Cron permanece pausado e geração assistida não publica.

Último checkpoint conferido antes da troca: production/38669463240/seq115.
O run anterior gerou três vídeos pendentes (EN2/ES1), sem upload, e preservou
91 IDs confirmados e11 estados rejeitados. EN/ES de1wyx2wj estão exported;
PT de1x43yzx está unavailable após429 na revisão de tradução, com adaptação EN
aprovada preservada. Verificação offline confirmou25arquivos imutáveis idênticos
à baseline seq73, os91IDs iguais e os dez rejeitados anteriores preservados.
Os registros abaixo são histórico e não substituem esse checkpoint.

Após a troca, run38983801654 validou Gemini real (tradução+nove revisões sem
erro de API), mas PT foi rejeitado num ciclo de sugestões incorretas do LT.
Encerramento assistido preservou checkpoint final production/seq120,91IDs,
EN2/ES1 pendentes e12rejeitados; sem mídia nova Gemini. Nenhum rejeitado deve
ser reaberto. O reparo do ciclo do LT é documentado na migração acima.

Main/5ced683 integrou o reparo após1.288testes no backend6.6 real. O teste
sintético38986158416 aprovou tradução PT e gerou naturalização Gemini, mas sua
revisão global recebeu429/resource_exhausted, RetryInfo84.537s (aproximadamente
17/10 às21h de São Paulo). Não repetir antes do prazo nem trocar provedor por
cota. Checkpoint validation-gemini-20261013/seq47 guarda tradução aprovada;
zero mídia, sem tocar em production. Tokens OAuth locais PT/EN/ES retornaram
invalid_grant; aguardam login do operador para renovar. Cron continua false.

Atualização posterior: OAuth PT/EN/ES renovado com login do operador em16/10
às21h55–21h57 de São Paulo (17/10 00h55–00h57UTC). Refresh e API YouTube
confirmaram os canais Ah Voz do Reddit, The Voice of Reddit e La voz de Reddit,
com IDs iguais aos uploads anteriores. Secrets YOUTUBE_TOKEN_PT/EN/ES atualizados
e cópias locais sincronizadas. Datas novas em data/oauth_token_status.json.
O invalid_grant anterior foi resolvido; a cota Gemini e a prova de geração
completa continuam pendentes. Nenhum upload executado; cron permanece pausado.

Normal38425392437 terminou por cancelamento assistido após oito estados EN/ES
rejeitados, sem mídia nova. Snapshot final production/seq47 mantém91IDs, nenhuma
pendência de upload e nenhuma linguagem processing/pending/unavailable. Fontes,
perfis e etapas aprovadas permanecem preservados; rejeitados não são retomáveis.
Mudanças na expansão de abreviações só afetam fontes novas: retomadas usam hash e
texto expandido persistidos, sem recalcular a identidade pela regra nova.
Uma adaptação ainda não aprovada expande AITA/AITAH no candidato antes da
revisão inglesa, inclusive em retomadas; o cache já aprovado não é reescrito.

Head mais recente conferido: production/38666579042/seq101,91IDs, nenhuma
fila YouTube pendente, nenhum processing; 1wyx2wj EN/ES unavailable e PT rejected.
A adaptação EN foi aprovada e salva, mas a tradução PT terminou por
nonliteral_evidence na revisão de bloco do run38660290998; o run seguinte
terminou429/chunk, após uma resposta200 intermediária. Retomar deve reutilizar a adaptação
aprovada. O run38664030524 respeitou61s, recebeu429/429/200 no bloco PT e
terminou por evidência ausente num achado factual. Retomar mantém a adaptação
aprovada, a mesma fonte/perfil e os dez rejeitados. A geração completa
ainda não tem aceite. A comparação anterior entreseq61/66 confirmou24arquivos
imutáveis byte a byte e igualdade dos91IDs/dez rejeitados.
Entreseq73/80 foram conferidos25arquivos imutáveis,91IDs e dez rejeitados iguais.
O run38665231394 terminou400 no primeiro bloco, por união de schema ambígua;
seq94 conserva25arquivos imutáveis,91IDs e dez rejeitados idênticos aseq73.
O run38666579042 aceitou o formato de duas listas. PT chegou ao gate final
de tradução e foi rejeitado após dois reparos; não deve ser reaberto. ES
terminou por resposta incompleta no segundo reparo; EN ainda não iniciou.
Os dez rejeitados anteriores permanecem; o total agora é11 com PT novo.

A automação foi pausada (`PIPELINE_AUTOMATION_ENABLED=false`) na geração
assistida para impedir publicação pelo cron antes da autorização específica.
O horário versionado continua09UTC, mas não executa enquanto a variável ficar
falsa. Testes Gemini permanecem isolados, sem upload, na branch gemini-recovery;
isso não substitui o provedor em produção.

## Autoridade e pré-requisitos

O transporte semântico pode usar `semantic_citation_ids: true`: o modelo escolhe
um ID `fN` do ledger factual ou `s0` da fonte completa disponível na chamada,
e o código recupera a citação original
antes dos mesmos parsers, gates e validações de patches.
O schema separa gramática/estilo/idioma (referência opcional) das mesmas categorias
que exigem evidência no gate local (ID válido não vazio obrigatório).
No transporte, `issues` e `language_issues` são listas fechadas separadas; a
aplicação reúne ambas antes dos parsers/gates. Não usa a união `anyOf` recusada
pelo backend. Categoria na lista errada bloqueia, sem reclassificar o achado.
O candidato viaja inteiro como unidades `cN`, sem duplicar/truncar o texto.
O modelo escolhe IDs contíguos e um original literal único nesse intervalo;
a aplicação calcula `start` e aplica os mesmos gates de span/perfil/sobreposição.
IDs inválidos, repetidos, fora de ordem ou ocorrência ambígua bloqueiam com o
mesmo orçamento de três tentativas. O rollback do transporte também restaura
o candidato literal e offsets legados; não muda etapas aprovadas persistidas.
IDs desconhecidos, campos/tipos inválidos e evidência factual ausente bloqueiam. Não altera hashes,
perfis ou etapas aprovadas persistidas. `false` restaura o protocolo literal
anterior; ledger ausente/não tipificado também mantém esse protocolo. O registro
aceita ledger tipado vazio e conserva `s0` quando há fonte disponível. O orçamento
de três tentativas e o teto de2.048 tokens não aumentam.

O snapshot privado contém backup SQLite, filas explícitas, fonte/perfil e
passos aprovados, metadados e MP4/JPG ainda necessários. A restauração verifica
hashes, schema, caminhos e batches completos antes de escrever `ready.json`.
Cache legado é candidato à importação, nunca substituto automático do head.

Destino único: `MoneyzxD/Automatic-Reddit-State`, privado. Configure em
`MoneyzxD/Automatic-Reddit-Git`:

- Variable `PIPELINE_STATE_REPO=MoneyzxD/Automatic-Reddit-State`.
- Secret `PIPELINE_STATE_TOKEN`: token fine-grained com acesso somente ao
  destino privado e permissão **Contents: Read and write**. O operador cria e
  cadastra o token; não o envie no chat nem imprima seu valor.

Em operações assistidas no host, configure os mesmos nomes, namespace e
`PIPELINE_STATE_REQUIRED=true`. Checkpoints precisam de identidade run/attempt
não anterior ao head e commit hexadecimal; sem isso, a operação bloqueia.
Produção automática desta entrega é Actions; implantação Oracle não foi validada.
Mantenha um único gravador. O token amplo do
`gh` e `GITHUB_TOKEN` não são substitutos implícitos dessa credencial.
OAuth YouTube continua separado, com renovação manual enquanto Testing.

Para escoar mídia já aprovada sem depender de geração nova, o disparo manual
em `main` aceita `state_action=publish`, `apenas_gerar=false`,
`historia_teste=false`, `dry_run=false` e namespace vazio. Ele restaura
`production`, executa somente `publish.py` e confirma o checkpoint final.
O grupo de concorrência, a conferência de upload incerto, a meta diária e as
janelas continuam os mesmos. Preview, branch de validação e falha de restore
bloqueiam esse modo. O cron normal continua responsável por completar a meta.

Para retomar a geração real preservando a mesma fonte/perfil e a fila, sem
publicar, use `state_action=generate` em `main`, `historia_teste=false`,
`dry_run=false` e namespace vazio. Esse modo restaura `production`, gera com
todos os gates e salva checkpoints/MP4/JPG/fila pendente no destino privado.
`apenas_gerar` pode ficar ligado: a ação explícita define produção sem upload,
não cria o namespace vazio de preview usado por `normal` + `apenas_gerar`.
Tokens YouTube não são entregues à geração e `publish.py` é pulado, mesmo
se `apenas_gerar=false`. O grupo de concorrência continua `pipeline-videos`;
cron, dados sintéticos, dry-run e branches de validação não aceitam essa ação.
O envio posterior da fila aprovada usa `state_action=publish`, após autorização
de publicação. Nenhum desses modos apaga o head nem reabre conteúdo rejeitado.
Uma execução futura normal/cron pode publicar essa fila; durante uma geração
assistida que aguarda autorização, mantenha a automação pausada.

## Incidente de sigla em 14/10/2026

O run isolado `38504547891` extraiu uma fonte real, aprovou a adaptação EN,
mas bloqueou PT na tradução e terminou por indisponibilidade semântica em ES.
Não gerou mídia nem executou upload. O snapshot privado e a quarentena mostram
`AITAH` na fonte, `AITCH` na adaptação aprovada e um erro crítico de ortografia
em `AITCH` na última revisão PT. A expansão EN ausente deixou o corretor
transformar a sigla em outra palavra, carregada para a tradução.

A correção expande AITA/AITAH para `Am I in the wrong` antes da revisão.
A regressão reproduz a sugestão AITAH→AITCH e verifica fonte/perfil imutáveis
em retomada. Gates, modelos, chaves, número de reparos e estados rejeitados
permanecem preservados. Esse diagnóstico não comprova a resolução de todos os
429: ES terminou com subtipo de quota desconhecido e ainda exige execução real.

O JSON do revisor elimina somente espaços estruturais; o conteúdo decodificado
permanece idêntico. No contexto de outro incidente, isso economizou 343 tokens
de entrada no tokenizer oficial, sem remover fonte, fatos ou perfil. Não é
promessa de caber na quota diária nem autorização para aprovar sem revisão.

## Bootstrap de produção: importação assistida

Antes do bootstrap, quando o candidato existe apenas no cache do Actions,
execute `state_action=inventory` na branch revisada, com `legacy_cache_run_id`
do run exato. O modo restaura DB e fila desse mesmo run e preserva um ZIP
somente no destino privado, namespace `legacy-inventory`. Ausência de fila é
registrada, nunca preenchida. Ele não gera/publica, não cria marker/head,
não salva cache nem altera a autoridade de produção. Falta/divergência de um
dos caches bloqueia a captura. O ZIP é candidato para comparação/reconciliação,
não snapshot aprovado; mídias não estavam no cache e precisam de recuperação.
Compare também o último estado íntegro quando o DB recente apresentar perda de
histórico. A decisão de importação continua exigindo o relatório abaixo.

1. Preserve a cópia atual do DB/filas e recupere a mídia referenciada. Não
   apague caches, dedupe ou IDs. Paths devem pertencer à raiz candidata.
2. Na raiz candidata, gere o inventário privado:

   ```bash
   python scripts/pipeline_state.py verify --namespace production --base-dir . --legacy-report data/state/reconciliation.json
   ```

3. Revise hashes, arquivos faltantes, IDs confirmados e itens incertos/legados.
   Para cada item ambíguo, confira o Studio e preencha `decisions` com
   `language`, `item_id`, `studio_checked: true` e a ação explícita:
   `retain_pending` + `confirmed_absent: true`; `confirmed_uploaded` +
   `video_id` e `confirmed_at` com fuso; ou `cancel_unknown` sem ID conhecido.
   `tiktok: cancelled` é decisão opcional para encerramento do kit manual.
   `thumbnail: cancelled` encerra somente uma tentativa de capa `failed` ou
   `missing`, exige `confirmed_uploaded` e preserva o ID, os erros e os estados
   anteriores no registro de reconciliação. Não declara sucesso de capa.
   Um ID já confirmado nunca é substituído nem volta a pending.
4. Calcule SHA256 do arquivo revisado. Bootstrap exige esse digest, a mesma
   raiz/namespace e inventário ainda idêntico; qualquer mudança invalida a
   aprovação. Execute com o hash real do relatório:

   ```bash
   python scripts/pipeline_state.py bootstrap --namespace production --base-dir . --reconciliation-file data/state/reconciliation.json --confirm-digest <SHA256>
   ```

   No Actions, `state_action=bootstrap` usa o relatório no Secret
   `PIPELINE_STATE_RECONCILIATION_REPORT` e o input `bootstrap_confirm_digest`.
   Cache sozinho não recupera mídia: prepare previamente o candidato íntegro
   no runner ou realize a importação assistida na raiz local completa.
5. Restaure/verifique o primeiro head em outra raiz privada antes da liberação.
   Se o namespace já tiver head, use restore; bootstrap não o sobrescreve.

Fonte legada não preservada não pode ser inventada a partir de hash ou
quarentena redigida. Sem fonte íntegra/prova de efeitos externos, mantenha
dedupe e bloqueio de replay, inclusive no incidente `1wfduc8`.

## Validação isolada no Actions

Na branch revisada, rode `state_action=normal`, `historia_teste=true`,
`apenas_gerar=true`, `dry_run=false`, idiomas `pt en es` e um namespace
`validation-<nome>` explícito. Um preview novo faz bootstrap vazio autorizado
somente nesse namespace; se já existir head, restaura-o. Nenhum token YouTube
é entregue ao passo de geração e namespaces de validação bloqueiam publicação
também no código, não apenas no YAML.

O segundo run usa `state_action=verify` e o mesmo namespace. Restaura em outro
runner sem gerar/publicar e verifica controle/mídia. Inspecione MP4, ASS/card,
perfil/source IDs e duração/resolução, além do diagnóstico semântico real.
`dry_run=true` simula em namespace isolado e não cria snapshot production.
O dry-run também não abre/cria/migra o banco persistente: a suíte de testes
anterior ao restore deve deixar a raiz de bootstrap sem DB/fila de simulação.
Bootstrap/verify também não geram/publicam. Publicação normal exige main,
namespace production, restore íntegro e serviços obrigatórios disponíveis.

## Falhas e recuperação

- Falha HTTP, snapshot ausente/corrompido, mídia pendente ausente ou recibo
  incompatível bloqueiam a operação; não iniciam estado vazio.
- Fila ausente após restauração ou em modo obrigatório bloqueia checkpoint,
  inclusive para itens legados. O bootstrap vazio de validação cria as quatro
  filas explicitamente; ausência de arquivo nunca significa descarte aprovado.
- Restore bloqueia se houver `pipeline.db-wal`, `pipeline.db-shm` ou
  `pipeline.db-journal` no destino. Preserve DB/sidecars e interrompa qualquer
  gravador antes da recuperação assistida; o código não os apaga. Paths que
  colidem por caixa ou ponto/espaço final também são rejeitados antes do commit.
- A fonte, perfil, roteiro aprovado, partes preparadas e batch exportado têm
  checkpoints intermediários. O save final em erro só roda após restore
  bem-sucedido e exige recibo válido, sem marker de restauração incompleta.
- Antes de enviar ao YouTube, o head registra `uploading`. O ID retornado é
  confirmado duravelmente antes de thumbnail/limpeza. Capa 403 não reenvia o
  vídeo. Se o resultado ou checkpoint for incerto, confira o Studio antes de
  reconciliar; a rodada é interrompida e novos envios desse idioma ficam
  bloqueados, inclusive por chamada direta ao uploader. Não existe garantia
  de exactly-once após efeitos externos.
- Processing abandonado permanece bloqueado até reconciliação assistida por
  fonte/perfil/batch. Bootstrap inicial não é um comando de edição de um head
  existente; recuperação de head já criado exige procedimento revisado e
  autorização específica, não apagar releases para forçar bootstrap.
- Payloads são publicados antes do marker completo; upload parcial não vira
  head. Os completos anteriores permanecem para recuperação assistida. Não
  há DELETE externo; capacidade/limites causam erro, nunca descarte silencioso.
- Reexecutar um run mais antigo que o head não permite confirmar um novo
  checkpoint. Inicie novo workflow_dispatch em vez de publicar estado que a
  ordenação dos heads ignoraria.
- Rollback de código conserva schema aditivo e snapshots; voltar à versão
  antiga exige reconciliar IDs posteriores, não restaurar cache velho.

Estado, relatórios de reconciliação, tokens e fontes de recuperação ficam fora
dos artifacts públicos. Logs sanitizados e mídia aprovada mantêm a política
existente. Agentes de manutenção/crescimento são entregas posteriores.

## Publicação independente da disponibilidade de geração

O operador autorizou retomar publicação automática em 17/10/2026 UTC. O passo
de publicação pode executar após falha da geração, exigindo restore e testes
bem-sucedidos, política de publicação válida e execução não cancelada. Antes
de qualquer kit ou upload de uma fila não vazia, um checkpoint
`publication_preflight` valida e persiste o estado atual. Falha de estado
interrompe os efeitos externos; o checkpoint anterior a cada upload permanece.
Estados rejeitados e IDs confirmados não são reabertos por essa separação.

A variável `GEMINI_RETRY_NOT_BEFORE` aceita data ISO com fuso. Até esse prazo,
o workflow pula geração e pode publicar a fila aprovada. Data inválida bloqueia
geração; ausência libera a tentativa normal. Catálogo e dry-run não geram
conteúdo. A data expirar não garante disponibilidade da API. O primeiro prazo
é `2026-10-18T00:00:05Z`, derivado do RetryInfo real, sem trocar chave/modelo.

Prova real: [run38989995803](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38989995803)
terminou success, com 1.302 testes reais sem skips, geração pulada pela janela e
três vídeos enviados/agendados, conferidos na API YouTube. Production/seq132
conserva os 91 IDs anteriores, acrescenta três e mantém 12 estados rejeitados,
sem pendência nem envio incerto. Cron09UTC e automação true conferidos após o
upload. Os três novos vídeos têm capa403, sem afetar o agendamento; mídia fica
preservada. Evidência e limite da geração em [GEMINI_MIGRATION](GEMINI_MIGRATION.md).
