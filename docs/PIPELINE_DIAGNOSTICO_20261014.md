# Diagnóstico da interrupção — YouTube e geração

## Resultado verificado

Em 14/10/2026, os tokens locais PT/EN/ES passaram no refresh OAuth em memória e
em channels.list(mine=true). Cada credencial aponta para um canal distinto e
vinculado. Nenhum token em disco foi substituído e nenhum upload foi tentado.
Essa consulta não mede saldo de cota para videos.insert nem demonstra que os
Secrets remotos são byte-identical aos arquivos locais.

O [run real de publicação 38344600714](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38344600714)
enviou sete vídeos e terminou com zero falhas de upload. HTTP403 afetou somente
as thumbnails EN/ES após confirmar os IDs; não causou reenvio. Não há evidência
de YouTube quotaExceeded nas falhas examinadas. Nos runs de geração que falharam,
a publicação foi pulada antes de qualquer chamada YouTube para vídeo novo.

O [run 38441271214](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38441271214)
registrou Groq HTTP429/TPD na revisão global da adaptação EN, com TPM restante
8.000 e RPD restante997. Portanto esses saldos não descartam limite diário de
tokens. O [run seguinte 38447177562](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38447177562)
repetiu 429 em chunk após aguardar534s/26s; o subtipo da última recusa não foi
capturado. Não atribuir a ela um subtipo por analogia.

O [último teste Gemini 38494779551](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38494779551)
recebeu uma tradução PT, mas a revisão encontrou HTTP429/resource_exhausted,
RetryInfo81.609s. Zero mídia/upload. Não há rodada PT/EN/ES Gemini aprovada.

## Reproduções sem envio de conteúdo

A fonte do incidente1wyx2wj foi lida somente do snapshot privado específico
production/38447177562/seq61, usando a credencial limitada de estado. Hash do
bundle, do membro e da fonte conferidos; não houve restore/escrita em produção.
O transporte do revisor foi substituído por captura local, sem chamar LLM.

O pedido reproduzido tem3.066 caracteres de fonte,3.136 de candidato,31 fatos,
instrução3.689 e contexto HTTP14.695 caracteres. O ledger armazenado tem9.312
caracteres, incluindo4.951 de citações e2.728 de valores. O tokenizer oficial
Qwen contou4.808 tokens no texto,263 no schema e cap2.048:7.119 no total estimado,
antes dos detalhes de template/provider. Isso não prova que o limite TPM de8.000
foi excedido e não substitui a contagem efetiva do provedor.

A retomada do gate indisponível refaz adaptação/coleta factual quando nenhum
checkpoint aprovado desse gate existe: dois sucessos do adaptador e um do
coletor aparecem novamente no run38447177562. É consumo adicional confirmado,
não prova isolada de que cache/compactação resolveria a produção.

## Limite da investigação e próxima prova

Não há navegador conectado disponível para ler Usage/Limits. Falta confirmar
o consumo TPD e a organização da chave EN usada no Actions. A
[documentação Groq](https://console.groq.com/docs/rate-limits) distingue TPM/TPD/RPD
e aplica cotas por organização, não por chave; não presumir que três chaves
significam três orçamentos. O modelo qwen/qwen3.8-27b tem base gratuita anunciada
de200KTPD, mas limites efetivos podem ser diferentes.

Um replay de uma única chamada real, mesma chave/modelo/cap, foi preparado em
data/state/probe_groq_incident.py, fora do Git. Ele imprime somente códigos,
limites/consumo numéricos e guarda eventual resposta apenas no diretório privado.
A revisão automática inicialmente rejeitou transmitir esse contexto privado.
Após a autorização do operador para a chamada específica, o replay foi executado
uma vez: HTTP200, prompt4.825, completion11, total4.836 tokens; TPM restante2.510,
RPD restante999. A chamada usou a mesma chave EN e o mesmo modelo, mas não incluiu
os achados LanguageTool do pedido original nem executou todo o guardião. Portanto
ela demonstra disponibilidade naquele momento, sem validar o pipeline completo.

O Reddit local também respondeu HTTP200 usando a sessão já configurada.
Não reiniciar loops de geração,
trocar chaves/modelos por cota, reduzir gates, reabrir rejeitados ou prometer
pipeline restaurado sem geração real e IDs de publicação confirmados. Produção
e documentos locais existentes do operador permanecem preservados.

## Causa concreta encontrada na execução seguinte

O [run38504547891](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38504547891)
usou fonte real em namespace isolado, sem upload. A adaptação EN foi aprovada,
mas AITAH na fonte virou AITCH no texto aprovado. Esse termo foi o último erro
gramatical crítico da tradução PT. ES terminou com429 de subtipo desconhecido.
Zero mídia gerada; a publicação foi pulada. O problema não se limita a EN.

A correção expande AITA/AITAH em inglês antes da revisão e no candidato novo de
adaptações retomáveis. Preserva fonte, hash, perfil, etapas aprovadas e rejeitados.
Não corrige arbitrariamente AITCH nem reabre a adaptação já aprovada do namespace
do incidente. A execução seguinte deve usar estado elegível de produção ou uma
validação nova. Veja [PIPELINE_STATE.md](PIPELINE_STATE.md) para gerar mantendo
produção, sem upload, e para o limite de publicação posterior pelo cron.
