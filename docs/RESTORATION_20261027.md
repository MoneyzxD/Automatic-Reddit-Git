# Retomada automática — 27/10/2026

## Incidentes de conteúdo de28/10

Run40761430663 foi cancelado para diagnosticar três recusas antes de upload.
O save final confirmou checkpoint344,97IDs preservados e nenhum ID novo. Os
três rejeitados PT permanecem fechados. A quarta fonte1xf3poe/PT foi marcada
unavailable ao desligar LT no cancelamento e pode retomar sem reabrir rejeições.

Dois bloqueios comprovados e corrigidos:

- EN: regra COMMA_COMPOUND_SENTENCE marcava " or", fora da candidata restrita
  anterior. Apenas a inserção literal sugerida pelo LT é testada, com nova
  revisão gramatical e semântica completa; não altera palavras ou fatos.
- PT: falso positivo TU_TI_EU_MIM em "para eu nem precisar subir". Eu é sujeito
  de precisar, conforme a [regra gramatical](https://ciberduvidas.iscte-iul.pt/consultorio/perguntas/para-eu-e-para-mim/39216).
  A exceção exige esse contexto literal no pt-BR. A mesma regra continua
  detectando erros verdadeiros, inclusive ao lado da ocorrência correta.

Seis regressões falharam antes. Backend6.6 real e contraprovas confirmaram os
reparos sem dispensar a autoridade semântica. Suíte final**1.506aprovados em78,34s**;
revisão independente sem achados. Nova rodada integral com meta3 ainda pendente.

## Atualização em28/10

Complemento de isolamento: cada filho único recebe carga Groq fixa PT/EN/ES,
inclusive para leitura e adaptação da fonte inglesa. O idioma do texto não
direciona chamadas PT/ES à chave EN. Sem override, mantém a seleção legada;
Gemini permanece independente. Isso corrige atribuição de orçamento, não prova
a origem do429 anterior. Em empate de faltas, o lote favorece menos tentativas.
Regressões reproduziram10falhas antes; suíte final**1.493aprovados em74,98s**,
com revisão independente sem achados. O run40761430663 continua com9cdfc83.

O Actions40596712855 terminou com sucesso e publicou EN1x9een7:
https://youtu.be/U4WtiENWvjg. A verificação autenticada confirmou public/processed
no canal EN correto; acesso anônimo oEmbed200. Coleta e FFmpeg passaram no runner.

O cron40718225099 parou na naturalização ES por429/OTPM, com reserva2048 e
cabeçalho TPM geral indicando8000. Esse cabeçalho não prova saldo de OTPM:
a [Groq documenta limites separados de saída](https://console.groq.com/docs/rate-limits).
Revisão de controle com texto ES já aprovado passou após a cota
recompor; não é prova de defeito no YouTube ou limite estrutural de2048.

O lote agora processa idiomas em série, com tentativas próprias. Indisponibilidade
de serviço pausa o idioma, sem trocar chave/modelo, e os demais completam sua meta.
Estado inseguro continua interrompendo todos. A flag interna --isolar-idioma,
permitida só com um idioma, retorna4 para dependência e2 para StateError; sem ela
a CLI continua retornando2 como antes. O lote ainda termina2 se houve dependência
indisponível, preservando o alerta e a publicação das filas aprovadas.

Groq reserva1024 nas revisões; extração de fatos e Gemini mantêm2048. Comprimento
incompleto continua bloqueado. Os**1.481 testes** passaram com o LanguageTool real
obrigatório em79,48s; revisão independente sem achados. Tokens dos três idiomas
renovados e Secrets atualizados em28/10 às20:08–20:09UTC. Refresh e canal esperado
confirmados por API. Datas públicas de expiração sincronizadas para produção.
Nova rodada real em preparação, com meta normal de3por idioma.

O operador autorizou restaurar geração e publicação pública nos três idiomas.
O aceite local PT é https://youtu.be/H2XqpcQM_50, sem repetição desse upload.
Este documento acompanha a implantação; o aceite local não equivale ao cron.

## Configuração da rotina

- `PIPELINE_LLM_PROVIDER=groq` seleciona explicitamente Groq no repositório.
  Gemini continua disponível com a mesma variável igual a `gemini`; não há
  alternância automática por indisponibilidade ou cota.
- `DAILY_VIDEO_TARGET=3` mantém a meta de três vídeos por idioma. A opção
  manual `validacao_groq=true` conserva meta mínima de um para diagnóstico.
- Tradução Groq direta foi habilitada em `config/settings.yaml`, como no
  teste PT aprovado. Os gates, perfil, dedupe e revisões continuam obrigatórios.
- FFmpeg tem instalação limitada a 300 segundos, em passo de dez minutos.
- Voz usa os tempos nativos do edge-tts; Whisper CPU recupera falha de CUDA.
  Sem tempos reais, o vídeo não é aprovado para legendagem por estimativa.

## Coleta

O cookie do GitHub era de setembro e foi atualizado com a sessão local.
Mesmo assim, o runner confirmou HTTP403 nos dois hosts Reddit, tanto com
requests (run40595012227) quanto com Chrome padrão (run40595331324).
Não foi implementado contorno de CAPTCHA, stealth ou alteração de fingerprint.
PullPush respondeu429 com mensagem de que exige serviço pago, fora da restrição.

O fallback foi substituído pelo arquivo público gratuito
[Arctic Shift](https://github.com/ArthurHeitmann/arctic_shift/blob/master/api/README.md).
Ele não recebe cookie Reddit. Busca posts com pelo menos dois dias para as
métricas amadurecerem, dentro da janela configurada, e exige votos, comentários
e proporção de aprovação presentes e válidos. Nenhum ratio padrão é inventado.
Posts removidos, IDs/subreddit inválidos e textos ausentes são descartados.
Os filtros normais permanecem responsáveis pelo aceite editorial.

Prova local real: consulta de cem posts retornou sete candidatos com voto/ratio
e texto suficientes para pré-filtro. O extrator completo obteve vinte posts
íntegros em cinquenta consultados, sem IA ou chamadas YouTube. A data do arquivo
é registrada em `source_retrieved_utc`; pode haver atraso de atualização.

## Provas e pendências

- Seleção de provedor/meta e gates próximos:149 testes aprovados.
- Suíte completa com LanguageTool real e ambiente obrigatório do CI:
  **1.472 testes aprovados em75,02s**, incluindo o fallback.
- Fallback:14 testes de regressão aprovados, após reproduzir13 falhas.
- Revisão independente: sem achados Critical/Important, incluindo o fallback.
- Autenticação Groq e modelos configurados presentes: PT, EN e ES confirmados.
- OAuth YouTube PT/EN válidos; ES precisa de login do operador (`invalid_grant`).
- Ainda conferir coleta e fluxo integral pelo runner com as correções implantadas.

OAuth em Testing continua decisão aceita: requer renovação manual semanal.
Mudar para Production não foi autorizado nem aplicado nesta retomada.
