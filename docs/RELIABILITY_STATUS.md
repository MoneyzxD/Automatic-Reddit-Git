# Confiabilidade — evidência operacional 2026-10-04

Main permanece em 30a0a0c; não houve integração/publicação nesta validação.
Branch de trabalho: pipeline-reliability. Retomada técnica e rulings ficam no
ledger privado `.superpowers/sdd/2026-10-03-pipeline-reliability/progress.md`.

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
- Suíte local fresh: 773passed, 30warnings, 83.30s. Os dois runs de captura
  passaram 773testes e LanguageTool real; isso não é aceite de geração.

## Estado preservado, ainda não importado

Capturas somente privadas, sem marker/head production:

| Candidato cache | Run de captura | Histórias DB | Partes DB |
|---|---|---:|---:|
| 37209564422 | 37238541263 | 2 | 0 |
| 37025408714 | 37238543218 | 30 | 91 |

ZIPs e arquivos conferidos por SHA256. Filas PT/EN/ES são iguais byte a byte
nas duas cópias; a cópia anterior inclui as duas histórias dos incidentes.
Run37063586921 salvou cache de DB após falha dos testes antes de restaurar;
run37064703594 o combinou com fila37025408714. O workflow novo remove essa
autoridade de cache e exige restore confirmado para save final. Dry-run agora
não abre/migra DB persistente. Essas correções ainda não estão em main.

Filas: PT31itens/28IDs, EN31/29IDs, ES29/27IDs. Total84IDs confirmados,
preservados sem alteração. Consulta autenticada de leitura aos canais confirmou
81IDs. Três PT não foram encontrados em playlist nem videos.list:
2kj7o4kuHrw, ay5u5p8f3mw, kMH9jjv8XQo. Preservar histórico; ausência atual
não autoriza recriar vídeos nem apagar registros.

Sete itens sem ID (global uploading, YouTube failed): 1wtjwq4_pt e as duas
partes de 1wqijcl em cada idioma. Logs36737131418 mostram invalid_grant antes
de iniciar envio; os runs36887596133/37025408714 não os tentaram novamente.
Playlist atual não encontrou título exato. Isso não exclui upload manual com
outro título: operador precisa conferir e aprovar a decisão antes de reenvio.

Mídias desses sete itens recuperadas de video-36737131418: 7MP4 +14JPG,
490246562bytes. ffprobe: todos1080x1920, durações77.30–137.54s. Não foram
assistidos nem aprovados semanticamente nesta etapa; são mídia legada para
reconciliação, não prova da renderização da branch nova.

Todos91kits TikTok continuam pending. EN/ES têm56tentativas de capa failed.
Esses estados ainda requerem mídia no snapshot, mesmo com YouTube confirmado.
Recuperar artefatos disponíveis ou obter decisão explícita sobre encerrar
kits/tentativas antigos, conservando IDs e diagnóstico; não fingir postagem
TikTok nem sucesso de capa. Bootstrap exige relatório aprovado e candidato
íntegro; ele não foi executado. Não substituir faltantes por fila vazia.

## Gates restantes

1. Aprovar/revisar ajuste da coleta factual, mantendo evidência verificável.
2. Gerar PT/EN/ES completos, conferir roteiro/voz/ASS/card e restore da mídia.
3. Aprovar reconciliação específica de efeitos externos e mídias legadas.
4. Bootstrap, verify independente, integração em main e rodada dentro da meta.

Agentes de manutenção/crescimento ficam após esses gates. Nenhum Secret
YouTube/Groq/Reddit, cron, meta, vídeo remoto ou estado production foi alterado.
