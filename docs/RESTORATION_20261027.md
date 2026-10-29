# Retomada automática — 27/10/2026

## Situação conferida em29/10, 14h de São Paulo

Manual40797660200 e cron40866173891 terminaram com erro de geração, mas upload
e estado foram salvos. Cinco vídeos novos confirmados pela API: PT2 e EN3,
todos processados no canal correto. ES ainda0. O snapshot430 preserva102IDs,
43estados encerrados e o conteúdo dos140arquivos imutáveis anteriores; zero
processing. As três diferenças de perfil são só serialização canônica idêntica.

O diagnóstico do Groq prova OTPM1000 contra pedido1024. A revisão passa a900,
sem mudar fatos/Gemini2048, modelo, chave ou bloqueio de resposta incompleta.
Recusa sem motivo também pode regenerar título/hooks dentro do orçamento de
três candidatas; persistência continua indisponível. Falha real da geração
429/5xx/conexão/timeout propaga antes de fallback e não provoca regeneração.

Agenda corrigida para ocupar também os horários confirmados de rodadas
anteriores: o incidente EN16h09/16h15UTC vira19h10 no replay isolado, mantendo
90min. Janela/quota e excedente máximo de uma parte amanhã são preservados;
pendentes sem vaga permanecem na fila. Vídeos já enviados não foram alterados.

24REDs,339testes próximos e1.581completos com LanguageTool real passaram;
revisão independente sem pendências. Correções implantadas em0720fc8 e
[run40918218668](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/40918218668)
iniciado às14h07, meta3/publicação PT/EN/ES, restaurando430. Falta aceite PT/ES.
Checkpoint434: ES1x5ugmy em processamento;102IDs anteriores preservados.

Outra falha concreta no log: tradução PT1wybqga completou2048tokens e terminou
em length, sem usar texto parcial. O ajuste seguinte envia none só para Qwen3.8
Groq, como já faz o guardião; outros modelos/Gemini e cap2048 preservados. Dois
REDs e seis casos de SDK,222testes próximos e1.587completos com LT real passaram
em82,14s; revisão sem achados. A eficácia real fica para a execução posterior,
pois o run ativo usa0720fc8. Atribuir o truncamento ao raciocínio é inferência.
Os registros abaixo são históricos, não evidência de uma execução ainda ativa.

## Estado vigente — 28/10/2026

Run40797660200 está em andamento no head4777aa2. Checkpoint378: dois vídeos PT
de1x5ugmy exportados/pendentes; ES da mesma fonte unavailable por recusa sem
motivo válido, com metadata_part1 aprovada e metadata_part2 pendente. EN1x9nddb
1x9vb4m e1x9w7n2 rejeitados pela revisão;1wvcl31 com tradução/naturalização
aprovadas. Os97IDs preservados;
nenhum upload novo até esse checkpoint. Não é aceite integral.

A retomada parcial de descrições consulta o checkpoint antes da geração.
Se fonte/perfil/entrada/parte coincidem, recompõe os blocos localmente usando
o texto aprovado, sem chamada remota descartada. Entrada diferente exige nova
geração e revisão; o gate antes da voz permanece. Um RED e uma contraprova;
182testes próximos e1.541completos com LanguageTool real passaram em78,05s.
Revisão independente sem achados. O run em curso não recebe esta alteração.

Descrições agora têm uma única candidata adicional para recusa fundamentada ou
unexplained_rejection, sempre com os gates completos. Recusa vazia persistente
continua indisponível. Quota, timeout,503,LT,JSON e estado não geram nova candidata.
Na geração Groq de metadados, falhas reconhecidas429/5xx/conexão/timeout propagam
LLMUnavailable antes do template; esse é um ajuste deliberado para não repetir
um serviço indisponível. Truncamento/ausência de chave e Gemini mantêm seu fluxo.
Oito RED (recuperação e falha da geração),188testes próximos e1.556completos com
LanguageTool real passaram em79,42s; revisão independente sem achados. São provas
locais com clientes de IA falsos, sem nova chamada externa ou upload.

O seletor agora prioriza retomadas explícitas, depois idioma ausente de fonte
que já concluiu geração em outro idioma, e só então demais ausentes. Na ordem
anterior, a fonte PT bem-sucedida1x4uvxk ficava em8º para EN, fora das seis
tentativas. Reprodução em cópia isolada confirmou a nova prioridade. Nenhum
estado, perfil, gate ou limite é alterado. Quatro regressões RED;113testes
próximos e1.539completos passaram; revisão independente sem achados. A alteração
não modifica o run que já está ativo.

A rodada [40772331493](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/40772331493)
usou `c36770f`, produção, Groq, PT/EN/ES, meta normal de três vídeos e publicação
habilitada. Foi cancelada pelo agente para liberar os diagnósticos após PT e
ES ficarem indisponíveis, antes de qualquer upload novo. Save final e logs
passaram. O checkpoint 354 preserva 97 IDs, todas as rejeições anteriores e
132 arquivos imutáveis idênticos à baseline; não deixou linhas `processing`.

PT falhou na revisão chunk da tradução de `1xf3poe`; ES passou a naturalização
de `1x6sq3x`, mas falhou na revisão global do título. Ambos receberam HTTP429
com tipo declarado **OTPM**, mesmo com cap 1024, e sem Retry-After. Os cabeçalhos
gerais ainda indicavam TPM 8000 disponível; não representam saldo de saída.
Não foi comprovado que reduzir o cap ou esperar 61 segundos resolva esse limite.
Após autorização específica, uma chamada diagnóstica ES retornou HTTP200 em
1,52s, completa, com cap1024 e sem retries. Título/fonte foram conferidos por SHA;
o contexto factual veio do checkpoint aprovado de naturalização. A chamada
isolada não informa o limite, pois não houve429, nem comprova continuidade.

A rodada normal passa a registrar `rate_limit_diagnostic`: apenas números
finitos de limite, uso, pedido e espera declarados em uma mensagem 429 com código
conhecido e cota única reconhecida. Mensagem, IDs e conteúdo não são armazenados.
Este diagnóstico não altera `_retry_wait`, tentativas ou gates. Formatos parciais
e ambíguos são descartados. Provas com SDK/transporte HTTP isolado e privacidade:
345 testes próximos e 1.535 na suíte completa, com LanguageTool real; revisão
independente sem pendências. Disponibilidade real será medida separadamente.

EN ficou sem fontes após 36 respostas 502/503 do arquivo gratuito. A revisão
encontrou uma inconsistência: fonte gerenciada com idioma ainda não registrado
era elegível em `processing_languages`, mas não em `retry_candidates`. O seletor
agora inclui esse idioma ausente e usa a fonte privada íntegra, sem exigir raw
ou nova coleta. Não muda estados anteriores, fonte, perfil ou gates. Idiomas
explicitamente rejeitados, exportados ou processando e fontes legadas continuam
fora da retomada. Oito casos falharam antes da correção; os testes integrados
proíbem extração e preservam a linha PT inteira ao iniciar EN. Isso corrige a
dependência desnecessária da coleta, sem prometer disponibilidade do Groq.

Os três tokens foram renovados em 28/10, enviados aos Secrets e validados por
refresh e consulta autenticada do canal esperado. Nenhum login está pendente.
A suíte local final passou com 1.517 testes e LanguageTool 6.6 real; a revisão
independente não encontrou bloqueios. Esses resultados não substituem a
confirmação de geração e publicação nos três idiomas.

Correção implantada em `c6faba7`. A verificação
[40779021584](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/40779021584)
terminou com sucesso: 1.517 testes em 28,89s, restauração privada e validação do
estado aprovadas, geração/publicação/save pulados. Automação permanece habilitada,
Groq fixo e meta3. A rotina integral ainda não foi comprovada nesta retomada.

Os registros abaixo são históricos; o estado acima prevalece sobre pendências
antigas. Para continuar o acompanhamento sem alterar produção, consulte a
seção inicial de [PROJECT_HANDOFF.md](../PROJECT_HANDOFF.md).

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

- Geração diária antecipada para `17 5 * * *` (05h17 UTC / 02h17 São Paulo),
  com as mesmas janelas de publicação, meta e exclusão de gravadores simultâneos.
  Oito execuções agendadas consultadas começaram entre13h00 e15h39 UTC sob o
  cron antigo de09h00 UTC. A antecipação dá margem para atraso e processamento;
  o minuto17 segue a [orientação do GitHub](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows)
  de evitar hora cheia, sem garantir pontualidade. Às05h17 UTC, os três canais
  já estão no mesmo dia local inclusive no inverno de Nova York.
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
