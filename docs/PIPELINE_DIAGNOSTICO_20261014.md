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

## Estado depois da retomada sem upload

O [run38508047757](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38508047757),
commit ebb6ca0, passou testes e restore; dois pedidos do adaptador responderam200.
A coleta factual EN recebeu429 nas três tentativas, contexto3.738 caracteres,
TPM restante8.000/RPD restante1.000, sem subtipo nem espera declarados. Nenhuma
etapa nova aprovada, mídia nova ou upload. Não chamar esse resultado de falha
YouTube nem presumir qual cota foi atingida.

Snapshot production/38508047757/seq66:91IDs idênticos,24arquivos imutáveis
preservados byte a byte, dez estados rejeitados idênticos, EN/ES/PT unavailable
e nenhuma fila YouTube pendente. A automação está pausada, impedindo publicação
indireta da fila durante a recuperação assistida.

Em paralelo, Gemini ficou somente na branch gemini-recovery. A combinação passou
1.180 testes locais e revisão. O [teste38657422977](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38657422977)
respondeu à tradução e a cinco pedidos de revisão; terminou503/chunk após três
tentativas, sem429 nem mídia/upload. O diagnóstico encontrou também um ciclo de
crase: LT mudou `todas as vezes` para `todas às vezes`, o modelo desfez, e LT
voltou a apontar erro. A correção contextual e a prova com LanguageTool real
estão sendo validadas nessa branch; ainda não há aceite para substituir produção.

O [run38659167207](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38659167207)
passou1.190 testes no Actions, incluindo a prova do falso positivo na regra
AS_VEZES_BR6.6 real e a preservação do erro adverbial verdadeiro. A geração
Gemini terminou429/resource_exhausted, RetryInfo85.047s, sem mídia. Não repetir
antes do prazo, aproximadamente21h de15/10 em São Paulo. O filtro contextual
isolado foi aprovado para produção: apenas `todas as vezes`, com os demais
achados e as revisões semânticas preservados. A suíte local de produção passou
1.137 testes; os dois testes de runtime real ficam explicitamente pulados localmente.

A [comparação38659547097](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38659547097),
autorizada pelo operador, confirmou que a chave EN normalizada no Actions é
idêntica à local e usa o Secret específico EN. Nenhuma chamada LLM nessa
comparação. A [sonda pública38659982743](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38659982743)
fez uma chamada sem retry, chave/modelo EN fixos, cap2.048: HTTP200, prompt19,
completion2, total21. Texto público, sem história privada. Esse resultado não
valida a coleta factual com schema ou a geração completa.

## Retomadas com a chave conferida

O [run38660290998](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38660290998)
aprovou e persistiu a adaptação EN. A tradução PT terminou por
`nonliteral_evidence`: dois429 e uma resposta200 consumiram as três tentativas
do bloco. Snapshotseq73 sem mídia nova. A correção de transporte usa IDs locais
do ledger e da fonte; a aplicação recupera a citação original e mantém os gates.

O [run38662836166](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38662836166)
passou1.152 testes no CI, incluindo o LanguageTool real, e reutilizou a adaptação
aprovada. A coleta factual PT respondeu200. O bloco recebeu429/200/429; a última
recusa declarou Retry-After2s, TPM restante7.799/RPD998 e nenhum subtipo conhecido.
O relatório anterior conserva só a falha final; não afirmar por que a resposta
intermediária foi recusada. Snapshotseq80 sem mídia nova,25arquivos imutáveis
idênticos aseq73, mesmos91IDs/dez rejeitados.

A cadência anterior esperou16,3s após o coletor e35,3s após o bloco200. O reset
TPM do pedido anterior não garante capacidade para o próximo pedido maior.
O modelo fixo qwen/qwen3.8-27b agora tem piso conservador de61s, preservando
cabeçalhos com espera maior. Isso aumenta latência e só coordena o processo
atual; não garante cota diária nem coordena consumidores externos. Nenhum
modelo/chave alterna. Os limites de três tentativas/cap2.048 ficam iguais.
O relatório também guarda até20falhas intermediárias sanitizadas, com contagens
de evidência ausente/não literal; não guarda resposta, citação ou erro HTTP livre.
Ainda falta comprovar geração completa e restauração da mídia em outro runner.

O [run38664030524](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38664030524)
passou1.157 testes reais de CI. A pausa de61s foi respeitada, mas o bloco PT
recebeu429/429/200; as recusas não declararam subtipo ou Retry-After. O histórico
identificou a falha da resposta200: `nonliteral_evidence`, `missing: 1`.
O schema anterior permitia ID vazio mesmo em achado factual; o gate bloqueou
corretamente a resposta. Snapshotseq87 sem mídia nova; adaptação preservada.

O schema com IDs agora usa duas variantes fechadas de categorias disjuntas:
grammar/style/language admitem referência vazia, as demais exigem ID válido não
vazio. Corresponde ao critério local existente, sem retirar achados críticos.
A composição `anyOf` é suportada pela [documentação Groq](https://console.groq.com/docs/structured-outputs).
Rollback continua em `semantic_citation_ids: false`. O diagnóstico dessa união
guarda apenas paths conhecidos e regras, sem valores da resposta. A mudança
ainda precisa de prova real de aceitação do schema e conclusão dos gates.
