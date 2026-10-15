# Recuperação privada do pipeline

Status: integrado em main; bootstrap e publicação recuperada confirmados em 13/10.
Teste unitário/fake HTTP não comprova persistência no GitHub nem upload real.

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
