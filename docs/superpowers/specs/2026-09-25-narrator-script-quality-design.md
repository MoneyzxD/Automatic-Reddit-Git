# Perfil do narrador e guardião de roteiro

## Objetivo

Impedir que adaptação, tradução, naturalização ou divisão do roteiro alterem a
identidade do narrador ou produzam texto incompatível com a voz escolhida. O
pipeline deve usar o contexto completo da história, tomar uma única decisão de
narração e manter essa decisão em português, inglês, espanhol e em todas as
partes do vídeo.

O mesmo subsistema também deve detectar erros linguísticos e semânticos como
traduzir "Pokémon card" para "cartão Pokémon" quando o sentido correto é
"carta Pokémon". Toda dependência usada em produção precisa funcionar tanto no
GitHub Actions quanto na Oracle Cloud e continuar dentro da stack gratuita.

## Critérios de sucesso

- Uma história recebe exatamente um perfil de narrador antes da adaptação.
- `narration_gender` é sempre `male` ou `female`; nunca chega como `unknown` ao
  naturalizador, metadados ou TTS.
- PT, EN, ES e todas as partes compartilham o mesmo `profile_id` e a mesma voz
  gramatical.
- Relacionamento, cabelo, nome, profissão, hobby e personalidade não contam
  como prova do gênero do narrador.
- Evidências explícitas no fim de histórias longas não são descartadas por
  truncamentos de 3.000 ou 5.000 caracteres.
- Formas em primeira pessoa concordam com a voz escolhida. Por exemplo, uma
  voz feminina não pode narrar "agora sou faxineiro".
- Correções são cirúrgicas, verificáveis e não alteram o gênero de outros
  personagens.
- O LanguageTool usado pelo pipeline é uma instância própria, reproduzível e
  sem depender da API pública.
- Um erro crítico não corrigido impede o TTS e a publicação daquela história.

## Escopo desta entrega

Esta entrega cobre o perfil do narrador, a consistência linguística do roteiro,
o glossário contextual, a integração do LanguageTool e os gates antes do TTS.
O auditor multimodal que assiste ao vídeo final, a integração com YouTube
Analytics, o repositório privado de inteligência e a promoção automática de
regras aprendidas ficam para entregas separadas. O log estruturado desta
entrega já deixará uma interface estável para esses consumidores futuros.

## Abordagens avaliadas

### Escolhida: livro de evidências + decisão determinística + revisão semântica

Regras locais encontram sinais explícitos; o Groq resolve atribuição de sujeito
e correferência quando necessário; um redutor determinístico toma a decisão
final. A saída é persistida e travada. Esse desenho combina auditabilidade,
resistência a estereótipos e comportamento previsível durante indisponibilidade
parcial.

### Rejeitada: somente regras e expressões regulares

É barata, mas não distingue de forma confiável o narrador dos outros
personagens e não entende citações, pronomes ou relações complexas.

### Rejeitada: pedir ao LLM uma resposta livre em cada idioma

É o comportamento atual em essência. Produz decisões divergentes por tradução,
aceita evidência inventada, sofre com truncamento e torna impossível explicar
por que uma voz foi escolhida.

## Arquitetura

O desenho introduz dois módulos profundos e preserva as etapas existentes como
adaptadores:

1. `NarratorProfileResolver`: recebe a história original completa e devolve um
   `NarratorProfile` imutável.
2. `ScriptGuardian`: recebe fonte, versão candidata, idioma, etapa e perfil;
   devolve texto corrigido e um relatório estruturado ou lança um erro de
   qualidade crítico.

O `main.py` conhece apenas essas duas interfaces. Detecção por regras, chamadas
ao Groq, validação de JSON, LanguageTool, glossário, aplicação de patches e
telemetria permanecem escondidos dentro dos módulos.

```text
Reddit original completo
        |
        v
NarratorProfileResolver ----> NarratorProfile travado
        |                              |
        v                              v
adaptação -> tradução -> naturalização -> hook -> divisão
    |           |             |          |        |
    +-----------+-------------+----------+--------+
                              |
                              v
                  ScriptGuardian por checkpoint
                              |
                              v
                 gate final de cada parte -> TTS
```

## Perfil do narrador

### Interface

```python
class NarratorProfileResolver:
    def resolve(
        self,
        *,
        story_id: str,
        title: str,
        original_text: str,
    ) -> NarratorProfile: ...
```

`NarratorProfile` contém:

- `profile_id`: identificador determinístico do perfil;
- `story_id`;
- `source_gender`: `male`, `female` ou `unknown`, representando a identidade
  mais provável encontrada na fonte;
- `narration_gender`: sempre `male` ou `female`, usado por todo o pipeline;
- `confidence`: número entre 0 e 1;
- `decision_method`: `explicit`, `semantic`, `weighted` ou `stable_tiebreak`;
- `evidence`: lista de evidências aceitas;
- `resolver_version`: versão da política que tomou a decisão.

Cada evidência registra tipo, trecho literal, posição na fonte, gênero sugerido,
peso, sujeito atribuído e origem (`rules` ou `groq`). Uma evidência do Groq só é
aceita se seu trecho existir literalmente no texto recebido. Evidências sem
trecho verificável, sobre outro personagem ou baseadas em estereótipos são
descartadas.

### Política de decisão

1. Processar título e texto original completos, sem corte por caracteres.
2. Priorizar autodescrições inequívocas do narrador, como `(28M)`, `(28F)`,
   "I am a 28-year-old man" ou "I am a 28-year-old woman".
3. Dividir textos longos em blocos apenas para respeitar o limite do modelo;
   todos os blocos entram no livro de evidências antes da redução.
4. Usar o Groq com JSON estrito somente para atribuição de sujeito e
   correferência. O modelo não toma a decisão final.
5. Reduzir evidências válidas por precedência e peso determinísticos.
6. Em baixa confiança, escolher o gênero com maior pontuação e registrar a
   baixa confiança; o pipeline não redetecta nem troca essa escolha depois.
7. Em empate absoluto ou ausência de evidência, usar um hash estável de
   `story_id` para escolher `male` ou `female`. Isso distribui vozes sem
   aleatoriedade e reproduz a mesma escolha em todos os idiomas e reruns.

Parceiro ou parceira, orientação sexual, cabelo comprido, profissão, nome,
roupa, hobby, personalidade e emoção têm peso zero. Portanto, "my husband" não
transforma um narrador homem em mulher e "my wife" não transforma uma
narradora mulher em homem.

O perfil é salvo em
`data/scripts/profiles/{story_id}_narrator_profile.json` para auditoria e seu
`profile_id` é copiado para metadados e eventos de qualidade. Esse arquivo não
contém segredo.

## Guardião de roteiro

### Interface

```python
class ScriptGuardian:
    def review_and_fix(
        self,
        *,
        source_text: str,
        candidate_text: str,
        language: str,
        stage: str,
        story_id: str,
        profile: NarratorProfile,
        final_gate: bool = False,
    ) -> ScriptReview: ...
```

`ScriptReview` contém o texto aprovado, alterações aplicadas, achados restantes,
estado das dependências e uma decisão `approved`, `rejected` ou `unavailable`.
`rejected` representa conteúdo analisado e reprovado; `unavailable` representa
uma análise obrigatória que não pôde ser concluída. Ambos bloqueiam o gate
final por meio de `QualityGateError`.

### Ordem da revisão

1. Validar idioma, perfil e integridade básica do texto.
2. Aplicar regras do glossário contextual.
3. Consultar o LanguageTool e coletar problemas gramaticais e ortográficos.
4. Pedir ao Groq uma revisão semântica de fidelidade, atribuição de personagem,
   gênero em primeira pessoa, valores, parentesco e continuidade.
5. Aceitar somente patches estruturados cujo trecho original seja encontrado
   exatamente no candidato e cuja justificativa tenha suporte na fonte ou no
   perfil.
6. Aplicar os patches do fim para o começo para preservar posições.
7. Rodar novamente as verificações determinísticas e o LanguageTool.
8. No gate final, bloquear se ainda existir um problema crítico.

O Groq não devolve uma reescrita integral. O contrato é JSON estrito com
`original`, `replacement`, `category`, `severity`, `subject`, `reason` e
`source_quote`. Patches de gênero só são aceitos quando `subject=narrator`.
Trecho inexistente, ocorrência ambígua sem posição ou citação inventada torna o
patch inválido. Outros personagens nunca são corrigidos com base no perfil do
narrador.

### Concordância de primeira pessoa

O guardião verifica o texto completo após tradução, após naturalização, após a
injeção do hook, após a divisão e imediatamente antes do TTS. O último gate
recebe cada parte exatamente como será narrada.

Quando uma forma flexionada contradiz `narration_gender`, a ordem de preferência
é:

1. corrigir a flexão sem mudar o sentido;
2. usar uma formulação neutra natural quando a flexão for duvidosa;
3. bloquear a parte se a inconsistência crítica continuar.

Assim, uma narradora pode dizer "agora sou faxineira" ou "agora trabalho com
limpeza", mas nunca "agora sou faxineiro". A escolha de voz não muda para
acomodar um erro criado pela tradução.

## Glossário contextual

`config/contextual_glossary.yaml` contém regras pequenas, revisáveis e com teste
de regressão. Cada regra declara idioma, contexto obrigatório, forma incorreta e
substituição. A regra inicial cobre o domínio de cartas colecionáveis:

- `Pokémon card` / `trading card` -> `carta Pokémon` / `carta colecionável` em
  português;
- equivalentes corretos em espanhol;
- `cartão` continua permitido em contextos financeiros, de identificação,
  acesso ou pagamento.

O glossário não cresce automaticamente a partir da saída de um LLM. Achados são
registrados como propostas; uma regra só entra no arquivo versionado com teste e
revisão humana. Isso evita que um erro isolado contamine histórias futuras.

## LanguageTool

Será usada a distribuição standalone oficial `LanguageTool 6.6`, executada com
Java Temurin 17 e acessada em `http://127.0.0.1:8081/v2`. Não será usada a API
pública, imagem Docker comunitária nem wrapper Python que faça downloads
ocultos.

Artefato oficial:

- URL: `https://languagetool.org/download/LanguageTool-6.6.zip`
- SHA-256:
  `53600506b399bb5ffe1e4c8dec794fd378212f14aaf38ccef9b6f89314d11631`

No GitHub Actions, o workflow configura Java 17, restaura um cache versionado,
baixa o ZIP quando ausente, sempre confere o SHA-256, inicia o servidor local,
aguarda `/v2/languages`, confirma PT-BR, en-US e es e aquece `/v2/check` para
os três idiomas. Falha de download, hash, inicialização, versão ou locale encerra
o job antes da geração.

Na Oracle Cloud, um instalador idempotente usa o mesmo ZIP e hash e instala uma
unidade `systemd` limitada a localhost, com usuário sem privilégios e
`Restart=on-failure`. O health check usado pelo pipeline é o mesmo nos dois
ambientes.

O cliente Python usa HTTP diretamente e recebe a URL por
`LANGUAGETOOL_URL`. Em `PIPELINE_ENV=runner` ou `oracle`, a ausência do servidor
é erro crítico. Testes unitários usam um adaptador falso; não existe fallback
silencioso para a API pública.

## Integração no fluxo

O fluxo passa a ser:

1. extrair e filtrar a história;
2. expandir marcadores explícitos no original;
3. resolver e persistir o perfil do narrador uma única vez;
4. adaptar o texto com o perfil disponível;
5. revisar adaptação comparando com a fonte completa;
6. traduzir;
7. revisar cada tradução comparando com a fonte e usando o mesmo perfil;
8. naturalizar usando `narration_gender` travado;
9. revisar a versão naturalizada;
10. gerar e revisar título e hooks;
11. injetar hook, revisar e dividir;
12. executar o gate final em cada parte;
13. somente então gerar voz, legendas, vídeo e metadados.

O estágio atual de detecção dentro do loop de idiomas é removido. Chamadores que
ainda usam `GenderDetector` passam por uma interface de compatibilidade que
devolve o perfil travado; não podem iniciar uma nova detecção sobre a tradução.
O valor padrão `female` em `VoiceGenerator` é removido. A geração de voz exige
explicitamente `male` ou `female` e rejeita qualquer outro valor. A voz de
fallback também precisa ter o mesmo gênero da voz principal; uma falha do
provedor nunca autoriza trocar uma voz masculina por feminina ou vice-versa.

Adaptação e tradução também deixam de tratar conteúdo parcial como sucesso. O
adaptador processa todos os blocos da história e comprova cobertura da fonte. O
tradutor devolve um resultado tipado com idioma, provedor, blocos traduzidos e
erros; quando destino e fonte diferem, bloco vazio, trecho original reinserido
ou idioma-alvo não confirmado reprova a tradução. Título, hook e metadados
recebem o contexto factual global do guardião em vez de prefixos arbitrários de
300, 400 ou 500 caracteres.

## Erros e política de publicação

- Fonte sem evidência: escolher pelo hash estável, marcar baixa confiança e
  continuar.
- Groq indisponível durante resolução: decidir com evidências determinísticas ou
  hash estável e emitir alerta.
- Groq indisponível no gate semântico final: bloquear a história, pois não há
  como garantir atribuição de sujeito e fidelidade.
- LanguageTool indisponível em produção: falhar antes da geração ou bloquear no
  health check; nunca chamar a API pública como fallback.
- Resposta JSON inválida ou citação inventada: rejeitar a resposta, tentar
  novamente dentro do limite existente e bloquear se o gate final não puder ser
  concluído.
- Patch que altera outro personagem: rejeitar e manter o texto anterior.
- Problema crítico não corrigido: não iniciar TTS, registrar relatório e avisar
  o Telegram.

Validadores deixam de interpretar "sem resposta" como `approved=true`. Uma
indisponibilidade deve aparecer como estado próprio e nunca ganhar nota zero com
aprovação silenciosa. `approved=true` acompanhado de achado bloqueante é
normalizado para `rejected`; esgotar tentativas não publica simplesmente a
versão com maior nota.

## Observabilidade e dados

Cada checkpoint acrescenta uma linha JSON ao log de qualidade com:

- `story_id`, `profile_id`, idioma, etapa e parte;
- gênero escolhido, confiança e método;
- versões do resolver, glossário e LanguageTool;
- contagem de achados por categoria e severidade;
- patches aceitos e rejeitados, sem registrar segredos;
- dependência usada, latência, tentativas e decisão final.

O log é append-only e adequado para ingestão futura pelo repositório privado de
inteligência. Ele não promove regras nem modifica configuração sozinho.

## Configuração

`config/settings.yaml` recebe uma seção `script_quality` com `enabled`,
`fail_closed`, `languagetool_enabled`, `languagetool_required`,
`languagetool_url`, `languagetool_timeout_seconds` e o mapa de locales
`pt: pt-BR`, `en: en-US`, `es: es`. O modo inicial é bloqueante para perfil
inválido, dependência obrigatória ausente, tradução parcial e inconsistência
crítica no gate final. Achados puramente estilísticos são aviso.

Variáveis de ambiente:

- `LANGUAGETOOL_URL`, padrão `http://127.0.0.1:8081`;
- `LANGUAGETOOL_REQUIRED=true` em GitHub Actions e Oracle;
- as chaves Groq existentes continuam separadas por carga de idioma.

Gemini não é dependência desta entrega. Uma futura avaliação em shadow mode
poderá implementar o mesmo contrato JSON sem mudar a interface do guardião.
Chaves de provedor são tratadas como strings opacas, sem validação por prefixo.

## Estratégia de testes

### Perfil do narrador

- `I (28M) ... my husband` resulta em narrador masculino;
- `I (28F) ... my wife` resulta em narradora feminina;
- homem de cabelo comprido continua masculino;
- muitas personagens femininas não vencem um marcador `(30M)` do narrador;
- evidência depois dos caracteres 3.000 e 5.000 é encontrada;
- fala citada "I'm a woman" de outra personagem é ignorada;
- citação inventada pelo Groq é rejeitada;
- sem Groq e com marcador explícito, a decisão continua correta;
- empate sem evidência é estável entre reruns;
- PT, EN, ES e todas as partes compartilham `profile_id`.

### Guardião

- `cartão Pokémon` vira `carta Pokémon`, mas `cartão de crédito` não muda;
- narradora + `agora sou faxineiro` resulta em `faxineira` ou frase neutra;
- narrador + `agora sou faxineiro` permanece correto;
- correção do narrador não altera o gênero de outro personagem;
- patch com trecho inexistente, ambíguo ou citação falsa é rejeitado;
- valores, parentesco e fatos divergentes são marcados como críticos;
- falha do Groq ou do LanguageTool não é interpretada como aprovação;
- uma inconsistência crítica restante bloqueia o TTS.

### Tradução e cobertura

- falha em um único bloco não devolve nem armazena uma tradução parcial;
- destino diferente da fonte não aceita silenciosamente o texto inglês;
- a adaptação cobre também evidências e fatos depois dos caracteres 5.000;
- título, hook e metadados consideram fatos importantes fora dos prefixos
  usados pela implementação antiga.

### Integração

- uma história completa atravessa PT, EN e ES com um único perfil;
- o gate final recebe cada parte com hook e encerramento já inseridos;
- `VoiceGenerator` rejeita `unknown` e não escolhe voz feminina por padrão;
- o fallback do TTS preserva o gênero do perfil;
- tradução parcial ou no idioma errado bloqueia naturalização e TTS;
- o workflow valida hash, versão, locales e readiness do LanguageTool;
- o instalador Oracle é idempotente e o serviço responde apenas em localhost.

Os testes de unidade não fazem chamadas externas. Um teste de integração opt-in
usa o servidor LanguageTool real; o workflow de produção executa o health check
real antes dos testes e da geração.

## Compatibilidade e implantação

A implantação usa três passos no mesmo conjunto de mudanças:

1. adicionar módulos, contratos, configuração e testes sem remover as interfaces
   antigas;
2. migrar `main.py` para o perfil único e inserir os checkpoints do guardião;
3. endurecer o gate pré-TTS e remover defaults/redetecções perigosos.

Não há migração destrutiva de banco. Perfis e relatórios são novos artefatos. Em
rollback, o commit pode ser revertido sem alterar filas, tokens OAuth ou dedupe.

## Critérios de aceite

A entrega está pronta quando:

1. todo o corpus de regressão acima passa;
2. a suíte existente continua verde;
3. um teste ponta a ponta com história masculina casada com outro homem mantém
   voz masculina e flexões masculinas nos três idiomas;
4. um teste com gênero ausente escolhe a mesma voz em reruns;
5. um teste de tradução corrige "cartão Pokémon" sem tocar em "cartão de
   crédito";
6. o workflow do GitHub Actions sobe e valida LanguageTool 6.6 antes da geração;
7. os segredos não aparecem em arquivos, relatórios ou logs;
8. nenhuma parte chega ao TTS com gênero `unknown` ou inconsistência crítica.
