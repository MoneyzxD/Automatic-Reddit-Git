"""
validator.py
============
Motor de validacao e correcao cirurgica do pipeline.

Filosofia:
    O validador NUNCA apenas aprova/reprova. Ele SEMPRE aponta o problema
    especifico (trecho exato + motivo) e uma correcao e aplicada apenas
    naquele trecho, preservando o resto do conteudo palavra por palavra.

    Isso evita o problema de "regenerar tudo do zero" — que introduz
    variabilidade nova e pode piorar partes que ja estavam boas.

Categorias validadas:
    - script    : adaptacao + traducao + genero + naturalizacao (bloco 4-9)
    - title_hook: titulo de arquivo + hook de engajamento (etapa 10)
    - metadata  : descricao + tags SEO (etapa 17)

Cada validacao roda em llama-3.1-8b-instant (rate limit mais alto que o
70b usado na geracao) para nao sobrecarregar o Groq com o dobro de chamadas.

Loop de retry:
    - Tenta ate aprovar. Teto de seguranca MAX_SAFETY_RETRIES para nunca
      travar o pipeline indefinidamente (o Groq nao "aprende" entre
      chamadas, entao mais tentativas == mais chances de sorte, nao
      progresso garantido — por isso o teto e alto, nao curto).
    - Apos 2 tentativas sem aprovar, dispara alerta no Telegram.
    - A cada nova tentativa, a temperatura sobe (evita ficar preso no
      mesmo raciocinio) e o modelo recebe um resumo da tentativa anterior
      (o que foi tentado, o que ainda falhou) para nao repetir a mesma
      abordagem as cegas.
    - So para antecipadamente por "estagnacao" se a SAIDA for literalmente
      identica a da tentativa anterior por 2 vezes seguidas — isso sim e
      sinal de loop travado sem progresso algum. Reprovacoes com problemas
      parecidos mas nao identicos podem ser so variancia normal do modelo
      e continuam tentando ate o teto.
    - Toda tentativa (aprovada ou nao) e registrada em
      data/logs/improvement_log.jsonl com o problema encontrado e a
      correcao aplicada — base para deteccao de padroes recorrentes.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

MAX_SAFETY_RETRIES   = 6    # teto de seguranca — nunca trava o pipeline
TELEGRAM_ALERT_AFTER = 2    # apos N tentativas sem aprovar, avisa no Telegram
GROQ_CALL_DELAY       = 6.0 # segundos de pausa apos cada chamada Groq do validador
                             # (evita 429/413 por estourar TPM — configuravel via
                             # config["groq_call_delay"]. Valor calibrado para o teto
                             # de 6000 TPM do llama-3.1-8b-instant no tier on-demand —
                             # 2.5s deixava passar varios 429 em sequencia em runs reais)

BASE_TEMPERATURE   = 0.2    # temperatura inicial dos loops de correcao
TEMPERATURE_STEP   = 0.15   # incremento por tentativa reprovada
MAX_TEMPERATURE    = 0.9    # teto de temperatura — so para o loop de SCRIPT (texto
                             # longo, com espaco pra se recuperar de um token ruim)

MAX_TEMPERATURE_SHORT = 0.75  # teto reduzido para geracoes curtas (titulo/hook/
                               # metadados — uma frase so). Temperatura alta nao da
                               # "mais criatividade" nesses casos, colapsa a coerencia
                               # (ex real: "Ruiu o Meu Matrimônio" surgindo exatamente
                               # quando a temperatura batia em 0.9)

STAGNATION_STREAK_TO_STOP = 2  # saida identica por N tentativas seguidas = para


# ── ESTRUTURAS DE DADOS ────────────────────────────────────────────────────

@dataclass
class Issue:
    trecho:    str   # trecho exato com problema
    problema:  str   # o que esta errado
    sugestao:  str   # como deveria ficar (se o validador souber)
    categoria: str   # ex: "gramatica", "genero", "clareza_titulo", "coerencia"


@dataclass
class ValidationResult:
    approved: bool
    score:    int              # 0-100, apenas informativo
    issues:   list[Issue] = field(default_factory=list)
    raw:      str = ""         # resposta bruta do LLM (debug)


# ── PROMPTS DE VALIDACAO ────────────────────────────────────────────────────

SCRIPT_VALIDATION_PROMPTS = {
    "pt": (
        "Você é um revisor rigoroso de scripts narrados para vídeos do YouTube/TikTok "
        "em português do Brasil, estilo histórias do Reddit narradas em primeira pessoa.\n\n"
        "GÊNERO DO NARRADOR: {narrator_gender}\n\n"
        "SCRIPT PARA REVISAR:\n"
        "{script_text}\n\n"
        "TAREFA:\n"
        "Analise o script e identifique problemas REAIS que atrapalhariam a narração ou "
        "a compreensão do espectador. Seja rigoroso mas justo — não invente problemas. "
        "Liste no MÁXIMO 4 problemas, priorizando os mais graves (o script passa por "
        "múltiplas rodadas de correção, não precisa listar tudo de uma vez).\n"
        "Cada \"trecho\" deve ter no MÁXIMO 15 palavras — copie só o pedaço com o erro, "
        "não a frase inteira. Seja conciso: resposta longa demais é cortada no meio e "
        "todo o resultado se perde.\n\n"
        "VERIFIQUE, NESTA ORDEM DE PRIORIDADE:\n"
        "1. PALAVRA REPETIDA colada em sequência (ex: 'consultas, consultas pediátricas', "
        "'ele ele foi') — erro comum de tradução automática que traduz duas expressões "
        "diferentes do inglês para a mesma palavra em português. Procure ativamente por isso "
        "antes de qualquer outra checagem.\n"
        "2. Concordância de gênero incorreta (verbos, adjetivos, artigos) considerando "
        "que o narrador é {narrator_gender}\n"
        "3. Erros gramaticais ou de concordância — incluindo confusão entre 'porque' "
        "(causa) e 'por que' (pergunta), que a tradução automática as vezes coloca "
        "os dois colados na mesma frase por engano\n"
        "4. Frases sem sentido, cortadas, ou que pareçam traduzidas literalmente mal\n"
        "5. Frases excessivamente longas ou complexas demais para narração falada\n"
        "6. Inconsistências na história (nomes, fatos que se contradizem)\n\n"
        "Para CADA problema encontrado, retorne o TRECHO EXATO (copie literalmente do "
        "texto, não parafraseie) onde está o erro, explique o problema, e sugira a correção.\n\n"
        "Retorne APENAS um JSON no formato exato abaixo, sem texto antes ou depois:\n"
        "{{\n"
        '  "approved": true ou false,\n'
        '  "score": numero de 0 a 100,\n'
        '  "issues": [\n'
        "    {{\n"
        '      "trecho": "texto exato copiado do script",\n'
        '      "problema": "explicacao curta do erro",\n'
        '      "sugestao": "como deveria ficar",\n'
        '      "categoria": "gramatica" ou "genero" ou "coerencia" ou "clareza" ou "repeticao"\n'
        "    }}\n"
        "  ]\n"
        "}}\n\n"
        "Se o script estiver bom (sem problemas reais), retorne approved=true e issues=[].\n"
        "Nao sinalize estilo coloquial como erro — narracao natural e esperada.\n"
    ),
    "en": (
        "You are a rigorous script reviewer for YouTube/TikTok narrated videos in English, "
        "Reddit-story style narrated in first person.\n\n"
        "NARRATOR GENDER: {narrator_gender}\n\n"
        "SCRIPT TO REVIEW:\n"
        "{script_text}\n\n"
        "TASK:\n"
        "Analyze the script and identify REAL problems that would hurt narration or viewer "
        "comprehension. Be rigorous but fair — do not invent problems. List AT MOST 4 "
        "problems, prioritizing the most serious ones (the script goes through multiple "
        "correction rounds, no need to list everything at once).\n"
        "Each \"trecho\" must be AT MOST 15 words — copy only the fragment containing the "
        "error, not the whole sentence. Be concise: an overly long answer gets cut off "
        "and the whole result is lost.\n\n"
        "CHECK FOR, IN THIS PRIORITY ORDER:\n"
        "1. A WORD REPEATED back-to-back (e.g. 'appointments, appointments checkup') — a common "
        "translation artifact where two different source phrases both end up as the same word. "
        "Actively scan for this before anything else.\n"
        "2. Grammar or agreement errors\n"
        "3. Sentences that make no sense, are cut off, or read like bad literal translation\n"
        "4. Sentences too long or complex for spoken narration\n"
        "5. Story inconsistencies (names, contradicting facts)\n\n"
        "For EACH problem found, return the EXACT excerpt (copy literally from the text) "
        "where the error is, explain the problem, and suggest the fix.\n\n"
        "Return ONLY a JSON in the exact format below, no text before or after:\n"
        "{{\n"
        '  "approved": true or false,\n'
        '  "score": number 0 to 100,\n'
        '  "issues": [\n'
        "    {{\n"
        '      "trecho": "exact text copied from the script",\n'
        '      "problema": "short explanation of the error",\n'
        '      "sugestao": "how it should read",\n'
        '      "categoria": "gramatica" or "genero" or "coerencia" or "clareza" or "repeticao"\n'
        "    }}\n"
        "  ]\n"
        "}}\n\n"
        "If the script is good (no real problems), return approved=true and issues=[].\n"
        "Do not flag colloquial style as an error — natural narration is expected.\n"
    ),
    "es": (
        "Eres un revisor riguroso de guiones narrados para videos de YouTube/TikTok en "
        "español, estilo historias de Reddit narradas en primera persona.\n\n"
        "GÉNERO DEL NARRADOR: {narrator_gender}\n\n"
        "GUION A REVISAR:\n"
        "{script_text}\n\n"
        "TAREA:\n"
        "Analiza el guion e identifica problemas REALES que afectarian la narracion o la "
        "comprension del espectador. Se riguroso pero justo — no inventes problemas. Lista "
        "COMO MAXIMO 4 problemas, priorizando los mas graves (el guion pasa por multiples "
        "rondas de correccion, no hace falta listar todo de una vez).\n"
        "Cada \"trecho\" debe tener COMO MAXIMO 15 palabras — copia solo el fragmento con "
        "el error, no la frase entera. Se conciso: una respuesta demasiado larga se corta "
        "y se pierde todo el resultado.\n\n"
        "VERIFICA, EN ESTE ORDEN DE PRIORIDAD:\n"
        "1. PALABRA REPETIDA pegada en secuencia (ej: 'citas, citas médicas') — error comun de "
        "traduccion automatica que traduce dos expresiones distintas del ingles a la misma "
        "palabra en español. Busca esto activamente antes que cualquier otra cosa.\n"
        "2. Errores de concordancia de genero (verbos, adjetivos, articulos) considerando "
        "que el narrador es {narrator_gender}\n"
        "3. Errores gramaticales o de concordancia\n"
        "4. Frases sin sentido, cortadas, o que parezcan mal traducidas literalmente\n"
        "5. Frases demasiado largas o complejas para narracion hablada\n"
        "6. Inconsistencias en la historia (nombres, hechos que se contradicen)\n\n"
        "Para CADA problema encontrado, devuelve el FRAGMENTO EXACTO (copia literalmente "
        "del texto) donde esta el error, explica el problema, y sugiere la correccion.\n\n"
        "Devuelve SOLO un JSON en el formato exacto de abajo, sin texto antes o despues:\n"
        "{{\n"
        '  "approved": true o false,\n'
        '  "score": numero de 0 a 100,\n'
        '  "issues": [\n'
        "    {{\n"
        '      "trecho": "texto exacto copiado del guion",\n'
        '      "problema": "explicacion corta del error",\n'
        '      "sugestao": "como deberia quedar",\n'
        '      "categoria": "gramatica" o "genero" o "coerencia" o "clareza" o "repeticao"\n'
        "    }}\n"
        "  ]\n"
        "}}\n\n"
        "Si el guion esta bien (sin problemas reales), devuelve approved=true e issues=[].\n"
        "No senales el estilo coloquial como error — la narracion natural es esperada.\n"
    ),
}

TITLE_HOOK_VALIDATION_PROMPTS = {
    "pt": (
        "Você é um revisor rigoroso de títulos e hooks virais para YouTube Shorts/TikTok "
        "em português do Brasil.\n\n"
        "GÊNERO DO NARRADOR: {narrator_gender}\n\n"
        "CONTEXTO DA HISTÓRIA (resumo):\n"
        "{story_text}\n\n"
        "TÍTULO DE ARQUIVO GERADO:\n"
        "{title}\n\n"
        "HOOK DE ENGAJAMENTO GERADO (narrado no início e usado como título no YouTube):\n"
        "{hook}\n\n"
        "TAREFA:\n"
        "Avalie se o título e o hook fazem sentido, são claros, e vendem bem a história "
        "sem ser vagos ou confusos.\n\n"
        "PROBLEMAS COMUNS A DETECTAR:\n"
        "1. Concordância de gênero incorreta em palavras que variam por gênero (ex: "
        "'vilão'/'vilã', 'enganado'/'enganada', 'sozinho'/'sozinha') considerando que "
        "o narrador é {narrator_gender} — este é o erro mais comum e mais visível "
        "publicamente, verifique com atenção antes de qualquer outro item\n"
        "2. Referências vagas que não fazem sentido fora de contexto (ex: 'terminou o caso' "
        "sem deixar claro que é um caso extraconjugal)\n"
        "3. Título/hook que soa cortado ou gramaticalmente estranho\n"
        "4. Falta de clareza sobre O QUE aconteceu na história\n"
        "5. Título fraco que não gera curiosidade\n"
        "6. Inconsistência entre título/hook e o que realmente acontece na história\n"
        "7. Números/valores em dinheiro no HOOK escritos em dígitos (ex: '15.000', "
        "'R$15.000') em vez de por extenso ('quinze mil reais') — o hook é narrado por "
        "TTS, que lê dígitos um por um em vez de falar o número (não se aplica ao título, "
        "que não é narrado)\n\n"
        "Retorne APENAS um JSON no formato exato abaixo, sem texto antes ou depois:\n"
        "{{\n"
        '  "approved": true ou false,\n'
        '  "score": numero de 0 a 100,\n'
        '  "issues": [\n'
        "    {{\n"
        '      "trecho": "titulo" ou "hook",\n'
        '      "problema": "explicacao curta do erro",\n'
        '      "sugestao": "nova versao sugerida, completa e clara",\n'
        '      "categoria": "genero" ou "clareza" ou "gramatica" ou "impacto" ou "inconsistencia"\n'
        "    }}\n"
        "  ]\n"
        "}}\n"
    ),
    "en": (
        "You are a rigorous reviewer of viral titles and hooks for YouTube Shorts/TikTok "
        "in English.\n\n"
        "NARRATOR GENDER: {narrator_gender}\n\n"
        "STORY CONTEXT (summary):\n"
        "{story_text}\n\n"
        "GENERATED FILE TITLE:\n"
        "{title}\n\n"
        "GENERATED ENGAGEMENT HOOK (narrated at the start, used as YouTube title):\n"
        "{hook}\n\n"
        "TASK:\n"
        "Evaluate whether the title and hook make sense, are clear, and sell the story "
        "well without being vague or confusing.\n\n"
        "COMMON PROBLEMS TO DETECT:\n"
        "1. Incorrect gender agreement on words that vary by gender (e.g. villain/villainess, "
        "cheated-on husband vs. wife) given the narrator is {narrator_gender} — this is the "
        "most common and most publicly visible error, check it carefully before anything else\n"
        "2. Vague references that make no sense out of context\n"
        "3. Title/hook that sounds cut off or grammatically strange\n"
        "4. Lack of clarity about WHAT happened in the story\n"
        "5. Weak title that doesn't create curiosity\n"
        "6. Inconsistency between title/hook and what actually happens in the story\n"
        "7. Numbers/money amounts in the HOOK written as digits (e.g. '$15,000', "
        "'15,000') instead of spelled out ('fifteen thousand dollars') — the hook is "
        "narrated by TTS, which reads digits one by one instead of speaking the number "
        "(does not apply to the title, which is not narrated)\n\n"
        "Return ONLY a JSON in the exact format below, no text before or after:\n"
        "{{\n"
        '  "approved": true or false,\n'
        '  "score": number 0 to 100,\n'
        '  "issues": [\n'
        "    {{\n"
        '      "trecho": "titulo" or "hook",\n'
        '      "problema": "short explanation of the error",\n'
        '      "sugestao": "suggested new version, complete and clear",\n'
        '      "categoria": "genero" or "clareza" or "gramatica" or "impacto" or "inconsistencia"\n'
        "    }}\n"
        "  ]\n"
        "}}\n"
    ),
    "es": (
        "Eres un revisor riguroso de titulos y hooks virales para YouTube Shorts/TikTok "
        "en español.\n\n"
        "GÉNERO DEL NARRADOR: {narrator_gender}\n\n"
        "CONTEXTO DE LA HISTORIA (resumen):\n"
        "{story_text}\n\n"
        "TITULO DE ARCHIVO GENERADO:\n"
        "{title}\n\n"
        "HOOK DE ENGANCHE GENERADO (narrado al inicio, usado como titulo de YouTube):\n"
        "{hook}\n\n"
        "TAREA:\n"
        "Evalua si el titulo y el hook tienen sentido, son claros, y venden bien la "
        "historia sin ser vagos o confusos.\n\n"
        "PROBLEMAS COMUNES A DETECTAR:\n"
        "1. Concordancia de genero incorrecta en palabras que varian por genero (ej: "
        "'villano'/'villana', 'engañado'/'engañada') considerando que el narrador es "
        "{narrator_gender} — este es el error mas comun y mas visible publicamente, "
        "verificalo con atencion antes que cualquier otro punto\n"
        "2. Referencias vagas que no tienen sentido fuera de contexto\n"
        "3. Titulo/hook que suena cortado o gramaticalmente extrano\n"
        "4. Falta de claridad sobre QUE paso en la historia\n"
        "5. Titulo debil que no genera curiosidad\n"
        "6. Inconsistencia entre titulo/hook y lo que realmente pasa en la historia\n"
        "7. Numeros/montos de dinero en el HOOK escritos en digitos (ej: '15.000', "
        "'$15.000') en vez de en palabras ('quince mil dolares') — el hook es narrado "
        "por TTS, que lee los digitos uno por uno en vez de decir el numero (no aplica "
        "al titulo, que no se narra)\n\n"
        "Devuelve SOLO un JSON en el formato exacto de abajo, sin texto antes o despues:\n"
        "{{\n"
        '  "approved": true o false,\n'
        '  "score": numero de 0 a 100,\n'
        '  "issues": [\n'
        "    {{\n"
        '      "trecho": "titulo" o "hook",\n'
        '      "problema": "explicacion corta del error",\n'
        '      "sugestao": "nueva version sugerida, completa y clara",\n'
        '      "categoria": "genero" o "clareza" o "gramatica" o "impacto" o "inconsistencia"\n'
        "    }}\n"
        "  ]\n"
        "}}\n"
    ),
}

METADATA_VALIDATION_PROMPTS = {
    "pt": (
        "Você é um revisor de metadados SEO para vídeos do YouTube em português do Brasil.\n\n"
        "CONTEXTO DA HISTÓRIA (resumo):\n"
        "{story_text}\n\n"
        "METADADOS GERADOS:\n"
        "Descrição: {description}\n"
        "Tags: {tags}\n\n"
        "TAREFA:\n"
        "Avalie se a descrição realmente corresponde à história, se está clara e "
        "gramaticalmente correta, e se as tags são relevantes.\n\n"
        "Retorne APENAS um JSON no formato exato abaixo, sem texto antes ou depois:\n"
        "{{\n"
        '  "approved": true ou false,\n'
        '  "score": numero de 0 a 100,\n'
        '  "issues": [\n'
        "    {{\n"
        '      "trecho": "description" ou "tags",\n'
        '      "problema": "explicacao curta do erro",\n'
        '      "sugestao": "correcao sugerida",\n'
        '      "categoria": "relevancia" ou "gramatica" ou "clareza"\n'
        "    }}\n"
        "  ]\n"
        "}}\n"
    ),
    "en": (
        "You are an SEO metadata reviewer for YouTube videos in English.\n\n"
        "STORY CONTEXT (summary):\n"
        "{story_text}\n\n"
        "GENERATED METADATA:\n"
        "Description: {description}\n"
        "Tags: {tags}\n\n"
        "TASK:\n"
        "Evaluate whether the description truly matches the story, is clear and "
        "grammatically correct, and whether the tags are relevant.\n\n"
        "Return ONLY a JSON in the exact format below, no text before or after:\n"
        "{{\n"
        '  "approved": true or false,\n'
        '  "score": number 0 to 100,\n'
        '  "issues": [\n'
        "    {{\n"
        '      "trecho": "description" or "tags",\n'
        '      "problema": "short explanation of the error",\n'
        '      "sugestao": "suggested fix",\n'
        '      "categoria": "relevancia" or "gramatica" or "clareza"\n'
        "    }}\n"
        "  ]\n"
        "}}\n"
    ),
    "es": (
        "Eres un revisor de metadatos SEO para videos de YouTube en español.\n\n"
        "CONTEXTO DE LA HISTORIA (resumen):\n"
        "{story_text}\n\n"
        "METADATOS GENERADOS:\n"
        "Descripcion: {description}\n"
        "Tags: {tags}\n\n"
        "TAREA:\n"
        "Evalua si la descripcion realmente corresponde a la historia, si es clara y "
        "gramaticalmente correcta, y si las tags son relevantes.\n\n"
        "Devuelve SOLO un JSON en el formato exacto de abajo, sin texto antes o despues:\n"
        "{{\n"
        '  "approved": true o false,\n'
        '  "score": numero de 0 a 100,\n'
        '  "issues": [\n'
        "    {{\n"
        '      "trecho": "description" o "tags",\n'
        '      "problema": "explicacion corta del error",\n'
        '      "sugestao": "correccion sugerida",\n'
        '      "categoria": "relevancia" o "gramatica" o "clareza"\n'
        "    }}\n"
        "  ]\n"
        "}}\n"
    ),
}


# ── PROMPTS DE CORRECAO CIRURGICA ───────────────────────────────────────────

SURGICAL_FIX_PROMPTS = {
    "pt": (
        "Você vai corrigir um texto de forma CIRURGICA — ou seja, alterar APENAS os "
        "trechos problematicos indicados abaixo, mantendo TODO o resto do texto "
        "EXATAMENTE IGUAL, palavra por palavra.\n\n"
        "TEXTO ORIGINAL COMPLETO:\n"
        "{original_text}\n\n"
        "PROBLEMAS A CORRIGIR:\n"
        "{issues_formatted}\n\n"
        "REGRAS OBRIGATORIAS:\n"
        "- Altere APENAS os trechos exatos listados acima\n"
        "- NAO reescreva frases que nao foram apontadas como problema\n"
        "- NAO mude o estilo, tom ou estrutura do restante do texto\n"
        "- Mantenha a mesma quantidade aproximada de paragrafos e quebras de linha\n"
        "- Retorne o TEXTO COMPLETO corrigido, do inicio ao fim\n"
        "- Nao adicione comentarios, explicacoes ou marcacoes — apenas o texto final\n"
    ),
    "en": (
        "You will fix a text SURGICALLY — meaning, change ONLY the problematic excerpts "
        "listed below, keeping ALL the rest of the text EXACTLY THE SAME, word for word.\n\n"
        "FULL ORIGINAL TEXT:\n"
        "{original_text}\n\n"
        "PROBLEMS TO FIX:\n"
        "{issues_formatted}\n\n"
        "MANDATORY RULES:\n"
        "- Change ONLY the exact excerpts listed above\n"
        "- Do NOT rewrite sentences that were not flagged as a problem\n"
        "- Do NOT change the style, tone, or structure of the rest of the text\n"
        "- Keep approximately the same number of paragraphs and line breaks\n"
        "- Return the FULL corrected text, from start to end\n"
        "- Do not add comments, explanations, or markup — just the final text\n"
    ),
    "es": (
        "Vas a corregir un texto de forma QUIRURGICA — es decir, cambiar SOLO los "
        "fragmentos problematicos indicados abajo, manteniendo TODO el resto del texto "
        "EXACTAMENTE IGUAL, palabra por palabra.\n\n"
        "TEXTO ORIGINAL COMPLETO:\n"
        "{original_text}\n\n"
        "PROBLEMAS A CORREGIR:\n"
        "{issues_formatted}\n\n"
        "REGLAS OBLIGATORIAS:\n"
        "- Cambia SOLO los fragmentos exactos listados arriba\n"
        "- NO reescribas frases que no fueron señaladas como problema\n"
        "- NO cambies el estilo, tono o estructura del resto del texto\n"
        "- Manten aproximadamente la misma cantidad de parrafos y saltos de linea\n"
        "- Devuelve el TEXTO COMPLETO corregido, de principio a fin\n"
        "- No agregues comentarios, explicaciones o marcas — solo el texto final\n"
    ),
}

# Exemplos de calibracao para a correcao de titulo/hook. Substituem a antiga
# regra rigida "proibido dois-pontos / proibido repetir palavra-chave": em vez
# de uma restricao mecanica (que erra em casos legitimos, ex. enfase retorica),
# o modelo recebe exemplos contrastantes e julga semanticamente caso a caso —
# mesmo principio ja usado na correcao de genero do script.
TITLE_HOOK_FIX_EXAMPLES = {
    "pt": (
        "CRITERIOS PARA CALIBRAR SEU JULGAMENTO (principios de julgamento, NUNCA copie uma "
        "frase de exemplo como se fosse a resposta certa — cada historia e diferente):\n"
        "- Dois-pontos costuma indicar duas ideias coladas sem conexao real (frase + "
        "subtitulo colado). Prefira integrar tudo numa frase so.\n"
        "- Repeticao NAO e sempre erro — pode ser enfase retorica valida e forte. So e fraca "
        "quando vem de falta de vocabulario, nao de intencao.\n"
        "- Referencia vaga ou eufemismo que exige contexto externo (algo que so faz sentido "
        "pra quem ja conhece a historia inteira) e fraco. Nomeie o conflito real da historia "
        "de forma direta, sem inventar detalhes que nao estao nela.\n"
        "- Julgue pelo efeito real na clareza e no impacto do hook, caso a caso — nunca por "
        "uma regra mecanica de 'nunca usar X' nem repetindo a redacao de um exemplo.\n"
    ),
    "en": (
        "JUDGMENT CRITERIA (principles, NEVER copy an example sentence as if it were the "
        "correct answer — every story is different):\n"
        "- A colon usually signals two loosely connected ideas glued together (sentence + "
        "subtitle). Prefer one fully integrated sentence.\n"
        "- Repetition is NOT always an error — it can be valid, strong rhetorical emphasis. "
        "It's only weak when it comes from lack of vocabulary, not intent.\n"
        "- A vague reference or euphemism that requires outside context (something that only "
        "makes sense to someone who already knows the full story) is weak. Name the story's "
        "real conflict directly, without inventing details that aren't in it.\n"
        "- Judge by the real effect on clarity and impact, case by case — never by a "
        "mechanical 'never use X' rule, and never by reusing an example's wording.\n"
    ),
    "es": (
        "CRITERIOS DE JUICIO (principios, NUNCA copies una frase de ejemplo como si fuera "
        "la respuesta correcta — cada historia es diferente):\n"
        "- Los dos puntos suelen indicar dos ideas pegadas sin conexion real (frase + "
        "subtitulo pegado). Prefiere integrar todo en una sola frase.\n"
        "- La repeticion NO siempre es error — puede ser enfasis retorico valido y fuerte. "
        "Solo es debil cuando viene de falta de vocabulario, no de intencion.\n"
        "- Una referencia vaga o eufemismo que exige contexto externo (algo que solo tiene "
        "sentido para quien ya conoce la historia completa) es debil. Nombra el conflicto "
        "real de la historia de forma directa, sin inventar detalles que no esten en ella.\n"
        "- Juzga por el efecto real en la claridad e impacto, caso por caso — nunca por una "
        "regla mecanica de 'nunca usar X' ni repitiendo la redaccion de un ejemplo.\n"
    ),
}


class ValidatorEngine:
    """
    Motor de validacao e correcao cirurgica.
    Usa um modelo mais leve (8b-instant) para nao competir com o modelo
    de geracao (70b-versatile) pelo mesmo rate limit no Groq.
    """

    def __init__(self, config: dict = None, base_dir: Path | str = "."):
        self.config          = config or {}
        self.groq_key        = os.environ.get("GROQ_API_KEY", "") or self.config.get("groq_api_key", "")
        self.groq_model      = self.config.get("groq_validator_model", "openai/gpt-oss-20b")
        self.enabled         = self.config.get("enabled", True)
        self.groq_call_delay = float(self.config.get("groq_call_delay", GROQ_CALL_DELAY))
        self.base_dir        = Path(base_dir)
        self.log_path        = self.base_dir / "data" / "logs" / "improvement_log.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # Consumo de tokens acumulado ao longo da execucao (1 instancia =
        # 1 execucao do pipeline, ja que main.py cria o ValidatorEngine uma
        # vez por rodada). Usado para reportar consumo em alertas Telegram
        # e para a analise de TPM/custo por historia.
        self.token_usage = {"prompt": 0, "completion": 0, "total": 0, "calls": 0}

    def get_token_usage_summary(self) -> str:
        """Resumo legivel do consumo de tokens do validador nesta execucao."""
        u = self.token_usage
        if u["calls"] == 0:
            return "0 chamadas"
        return (
            f"{u['calls']} chamada(s) | ~{u['total']} tokens totais "
            f"(entrada={u['prompt']}, saida={u['completion']})"
        )

    # ── CHAMADA GENERICA AO GROQ ────────────────────────────────────────────

    def _call_groq(self, system_prompt: str, user_prompt: str,
                   temperature: float = 0.3, max_tokens: int = 1500,
                   language: str = "") -> str | None:
        from utils import environment as env
        groq_key = env.groq_api_key(language) or self.groq_key
        if not groq_key:
            return None
        try:
            from utils.groq_client import tracked_groq
            client = tracked_groq(groq_key, "validator")
            resp = client.chat.completions.create(
                model=self.groq_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            choice = resp.choices[0]
            if getattr(choice, "finish_reason", None) == "length":
                logger.warning(
                    "Resposta do Groq TRUNCADA por max_tokens=%d — o JSON/texto pode "
                    "estar incompleto. Considere aumentar max_tokens para este caso.",
                    max_tokens,
                )

            usage = getattr(resp, "usage", None)
            if usage is not None:
                self.token_usage["prompt"]     += getattr(usage, "prompt_tokens", 0) or 0
                self.token_usage["completion"] += getattr(usage, "completion_tokens", 0) or 0
                self.token_usage["total"]      += getattr(usage, "total_tokens", 0) or 0
                self.token_usage["calls"]      += 1

            return choice.message.content.strip()
        except Exception as e:
            logger.warning("Groq falhou na validacao: %s", e)
            return None
        finally:
            # Pausa apos toda chamada (sucesso ou falha) para nao estourar o
            # TPM do Groq quando varios checkpoints disparam em sequencia.
            time.sleep(self.groq_call_delay)

    def _parse_validation_json(self, raw: str | None) -> ValidationResult:
        if not raw:
            # Sem resposta do LLM — aprova por seguranca (nao bloqueia o pipeline
            # por indisponibilidade da API) mas registra o problema
            from utils import telemetry
            telemetry.record_fallback("validator", "-", "sem resposta do Groq — aprovou sem validar")
            logger.warning("Validador sem resposta do Groq — aprovando por seguranca")
            return ValidationResult(approved=True, score=0, issues=[], raw="")

        cleaned = re.sub(r"^```json\s*|```\s*$", "", raw.strip(), flags=re.MULTILINE).strip()
        try:
            data = json.loads(cleaned)
            issues = [
                Issue(
                    trecho=i.get("trecho", ""),
                    problema=i.get("problema", ""),
                    sugestao=i.get("sugestao", ""),
                    categoria=i.get("categoria", "geral"),
                )
                for i in data.get("issues", [])
            ]
            return ValidationResult(
                approved=bool(data.get("approved", True)),
                score=int(data.get("score", 100)),
                issues=issues,
                raw=raw,
            )
        except Exception as e:
            recovered = self._salvage_issues(cleaned)
            if recovered:
                logger.warning(
                    "JSON de validacao truncado/malformado, mas %d problema(s) recuperado(s) "
                    "parcialmente — tratando como REPROVADO em vez de aprovar as cegas (%s)",
                    len(recovered), e,
                )
                return ValidationResult(approved=False, score=50, issues=recovered, raw=raw)
            logger.warning(
                "Falha ao parsear JSON de validacao e nada recuperavel — aprovando por "
                "seguranca (nao ha o que corrigir): %s | raw=%s", e, raw[:300],
            )
            return ValidationResult(approved=True, score=0, issues=[], raw=raw)

    @staticmethod
    def _salvage_issues(cleaned: str) -> list[Issue]:
        """
        Recupera objetos de issue COMPLETOS de um JSON truncado/malformado via
        regex, em vez de descartar tudo. O JSON costuma truncar no FIM (estouro
        de max_tokens) — os primeiros problemas geralmente vieram inteiros e sao
        recuperaveis, mesmo que o array/objeto externo nao feche corretamente.
        """
        issues: list[Issue] = []
        pattern = (
            r'\{\s*"trecho"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"problema"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*'
            r'"sugestao"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"categoria"\s*:\s*"((?:[^"\\]|\\.)*)"\s*\}'
        )
        for match in re.finditer(pattern, cleaned):
            try:
                trecho, problema, sugestao, categoria = (
                    json.loads(f'"{g}"') for g in match.groups()
                )
            except Exception:
                continue
            issues.append(Issue(trecho=trecho, problema=problema, sugestao=sugestao, categoria=categoria))
        return issues

    # ── VALIDACAO: SCRIPT (bloco adaptacao/traducao/genero/naturalizacao) ───

    _UNKNOWN_GENDER_LABEL = {
        "pt": "ainda nao determinado nesta etapa — NAO aponte problemas de concordancia de genero agora",
        "en": "not yet determined at this stage — do NOT flag gender agreement issues now",
        "es": "aun no determinado en esta etapa — NO señales problemas de concordancia de genero ahora",
    }

    def validate_script(self, script_text: str, language: str = "pt",
                        narrator_gender: str = "unknown") -> ValidationResult:
        prompt_tpl = SCRIPT_VALIDATION_PROMPTS.get(language, SCRIPT_VALIDATION_PROMPTS["en"])
        gender_label = (
            self._UNKNOWN_GENDER_LABEL.get(language, self._UNKNOWN_GENDER_LABEL["en"])
            if narrator_gender == "unknown" else narrator_gender
        )
        prompt = prompt_tpl.format(script_text=script_text, narrator_gender=gender_label)

        # max_tokens dinamico: script maior -> mais chance de mais problemas
        # apontados -> mais espaco de saida necessario para o JSON nao ser
        # truncado no meio.
        #
        # RESERVA DE RACIOCINIO: os modelos gpt-oss gastam parte do orcamento
        # "pensando" antes de escrever. Sem folga extra, o raciocinio consome
        # tudo, o conteudo volta vazio/truncado e o validador aprova sem
        # validar. Medido em producao: com reserva de 1400 ainda truncava as
        # vezes (~3254 num script medio) porque o raciocinio varia de
        # tentativa pra tentativa — subido pra 1800.
        # Teto subido de 3500 para 4500: agora cada idioma tem sua propria
        # chave/orcamento de 8000 TOKENS POR MINUTO (nao compartilhado mais
        # entre PT/EN/ES), entao ha mais folga pra uma chamada unica sem
        # comer o orcamento das chamadas seguintes no mesmo minuto.
        word_count = len(script_text.split())
        dynamic_max_tokens = min(4500, max(2000, 1800 + word_count * 3))

        raw = self._call_groq(
            system_prompt=f"Responda em {language}. Retorne APENAS JSON valido, sem texto adicional.",
            user_prompt=prompt,
            temperature=0.2,
            max_tokens=dynamic_max_tokens,
            language=language,
        )
        return self._parse_validation_json(raw)

    # ── VALIDACAO: TITULO + HOOK ─────────────────────────────────────────────

    def validate_title_hook(self, title: str, hook: str, story_text: str,
                            language: str = "pt",
                            narrator_gender: str = "unknown") -> ValidationResult:
        prompt_tpl = TITLE_HOOK_VALIDATION_PROMPTS.get(language, TITLE_HOOK_VALIDATION_PROMPTS["en"])
        gender_label = (
            self._UNKNOWN_GENDER_LABEL.get(language, self._UNKNOWN_GENDER_LABEL["en"])
            if narrator_gender == "unknown" else narrator_gender
        )
        prompt = prompt_tpl.format(
            title=title,
            hook=hook,
            story_text=story_text[:500].replace("\n", " "),
            narrator_gender=gender_label,
        )
        raw = self._call_groq(
            system_prompt=f"Responda em {language}. Retorne APENAS JSON valido, sem texto adicional.",
            user_prompt=prompt,
            temperature=0.3,
            # 800 truncava com frequencia: o modelo (reasoning) gasta parte
            # do orcamento "pensando" antes de escrever o JSON, e o prompt
            # de titulo/hook ficou mais longo depois da checagem de genero
            # (mais um item pra avaliar = mais raciocinio antes da resposta).
            max_tokens=1500,
            language=language,
        )
        return self._parse_validation_json(raw)

    # ── VALIDACAO: METADADOS ─────────────────────────────────────────────────

    def validate_metadata(self, description: str, tags: list | str, story_text: str,
                          language: str = "pt") -> ValidationResult:
        prompt_tpl = METADATA_VALIDATION_PROMPTS.get(language, METADATA_VALIDATION_PROMPTS["en"])
        tags_str = ", ".join(tags) if isinstance(tags, list) else str(tags)
        prompt = prompt_tpl.format(
            description=description,
            tags=tags_str,
            story_text=story_text[:500].replace("\n", " "),
        )
        raw = self._call_groq(
            system_prompt=f"Responda em {language}. Retorne APENAS JSON valido, sem texto adicional.",
            user_prompt=prompt,
            temperature=0.3,
            # Mesmo motivo do validate_title_hook acima — 800 e apertado
            # demais pra um modelo de raciocinio.
            max_tokens=1500,
            language=language,
        )
        return self._parse_validation_json(raw)

    # ── CORRECAO CIRURGICA DE TEXTO LONGO (script) ──────────────────────────

    # Prefixos que indicam que a "sugestao" e uma INSTRUCAO sobre o que fazer
    # ("Dividir a frase em duas...", "Remover a frase ou...") em vez do texto
    # de substituicao pronto. Aplicar isso via str.replace() cola a instrucao
    # literal na narracao (bug real observado varias vezes no improvement_log).
    _INSTRUCTION_PREFIXES = (
        "dividir ", "divida ", "remover ", "remova ", "reorganizar ", "reorganize ",
        "reescrever ", "reescreva ", "quebrar ", "quebre ", "reestruturar ",
        "reestruture ", "integrar ", "integre ", "verificar ", "verifique ",
        "simplificar ", "simplifique ", "trocar ", "troque ", "mudar a frase",
        "split ", "remove ", "rewrite ", "reorganize the", "restructure ",
        "break the", "simplify ", "change the sentence", "check ",
        "dividir la", "eliminar ", "elimine ", "reescribir ", "reescriba ",
        "romper la", "cambiar la frase", "simplificar la", "verificar si",
    )

    @classmethod
    def _looks_like_instruction(cls, sugestao: str) -> bool:
        """Detecta sugestao que descreve uma acao em vez de dar o texto pronto."""
        s = sugestao.strip().lower()
        return s.startswith(cls._INSTRUCTION_PREFIXES)

    @classmethod
    def _apply_direct_replacements(cls, text: str, issues: list[Issue]) -> tuple[str, list[Issue]]:
        """
        TIER 1 — substituicao direta trecho -> sugestao, SEM chamada ao LLM.

        A validacao ja retorna "sugestao" pronta para cada problema. Se o
        `trecho` aparece EXATAMENTE UMA VEZ no texto E a sugestao parece ser
        texto de substituicao de verdade (nao uma instrucao tipo "divida a
        frase"), a troca e segura e gratuita (0 tokens). Caso contrario, o
        issue fica pendente para o TIER 2 (LLM com contexto completo, que
        recebe a instrucao e de fato reescreve o trecho).

        Retorna (texto_atualizado, issues_que_ainda_precisam_de_llm).
        """
        unresolved: list[Issue] = []
        for issue in issues:
            if (
                issue.trecho and issue.sugestao
                and text.count(issue.trecho) == 1
                and not cls._looks_like_instruction(issue.sugestao)
            ):
                text = text.replace(issue.trecho, issue.sugestao, 1)
            else:
                unresolved.append(issue)
        return text, unresolved

    def apply_surgical_fix(self, original_text: str, issues: list[Issue],
                           language: str = "pt", previous_feedback: str = "",
                           temperature: float = 0.2) -> str | None:
        """
        Corrige APENAS os trechos apontados em `issues`, preservando o
        resto do texto palavra por palavra. Usado para scripts longos.

        Estrategia em 2 niveis:
        - TIER 1: substituicao direta trecho->sugestao (0 tokens), quando
          o trecho aparece uma unica vez no texto (seguro).
        - TIER 2: para o que sobrar (trecho ambiguo/repetido ou sem
          sugestao utilizavel), chamada ao LLM em modo cirurgico com o
          texto completo como rede de seguranca — mas so pedindo correcao
          dos issues restantes, nao de todos.

        previous_feedback: resumo da tentativa anterior (o que foi apontado
        e sugerido) para o modelo nao repetir a mesma correcao que ja
        falhou na validacao seguinte.
        """
        if not issues:
            return original_text

        text, unresolved = self._apply_direct_replacements(original_text, issues)
        resolved_count = len(issues) - len(unresolved)
        if resolved_count:
            logger.info(
                "%d/%d problema(s) do script corrigido(s) por substituicao "
                "direta (0 tokens extras)", resolved_count, len(issues),
            )

        if not unresolved:
            return text

        issues_formatted = "\n".join(
            f"{idx+1}. Trecho: \"{iss.trecho}\"\n"
            f"   Problema: {iss.problema}\n"
            f"   Sugestao: {iss.sugestao}"
            for idx, iss in enumerate(unresolved)
        )

        prompt_tpl = SURGICAL_FIX_PROMPTS.get(language, SURGICAL_FIX_PROMPTS["en"])
        prompt = prompt_tpl.format(
            original_text=text,
            issues_formatted=issues_formatted,
        )
        if previous_feedback:
            prompt += (
                "\n\nHISTORICO DA TENTATIVA ANTERIOR (a correcao abaixo ja foi tentada "
                "e o problema AINDA persistiu na validacao seguinte — tente uma "
                "abordagem diferente desta vez, nao repita a mesma redacao):\n"
                f"{previous_feedback}\n"
            )

        raw = self._call_groq(
            system_prompt=f"Responda em {language}. Retorne APENAS o texto corrigido, sem comentarios.",
            user_prompt=prompt,
            temperature=temperature,
            max_tokens=4000,
            language=language,
        )
        if raw:
            return raw.strip()
        if resolved_count:
            logger.warning(
                "Correcao cirurgica (tier 2) falhou — mantendo as %d correcao(oes) "
                "diretas ja aplicadas", resolved_count,
            )
            return text
        logger.warning("Correcao cirurgica falhou — mantendo texto original")
        return None

    # ── CORRECAO DE TITULO/HOOK (regeneracao guiada) ─────────────────────────

    def apply_title_hook_fix(self, title: str, hook: str, issues: list[Issue],
                             story_text: str, language: str = "pt",
                             previous_feedback: str = "",
                             temperature: float = 0.7) -> tuple[str, str]:
        """
        Regenera titulo e/ou hook considerando especificamente os problemas
        apontados. So altera o campo (titulo ou hook) que teve problema
        reportado; o outro permanece igual.

        Usa exemplos de calibracao (TITLE_HOOK_FIX_EXAMPLES) em vez de regras
        rigidas tipo "proibido dois-pontos" — o modelo julga semanticamente
        caso a caso, porque regra mecanica erra em casos legitimos (ex.
        repeticao como enfase retorica).
        """
        title_issues = [i for i in issues if i.trecho.lower() == "titulo"]
        hook_issues  = [i for i in issues if i.trecho.lower() == "hook"]

        # Titulo/hook deve ser UMA frase — nunca "frase: subtitulo". O modelo
        # insiste nesse formato mesmo com exemplo de calibracao no prompt
        # (caso real: "Descobri o caso...: a minha historia de dor e superacao"),
        # entao aqui e uma trava deterministica sobre qualquer texto aceito.
        def _strip_colon_subtitle(s: str) -> str:
            return s.split(":", 1)[0].strip() if ":" in s else s

        new_title = title
        new_hook  = hook

        # TIER 1: a validacao ja pede "sugestao" como versao COMPLETA e
        # pronta (nao um trecho isolado). Se for utilizavel, usamos direto
        # -- sem segunda chamada ao Groq.
        def _usable_suggestion(sugestao: str, current: str) -> bool:
            s = (sugestao or "").strip()
            return (
                bool(s) and len(s) >= 10 and s.lower() != current.strip().lower()
                and not self._looks_like_instruction(s)
            )

        remaining_title_issues = []
        for iss in title_issues:
            if _usable_suggestion(iss.sugestao, title):
                new_title = _strip_colon_subtitle(iss.sugestao.strip())
            else:
                remaining_title_issues.append(iss)

        remaining_hook_issues = []
        for iss in hook_issues:
            if _usable_suggestion(iss.sugestao, hook):
                new_hook = _strip_colon_subtitle(iss.sugestao.strip())
            else:
                remaining_hook_issues.append(iss)

        if title_issues and not remaining_title_issues:
            logger.info("Titulo corrigido via sugestao direta da validacao (0 tokens extras)")
        if hook_issues and not remaining_hook_issues:
            logger.info("Hook corrigido via sugestao direta da validacao (0 tokens extras)")

        title_issues = remaining_title_issues
        hook_issues  = remaining_hook_issues

        examples = TITLE_HOOK_FIX_EXAMPLES.get(language, TITLE_HOOK_FIX_EXAMPLES["en"])
        history_block = (
            f"\n\nTENTATIVA ANTERIOR (a sugestao abaixo ja foi usada e o problema "
            f"AINDA persistiu na validacao seguinte — nao repita a mesma solucao):\n"
            f"{previous_feedback}\n"
            if previous_feedback else ""
        )

        if title_issues:
            feedback = "; ".join(f"{i.problema} (sugestao: {i.sugestao})" for i in title_issues)
            prompt = (
                f"O titulo atual '{title}' tem este problema: {feedback}\n\n"
                f"{examples}\n"
                f"Contexto da historia: {story_text[:400]}"
                f"{history_block}\n\n"
                f"Gere um titulo NOVO e MELHOR que corrija especificamente esse problema, "
                f"usando os exemplos acima como calibracao de julgamento (nao como regra "
                f"rigida). Retorne APENAS o titulo final, sem explicacoes."
            )
            raw = self._call_groq(
                system_prompt=f"Responda em {language}. Retorne apenas o titulo, nada mais.",
                user_prompt=prompt,
                temperature=temperature,
                max_tokens=100,
                language=language,
            )
            if raw:
                new_title = _strip_colon_subtitle(raw.strip().strip('"').split("\n")[0])

        if hook_issues:
            feedback = "; ".join(f"{i.problema} (sugestao: {i.sugestao})" for i in hook_issues)
            prompt = (
                f"O hook atual '{hook}' tem este problema: {feedback}\n\n"
                f"{examples}\n"
                f"Contexto da historia: {story_text[:400]}"
                f"{history_block}\n\n"
                f"Gere um hook NOVO e MELHOR que corrija especificamente esse problema, "
                f"usando os exemplos acima como calibracao de julgamento (nao como regra "
                f"rigida). Deve funcionar como titulo do YouTube e frase narrada. "
                f"Retorne APENAS o hook final, sem explicacoes."
            )
            raw = self._call_groq(
                system_prompt=f"Responda em {language}. Retorne apenas o hook, nada mais.",
                user_prompt=prompt,
                temperature=temperature,
                max_tokens=100,
                language=language,
            )
            if raw:
                new_hook = _strip_colon_subtitle(raw.strip().strip('"').split("\n")[0])

        return new_title, new_hook

    # ── CORRECAO DE METADADOS ────────────────────────────────────────────────

    def apply_metadata_fix(self, description: str, tags: list, issues: list[Issue],
                           story_text: str, language: str = "pt",
                           previous_feedback: str = "",
                           temperature: float = 0.6) -> tuple[str, list]:
        desc_issues = [i for i in issues if i.trecho.lower() == "description"]
        tags_issues = [i for i in issues if i.trecho.lower() == "tags"]

        new_description = description
        new_tags = tags

        # TIER 1: sugestao da validacao para a descricao ja costuma vir
        # como texto pronto (nao um trecho isolado) — usamos direto quando
        # for utilizavel, sem segunda chamada ao Groq. Tags ficam sempre
        # no Tier 2, pois a sugestao vem como string unica, nao lista.
        remaining_desc_issues = []
        for iss in desc_issues:
            s = (iss.sugestao or "").strip()
            if (
                s and len(s) >= 10 and s.lower() != description.strip().lower()
                and not self._looks_like_instruction(s)
            ):
                new_description = s
            else:
                remaining_desc_issues.append(iss)

        if desc_issues and not remaining_desc_issues:
            logger.info("Descricao corrigida via sugestao direta da validacao (0 tokens extras)")

        desc_issues = remaining_desc_issues

        history_block = (
            f"\n\nTentativa anterior ja tentou algo parecido e o problema persistiu: "
            f"{previous_feedback}\n"
            if previous_feedback else ""
        )

        if desc_issues:
            feedback = "; ".join(f"{i.problema} (sugestao: {i.sugestao})" for i in desc_issues)
            prompt = (
                f"A descricao atual '{description}' tem este problema: {feedback}\n\n"
                f"Contexto da historia: {story_text[:400]}"
                f"{history_block}\n\n"
                f"Gere uma descricao NOVA e MELHOR (1-2 frases, estilo SEO para YouTube) "
                f"que corrija especificamente esse problema. Retorne APENAS a descricao."
            )
            raw = self._call_groq(
                system_prompt=f"Responda em {language}. Retorne apenas a descricao, nada mais.",
                user_prompt=prompt,
                temperature=temperature,
                max_tokens=150,
                language=language,
            )
            if raw:
                new_description = raw.strip().strip('"').split("\n")[0]

        if tags_issues:
            feedback = "; ".join(f"{i.problema} (sugestao: {i.sugestao})" for i in tags_issues)
            prompt = (
                f"As tags atuais '{', '.join(tags)}' tem este problema: {feedback}\n\n"
                f"Contexto da historia: {story_text[:400]}"
                f"{history_block}\n\n"
                f"Gere uma lista de 8-12 tags NOVAS e relevantes, separadas por virgula. "
                f"Retorne APENAS as tags, nada mais."
            )
            raw = self._call_groq(
                system_prompt=f"Responda em {language}. Retorne apenas as tags separadas por virgula.",
                user_prompt=prompt,
                temperature=temperature,
                max_tokens=150,
                language=language,
            )
            if raw:
                new_tags = [t.strip() for t in raw.strip().split(",") if t.strip()]

        return new_description, new_tags

    # ── LOG DE MELHORIAS (JSONL) ─────────────────────────────────────────────

    def log_attempt(self, story_id: str, stage: str, language: str, attempt: int,
                    result: ValidationResult, corrected: bool) -> None:
        """
        Registra cada tentativa de validacao — aprovada ou nao — com o
        detalhe do problema e se foi corrigido. Base para futuramente
        detectar padroes recorrentes de erro e corrigi-los preventivamente.
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "story_id":  story_id,
            "stage":     stage,
            "language":  language,
            "attempt":   attempt,
            "approved":  result.approved,
            "score":     result.score,
            "corrected": corrected,
            "issues": [
                {
                    "trecho":    iss.trecho,
                    "problema":  iss.problema,
                    "sugestao":  iss.sugestao,
                    "categoria": iss.categoria,
                }
                for iss in result.issues
            ],
        }
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("Falha ao escrever improvement_log.jsonl: %s", e)

    # ── ALERTA TELEGRAM ───────────────────────────────────────────────────────

    def send_telegram_alert(self, story_id: str, stage: str, attempt: int,
                            issues: list[Issue], language: str = "?",
                            story_title: str = "") -> None:
        """
        Dispara alerta no bot do Telegram apos multiplas tentativas sem
        aprovar. Usa scheduler.notifier.send_admin_alert (texto simples,
        sem video, para o chat de administracao).

        Inclui idioma, titulo da historia e consumo de tokens acumulado
        ate o momento, para o operador nao precisar abrir o log pra saber
        o contexto completo do alerta.
        """
        problemas = "; ".join(iss.problema for iss in issues[:3])
        title_line = f"Titulo: {story_title[:60]}\n" if story_title else ""
        message = (
            f"⚠️ Validacao insistente\n"
            f"{title_line}"
            f"Historia: {story_id}\n"
            f"Idioma: {language}\n"
            f"Etapa: {stage}\n"
            f"Tentativa: {attempt}\n"
            f"Problemas: {problemas}\n"
            f"Tokens (validador, ate agora): {self.get_token_usage_summary()}"
        )
        try:
            from scheduler.notifier import send_admin_alert
            # send_admin_alert le TELEGRAM_BOT_TOKEN e TELEGRAM_ADMIN_CHAT_ID
            # do ambiente (.env) quando config nao e passado
            ok = send_admin_alert(message)
            if ok:
                logger.info("Alerta Telegram enviado (%s, tentativa %d)", stage, attempt)
            else:
                logger.warning("Alerta Telegram nao enviado (%s, tentativa %d)", stage, attempt)
        except ImportError:
            logger.warning(
                "scheduler.notifier.send_admin_alert nao encontrado — "
                "alerta nao enviado. Mensagem: %s", message,
            )
        except Exception as e:
            logger.warning("Falha ao enviar alerta Telegram: %s", e)

    # ── HELPERS DE RETRY (temperatura + estagnacao) ──────────────────────────

    @staticmethod
    def _next_temperature(attempt: int, base: float, max_temp: float = MAX_TEMPERATURE) -> float:
        """Temperatura sobe a cada tentativa reprovada, ate o teto."""
        return min(max_temp, base + (attempt - 1) * TEMPERATURE_STEP)

    @staticmethod
    def _issues_feedback_summary(issues: list[Issue]) -> str:
        """Resumo compacto dos problemas + sugestoes para dar contexto na proxima tentativa."""
        return "; ".join(f"{i.problema} -> sugerido: {i.sugestao}" for i in issues[:5])

    # ── LOOP DE RETRY GENERICO ────────────────────────────────────────────────

    def validate_and_fix_script(self, script_text: str, language: str,
                                narrator_gender: str, story_id: str,
                                story_title: str = "") -> str:
        """
        Valida o script e aplica correcoes cirurgicas ate aprovar (ou
        atingir o teto de seguranca). Retorna o script final (corrigido
        ou original, se ja estava aprovado).
        """
        current_text = script_text
        attempt = 0
        previous_fixed_text: str | None = None
        previous_feedback = ""
        identical_streak = 0

        # Guarda a melhor versao vista (maior score), nao so a ultima
        # tentativa — evita devolver uma versao pior que o original ou que
        # uma tentativa anterior quando o teto de retries e atingido sem
        # aprovacao (ver caso real: hook final com fato inventado que nao
        # estava em nenhuma versao anterior nem na historia original).
        best_text = script_text
        best_score = -1

        while attempt < MAX_SAFETY_RETRIES:
            attempt += 1
            result = self.validate_script(current_text, language, narrator_gender)

            if result.score > best_score:
                best_score = result.score
                best_text = current_text

            if result.approved:
                self.log_attempt(story_id, "script", language, attempt, result, corrected=False)
                if attempt > 1:
                    logger.info(
                        "Script aprovado apos %d tentativa(s) (%s)", attempt, language,
                    )
                return current_text

            logger.warning(
                "Script reprovado (tentativa %d, score=%d, %d problema(s)): %s",
                attempt, result.score, len(result.issues),
                "; ".join(i.problema for i in result.issues[:3]),
            )

            if attempt >= TELEGRAM_ALERT_AFTER:
                self.send_telegram_alert(
                    story_id, "script", attempt, result.issues,
                    language=language, story_title=story_title,
                )

            temperature = self._next_temperature(attempt, BASE_TEMPERATURE)
            fixed = self.apply_surgical_fix(
                current_text, result.issues, language,
                previous_feedback=previous_feedback,
                temperature=temperature,
            )
            self.log_attempt(story_id, "script", language, attempt, result, corrected=bool(fixed))

            if not fixed:
                # correcao falhou (Groq indisponivel) — mantem texto atual e para
                break

            # Estagnacao real: saida IDENTICA a tentativa anterior, 2x seguidas.
            # (nao "mesma categoria de problema" — isso pode ser so variancia
            # normal do modelo e nao impede progresso nas proximas tentativas)
            if previous_fixed_text is not None and fixed == previous_fixed_text:
                identical_streak += 1
                if identical_streak >= STAGNATION_STREAK_TO_STOP:
                    logger.warning(
                        "Script estagnado (saida identica por %d tentativas seguidas) "
                        "— parando em %d/%d", identical_streak + 1, attempt, MAX_SAFETY_RETRIES,
                    )
                    current_text = fixed
                    break
            else:
                identical_streak = 0

            previous_feedback = self._issues_feedback_summary(result.issues)
            previous_fixed_text = fixed
            current_text = fixed

        if best_text != current_text:
            logger.warning(
                "Script nao aprovado apos %d tentativas — usando a MELHOR versao "
                "vista (score=%d), nao a ultima tentativa (%s)",
                attempt, best_score, language,
            )
        else:
            logger.warning(
                "Script nao aprovado apos %d tentativas — seguindo com a ultima versao (%s)",
                attempt, language,
            )
        return best_text

    def validate_and_fix_title_hook(self, title: str, hook: str, story_text: str,
                                    language: str, story_id: str,
                                    story_title: str = "",
                                    narrator_gender: str = "unknown") -> tuple[str, str]:
        current_title = title
        current_hook  = hook
        attempt = 0
        previous_pair: tuple[str, str] | None = None
        previous_feedback = ""
        identical_streak = 0

        best_title, best_hook = title, hook
        best_score = -1

        while attempt < MAX_SAFETY_RETRIES:
            attempt += 1
            result = self.validate_title_hook(current_title, current_hook, story_text, language,
                                               narrator_gender=narrator_gender)

            if result.score > best_score:
                best_score = result.score
                best_title, best_hook = current_title, current_hook

            if result.approved:
                self.log_attempt(story_id, "title_hook", language, attempt, result, corrected=False)
                if attempt > 1:
                    logger.info("Titulo/hook aprovados apos %d tentativa(s) (%s)", attempt, language)
                return current_title, current_hook

            logger.warning(
                "Titulo/hook reprovados (tentativa %d, score=%d): %s",
                attempt, result.score,
                "; ".join(i.problema for i in result.issues[:3]),
            )

            if attempt >= TELEGRAM_ALERT_AFTER:
                self.send_telegram_alert(
                    story_id, "title_hook", attempt, result.issues,
                    language=language, story_title=story_title,
                )

            temperature = self._next_temperature(attempt, 0.5, max_temp=MAX_TEMPERATURE_SHORT)
            new_title, new_hook = self.apply_title_hook_fix(
                current_title, current_hook, result.issues, story_text, language,
                previous_feedback=previous_feedback,
                temperature=temperature,
            )
            corrected = (new_title != current_title) or (new_hook != current_hook)
            self.log_attempt(story_id, "title_hook", language, attempt, result, corrected=corrected)

            current_pair = (new_title, new_hook)
            if previous_pair is not None and current_pair == previous_pair:
                identical_streak += 1
                if identical_streak >= STAGNATION_STREAK_TO_STOP:
                    logger.warning(
                        "Titulo/hook estagnados (saida identica por %d tentativas "
                        "seguidas) — parando em %d/%d",
                        identical_streak + 1, attempt, MAX_SAFETY_RETRIES,
                    )
                    current_title, current_hook = new_title, new_hook
                    break
            else:
                identical_streak = 0

            previous_feedback = self._issues_feedback_summary(result.issues)
            previous_pair = current_pair
            current_title, current_hook = new_title, new_hook

        if (best_title, best_hook) != (current_title, current_hook):
            logger.warning(
                "Titulo/hook nao aprovados apos %d tentativas — usando a MELHOR "
                "versao vista (score=%d), nao a ultima tentativa (%s)",
                attempt, best_score, language,
            )
        else:
            logger.warning(
                "Titulo/hook nao aprovados apos %d tentativas — seguindo com a ultima versao (%s)",
                attempt, language,
            )
        return best_title, best_hook

    def validate_and_fix_metadata(self, description: str, tags: list, story_text: str,
                                  language: str, story_id: str,
                                  story_title: str = "") -> tuple[str, list]:
        current_desc = description
        current_tags = tags
        attempt = 0
        previous_pair: tuple | None = None
        previous_feedback = ""
        identical_streak = 0

        best_desc, best_tags = description, tags
        best_score = -1

        while attempt < MAX_SAFETY_RETRIES:
            attempt += 1
            result = self.validate_metadata(current_desc, current_tags, story_text, language)

            if result.score > best_score:
                best_score = result.score
                best_desc, best_tags = current_desc, current_tags

            if result.approved:
                self.log_attempt(story_id, "metadata", language, attempt, result, corrected=False)
                if attempt > 1:
                    logger.info("Metadados aprovados apos %d tentativa(s) (%s)", attempt, language)
                return current_desc, current_tags

            logger.warning(
                "Metadados reprovados (tentativa %d, score=%d): %s",
                attempt, result.score,
                "; ".join(i.problema for i in result.issues[:3]),
            )

            if attempt >= TELEGRAM_ALERT_AFTER:
                self.send_telegram_alert(
                    story_id, "metadata", attempt, result.issues,
                    language=language, story_title=story_title,
                )

            temperature = self._next_temperature(attempt, 0.45, max_temp=MAX_TEMPERATURE_SHORT)
            new_desc, new_tags = self.apply_metadata_fix(
                current_desc, current_tags, result.issues, story_text, language,
                previous_feedback=previous_feedback,
                temperature=temperature,
            )
            corrected = (new_desc != current_desc) or (new_tags != current_tags)
            self.log_attempt(story_id, "metadata", language, attempt, result, corrected=corrected)

            current_pair = (new_desc, tuple(new_tags) if isinstance(new_tags, list) else new_tags)
            if previous_pair is not None and current_pair == previous_pair:
                identical_streak += 1
                if identical_streak >= STAGNATION_STREAK_TO_STOP:
                    logger.warning(
                        "Metadados estagnados (saida identica por %d tentativas "
                        "seguidas) — parando em %d/%d",
                        identical_streak + 1, attempt, MAX_SAFETY_RETRIES,
                    )
                    current_desc, current_tags = new_desc, new_tags
                    break
            else:
                identical_streak = 0

            previous_feedback = self._issues_feedback_summary(result.issues)
            previous_pair = current_pair
            current_desc, current_tags = new_desc, new_tags

        if (best_desc, best_tags) != (current_desc, current_tags):
            logger.warning(
                "Metadados nao aprovados apos %d tentativas — usando a MELHOR "
                "versao vista (score=%d), nao a ultima tentativa (%s)",
                attempt, best_score, language,
            )
        else:
            logger.warning(
                "Metadados nao aprovados apos %d tentativas — seguindo com a ultima versao (%s)",
                attempt, language,
            )
        return best_desc, best_tags