"""
titler.py
=========
Gera titulos virais para YouTube Shorts, TikTok e Instagram Reels.

Três tipos de saída:
    generate()             — título descritivo para slug do arquivo
    generate_hook()         — hook de engajamento para narração E título YouTube/TikTok
    generate_closing_hook() — hook de encerramento (CTA) para o fim do video/ultima parte

Providers (em ordem de tentativa):
    1. Groq API  — titulo otimizado com contexto completo da historia
    2. Ollama    — fallback com prompt simplificado
    3. Regras    — extracao basica como fallback final
"""

from __future__ import annotations
import logging
import os
import random
import re

logger = logging.getLogger(__name__)


# ── PROMPTS DE TÍTULO DESCRITIVO ──────────────────────────────────────────────

TITLE_PROMPTS = {
    "pt": (
        "Você é especialista em títulos virais para YouTube Shorts e TikTok.\n\n"
        "OBJETIVO:\n"
        "Gerar um título extremamente clicável que faça o espectador sentir curiosidade imediata.\n"
        "O título deve parecer um conflito, dilema ou experiência real e pessoal.\n\n"
        "CONTEXTO DA HISTÓRIA:\n"
        "TÍTULO ORIGINAL:\n"
        "{original_title}\n\n"
        "RESUMO DA HISTÓRIA:\n"
        "{story_text}\n\n"
        "TAREFA:\n"
        "Gere 3-5 opções de títulos virais.\n"
        "Depois escolha o melhor baseado em: curiosidade, impacto emocional, clareza, qualidade da frase.\n"
        "Retorne apenas o melhor título.\n\n"
        "PRINCÍPIOS DE CONSTRUÇÃO:\n"
        "- Identifique o CONFLITO CENTRAL da história (moral, emocional, social, sobrenatural)\n"
        "- Identifique a EMOÇÃO PRIMÁRIA (medo, raiva, dúvida, espanto, injustiça)\n"
        "- Construa o título que melhor capture esse conflito + emoção\n"
        "- O título deve fazer o espectador perguntar: 'Qual é a história? Preciso saber.'\n\n"
        "EXEMPLOS DE TÍTULOS RUINS vs BONS:\n"
        "❌ RUIM: 'Minha irmã me ofendeu e agora quer emprestado'\n"
        "✅ BOM:  'Minha irmã me humilhou no jantar e ainda quer dinheiro emprestado'\n"
        "❌ RUIM: 'Recusei ajudar minha família e paguei o preço'\n"
        "✅ BOM:  'Recusei emprestar dinheiro pra minha irmã depois que ela me humilhou'\n"
        "❌ RUIM: 'Meu cunhado foi longe demais'\n"
        "✅ BOM:  'Expulsei meu cunhado de casa depois do que ele fez'\n\n"
        "REGRAS OBRIGATÓRIAS:\n"
        "- NÃO usar siglas de subreddit (AITA, TIFU etc)\n"
        "- NÃO inventar fatos que não aparecem na história\n"
        "- Sem aspas, reticências ou emojis\n"
        "- Sem explicações ou numerações\n"
        "- O título deve ser uma frase COMPLETA e gramaticalmente correta\n"
        "- NUNCA use construções vagas ou incompletas\n"
        "- Sempre especifique O QUÊ aconteceu\n"
        "- Leia o título em voz alta — se soar estranho ou incompleto, reescreva\n\n"
        "ESTILO:\n"
        "- Linguagem natural e falada — como alguém contaria para um amigo\n"
        "- Emocional mas não dramática\n"
        "- Direta, clara e completa\n\n"
    ),
    "en": (
        "You are a viral title specialist for YouTube Shorts and TikTok.\n\n"
        "GOAL:\n"
        "Generate an extremely clickable title that creates immediate curiosity.\n"
        "The title must feel like a real personal conflict, dilemma or experience.\n\n"
        "STORY CONTEXT:\n"
        "ORIGINAL TITLE:\n"
        "{original_title}\n\n"
        "STORY SUMMARY:\n"
        "{story_text}\n\n"
        "TASK:\n"
        "Generate 3-5 viral title options.\n"
        "Then choose the best based on: curiosity, emotional impact, clarity, sentence quality.\n"
        "Return only the best title.\n\n"
        "CONSTRUCTION PRINCIPLES:\n"
        "- Identify the CENTRAL CONFLICT (moral, emotional, social, supernatural)\n"
        "- Identify the PRIMARY EMOTION (fear, anger, doubt, shock, injustice)\n"
        "- Build the title that best captures that conflict + emotion\n\n"
        "EXAMPLES OF BAD vs GOOD TITLES:\n"
        "❌ BAD:  'My sister insulted me and now wants to borrow'\n"
        "✅ GOOD: 'My sister humiliated me at dinner and still wants to borrow money'\n"
        "❌ BAD:  'I refused to help my family and paid the price'\n"
        "✅ GOOD: 'I refused to lend money to my sister after she humiliated me'\n"
        "❌ BAD:  'My brother-in-law went too far'\n"
        "✅ GOOD: 'I kicked my brother-in-law out after what he did'\n\n"
        "MANDATORY RULES:\n"
        "- NO subreddit acronyms (AITA, TIFU etc)\n"
        "- NO invented facts not in the story\n"
        "- No quotes, ellipsis or emojis\n"
        "- No explanations or numbering\n"
        "- The title must be a COMPLETE and grammatically correct sentence\n"
        "- NEVER use vague or incomplete constructions\n"
        "- Always specify WHAT happened\n"
        "- Read the title out loud — if it sounds strange or incomplete, rewrite it\n\n"
        "STYLE:\n"
        "- Natural spoken language — like someone telling a friend\n"
        "- Emotional but not dramatic\n"
        "- Direct, clear and complete\n\n"
    ),
    "es": (
        "Eres especialista en títulos virales para YouTube Shorts y TikTok.\n\n"
        "OBJETIVO:\n"
        "Generar un título extremadamente clicable que cause curiosidad inmediata.\n"
        "El título debe parecer un conflicto, dilema o experiencia real y personal.\n\n"
        "CONTEXTO DE LA HISTORIA:\n"
        "TÍTULO ORIGINAL:\n"
        "{original_title}\n\n"
        "RESUMEN DE LA HISTORIA:\n"
        "{story_text}\n\n"
        "TAREA:\n"
        "Genera 3-5 opciones de títulos virales.\n"
        "Luego elige el mejor basado en: curiosidad, impacto emocional, claridad, calidad de la frase.\n"
        "Devuelve solo el mejor título.\n\n"
        "PRINCIPIOS DE CONSTRUCCIÓN:\n"
        "- Identifica el CONFLICTO CENTRAL (moral, emocional, social, sobrenatural)\n"
        "- Identifica la EMOCIÓN PRIMARIA (miedo, rabia, duda, asombro, injusticia)\n"
        "- Construye el título que mejor capture ese conflicto + emoción\n\n"
        "EJEMPLOS DE TÍTULOS MALOS vs BUENOS:\n"
        "❌ MALO: 'Mi hermana me insultó y ahora quiere prestado'\n"
        "✅ BUENO: 'Mi hermana me humilló en la cena y encima quiere dinero prestado'\n"
        "❌ MALO: 'Me negué a ayudar a mi familia y pagué las consecuencias'\n"
        "✅ BUENO: 'Me negué a prestarle dinero a mi hermana después de que me humilló'\n\n"
        "REGLAS OBLIGATORIAS:\n"
        "- NO usar siglas de subreddit (AITA, TIFU etc)\n"
        "- NO inventar hechos que no aparecen en la historia\n"
        "- Sin comillas, puntos suspensivos o emojis\n"
        "- Sin explicaciones o numeraciones\n"
        "- El título debe ser una frase COMPLETA y gramaticalmente correcta\n"
        "- NUNCA uses construcciones vagas o incompletas\n"
        "- Siempre especifica QUÉ pasó\n\n"
        "ESTILO:\n"
        "- Lenguaje natural y hablado — como alguien contándoselo a un amigo\n"
        "- Emocional pero no dramático\n"
        "- Directo, claro y completo\n\n"
    ),
}


# ── PROMPTS DE HOOK DE ENGAJAMENTO ────────────────────────────────────────────

HOOK_PROMPTS = {
    "pt": (
        "Você é especialista em hooks de abertura para vídeos virais do Reddit no YouTube e TikTok.\n\n"
        "CONTEXTO DA HISTÓRIA:\n"
        "TÍTULO ORIGINAL:\n"
        "{original_title}\n\n"
        "RESUMO DA HISTÓRIA:\n"
        "{story_text}\n\n"
        "OBJETIVO:\n"
        "Criar uma frase de abertura que prende o espectador nos primeiros 3 segundos.\n"
        "Essa frase será narrada em voz alta no início do vídeo E será o título no YouTube/TikTok.\n\n"
        "TIPOS DE HOOK (escolha o mais adequado para a história):\n"
        "- Confissão moral: 'Fui babaca por recusar emprestar dinheiro pra minha irmã depois que ela me humilhou?'\n"
        "- Dilema em primeira pessoa: 'Estou errada em não querer ajudar minha irmã depois do que ela fez?'\n"
        "- Revelação chocante: 'Virei a vilã da família só porque me recusei a bancar minha irmã.'\n"
        "- Pergunta para o espectador: 'Já tiveram que escolher entre família e autorespeito?'\n"
        "- Experiência extrema: 'Minha irmã me humilhou na frente de todos e ainda achou que ia pedir dinheiro.'\n"
        "- Chamada de identificação: 'Pessoas que já foram tratadas como a mais forte da família, isso é pra vocês.'\n\n"
        "EXEMPLOS REAIS DO ESTILO DESEJADO:\n"
        "✅ 'Fui babaca por recusar emprestar dinheiro pra minha irmã depois que ela me humilhou?'\n"
        "✅ 'Estou errada em não querer ajudar minha irmã depois do que ela fez comigo?'\n"
        "✅ 'Virei a vilã da família depois que me recusei a bancar o estilo de vida do meu irmão.'\n"
        "✅ 'O que fez minha avó de 79 anos perder a paciência na frente de toda a família.'\n"
        "✅ 'Pessoas que já tiveram problemas com os pais — o que aprenderam com isso?'\n"
        "✅ 'Eu tinha 28 anos, trabalhava como enfermeira, e minha irmã ainda achava que eu devia dinheiro a ela.'\n\n"
        "CLAREZA SEM AMBIGUIDADE:\n"
        "Algumas palavras têm mais de um sentido em português (ex: 'caso' pode ser processo "
        "judicial ou caso amoroso). Antes de finalizar, leia o hook como se não conhecesse a "
        "história: dá pra entender o conflito real sem depender de contexto externo? Se "
        "alguma palavra ou referência puder ser mal-interpretada, reescreva nomeando o "
        "conflito de forma direta — sem inventar detalhes que não estão na história. Não "
        "existe uma frase-modelo pra isso; cada história pede uma solução diferente.\n\n"
        "REGRAS OBRIGATÓRIAS:\n"
        "- Máximo 120 caracteres\n"
        "- NÃO usar siglas de subreddit (AITA, TIFU etc)\n"
        "- NÃO inventar fatos que não estão na história\n"
        "- Sem aspas, sem reticências, sem emojis\n"
        "- Se o hook for uma PERGUNTA, OBRIGATORIAMENTE termine com ?\n"
        "- Exemplos de pergunta correta: 'Fui babaca por recusar emprestar dinheiro pra minha irmã?'\n"
        "- Deve funcionar como título do YouTube E como frase narrada\n"
        "- Deve soar natural quando lido em voz alta\n"
        "- Frase COMPLETA e gramaticalmente correta\n\n"
        "ESTILO:\n"
        "- Tom direto, humano, como alguém falando com o espectador\n"
        "- Pode ser pergunta, confissão ou declaração forte\n"
        "- Linguagem simples e coloquial\n\n"
        "Retorne APENAS o hook final. Sem explicações.\n"
    ),
    "en": (
        "You are a specialist in opening hooks for viral Reddit videos on YouTube and TikTok.\n\n"
        "STORY CONTEXT:\n"
        "ORIGINAL TITLE:\n"
        "{original_title}\n\n"
        "STORY SUMMARY:\n"
        "{story_text}\n\n"
        "GOAL:\n"
        "Create an opening line that hooks the viewer in the first 3 seconds.\n"
        "This line will be narrated at the start of the video AND will be the YouTube/TikTok title.\n\n"
        "HOOK TYPES (choose the most fitting for the story):\n"
        "- Moral confession: 'Was I wrong for refusing to lend money to my sister after she humiliated me?'\n"
        "- First-person dilemma: 'Am I a bad person for cutting off my family after what they did?'\n"
        "- Shocking reveal: 'I became the villain of my family just for setting a boundary.'\n"
        "- Viewer question: 'Have you ever had to choose between family and self-respect?'\n"
        "- Extreme experience: 'My sister humiliated me in front of everyone and still thought she could ask for money.'\n"
        "- Identification call: 'People who were always called the strong one in the family — this is for you.'\n\n"
        "REAL EXAMPLES OF THE DESIRED STYLE:\n"
        "✅ 'Was I wrong for refusing to lend money to my sister after she humiliated me?'\n"
        "✅ 'Am I the bad guy for not helping my sister after everything she put me through?'\n"
        "✅ 'I became the family villain after I refused to fund my brother's lifestyle.'\n"
        "✅ 'What made my 79-year-old grandmother lose her patience in front of the whole family.'\n"
        "✅ 'People who had to cut off their parents — what did you learn from it?'\n\n"
        "MANDATORY RULES:\n"
        "- Maximum 120 characters\n"
        "- NO subreddit acronyms (AITA, TIFU etc)\n"
        "- NO invented facts not in the story\n"
        "- No quotes, ellipsis or emojis\n"
        "- If the hook is a QUESTION, it MUST end with ?\n"
        "- Example of correct question: 'Was I wrong for refusing to lend money to my sister?'\n"
        "- Must work as a YouTube title AND as a narrated line\n"
        "- Must sound natural when read aloud\n"
        "- COMPLETE and grammatically correct sentence\n\n"
        "STYLE:\n"
        "- Direct, human tone — like someone talking to the viewer\n"
        "- Can be a question, confession or strong statement\n"
        "- Simple, conversational language\n\n"
        "Return ONLY the final hook. No explanations.\n"
    ),
    "es": (
        "Eres especialista en hooks de apertura para videos virales de Reddit en YouTube y TikTok.\n\n"
        "CONTEXTO DE LA HISTORIA:\n"
        "TÍTULO ORIGINAL:\n"
        "{original_title}\n\n"
        "RESUMEN DE LA HISTORIA:\n"
        "{story_text}\n\n"
        "OBJETIVO:\n"
        "Crear una frase de apertura que enganche al espectador en los primeros 3 segundos.\n"
        "Esta frase será narrada al inicio del video Y será el título en YouTube/TikTok.\n\n"
        "TIPOS DE HOOK (elige el más adecuado para la historia):\n"
        "- Confesión moral: '¿Estuve mal por negarme a prestarle dinero a mi hermana después de que me humilló?'\n"
        "- Dilema en primera persona: '¿Soy mala persona por no querer ayudar a mi hermana después de lo que hizo?'\n"
        "- Revelación impactante: 'Me convertí en la villana de la familia solo por poner un límite.'\n"
        "- Pregunta al espectador: '¿Alguna vez tuvieron que elegir entre familia y autorespeto?'\n"
        "- Experiencia extrema: 'Mi hermana me humilló delante de todos y aun así esperaba que le prestara dinero.'\n\n"
        "EJEMPLOS REALES DEL ESTILO DESEADO:\n"
        "✅ '¿Estuve mal por negarme a prestarle dinero a mi hermana después de que me humilló?'\n"
        "✅ '¿Soy la mala de la historia por no ayudar a mi hermana después de todo lo que me hizo?'\n"
        "✅ 'Me volví la villana de la familia después de negarme a financiar el estilo de vida de mi hermano.'\n"
        "✅ 'Lo que hizo que mi abuela de 79 años perdiera la paciencia delante de toda la familia.'\n\n"
        "CLARIDAD SIN AMBIGÜEDAD:\n"
        "Algunas palabras tienen mas de un significado en español (ej: 'caso' puede sonar a "
        "proceso judicial). Antes de terminar, lee el hook como si no conocieras la historia: "
        "¿se entiende el conflicto real sin depender de contexto externo? Si alguna palabra o "
        "referencia puede malinterpretarse, reescribe nombrando el conflicto de forma directa "
        "— sin inventar detalles que no esten en la historia. No hay una frase-modelo fija; "
        "cada historia pide una solucion distinta.\n\n"
        "REGLAS OBLIGATORIAS:\n"
        "- Máximo 120 caracteres\n"
        "- NO usar siglas de subreddit (AITA, TIFU etc)\n"
        "- NO inventar hechos que no están en la historia\n"
        "- Sin comillas, sin puntos suspensivos, sin emojis\n"
        "- Si el hook es una PREGUNTA, OBLIGATORIAMENTE debe terminar con ?\n"
        "- Ejemplo de pregunta correcta: '¿Estuve mal por negarme a prestarle dinero a mi hermana?'\n"
        "- Debe funcionar como título de YouTube Y como frase narrada\n"
        "- Debe sonar natural al leerse en voz alta\n"
        "- Frase COMPLETA y gramaticalmente correcta\n\n"
        "ESTILO:\n"
        "- Tono directo y humano — como alguien hablando con el espectador\n"
        "- Puede ser pregunta, confesión o declaración fuerte\n"
        "- Lenguaje simple y coloquial\n\n"
        "Devuelve SOLO el hook final. Sin explicaciones.\n"
    ),
}


# ── PROMPTS DE HOOK DE ENCERRAMENTO (CTA) ─────────────────────────────────────

CLOSING_HOOK_PROMPTS = {
    "pt": (
        "Você é especialista em encerramentos (call-to-action) para vídeos virais do Reddit "
        "no YouTube e TikTok.\n\n"
        "CONTEXTO DA HISTÓRIA:\n"
        "TÍTULO ORIGINAL:\n"
        "{original_title}\n\n"
        "RESUMO DA HISTÓRIA:\n"
        "{story_text}\n\n"
        "OBJETIVO:\n"
        "Criar uma frase de ENCERRAMENTO que sera narrada no final do video, logo apos o "
        "desfecho da historia. Essa frase deve convidar o espectador a comentar, dar sua "
        "opiniao ou dizer o que faria no lugar do narrador. Sera a ultima coisa dita no video.\n\n"
        "TIPOS DE ENCERRAMENTO (escolha o mais adequado):\n"
        "- Pergunta direta de opiniao: 'E você, acha que eu fui longe demais? Comenta aí embaixo.'\n"
        "- Convite para se colocar no lugar: 'O que você teria feito no meu lugar? Quero saber.'\n"
        "- Pergunta de julgamento: 'Vocês acham que eu fui a errada nessa historia? Deixa nos comentarios.'\n"
        "- Convite para compartilhar experiencia: 'Ja passaram por algo parecido? Contem pra mim.'\n\n"
        "EXEMPLOS REAIS DO ESTILO DESEJADO:\n"
        "✅ 'E você, acha que eu fui babaca por recusar o dinheiro? Comenta aí embaixo.'\n"
        "✅ 'O que você teria feito no meu lugar? Deixa sua opiniao nos comentarios.'\n"
        "✅ 'Vocês acham que eu fui longe demais com meu cunhado? Quero saber a opiniao de voces.'\n\n"
        "REGRAS OBRIGATÓRIAS:\n"
        "- Máximo 140 caracteres\n"
        "- Deve claramente pedir que o espectador comente ou de sua opiniao\n"
        "- NÃO usar siglas de subreddit (AITA, TIFU etc)\n"
        "- NÃO inventar fatos que não estão na história\n"
        "- Sem aspas, sem reticências, sem emojis\n"
        "- Deve soar natural quando lido em voz alta, como um convite genuino\n"
        "- Frase COMPLETA e gramaticalmente correta\n"
        "- Conecte com o dilema especifico da historia, nao seja generico demais\n\n"
        "ESTILO:\n"
        "- Tom direto, caloroso, como alguém conversando com o espectador\n"
        "- Sempre termina convidando para comentar\n"
        "- Linguagem simples e coloquial\n\n"
        "Retorne APENAS o encerramento final. Sem explicações.\n"
    ),
    "en": (
        "You are a specialist in closing call-to-actions for viral Reddit videos on YouTube and TikTok.\n\n"
        "STORY CONTEXT:\n"
        "ORIGINAL TITLE:\n"
        "{original_title}\n\n"
        "STORY SUMMARY:\n"
        "{story_text}\n\n"
        "GOAL:\n"
        "Create a CLOSING line that will be narrated at the very end of the video, right after "
        "the story's resolution. This line must invite the viewer to comment, share their "
        "opinion, or say what they would have done in the narrator's place. It is the last "
        "thing said in the video.\n\n"
        "CLOSING TYPES (choose the most fitting):\n"
        "- Direct opinion question: 'So, do you think I went too far? Let me know in the comments.'\n"
        "- Put-yourself-in-my-shoes: 'What would you have done in my place? I want to know.'\n"
        "- Judgment question: 'Do you think I was wrong here? Drop your thoughts below.'\n"
        "- Share experience invite: 'Has something like this happened to you? Tell me about it.'\n\n"
        "REAL EXAMPLES OF THE DESIRED STYLE:\n"
        "✅ 'So, do you think I was wrong for refusing the money? Let me know in the comments.'\n"
        "✅ 'What would you have done in my place? Drop your opinion below.'\n"
        "✅ 'Do you think I went too far with my brother-in-law? I want to hear your take.'\n\n"
        "MANDATORY RULES:\n"
        "- Maximum 140 characters\n"
        "- Must clearly ask the viewer to comment or share their opinion\n"
        "- NO subreddit acronyms (AITA, TIFU etc)\n"
        "- NO invented facts not in the story\n"
        "- No quotes, ellipsis or emojis\n"
        "- Must sound natural when read aloud, like a genuine invitation\n"
        "- COMPLETE and grammatically correct sentence\n"
        "- Tie it to the story's specific dilemma, don't be too generic\n\n"
        "STYLE:\n"
        "- Direct, warm tone — like someone talking to the viewer\n"
        "- Always ends by inviting a comment\n"
        "- Simple, conversational language\n\n"
        "Return ONLY the final closing line. No explanations.\n"
    ),
    "es": (
        "Eres especialista en cierres (call-to-action) para videos virales de Reddit en YouTube y TikTok.\n\n"
        "CONTEXTO DE LA HISTORIA:\n"
        "TÍTULO ORIGINAL:\n"
        "{original_title}\n\n"
        "RESUMEN DE LA HISTORIA:\n"
        "{story_text}\n\n"
        "OBJETIVO:\n"
        "Crear una frase de CIERRE que sera narrada al final del video, justo despues del "
        "desenlace de la historia. Esta frase debe invitar al espectador a comentar, dar su "
        "opinion o decir que habria hecho en el lugar del narrador. Sera lo ultimo dicho en el video.\n\n"
        "TIPOS DE CIERRE (elige el mas adecuado):\n"
        "- Pregunta directa de opinion: '¿Y tú, crees que me pase de la raya? Comenta abajo.'\n"
        "- Ponerse en mi lugar: '¿Que habrias hecho en mi lugar? Quiero saber.'\n"
        "- Pregunta de juicio: '¿Creen que estuve mal en esta historia? Dejenme su opinion.'\n"
        "- Invitacion a compartir experiencia: '¿Les paso algo parecido? Cuentenme.'\n\n"
        "EJEMPLOS REALES DEL ESTILO DESEADO:\n"
        "✅ '¿Y tú, crees que estuve mal por negarme a prestar el dinero? Comenta abajo.'\n"
        "✅ '¿Que habrias hecho en mi lugar? Deja tu opinion en los comentarios.'\n"
        "✅ '¿Creen que me pase con mi cuñado? Quiero saber que opinan ustedes.'\n\n"
        "REGLAS OBLIGATORIAS:\n"
        "- Máximo 140 caracteres\n"
        "- Debe pedir claramente que el espectador comente o de su opinion\n"
        "- NO usar siglas de subreddit (AITA, TIFU etc)\n"
        "- NO inventar hechos que no están en la historia\n"
        "- Sin comillas, sin puntos suspensivos, sin emojis\n"
        "- Debe sonar natural al leerse en voz alta, como una invitacion genuina\n"
        "- Frase COMPLETA y gramaticalmente correcta\n"
        "- Conectala con el dilema especifico de la historia, no seas generico\n\n"
        "ESTILO:\n"
        "- Tono directo y calido — como alguien hablando con el espectador\n"
        "- Siempre termina invitando a comentar\n"
        "- Lenguaje simple y coloquial\n\n"
        "Devuelve SOLO el cierre final. Sin explicaciones.\n"
    ),
}


# ── SYSTEM PROMPTS ────────────────────────────────────────────────────────────

SYSTEM_PROMPTS = {
    "pt": (
        "Você é especialista em títulos virais para YouTube e TikTok. "
        "Retorne APENAS o título final escolhido. "
        "O título deve ser uma frase completa, natural e gramaticalmente correta em português do Brasil. "
        "Sem aspas, sem reticências, sem exclamação, sem numeração, sem explicações. "
        "RESPONDA SEMPRE EM PORTUGUÊS DO BRASIL."
    ),
    "en": (
        "You are a viral title specialist for YouTube and TikTok. "
        "Return ONLY the final chosen title. "
        "The title must be a complete, natural and grammatically correct sentence in English. "
        "No quotes, no ellipsis, no exclamation marks, no numbering, no explanations. "
        "ALWAYS RESPOND IN ENGLISH."
    ),
    "es": (
        "Eres especialista en títulos virales para YouTube y TikTok. "
        "Devuelve SOLO el título final elegido. "
        "El título debe ser una frase completa, natural y gramaticalmente correcta en español. "
        "Sin comillas, sin puntos suspensivos, sin exclamación, sin numeración, sin explicaciones. "
        "RESPONDE SIEMPRE EN ESPAÑOL."
    ),
}

SYSTEM_PROMPTS_HOOK = {
    "pt": (
        "Você é especialista em hooks de abertura para vídeos virais. "
        "Retorne APENAS o hook final. "
        "Deve ser uma frase completa, natural e coloquial em português do Brasil. "
        "Perguntas DEVEM terminar com ponto de interrogação. "
        "Sem aspas, sem reticências, sem numeração, sem explicações. "
        "RESPONDA SEMPRE EM PORTUGUÊS DO BRASIL."
    ),
    "en": (
        "You are a specialist in opening hooks for viral videos. "
        "Return ONLY the final hook. "
        "Must be a complete, natural and conversational sentence in English. "
        "Questions MUST end with a question mark. "
        "No quotes, no ellipsis, no numbering, no explanations. "
        "ALWAYS RESPOND IN ENGLISH."
    ),
    "es": (
        "Eres especialista en hooks de apertura para videos virales. "
        "Devuelve SOLO el hook final. "
        "Debe ser una frase completa, natural y coloquial en español. "
        "Las preguntas DEBEN terminar con signo de interrogación. "
        "Sin comillas, sin puntos suspensivos, sin numeración, sin explicaciones. "
        "RESPONDE SIEMPRE EN ESPAÑOL."
    ),
}

SYSTEM_PROMPTS_CLOSING = {
    "pt": (
        "Você é especialista em encerramentos (call-to-action) para vídeos virais. "
        "Retorne APENAS o encerramento final. "
        "Deve ser uma frase completa, natural e coloquial em português do Brasil que "
        "convide o espectador a comentar ou dar sua opiniao. "
        "Sem aspas, sem reticências, sem numeração, sem explicações. "
        "RESPONDA SEMPRE EM PORTUGUÊS DO BRASIL."
    ),
    "en": (
        "You are a specialist in closing call-to-actions for viral videos. "
        "Return ONLY the final closing line. "
        "Must be a complete, natural and conversational sentence in English that invites "
        "the viewer to comment or share their opinion. "
        "No quotes, no ellipsis, no numbering, no explanations. "
        "ALWAYS RESPOND IN ENGLISH."
    ),
    "es": (
        "Eres especialista en cierres (call-to-action) para videos virales. "
        "Devuelve SOLO el cierre final. "
        "Debe ser una frase completa, natural y coloquial en español que invite "
        "al espectador a comentar o dar su opinion. "
        "Sin comillas, sin puntos suspensivos, sin numeración, sin explicaciones. "
        "RESPONDE SIEMPRE EN ESPAÑOL."
    ),
}

SUBREDDIT_PREFIXES = re.compile(
    r"^(AITA|AITAH|TIFU|WIBTA|UPDATE|OC|TIL|CMV|ELI5)[:\s\-–|]+",
    flags=re.IGNORECASE,
)


class TitleGenerator:

    def __init__(self, config: dict = None):
        self.config       = config or {}
        self.groq_key     = os.environ.get("GROQ_API_KEY", "") or self.config.get("groq_api_key", "")
        self.groq_model   = self.config.get("groq_model", "openai/gpt-oss-120b")
        self.ollama_url   = self.config.get("ollama_url", "http://localhost:11434/api/generate")
        self.ollama_model = self.config.get("ollama_model", "llama3.2")
        self.enabled      = self.config.get("enabled", True)

    # ── TÍTULO DESCRITIVO (para slug do arquivo) ──────────────────────────────

    def generate(self, story_text: str, language: str = "pt",
                 original_title: str = "", hook_type: str = None) -> str:
        """Gera título descritivo — usado apenas para nomear o arquivo."""
        if not self.enabled:
            return self._rule_based_title(original_title)

        if hook_type is None:
            hook_type = random.choice(["short", "narrative"])

        logger.info("Gerando titulo descritivo (%s, tipo=%s)", language, hook_type)

        story_summary = story_text[:400].replace("\n", " ").strip()
        result = self._groq_title(original_title, story_summary, language, hook_type)
        if result:
            return result
        result = self._ollama_title(original_title, story_summary, language, hook_type)
        if result:
            return result
        from utils import telemetry
        telemetry.record_fallback("titler.titulo", language, "todos os LLMs falharam")
        logger.warning("Todos LLMs falharam para titulo — usando regras")
        return self._rule_based_title(original_title)

    # ── HOOK DE ENGAJAMENTO (para YouTube/TikTok E narração) ─────────────────

    def generate_hook(self, story_text: str, language: str = "pt",
                      original_title: str = "") -> str:
        """
        Gera hook de engajamento para abertura do vídeo.
        Essa frase é narrada no início E usada como título no YouTube/TikTok.
        """
        if not self.enabled:
            return self._rule_based_title(original_title)

        logger.info("Gerando hook de engajamento (%s)", language)

        story_summary = story_text[:400].replace("\n", " ").strip()
        result = self._groq_hook(original_title, story_summary, language)
        if result:
            return result
        result = self._ollama_hook(original_title, story_summary, language)
        if result:
            return result
        from utils import telemetry
        telemetry.record_fallback("titler.hook", language, "todos os LLMs falharam")
        logger.warning("Todos LLMs falharam para hook — usando titulo como fallback")
        return self._rule_based_title(original_title)

    # ── HOOK DE ENCERRAMENTO (CTA para o fim do video / ultima parte) ────────

    def generate_closing_hook(self, story_text: str, language: str = "pt",
                              original_title: str = "") -> str:
        """
        Gera o hook de encerramento (call-to-action) narrado no final do video.
        Usado apenas na ultima parte de uma historia dividida, ou na unica parte
        quando a historia nao precisa de divisao.
        """
        if not self.enabled:
            return self._rule_based_closing(language)

        logger.info("Gerando hook de encerramento (%s)", language)

        story_summary = story_text[:400].replace("\n", " ").strip()
        result = self._groq_closing(original_title, story_summary, language)
        if result:
            return result
        result = self._ollama_closing(original_title, story_summary, language)
        if result:
            return result
        from utils import telemetry
        telemetry.record_fallback("titler.encerramento", language, "todos os LLMs falharam")
        logger.warning("Todos LLMs falharam para encerramento — usando fallback fixo")
        return self._rule_based_closing(language)

    # ── LIMPEZA ───────────────────────────────────────────────────────────────

    def _clean_title(self, title: str, max_len: int = 120, is_hook: bool = False) -> str:
        title = re.sub(r'^["\'`]|["\'`]$', "", title).strip()
        title = re.sub(r"^t[íi]tulo:\s*", "", title, flags=re.IGNORECASE).strip()
        title = re.sub(r"^hook:\s*",       "", title, flags=re.IGNORECASE).strip()
        title = re.sub(r"^encerramento:\s*", "", title, flags=re.IGNORECASE).strip()
        title = re.sub(r"^closing:\s*",     "", title, flags=re.IGNORECASE).strip()
        title = re.sub(r"^cierre:\s*",      "", title, flags=re.IGNORECASE).strip()
        title = re.sub(r"\.{2,}$",         "", title).strip()
        title = re.sub(r"!+$",             "", title).strip()
        title = re.sub(r"^\d+[\.\)]\s*",   "", title).strip()
        title = title.split("\n")[0].strip()

        # Nunca deixar passar estrutura "frase: subtitulo" — deve ser UMA frase.
        # O modelo insiste nesse formato mesmo com regra no prompt, entao aqui
        # e uma trava deterministica: corta tudo a partir do primeiro ':'.
        if ":" in title:
            title = title.split(":", 1)[0].strip()

        # Para hooks: garantir que perguntas terminam com ?
        if is_hook:
            title = self._ensure_question_mark(title)

        if len(title) > max_len:
            title = title[:max_len - 3]

        return title

    def _ensure_question_mark(self, text: str) -> str:
        """
        Se o texto parece uma pergunta mas não tem ?, adiciona.
        Detecta padrões de pergunta em PT, EN e ES.
        """
        question_starters_pt = [
            "fui ", "estou ", "estava ", "sou ", "era ", "seria ",
            "devo ", "devia ", "posso ", "podia ", "vale ", "é certo ",
            "fiz certo ", "fiz errado ", "errei ", "estaria ",
        ]
        question_starters_en = [
            "was i ", "am i ", "is it ", "did i ", "should i ",
            "would i ", "could i ", "have i ", "are they ", "were they ",
        ]
        question_starters_es = [
            "estuve ", "estoy ", "soy ", "era ", "fui ", "debo ",
            "debería ", "puedo ", "podría ", "¿", "vale ",
        ]

        text_lower = text.lower().strip()
        all_starters = question_starters_pt + question_starters_en + question_starters_es

        is_question = any(text_lower.startswith(s) for s in all_starters)

        if is_question and not text.endswith("?"):
            text = text.rstrip(".") + "?"

        return text

    # ── GROQ — TÍTULO ─────────────────────────────────────────────────────────

    def _groq_title(self, original_title: str, story_summary: str,
                    language: str, hook_type: str = "short") -> str | None:
        from utils import environment as env
        groq_key = env.groq_api_key(language) or self.groq_key
        if not groq_key:
            return None
        try:
            from utils.groq_client import tracked_groq
            client = tracked_groq(groq_key, "titler")

            base_prompt = TITLE_PROMPTS.get(language, TITLE_PROMPTS["en"]).format(
                original_title=original_title,
                story_text=story_summary,
            )
            type_instruction = self._build_type_instruction(hook_type, language)
            prompt = base_prompt + "\n" + type_instruction

            resp = client.chat.completions.create(
                model=self.groq_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPTS.get(language, SYSTEM_PROMPTS["en"])},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.85,
                # 400 e nao 150: os modelos gpt-oss gastam parte do orcamento
                # "pensando" antes de escrever. Com 150 o raciocinio consumia
                # tudo, o conteudo voltava vazio e o titulo caia para regras
                # (visto em producao: titulo cortado "por interromper...").
                max_tokens=400,
            )
            title = self._clean_title(resp.choices[0].message.content.strip())
            if title and len(title) > 3:
                logger.info("Titulo gerado via Groq (%s, tipo=%s): %s", language, hook_type, title)
                return title
        except Exception as e:
            logger.warning("Groq falhou para titulo (%s): %s", language, e)
        return None

    # ── GROQ — HOOK ───────────────────────────────────────────────────────────

    def _groq_hook(self, original_title: str, story_summary: str,
                   language: str) -> str | None:
        from utils import environment as env
        groq_key = env.groq_api_key(language) or self.groq_key
        if not groq_key:
            return None
        try:
            from utils.groq_client import tracked_groq
            client = tracked_groq(groq_key, "titler")

            prompt = HOOK_PROMPTS.get(language, HOOK_PROMPTS["en"]).format(
                original_title=original_title,
                story_text=story_summary,
            )

            resp = client.chat.completions.create(
                model=self.groq_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPTS_HOOK.get(language, SYSTEM_PROMPTS_HOOK["en"])},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.88,
                # 400 e nao 150: os modelos gpt-oss gastam parte do orcamento
                # "pensando" antes de escrever. Com 150 o raciocinio consumia
                # tudo, o conteudo voltava vazio e o titulo caia para regras
                # (visto em producao: titulo cortado "por interromper...").
                max_tokens=400,
            )
            hook = self._clean_title(
                resp.choices[0].message.content.strip(),
                max_len=120,
                is_hook=True,
            )
            if hook and len(hook) > 3:
                logger.info("Hook gerado via Groq (%s): %s", language, hook)
                return hook
        except Exception as e:
            logger.warning("Groq falhou para hook (%s): %s", language, e)
        return None

    # ── GROQ — ENCERRAMENTO (CTA) ─────────────────────────────────────────────

    def _groq_closing(self, original_title: str, story_summary: str,
                      language: str) -> str | None:
        from utils import environment as env
        groq_key = env.groq_api_key(language) or self.groq_key
        if not groq_key:
            return None
        try:
            from utils.groq_client import tracked_groq
            client = tracked_groq(groq_key, "titler")

            prompt = CLOSING_HOOK_PROMPTS.get(language, CLOSING_HOOK_PROMPTS["en"]).format(
                original_title=original_title,
                story_text=story_summary,
            )

            resp = client.chat.completions.create(
                model=self.groq_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPTS_CLOSING.get(language, SYSTEM_PROMPTS_CLOSING["en"])},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.85,
                # 400 e nao 150: os modelos gpt-oss gastam parte do orcamento
                # "pensando" antes de escrever. Com 150 o raciocinio consumia
                # tudo, o conteudo voltava vazio e o titulo caia para regras
                # (visto em producao: titulo cortado "por interromper...").
                max_tokens=400,
            )
            closing = self._clean_title(
                resp.choices[0].message.content.strip(),
                max_len=140,
                is_hook=False,
            )
            if closing and len(closing) > 3:
                logger.info("Encerramento gerado via Groq (%s): %s", language, closing)
                return closing
        except Exception as e:
            logger.warning("Groq falhou para encerramento (%s): %s", language, e)
        return None

    # ── OLLAMA — TÍTULO ───────────────────────────────────────────────────────

    def _ollama_title(self, original_title: str, story_summary: str,
                      language: str, hook_type: str = "short") -> str | None:
        try:
            import requests
            base_prompt = TITLE_PROMPTS.get(language, TITLE_PROMPTS["en"]).format(
                original_title=original_title,
                story_text=story_summary,
            )
            type_instruction = self._build_type_instruction(hook_type, language)
            prompt = base_prompt + "\n" + type_instruction

            resp = requests.post(
                self.ollama_url,
                json={"model": self.ollama_model, "prompt": prompt, "stream": False},
                timeout=60,
            )
            if resp.status_code == 200:
                title = self._clean_title(resp.json().get("response", "").strip())
                if title and len(title) > 3:
                    logger.info("Titulo gerado via Ollama (%s): %s", language, title)
                    return title
        except Exception as e:
            logger.warning("Ollama falhou para titulo (%s): %s", language, e)
        return None

    # ── OLLAMA — HOOK ─────────────────────────────────────────────────────────

    def _ollama_hook(self, original_title: str, story_summary: str,
                     language: str) -> str | None:
        try:
            import requests
            prompt = HOOK_PROMPTS.get(language, HOOK_PROMPTS["en"]).format(
                original_title=original_title,
                story_text=story_summary,
            )
            resp = requests.post(
                self.ollama_url,
                json={"model": self.ollama_model, "prompt": prompt, "stream": False},
                timeout=60,
            )
            if resp.status_code == 200:
                hook = self._clean_title(
                    resp.json().get("response", "").strip(),
                    max_len=120,
                    is_hook=True,
                )
                if hook and len(hook) > 3:
                    logger.info("Hook gerado via Ollama (%s): %s", language, hook)
                    return hook
        except Exception as e:
            logger.warning("Ollama falhou para hook (%s): %s", language, e)
        return None

    # ── OLLAMA — ENCERRAMENTO (CTA) ───────────────────────────────────────────

    def _ollama_closing(self, original_title: str, story_summary: str,
                        language: str) -> str | None:
        try:
            import requests
            prompt = CLOSING_HOOK_PROMPTS.get(language, CLOSING_HOOK_PROMPTS["en"]).format(
                original_title=original_title,
                story_text=story_summary,
            )
            resp = requests.post(
                self.ollama_url,
                json={"model": self.ollama_model, "prompt": prompt, "stream": False},
                timeout=60,
            )
            if resp.status_code == 200:
                closing = self._clean_title(
                    resp.json().get("response", "").strip(),
                    max_len=140,
                    is_hook=False,
                )
                if closing and len(closing) > 3:
                    logger.info("Encerramento gerado via Ollama (%s): %s", language, closing)
                    return closing
        except Exception as e:
            logger.warning("Ollama falhou para encerramento (%s): %s", language, e)
        return None

    # ── INSTRUÇÃO DE TIPO ─────────────────────────────────────────────────────

    def _build_type_instruction(self, hook_type: str, language: str) -> str:
        instructions = {
            "short": {
                "pt": (
                    "INSTRUÇÃO FINAL:\n"
                    "Gere um TÍTULO CURTO, direto e completo (máximo 58 caracteres).\n"
                    "Deve ser uma frase gramaticalmente correta e natural em português.\n"
                    "Retorne apenas o título final.\n"
                ),
                "en": (
                    "FINAL INSTRUCTION:\n"
                    "Generate a SHORT, direct and complete title (maximum 58 characters).\n"
                    "Must be a grammatically correct and natural sentence in English.\n"
                    "Return only the final title.\n"
                ),
                "es": (
                    "INSTRUCCIÓN FINAL:\n"
                    "Genera un TÍTULO CORTO, directo y completo (máximo 58 caracteres).\n"
                    "Debe ser una frase gramaticalmente correcta y natural en español.\n"
                    "Devuelve solo el título final.\n"
                ),
            },
            "narrative": {
                "pt": (
                    "INSTRUÇÃO FINAL:\n"
                    "Gere um TÍTULO NARRATIVO envolvente (máximo 120 caracteres).\n"
                    "Deve ser uma frase completa que cria curiosidade imediata.\n"
                    "Exemplos: 'Recusei emprestar dinheiro pra minha irmã depois que ela me humilhou',\n"
                    "'Expulsei meu cunhado de casa depois de descobrir o que ele estava fazendo'.\n"
                    "Retorne apenas o título final.\n"
                ),
                "en": (
                    "FINAL INSTRUCTION:\n"
                    "Generate an engaging NARRATIVE TITLE (maximum 120 characters).\n"
                    "Must be a complete sentence that creates immediate curiosity.\n"
                    "Examples: 'I refused to lend money to my sister after she humiliated me',\n"
                    "'I kicked my brother-in-law out after finding out what he was doing'.\n"
                    "Return only the final title.\n"
                ),
                "es": (
                    "INSTRUCCIÓN FINAL:\n"
                    "Genera un TÍTULO NARRATIVO envolvente (máximo 120 caracteres).\n"
                    "Debe ser una frase completa que crea curiosidad inmediata.\n"
                    "Ejemplos: 'Me negué a prestarle dinero a mi hermana después de que me humilló',\n"
                    "'Eché a mi cuñado de casa después de descubrir lo que estaba haciendo'.\n"
                    "Devuelve solo el título final.\n"
                ),
            },
        }
        lang_inst = instructions.get(hook_type, instructions["narrative"])
        return lang_inst.get(language, lang_inst.get("en", ""))

    # ── FALLBACK ──────────────────────────────────────────────────────────────

    def _rule_based_title(self, text: str) -> str:
        text  = SUBREDDIT_PREFIXES.sub("", text).strip()
        first = re.split(r"[.!?]", text)[0].strip()
        first = re.sub(r'^["\'"]|["\'"]$', "", first).strip()
        if len(first) > 58:
            first = first[:55]
        return first if first else text[:58]

    def _rule_based_closing(self, language: str) -> str:
        """Fallback fixo de encerramento quando todos os LLMs falham."""
        fallbacks = {
            "pt": "E você, o que faria no meu lugar? Comenta aqui embaixo.",
            "en": "What would you have done in my place? Let me know in the comments.",
            "es": "¿Y tú, qué habrías hecho en mi lugar? Cuéntame en los comentarios.",
        }
        return fallbacks.get(language, fallbacks["en"])


def generate_title(story_text: str, language: str = "pt",
                   original_title: str = "", config: dict = None,
                   hook_type: str = None) -> str:
    gen = TitleGenerator(config or {})
    return gen.generate(story_text, language, original_title, hook_type)


def generate_hook(story_text: str, language: str = "pt",
                  original_title: str = "", config: dict = None) -> str:
    gen = TitleGenerator(config or {})
    return gen.generate_hook(story_text, language, original_title)


def generate_closing_hook(story_text: str, language: str = "pt",
                          original_title: str = "", config: dict = None) -> str:
    gen = TitleGenerator(config or {})
    return gen.generate_closing_hook(story_text, language, original_title)



