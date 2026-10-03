# Confiabilidade do pipeline antes dos agentes

Data: 2026-10-03. Status: **desenho para revisão; código não implementado**.
O operador aprovou avançar nas correções e, depois, nos observadores de
manutenção/crescimento. A escolha de armazenamento privado abaixo precisa
de aprovação antes de criar recursos ou configurar Secrets.

## Objetivo e limite da entrega

Recuperar falhas temporárias sem perder histórias, estado ou identidade do
narrador; evitar duplicação de uploads; diagnosticar indisponibilidade sem
publicar conteúdo não aprovado. Produção continua no GitHub Actions, com
stack gratuita, geração/publicação no mesmo job e renovação manual de OAuth.

Esta primeira entrega cobre revisão semântica, retomada e persistência.
Os agentes são entregas posteriores: manutenção observa execução/qualidade;
crescimento coleta audiência e propõe experimentos. Compartilham identidade
e histórico, não um framework multiagente. A proposta editorial permanece em
[YOUTUBE_GROWTH_AGENT](../../YOUTUBE_GROWTH_AGENT.md).

## Evidência e incerteza

**FATO DO CÓDIGO / EXECUÇÃO**:

- O [run 37128480329](https://github.com/MoneyzxD/Automatic-Reddit-Git/actions/runs/37128480329),
  em `30a0a0c`, passou nos 533 testes e no aquecimento real do LanguageTool,
  mas falhou na adaptação EN de `1wfduc8`. Publicação foi pulada.
- `script_quality.jsonl` registra `status=unavailable`, cinco chamadas
  semânticas e a mensagem genérica de três tentativas esgotadas. A causa
  específica da API/resposta não foi preservada.
- Em reprodução sintética, um erro HTTP 429 e JSON inválido resultam na
  mesma mensagem. Isso comprova uma lacuna de diagnóstico, **não** que o
  run real falhou por cota. Os retries do SDK tornam cota uma hipótese.
- `main.py` insere a história antes da adaptação. `StoryFilter` consulta
  somente existência no banco. Em banco temporário, uma história inserida
  sem partes exportadas já é considerada duplicada.
- O workflow salva DB e filas somente em cache. O comentário sobre um
  commit de estado não corresponde a um passo existente. A mídia pendente
  precisa ser recuperada junto da fila, não apenas seus caminhos antigos.
- O repositório `MoneyzxD/Automatic-Reddit-Git` é público, confirmado via CLI.
- Baseline local desta investigação: **89 testes passando** em guardião,
  lote diário e fila TikTok. Não houve chamada real Groq, render ou upload.

Não atribuir a falha ao YouTube, OAuth ou LanguageTool. Primeiro obter uma
classificação segura do erro semântico; só então corrigir seu mecanismo real.

## Alternativas e recomendação

1. **Snapshot privado no GitHub — recomendado.** Mantém o ambiente atual,
   reutiliza Python/SQLite/HTTP já disponíveis e permite restaurar o runner.
   Exige repositório privado, permissão específica e teste real de restauração.
2. **Cache + artifacts do repositório atual.** Menor mudança, mas retenção e
   descarte continuam impedindo usá-los como autoridade durável.
3. **Migrar primeiro para Oracle.** Disco persistente ajuda, mas o host ainda
   não tem implantação real verificada; amplia esta entrega desnecessariamente.

O [GitHub documenta descarte do cache](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching#usage-limits-and-eviction-policy).
Assets de [releases](https://docs.github.com/en/rest/releases/assets#upload-a-release-asset)
oferecem uma API para o snapshot; acesso privado e permissões devem ser
validados. Não presumir armazenamento ilimitado nem disponibilidade garantida;
os próprios assets também precisam de cópias verificadas de recuperação.

## 1. Revisão semântica: diagnóstico e retries controlados

Preservar `approved/rejected/unavailable`, citações literais, patches
verificáveis, perfil imutável e todos os gates. Revisão indisponível continua
interrompendo o lote; nenhum fallback local aprova conteúdo.

Registrar apenas campos seguros: dependência, modo (`facts/chunk/global`),
idioma, etapa, classe de falha, HTTP status quando disponível, tentativas e
tamanho do contexto. Classes distinguem autenticação/permissão, cota,
timeout/conexão, erro do provedor, contexto excedido, JSON/schema inválido e
evidência não literal. Corpo da resposta, headers sensíveis e `str(exc)`
não entram em logs/quarentena.

O guardião terá um único dono do orçamento de tentativas, evitando multiplicar
retries do SDK, wrapper e checkpoint. Limites ficam em configuração validada;
timeouts e espera respeitam esse orçamento e `Retry-After` seguro. Erros
permanentes não são tratados como cota transitória. Chave fixa por idioma,
sem rotação de contas. Comportamento das etapas geradoras legadas é preservado.

A primeira validação real pode ainda terminar `unavailable`: deve então
mostrar a classe específica e permitir corrigir a causa observada. Alterar
modelo, orçamento/contexto ou formato de resposta exige essa evidência;
nunca aumentar retries indefinidamente ou relaxar schema para obter sucesso.

## 2. Retomada por história e idioma

Existência da fonte no banco não significa conclusão. Acrescentar estado
explícito por `(story_id, language)`, mantendo a tabela de partes e os IDs
atuais. Migração aditiva, sem apagar dedupe ou filas.

| Estado lógico | Tratamento na retomada |
|---|---|
| Processando | Após interrupção, investigar/reconciliar antes de repetir efeitos externos |
| Indisponível temporariamente | Repetir processamento somente dos idiomas incompletos |
| Conteúdo reprovado | Manter quarentena; não reabrir automaticamente como falha de infraestrutura |
| Exportado e enfileirado | Recuperar mídia/fila; não gerar outra cópia |
| Upload confirmado | Preservar `video_id`; nunca reenviar para corrigir capa |
| Upload de resultado incerto | Bloquear reenvio automático e alertar para reconciliação |
| Estado legado desconhecido | Preservar dedupe até reconciliar; não liberar todas as histórias antigas |

Conclusão da geração exige todas as partes do idioma exportadas e enfileiradas
com sucesso. Falhas de escrita/enfileiramento precisam ser visíveis ao
chamador, em vez de sucesso aparente. Ao retomar, conservar fonte, perfil e
scripts aprovados; não redetectar gênero nem mudar partes já publicadas.

Seleção/filtragem recebem os idiomas solicitados. Uma execução PT concluída
não impede terminar EN/ES; uma execução parcial não duplica PT. O lote conta
somente itens válidos/restaurados e agendamentos existentes, mantendo meta
inicial três, teto três partes por história e excedente máximo uma para amanhã.

Para dados anteriores, reconciliar DB/fila e evidências de quarentena. O
incidente `1wfduc8` pode ser marcado retomável após confirmar ausência de
upload. Registros antigos ambíguos não são considerados inéditos por padrão.

## 3. Estado durável e recuperação

Código fica público; snapshots ficam em repositório **privado**, sugerido
`MoneyzxD/Automatic-Reddit-State`. Uma CLI pequena de salvar/restaurar/verificar
e funções compartilhadas são suficientes. Não criar serviço permanente.

Snapshot com manifesto versionado, commit/run, sequência, hashes e caminhos
relativos: backup consistente do SQLite, filas, perfis/fontes/scripts necessários
à retomada e referências à mídia ainda pendente. MP4/JPG/metadados pendentes
também devem ser recuperáveis; não declarar prontidão restaurando somente JSON.
Credentials, tokens, cookie, `.env` e logs brutos ficam fora por lista permitida.

Publicar payloads únicos primeiro e o manifesto de conclusão por último.
Restauração aceita somente conjuntos completos, com hashes, integridade SQLite,
schema e associação fila/mídia verificados. Proteger extração contra caminhos
absolutos, travessia e links. Remapear caminhos para a raiz do runner atual.
Conferir a identidade e visibilidade privada do repositório antes de gravar;
um destino público ou diferente do aprovado bloqueia a operação.

Um gravador serializado; checkpoint antes de efeitos de upload e após receber
`video_id`. Salvar também em saída de erro quando o estado restaurado é válido.
Interrupção entre YouTube aceitar o vídeo e gravar sua confirmação permanece
incerta: reconciliar, não prometer exactly-once nem reenviar automaticamente.

Manter três snapshots completos de recuperação; mídia pendente é retida enquanto
referenciada. Limites de tamanho são checados antes da gravação, com alerta ao
atingir capacidade. Limpeza só remove assets não referenciados após validar uma
cópia recuperável; ativar limpeza externa exige aprovação específica.

Cache vira aceleração, não autoridade. Falta/corrupção de snapshot ou acesso
privado impede iniciar estado vazio ou continuar uploads automaticamente.
Uma cópia anterior serve à recuperação assistida: antes de voltar a publicar,
reconciliar uploads posteriores a ela, evitando dedupe desatualizado.
Bootstrap é explícito: importar/reconciliar o estado existente, conferir IDs já
enviados e fazer primeiro snapshot. A atualização não apaga caches existentes.
Modo sem geração/publicação usa namespace de teste e não altera o head de produção.

Criar o repositório e conceder permissão de conteúdo somente a ele são passos
externos sujeitos à aprovação. O `GITHUB_TOKEN` do repositório público não deve
ser presumido autorizado no privado. Nenhuma credencial será exibida no terminal.

## Verificação e liberação

Antes de liberar produção, provar:

1. JSON inválido, 429, timeout e erro de autenticação produzem classes distintas
   sem vazamento, sem mudar uma indisponibilidade para aprovação.
2. Retries são limitados e mensuráveis, sem chamadas aninhadas não contabilizadas.
3. Falha antes da mídia torna a história retomável; reprovação mantém quarentena.
4. PT concluído + EN indisponível retoma somente EN, com o mesmo perfil.
5. Falha de fila não marca geração concluída; ausência de mídia não aumenta meta.
6. Snapshot íntegro restaura DB/fila/mídia em outra raiz; corrupto/ausente bloqueia
   sem sobrescrever a cópia anterior. A segunda retomada não duplica itens.
7. Upload confirmado nunca é repetido; resultado incerto requer reconciliação.
8. Bootstrap preserva uploads legados; nenhum token/cookie entra no snapshot.
9. Testes existentes e regressões passam; verificar diff, schema e permissões.
10. GitHub Actions real gera PT/EN/ES sem publicar, exercita restauração privada
    e preserva evidências. Após isso, publicar dentro da meta normal aprovada,
    sem uploads de teste extras, e confirmar IDs/agendamentos recuperáveis.

Restaurar código anterior não autoriza apagar o novo estado. A migração deve
manter estruturas legadas legíveis; se o código antigo não entende uma situação
nova, recuperação fica bloqueada até reconciliação, em vez de gerar duplicatas.

## Handoff para os observadores

Depois dessa aceitação, especificar manutenção em modo observador: relatório
por execução, classe de incidente, cumprimento da meta, situação de uploads e
alerta deduplicado. Não consome LLM para checks determinísticos nem edita código,
glossário, Secrets, frequência ou conteúdo automaticamente.

Crescimento vem depois, com dados reais por canal, OAuth de leitura separado ou
exports Studio, histórico privado e experimentos aprovados. Falha de Analytics
não impede publicação. Os contratos/dados desse MVP ainda precisam de sua
própria revisão; esta spec não implementa os dois agentes.
