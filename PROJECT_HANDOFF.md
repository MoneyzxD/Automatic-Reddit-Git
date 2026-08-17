# PROJECT_HANDOFF.md

> **Escopo deste documento:** este arquivo **não** documenta estrutura de código, comandos de execução, dependências ou arquitetura técnica — isso já está coberto pelo `CLAUDE.md` gerado via `/init` a partir de leitura real do repositório, e é mais confiável que qualquer coisa que eu poderia reconstruir de memória de conversa.
>
> O que este documento faz é diferente e complementar: registra **a jornada do projeto** — por que decisões foram tomadas, o que já foi tentado e descartado, onde exatamente o desenvolvimento parou, e para onde ele deveria ir a seguir. É contexto que não está escrito no código e que o `/init` não conseguiria inferir sozinho.
>
> **Proveniência:** gerado a partir de memória consolidada de conversas anteriores, não de inspeção de código. Onde há incerteza, está marcado como `[VALIDAR]`. Em qualquer conflito entre este documento e o `CLAUDE.md`/código real, **o código real vence** — mas se o código contradizer uma decisão registrada aqui como deliberada (seção 4), isso é sinal de regressão, não de que a decisão mudou.

---

## 1. O que é o projeto, em uma frase

`reddit_pipeline` (canal MoneyzxD): sistema automatizado que transforma histórias do Reddit em vídeos curtos narrados, publicados em PT-BR, EN e ES, rodando localmente em dev (Windows) e em produção desatendida na Oracle Cloud, com o objetivo de gerar renda extra escalável sem operação manual diária — exceto a postagem no TikTok, que é deliberadamente manual (ver seção 4).

Para estrutura de diretórios, stack técnica, comandos e arquitetura de código: **ver `CLAUDE.md`**.

---

## 2. Como o projeto chegou até aqui

A memória disponível não cobre a origem do projeto nem as primeiras fases de desenvolvimento `[VALIDAR]` — o que se sabe com confiança é a fase mais recente e ativa, centrada no módulo de validação (`stages/validator.py`).

Marcos identificáveis, em ordem de relevância para entender o presente:

1. **Incidente de normalização de idioma.** Em algum ponto do desenvolvimento, a chave de idioma `pt-br` foi normalizada para `pt` de forma espalhada por múltiplos módulos, em vez de centralizada em um único ponto de entrada. Isso causou falhas em cascata e consumiu tempo desproporcional para depurar. Esse incidente virou a origem de duas regras permanentes do projeto (ver seção 4): normalizar só no ponto de entrada, e mapear dependências antes de mudanças que tocam múltiplos arquivos.
2. **Migração de regras hardcoded para julgamento semântico via LLM.** Detecção de gênero, avaliação de qualidade de título/hook e validação geral passaram de abordagens baseadas em regex/listas fixas para prompting com exemplos de calibração. Isso não foi um refinamento incremental — foi uma mudança de filosofia registrada como aprendizado central do projeto.
3. **Construção da validação em duas camadas.** O estágio de validação evoluiu para separar correções triviais (match exato de trecho, resolvido via `str.replace()`, custo zero de token) de correções ambíguas (delegadas ao LLM). Essa separação é uma resposta direta à necessidade de controlar custo/TPM em um pipeline que roda em lote.
4. **Correção do bug de tracking de melhor versão.** Os três loops de validate-and-fix retornavam a última tentativa em vez da tentativa de maior score entre as retries. Corrigido.
5. **Identificação (mas não confirmação de correção) do bug de drift de título/hook.** Cada retry sobrescrevia `current_title`/`current_hook` incondicionalmente, mesmo quando a nova versão era pior, causando alucinação de detalhes no output final. Este é o fio solto mais recente e mais crítico.
6. **Identificação do erro 413 Payload Too Large** quebrando silenciosamente loops de correção em tentativas de fix cirúrgico. Também não confirmado como resolvido.
7. **Decisão de não fazer rotação de múltiplas chaves/contas Groq** para contornar rate limit, por violar a Acceptable Use Policy da Groq — e opção deliberada por buscar fallback multi-provedor legítimo (ex: Cerebras) em vez disso.

---

## 3. Onde estamos agora

A última área de trabalho ativa e confirmada é `stages/validator.py`. Dentro dela, dois problemas estão **identificados mas com status de correção não confirmado**:

- **Drift de título/hook** — prioridade mais alta, por impacto direto na qualidade do conteúdo final (o vídeo pode sair com detalhes que não existiam na história original).
- **Erro 413 Payload Too Large** — prioridade alta, por quebrar loops de correção de forma silenciosa (falha que não avisa, o que é pior do que uma falha visível).

O próximo item já priorizado por Henri, independente do estado desses dois bugs, é a **análise de consumo de TPM/tokens** — terceira posição na agenda de melhorias dele, com dados já sendo coletados via `resp.usage` acumulado em `_call_groq` e via `data/logs/improvement_log.jsonl`.

Este é o ponto de retomada: **confirmar no código real (via `CLAUDE.md` + leitura direta) se os dois bugs da seção acima já foram corrigidos**, e só então decidir se o próximo passo é fechar essas pontas ou avançar para a análise de TPM.

---

## 4. Decisões que não devem ser revertidas sem entender o motivo

Estas não são preferências de estilo — são decisões com uma história de custo por trás. Se o código atual contradiz alguma delas, é mais provável que seja uma regressão do que uma mudança de estratégia deliberada.

| Decisão | Por quê | O que acontece se for revertida sem análise |
|---|---|---|
| Normalização de idioma só em `main.py` | Espalhar a normalização causou falhas em cascata (incidente documentado) | Risco real de repetir o mesmo incidente |
| Validação em duas camadas (str.replace / LLM) | Controle de custo de token em pipeline batch | Perde a economia de tokens que motivou a mudança |
| Sem rotação de chaves Groq | Violação de AUP da Groq | Risco de conta suspensa, não é uma questão de preferência técnica |
| TikTok semi-automático (Telegram + postagem manual) | API direta bloqueada por aprovação pendente do TikTok Developer App | Não é uma limitação a "corrigir" sozinho — é contingência externa |
| Julgamento semântico LLM > regras hardcoded | Regras rígidas performaram pior em gênero, título/hook e validação | Reintroduzir regex/listas fixas reverte um aprendizado já validado empiricamente |
| Retries esgotam tentativas, não cortam por similaridade | Casos reais precisaram de até 6 tentativas para convergir | Cortar cedo reintroduz falhas que já foram resolvidas por paciência do loop |
| `max_tokens`/temperatura/retries dinâmicos, nunca hardcoded | Escala com o tamanho real do script | Hardcoding quebra em casos fora da média |
| Tempo de processamento por história é irrelevante como métrica | Workflow é batch overnight + publicação no dia seguinte | Otimizar velocidade em vez de TPM/confiabilidade é esforço mal direcionado |

---

## 5. Bugs em aberto (para onde ir primeiro)

| Problema | Impacto | Status | Ação imediata |
|---|---|---|---|
| Drift de título/hook | Alto — conteúdo final com detalhes alucinados | Identificado, correção `[VALIDAR]` | Confirmar no código se há guarda condicional (só atualizar `current_title`/`current_hook` se score igual ou melhor); se não houver, implementar seguindo o mesmo padrão já usado no tracking de melhor versão geral |
| 413 Payload Too Large | Alto — quebra silenciosa de loop de correção | Identificado, correção `[VALIDAR]` | Investigar tamanho do payload de correção cirúrgica; avaliar chunking/redução de contexto enviado |
| Rate limit / TPM Groq | Médio-alto — pode travar batch overnight | Mitigação planejada, não implementada | Aguardar resultado da análise de TPM (próximo item da agenda) antes de implementar fallback |

---

## 6. Para onde o projeto deveria ir a seguir

1. **Fechar os dois bugs da seção 5**, começando pelo drift de título/hook (maior impacto em qualidade percebida).
2. **Executar a análise de TPM/consumo de tokens** já priorizada por Henri, usando dados já coletados.
3. **Só depois** decidir, com dados concretos em mãos, se e como implementar fallback multi-provedor de LLM (ex: Cerebras) — não implementar isso especulativamente antes da análise.
4. **Acompanhar de forma passiva** o resultado da resubmissão do TikTok Developer App — não é algo a ser resolvido por desenvolvimento, é uma dependência externa que, quando desbloqueada, muda a decisão da seção 4 sobre publicação semi-automática.

Não há evidência de um roadmap além desses quatro pontos — qualquer item além disso na cabeça de Henri não está registrado na memória disponível e deveria ser perguntado diretamente a ele antes de ser assumido como próximo passo.

---

## 7. O que validar antes de agir

- [ ] Status real de correção do bug de drift de título/hook.
- [ ] Status real de correção/mitigação do erro 413.
- [ ] Se o `CLAUDE.md` gerado pelo `/init` já documenta esses dois pontos com mais precisão que este handoff (provável, já que foi gerado por leitura de código).
- [ ] Se há algum plano de Henri para o projeto além dos quatro pontos da seção 6, não capturado nesta memória.

---

## Claude Code Quick Context

- Este documento é sobre **contexto e trajetória**, não sobre estrutura técnica — para isso, use o `CLAUDE.md`.
- O ponto de retomada é `stages/validator.py`: confirmar se o drift de título/hook e o erro 413 já foram corrigidos.
- Não reverter as decisões da seção 4 sem entender a história por trás delas — todas têm um custo documentado.
- Próximo passo na agenda de Henri, independente dos bugs: análise de TPM/consumo de tokens.
- Fallback multi-provedor de LLM (Cerebras) só deve ser implementado depois da análise de TPM, não antes.
- TikTok automático via API é bloqueado por fator externo (aprovação pendente) — não é um problema de código a resolver agora.
- Henri espera análise crítica e honesta, incluindo deste próprio documento — sinalize divergências entre este handoff, o `CLAUDE.md` e o código real em vez de assumir que tudo está alinhado.