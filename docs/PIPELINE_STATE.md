# Recuperação privada do pipeline

Status: código na branch `pipeline-reliability`, ainda sem liberação de produção.
Teste unitário/fake HTTP não comprova persistência no GitHub nem upload real.

## Autoridade e pré-requisitos

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

## Bootstrap de produção: importação assistida

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
Bootstrap/verify também não geram/publicam. Publicação normal exige main,
namespace production, restore íntegro e serviços obrigatórios disponíveis.

## Falhas e recuperação

- Falha HTTP, snapshot ausente/corrompido, mídia pendente ausente ou recibo
  incompatível bloqueiam a operação; não iniciam estado vazio.
- A fonte, perfil, roteiro aprovado, partes preparadas e batch exportado têm
  checkpoints intermediários. O save final em erro só roda após restore
  bem-sucedido e exige recibo válido, sem marker de restauração incompleta.
- Antes de enviar ao YouTube, o head registra `uploading`. O ID retornado é
  confirmado duravelmente antes de thumbnail/limpeza. Capa 403 não reenvia o
  vídeo. Se o resultado ou checkpoint for incerto, confira o Studio antes de
  reconciliar; não existe garantia de exactly-once após efeitos externos.
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
