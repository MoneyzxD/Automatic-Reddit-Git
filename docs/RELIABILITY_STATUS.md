# Confiabilidade — evidência operacional 2026-10-04

Main permanece em 30a0a0c; não houve integração/publicação nesta validação.
Branch de trabalho: pipeline-reliability. Retomada técnica e rulings ficam no
ledger privado `.superpowers/sdd/2026-10-03-pipeline-reliability/progress.md`.

## Continuação: referências factuais aprovadas

Implementação limitada: unidades lossless de 200 caracteres com IDs locais,
seleção ordenada/contígua/única; evidência copiada da fonte pelo código.
Referências inválidas bloqueiam, e revisão de value/fidelidade/gênero/gramática
permanece obrigatória. Revisão independente aprovou. Probe Groq da história
sintética: dez fatos literais em duas chamadas. Ainda não é aceite de vídeo.
Após autorização do operador para continuar, probe da fonte preservada
1wfduc8 passou: 13 fatos, uma chamada, todas as citações literais. Isso valida
a coleta factual, não o roteiro completo. O encerramento de 91 kits TikTok
e 56 tentativas de capa antigas foi autorizado. A autorização não confirma
a ausência de publicação manual dos sete vídeos sem ID; esses ficam bloqueados.

Commit de código `dc87c02`, suíte local 786 passed/30 warnings/53.57s,
compileall e diff check passaram. Run37241728126 passou testes, LanguageTool
e restore; coleta factual avançou, adaptação entrou em repairing. Revisão
global interrompida por rate_limit/HTTP429, uma tentativa, contexto14265.
Checkpoint final foi salvo; nenhum MP4 ou upload. LT background aparece
cancelled no encerramento, mas seu health/warmup passaram; não atribuir a ele
a falha de geração. Verify37242044138 passou em outro runner, sem Groq/geração/
publicação: 786 testes/17.33s, sete arquivos de controle restaurados, mídia zero.
Confirma recuperação de fonte/perfil/controle, não renderização nem upload.

Run37243243200, no mesmo namespace isolado: geração interrompida por HTTP429
em facts, uma tentativa, contexto4794; sem mídia/publicação. Ainda não havia
diagnóstico do tipo de cota. Não atribuir esse limite aos incidentes antigos
nem concluir que a credencial local é idêntica à do runner. Ajuste aditivo
registra somente enumeração de limite declarada e Retry-After numérico finito;
não guarda mensagem livre, não muda retry e não alterna chaves.
Suíte local atual: 809 passed, 30 warnings, 54.89s; compilação e diff check
passaram. Revisão independente do diagnóstico aprovou o escopo, não o rollout.

Run37244100764, código ec15619: HTTP429 em facts confirmou limite de tokens
por dia (TPD), Retry-After430s, uma tentativa, contexto4794. Testes/LanguageTool/
restore/save final passaram; sem mídia/upload. O cancelamento do processo LT
ocorreu no encerramento, após health/warmup bem-sucedidos. Respeitar a espera
indicada antes de novo teste; não inferir renovação completa da cota diária.
Verify37244536054 passou em outro runner: 809 testes/19.15s, restore confirmado,
sete arquivos de controle/mídia zero, sem Groq/geração/publicação. Após a espera,
run37244757274 (dispatch23:43:03UTC) voltou a falhar em facts por TPD às23:46:15,
Retry-After647s, uma tentativa/contexto4794. Sem mídia/upload; save final passou.
Não continuar repetindo geração sob cota: a espera informada não garantiu
disponibilidade para essa chamada. FullPTENES permanece não validado.

Rascunho privado de reconciliação preparado em cópia local separada:
84 IDs/91 itens legados/7 incertos, 14 arquivos de mídia copiados com hash,
112 referências ainda sem bytes. Originais conferidos antes/depois, preservados.
Paths rebased só na cópia; nenhuma decisão aprovada, head ou importação.
Snapshot candidato continua inválido por necessidade de reconciliação.
Propostas adicionais privadas: 84 IDs, 7 desconhecidos bloqueados, 91 kits e
56 capas; inventário original intacto, nenhuma decisão aplicada. As propostas
não declaram Studio conferido nem constituem aprovação para bootstrap.
Versão2 das propostas preserva os horários reais do campo legado YouTube,
com fuso explícito, para não contabilizar 84 envios históricos como feitos hoje.

## Investigação e validação

- Runs antigos 37128480329/37209564422: revisão de adaptação EN indisponível;
  classe HTTP original não preservada. Mesma causa não comprovada.
- Fontes 1wfduc8/1wf0he0 recuperadas do Reddit com hashes originais conferidos;
  conteúdo e logs preservados apenas no workspace privado de investigação.
- Run37237857551: HTTP400/json_validate_failed facts tentativa2, sem mídia.
  Distinto do rate_limit429 registrado anteriormente.
- Probe da coleta com fontes conferidas: 1wf0he0 aprovado em três chamadas;
  1wfduc8 nonliteral_evidence após três. GPT-OSS120B também falhou com essa
  fonte, na mesma chave EN. Probes não testaram o roteiro completo/voz/card.
- Suíte local: 773 testes passaram, 30 avisos, 83.30s. Os dois runs de captura
  passaram 773 testes e LanguageTool real; isso não é aceite de geração.

## Estado preservado, ainda não importado

Capturas somente privadas, sem marker/head production:

| Candidato cache | Run de captura | Histórias DB | Partes DB |
|---|---|---:|---:|
| 37209564422 | 37238541263 | 2 | 0 |
| 37025408714 | 37238543218 | 30 | 91 |

ZIPs e arquivos conferidos por SHA-256. Filas PT/EN/ES são iguais byte a byte
nas duas cópias; a cópia anterior inclui as duas histórias dos incidentes.
Run37063586921 salvou cache de DB após falha dos testes antes de restaurar;
run37064703594 o combinou com fila37025408714. O workflow novo remove essa
autoridade de cache e exige restore confirmado para save final. Dry-run agora
não abre/migra DB persistente. Essas correções ainda não estão em main.

Filas: PT 31 itens/28 IDs, EN 31/29 IDs, ES 29/27 IDs. Total de 84 IDs confirmados,
preservados sem alteração. Consulta autenticada de leitura aos canais confirmou
81 IDs. Três PT não foram encontrados em playlist nem videos.list:
2kj7o4kuHrw, ay5u5p8f3mw, kMH9jjv8XQo. Preservar histórico; ausência atual
não autoriza recriar vídeos nem apagar registros.

Sete itens sem ID (global uploading, YouTube failed): 1wtjwq4_pt e as duas
partes de 1wqijcl em cada idioma. Logs36737131418 mostram invalid_grant antes
de iniciar envio; os runs36887596133/37025408714 não os tentaram novamente.
Playlist atual não encontrou título exato. Isso não exclui upload manual com
outro título: operador precisa conferir e aprovar a decisão antes de reenvio.

Mídias desses sete itens recuperadas de video-36737131418: 7 MP4 + 14 JPG,
490246562 bytes. ffprobe: todos 1080x1920, durações 77.30–137.54s. Não foram
aprovados semanticamente nesta etapa; são mídia legada para reconciliação,
não prova da renderização da branch nova. Skill watch conferiu três amostras
locais (PT casa, EN/ES irmão, parte1) em 00:01/00:03/00:15. Cards legíveis e
sem corte nos dois primeiros quadros de cada vídeo; legendas visíveis em PT/EN
aos15s, não no quadro ES. Sem transcrição/áudio, não distinguir pausa de fala
de problema de legenda nem aprovar voz/sincronização. Nenhum upload externo.

Todos os 91 kits TikTok continuam pending no original. EN/ES têm 56 tentativas
de capa failed. Encerramento autorizado, mas ainda não aplicado ao estado
production. Código de reconciliação aceita cancelamento explícito de capa
failed/missing somente junto de upload confirmado, conservando ID/erros e
auditando estados anteriores. Testes reais de clone/fila passaram e revisão
independente aprovou. Não fingir postagem TikTok nem sucesso de capa.
Bootstrap exige relatório aprovado e candidato
íntegro; ele não foi executado. Não substituir faltantes por fila vazia.

## Gates restantes

1. Cota TPD identificada no runner; respeitar espera antes de validar geração.
2. Gerar PT/EN/ES completos, conferir roteiro/voz/ASS/card e restore da mídia.
3. Aprovar reconciliação específica de efeitos externos e mídias legadas.
4. Bootstrap, verify independente, integração em main e rodada dentro da meta.

Cron legado permanece habilitado (`PIPELINE_AUTOMATION_ENABLED=true`), sem
alteração neste trabalho; isso não significa que a branch nova foi liberada.
Agentes de manutenção/crescimento ficam após esses gates. Nenhum Secret
YouTube/Groq/Reddit, cron, meta, vídeo remoto ou estado production foi alterado.
