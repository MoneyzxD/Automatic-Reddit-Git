# Gemini gratuito — validação antes da substituição

O operador autorizou integrar o Gemini em todas as etapas de IA e substituir
o Groq somente depois de demonstrar funcionamento. O Secret GEMINI_API_KEY foi
confirmado apenas pelo nome em 13/10/2026; seu valor não foi lido.

## Implementação e reversão

PIPELINE_LLM_PROVIDER seleciona groq ou gemini uma vez por execução. O default
continua groq enquanto o aceite real estiver pendente. A camada utils/llm_client.py
encaminha os clientes de adaptação, perfil, correção de gênero, naturalização,
título/hook/encerramento, metadados e validação. Métodos privados com nomes
históricos groq são preservados para manter compatibilidade e testes existentes.
A tradução continua usando seus provedores gratuitos existentes.

Gemini usa REST nativo com requests já instalado. GEMINI_MODEL começa em
gemini-2.5-flash, que tem modalidade gratuita documentada. Modelos fixos permitidos
também incluem gemini-2.5-flash-lite e gemini-3.8-flash. Não há alternância por
rate limit, contratação, ativação de faturamento, grounding ou ferramenta paga.
O projeto Google deve continuar sem faturamento: o endpoint não informa o plano
de cobrança da chave e uma chave de projeto pago pode cobrar pelo mesmo modelo.

Prompts e gates locais permanecem; o schema completo de fatos/patches é enviado
em responseJsonSchema. Só uma resposta STOP com texto final pode ser consumida.
Resposta bloqueada, truncada, vazia ou inválida não aprova conteúdo. O perfil,
evidências literais, rechecagem LanguageTool e quarentena continuam obrigatórios.
O guardião controla as três tentativas; o cliente não adiciona retries nesse
caminho. Geração tem no máximo duas tentativas em 429, com teto de espera 30s.
Cadência padrão 13s entre chamadas/etapas/idiomas no mesmo processo não garante
crédito diário nem coordena outros consumidores do projeto Google.

Erros armazenam só código/status/espera numérica. RetryInfo é lido sem preservar
mensagens livres. Chaves ficam no cabeçalho HTTPS, sem query string/redirect.
Consumo registra o modelo efetivamente usado, inclusive respostas incompletas.

## Aceite operacional

1. Suíte local e testes de encaminhamento, schema, truncamento, erros e credenciais.
2. Branch gemini-provider no Actions: llm_provider=gemini, idiomas=pt en es,
   historia_teste=true e apenas_gerar=true; namespace validation-* novo.
3. Conferir roteiro/perfil nos três idiomas, MP4/voz/legendas/cards e checkpoint.
   Um workflow verde com conteúdo rejeitado ou sem mídia não basta.
4. Restaurar/verificar a mídia em outro runner antes de liberar produção.
5. Após aceite, integrar código e selecionar Gemini no fluxo normal. Preservar
   estado production, IDs confirmados, filas, tokens OAuth e meta diária.

Reversão usa PIPELINE_LLM_PROVIDER=groq; não apaga snapshots, fontes ou perfil.
Uma aprovação antiga reutilizável não conta como revisão nova pelo Gemini.
Nenhum teste sintético deve ser publicado. Falha de cota ou gate mantém o
aceite pendente; não reduzir validações nem ativar cobrança para fazê-lo passar.

## Fontes oficiais

- [REST e configuração](https://ai.google.dev/api/generate-content)
- [Saídas estruturadas](https://ai.google.dev/gemini-api/docs/structured-output)
- [Modalidade gratuita e uso dos dados](https://ai.google.dev/gemini-api/docs/pricing)
- [Cotas efetivas por projeto](https://ai.google.dev/gemini-api/docs/rate-limits)

Na modalidade gratuita, conteúdo pode ser usado para melhorar produtos Google.
Limites efetivos dependem da conta/projeto e são conferidos no AI Studio.

## Evidência local em 13/10/2026

Baseline: 1.116 testes. Cliente ainda ausente: 20 testes novos falharam antes
da implementação. Suíte após integração: 1.146 passes/63,13s; checks adicionais
de cadência/workflow e interfaces: 119 passes/10,60s. compileall e diff check
passaram. Esses testes usam transporte falso, não o Secret do Actions.

Revisão independente sem Critical/Important aprovou somente validação isolada.
O único achado menor era o alerta genérico recomendar diagnóstico Groq mesmo
com Gemini; o texto foi corrigido para o provedor configurado. Qualidade real,
cotas/faturamento da conta, inspeção de mídia/restore e liberação de produção
continuam pendentes. Checkpoints antigos não são prova do novo provedor.

## Execução real iniciada

Commit d614352 na branch gemini-provider. Run
[38479275207](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/38479275207)
iniciado com llm_provider=gemini, PT/EN/ES, história sintética, apenas geração e
namespace validation-gemini-20261013. Main/production não foram alterados.
Terminou failure na adaptação EN: HTTP404 no modelo configurado, uma tentativa
do guardião, zero mídia; upload foi pulado. Isso não comprova erro de cota nem
autoriza substituir produção. Consulta autenticada de catálogo foi adicionada
para confirmar modelos disponíveis antes de outra geração; somente nomes públicos
de modelos aptos a generateContent são exibidos, sem corpos de erro/credenciais.
Revisão do delta reproduziu uma combinação publish+catalog-only que pulava a
verificação tardia; o resolver inicial agora rejeita essa combinação e qualquer
consulta fora de normal/apenas-gerar/validation. Regressão RED/GREEN antes do
disparo de catálogo, sem qualquer upload executado.
