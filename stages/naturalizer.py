
"""
naturalizer.py
==============
Reescreve scripts traduzidos em narracao natural, emocional e viral.

Otimizado para:
    - TikTok / YouTube Shorts / Instagram Reels
    - TTS automatico (edge-tts)
    - Legendas palavra-por-palavra sincronizadas
    - Retencao de publico jovem (13-30 anos)

Providers (em ordem de tentativa):
    1. Groq API  — llama-3.3-70b-versatile (preferido)
    2. Ollama    — local, llama3.2 (fallback)
    3. Regras    — substituicoes basicas (fallback final)

IMPORTANTE:
    O naturalizer NAO gera hook de abertura.
    O hook e o titulo viral injetado pelo main.py (inject_title_as_hook).
    O naturalizer reescreve apenas o corpo da historia.
"""

from __future__ import annotations
import os
import logging
import re

logger = logging.getLogger(__name__)


# ── INSTRUCAO DE GENERO POR IDIOMA ────────────────────────────────────────────

GENDER_INSTRUCTION = {
    "pt": {
        "female": (
            "GÊNERO DA NARRADORA — FEMININO (OBRIGATÓRIO):\n"
            "A narradora é uma MULHER. Use sempre concordância feminina para ela.\n"
            "Correto: 'me senti humilhada', 'estava sozinha', 'fiquei chateada', 'eu mesma'\n"
            "Errado:  'me senti humilhado', 'estava sozinho', 'fiquei chateado', 'eu mesmo'\n"
            "Mantenha o gênero dos outros personagens conforme o contexto.\n\n"
        ),
        "male": (
            "GÊNERO DO NARRADOR — MASCULINO (OBRIGATÓRIO):\n"
            "O narrador é um HOMEM. Use sempre concordância masculina para ele.\n"
            "Correto: 'me senti humilhado', 'estava sozinho', 'fiquei chateado', 'eu mesmo'\n"
            "Errado:  'me senti humilhada', 'estava sozinha', 'fiquei chateada', 'eu mesma'\n"
            "Mantenha o gênero dos outros personagens conforme o contexto.\n\n"
        ),
        "unknown": (
            "GÊNERO DO NARRADOR: incerto — use formas neutras quando for ambíguo.\n\n"
        ),
    },
    "en": {
        "female": (
            "NARRATOR GENDER — FEMALE (MANDATORY):\n"
            "The narrator is a WOMAN. Always use she/her for the narrator.\n"
            "Keep other characters' genders as shown in context.\n\n"
        ),
        "male": (
            "NARRATOR GENDER — MALE (MANDATORY):\n"
            "The narrator is a MAN. Always use he/him for the narrator.\n"
            "Keep other characters' genders as shown in context.\n\n"
        ),
        "unknown": (
            "NARRATOR GENDER: unclear — use neutral phrasing when ambiguous.\n\n"
        ),
    },
    "es": {
        "female": (
            "GÉNERO DE LA NARRADORA — FEMENINO (OBLIGATORIO):\n"
            "La narradora es una MUJER. Usa siempre concordancia femenina para ella.\n"
            "Mantén el género de los otros personajes según el contexto.\n\n"
        ),
        "male": (
            "GÉNERO DEL NARRADOR — MASCULINO (OBLIGATORIO):\n"
            "El narrador es un HOMBRE. Usa siempre concordancia masculina para él.\n"
            "Mantén el género de los otros personajes según el contexto.\n\n"
        ),
        "unknown": (
            "GÉNERO DEL NARRADOR: incierto — usa formas neutras cuando sea ambiguo.\n\n"
        ),
    },
}


# ── PROMPTS BASE POR IDIOMA ───────────────────────────────────────────────────

NATURALIZE_PROMPTS = {

    "pt": (
        "Você é um roteirista de canais de histórias do Reddit no YouTube e TikTok.\n"
        "Sua tarefa é reescrever o texto abaixo para narração em vídeo curto.\n\n"

        "MISSÃO:\n"
        "Transformar o texto em uma narração que soa como uma pessoa real contando o que viveu.\n"
        "NÃO invente fatos. NÃO resuma. NÃO transforme a história.\n"
        "Preserve todos os detalhes, personagens e a ordem dos acontecimentos.\n\n"

        "TOM E ESTILO — REFERÊNCIA REAL:\n"
        "Pense nos canais brasileiros de histórias do Reddit que fazem sucesso.\n"
        "A narração soa como alguém contando o que aconteceu de verdade — simples, direto, humano.\n"
        "Não é formal. Não é acadêmico. Não é dramático demais.\n"
        "É uma pessoa comum contando uma história real para quem está ouvindo.\n\n"

        "EXEMPLOS DO TOM CORRETO:\n"
        "✅ 'Meu primo trouxe a namorada pro jantar de família. Em cinco minutos eu já sabia que ia ser um desastre.'\n"
        "✅ 'Ela disse suavemente: na verdade sou engenheira de software. Ele riu e continuou ignorando.'\n"
        "✅ 'Fechei a porta. Meus pais não falaram comigo por oito meses.'\n"
        "✅ 'Ouvi meu pai gritar. Depois começar a implorar. Chamei a polícia.'\n"
        "✅ 'Olhei pra ele parado na varanda com a vida em sacos de lixo. Ela mentiu. Vai embora.'\n"
        "✅ 'Essa palavra virou minha prisão. Significava que eu não merecia conforto.'\n\n"

        "EXEMPLOS DO QUE EVITAR:\n"
        "❌ 'Recusei-me a emprestar o dinheiro.' → fala como: 'Não ia emprestar.'\n"
        "❌ 'Não vou lhe emprestar o dinheiro.' → fala como: 'Não vou emprestar pra ela.'\n"
        "❌ 'Ela comunicou à minha mãe.' → fala como: 'Ela contou pra minha mãe.'\n"
        "❌ 'Sentia-me culpada.' → fala como: 'Me sentia culpada.'\n"
        "❌ 'Naquela mesma noite, em um jantar de família.' → fala como: 'Naquela noite, no jantar.'\n"
        "❌ 'Ela evidentemente cruzou uma linha.' → fala como: 'Ela cruzou uma linha.'\n\n"

        "LINGUAGEM:\n"
        "- Use 'pra' em vez de 'para' quando soar mais natural\n"
        "- Use verbos simples: 'disse', 'falou', 'gritou', 'olhei', 'fechei', 'saí'\n"
        "- Diálogos curtos e diretos, integrados na narração\n"
        "- Sem gírias forçadas — só o que soaria natural na boca de uma pessoa comum\n"
        "- Sem palavras rebuscadas, sem estrutura de texto escrito\n\n"

        "REPETIÇÃO DE PALAVRAS — REGRA CRÍTICA:\n"
        "NUNCA repita a mesma palavra relevante em frases próximas ou consecutivas.\n"
        "Errado: 'Ela disse que não. Minha mãe disse que sim. Meu pai disse que...'\n"
        "Certo:  'Ela recusou. Minha mãe defendeu ela. Meu pai concordou comigo.'\n"
        "Preste atenção especial a duas palavras GRUDADAS uma na outra (ex: 'consultas, consultas "
        "pediátricas') — isso costuma vir de tradução automática que traduziu duas expressões "
        "diferentes do inglês para a mesma palavra em português. Reescreva para eliminar a repetição.\n\n"

        "ARTEFATOS DE TRADUÇÃO LITERAL — REGRA CRÍTICA:\n"
        "O texto original foi traduzido automaticamente do inglês e pode conter palavras corretas "
        "mas formais/literárias/estranhas na fala, ou falsos cognatos. Substitua por como uma "
        "pessoa realmente fala:\n"
        "❌ 'genuinamente felizes' → ✅ 'muito felizes' ou 'realmente felizes'\n"
        "❌ 'os e-mails datavam de quatorze meses atrás' → ✅ 'os e-mails eram de catorze meses atrás' "
        "ou 'isso vinha acontecendo fazia catorze meses'\n"
        "❌ 'evidentemente' → ✅ 'claramente' ou remova\n"
        "Desconfie de qualquer palavra que soe como tradução automática, mesmo que gramaticalmente correta.\n\n"

        "ESTRUTURA:\n"
        "- Comece direto na situação — sem apresentação longa\n"
        "- Siga a ordem cronológica dos fatos\n"
        "- NÃO adicione gancho, hook ou introdução — isso é feito em outro lugar\n"
        "- NÃO adicione reflexões ou morais fora do que o narrador expressou\n\n"

        "RITMO:\n"
        "- Deixe o ritmo ser guiado pela história — acelere em momentos de tensão, respire nos momentos calmos\n"
        "- Use pontuação para criar pausas naturais de fala\n"
        "- Leia em voz alta mentalmente — se travar, reescreva\n\n"

        "{gender_instruction}"

        "Retorne APENAS o texto adaptado. Sem títulos, explicações ou comentários.\n\n"
        "Texto original:\n"
    ),

    "en": (
        "You are a scriptwriter for Reddit story channels on YouTube and TikTok.\n"
        "Your task is to rewrite the text below for short-form video narration.\n\n"

        "MISSION:\n"
        "Turn the text into narration that sounds like a real person telling what they experienced.\n"
        "Do NOT invent facts. Do NOT summarize. Do NOT transform the story.\n"
        "Preserve all details, characters and the order of events.\n\n"

        "TONE AND STYLE — REAL REFERENCE:\n"
        "Think of successful English Reddit story channels on YouTube.\n"
        "The narration sounds like someone telling what really happened — simple, direct, human.\n"
        "Not formal. Not academic. Not overly dramatic.\n"
        "Just a regular person telling a real story to whoever is listening.\n\n"

        "EXAMPLES OF THE CORRECT TONE:\n"
        "✅ 'My cousin brought his girlfriend to family dinner. Five minutes in I knew it was going to be a disaster.'\n"
        "✅ 'She said quietly: I'm actually a software engineer. He laughed and kept ignoring her.'\n"
        "✅ 'I closed the door. My parents didn't speak to me for eight months.'\n"
        "✅ 'I heard my dad scream. Then beg. I called the police.'\n"
        "✅ 'I looked at him standing on the porch with his life in garbage bags. She lied. Get out.'\n"
        "✅ 'That word became my prison. It meant I didn't deserve comfort.'\n\n"

        "EXAMPLES OF WHAT TO AVOID:\n"
        "❌ 'I refused to lend him the money.' → say it like: 'I wasn't lending him anything.'\n"
        "❌ 'She informed my mother.' → say it like: 'She told my mom.'\n"
        "❌ 'I felt guilty.' → say it like: 'I felt bad about it.'\n"
        "❌ 'That same evening, at a family dinner.' → say it like: 'That night at dinner.'\n"
        "❌ 'She clearly crossed a line.' → say it like: 'She crossed a line.'\n\n"

        "LANGUAGE:\n"
        "- Use contractions naturally: 'I'm', 'she's', 'didn't', 'wasn't', 'couldn't'\n"
        "- Simple verbs: 'said', 'told', 'yelled', 'looked', 'closed', 'left'\n"
        "- Short, direct dialogue integrated into the narration\n"
        "- No forced slang — only what would naturally come out of a regular person's mouth\n"
        "- No fancy words, no written text structure\n\n"

        "WORD REPETITION — CRITICAL RULE:\n"
        "NEVER repeat the same meaningful word in nearby or consecutive sentences.\n"
        "Wrong: 'She said no. My mom said yes. My dad said that...'\n"
        "Right: 'She refused. My mom sided with her. My dad surprised me.'\n\n"

        "STRUCTURE:\n"
        "- Start directly in the situation — no long introduction\n"
        "- Follow the chronological order of events\n"
        "- NO hook or opening line — that's handled elsewhere\n"
        "- NO added reflections or morals beyond what the narrator expressed\n\n"

        "RHYTHM:\n"
        "- Let the rhythm follow the story — speed up in tense moments, breathe in calm ones\n"
        "- Use punctuation to create natural speech pauses\n"
        "- Read it aloud in your head — if it stumbles, rewrite it\n\n"

        "{gender_instruction}"

        "Return ONLY the adapted text. No titles, explanations or comments.\n\n"
        "Original text:\n"
    ),

    "es": (
        "Eres guionista de canales de historias de Reddit en YouTube y TikTok.\n"
        "Tu tarea es reescribir el texto abajo para narración en video corto.\n\n"

        "MISIÓN:\n"
        "Convertir el texto en una narración que suene como una persona real contando lo que vivió.\n"
        "NO inventes hechos. NO resumas. NO transformes la historia.\n"
        "Preserva todos los detalles, personajes y el orden de los eventos.\n\n"

        "TONO Y ESTILO — REFERENCIA REAL:\n"
        "Piensa en los canales exitosos de historias de Reddit en español en YouTube.\n"
        "La narración suena como alguien contando lo que realmente pasó — simple, directo, humano.\n"
        "No es formal. No es académico. No es exageradamente dramático.\n"
        "Es una persona común contando una historia real a quien la escucha.\n\n"

        "EJEMPLOS DEL TONO CORRECTO:\n"
        "✅ 'Mi primo trajo a su novia a la cena familiar. En cinco minutos ya sabía que iba a ser un desastre.'\n"
        "✅ 'Ella dijo en voz baja: en realidad soy ingeniera de software. Él se rió y siguió ignorándola.'\n"
        "✅ 'Cerré la puerta. Mis padres no me hablaron por ocho meses.'\n"
        "✅ 'Escuché a mi papá gritar. Después rogar. Llamé a la policía.'\n"
        "✅ 'Lo miré parado en la entrada con su vida en bolsas de basura. Ella mintió. Vete.'\n"
        "✅ 'Esa palabra se convirtió en mi prisión. Significaba que yo no merecía consuelo.'\n\n"

        "EJEMPLOS DE LO QUE EVITAR:\n"
        "❌ 'Me negué a prestarle el dinero.' → dilo así: 'No le iba a prestar nada.'\n"
        "❌ 'Ella le comunicó a mi madre.' → dilo así: 'Le contó a mi mamá.'\n"
        "❌ 'Me sentía culpable.' → dilo así: 'Me sentía mal.'\n"
        "❌ 'Esa misma noche, en una cena familiar.' → dilo así: 'Esa noche en la cena.'\n"
        "❌ 'Ella evidentemente cruzó una línea.' → dilo así: 'Cruzó una línea.'\n\n"

        "LENGUAJE:\n"
        "- Usa formas naturales y coloquiales sin forzar jerga\n"
        "- Verbos simples: 'dijo', 'contó', 'gritó', 'miré', 'cerré', 'salí'\n"
        "- Diálogos cortos y directos integrados en la narración\n"
        "- Sin palabras rebuscadas, sin estructura de texto escrito\n\n"

        "REPETICIÓN DE PALABRAS — REGLA CRÍTICA:\n"
        "NUNCA repitas la misma palabra relevante en frases cercanas o consecutivas.\n"
        "Mal: 'Ella dijo que no. Mi mamá dijo que sí. Mi papá dijo que...'\n"
        "Bien: 'Ella se negó. Mi mamá la defendió. Mi papá me sorprendió.'\n"
        "Presta atención especial a dos palabras PEGADAS una a la otra (ej: 'citas, citas médicas') "
        "— suele venir de traducción automática que tradujo dos expresiones distintas del inglés a "
        "la misma palabra en español. Reescribe para eliminar la repetición.\n\n"

        "ARTEFACTOS DE TRADUCCIÓN LITERAL — REGLA CRÍTICA:\n"
        "El texto original fue traducido automáticamente del inglés y puede tener palabras correctas "
        "pero formales/literarias o falsos cognados. Reemplaza por como habla una persona real:\n"
        "❌ 'genuinamente felices' → ✅ 'muy felices' o 'realmente felices'\n"
        "❌ 'evidentemente' → ✅ 'claramente' o quítalo\n"
        "Desconfía de cualquier palabra que suene a traducción automática, aunque sea gramaticalmente correcta.\n\n"

        "ESTRUCTURA:\n"
        "- Empieza directo en la situación — sin introducción larga\n"
        "- Sigue el orden cronológico de los hechos\n"
        "- NO agregues gancho ni apertura — eso se hace en otro lugar\n"
        "- NO agregues reflexiones o moralejas fuera de lo que el narrador expresó\n\n"

        "RITMO:\n"
        "- Deja que el ritmo lo marque la historia — acelera en momentos de tensión, respira en los calmos\n"
        "- Usa puntuación para crear pausas naturales de habla\n"
        "- Léelo en voz alta mentalmente — si traba, reescríbelo\n\n"

        "{gender_instruction}"

        "Devuelve SOLO el texto adaptado. Sin títulos, explicaciones o comentarios.\n\n"
        "Texto original:\n"
    ),
}


# ── CLASSE PRINCIPAL ──────────────────────────────────────────────────────────

class ScriptNaturalizer:
    """
    Reescreve scripts traduzidos em narracao viral e natural.
    Ordem: Groq → Ollama → regras.
    NAO gera hook — o hook e o titulo viral injetado pelo main.py.
    """

    def __init__(self, config: dict = None):
        self.config       = config or {}
        self.groq_key     = os.environ.get("GROQ_API_KEY", "") or self.config.get("groq_api_key", "")
        self.groq_model   = self.config.get("groq_model", "openai/gpt-oss-120b")
        self.ollama_url   = self.config.get("ollama_url", "http://localhost:11434/api/generate")
        self.ollama_model = self.config.get("ollama_model", "llama3.2")
        self.enabled      = self.config.get("enabled", True)

    def _build_prompt(self, language: str, narrator_gender: str) -> str:
        base         = NATURALIZE_PROMPTS.get(language, NATURALIZE_PROMPTS["en"])
        gender_map   = GENDER_INSTRUCTION.get(language, GENDER_INSTRUCTION["en"])
        gender_instr = gender_map.get(narrator_gender, gender_map["unknown"])
        return base.replace("{gender_instruction}", gender_instr)

    # ── PROVIDERS ─────────────────────────────────────────────────────────────

    def _groq_rewrite(self, text: str, language: str, narrator_gender: str) -> str | None:
        from utils import environment as env
        groq_key = env.groq_api_key(language) or self.groq_key
        if not groq_key:
            logger.debug("Groq ignorado — GROQ_API_KEY nao definida")
            return None
        try:
            from utils.groq_client import tracked_groq
            client = tracked_groq(groq_key, "naturalizer")
            prompt = self._build_prompt(language, narrator_gender)
            resp   = client.chat.completions.create(
                model=self.groq_model,
                messages=[
                    {
                        "role":    "system",
                        "content": (
                            "You are a viral Reddit storytelling script editor for YouTube and TikTok. "
                            "Rewrite narration to sound like a real person telling their story — "
                            "simple, direct, human, conversational. "
                            "Return ONLY the rewritten text. "
                            "No hook, no intro, no comments, no headers, no explanations."
                        ),
                    },
                    {"role": "user", "content": prompt + text},
                ],
                temperature=0.72,
                max_tokens=4096,
            )
            result = resp.choices[0].message.content.strip()
            result = re.sub(r"^```[a-z]*\n?", "", result)
            result = re.sub(r"\n?```$",        "", result).strip()
            if result:
                logger.info(
                    "Naturalizacao concluida via Groq (%s, genero=%s)",
                    language, narrator_gender,
                )
                return result
        except ImportError:
            logger.debug("groq nao instalado: pip install groq")
        except Exception as e:
            logger.warning("Groq falhou (%s): %s", language, e)
        return None

    def _ollama_rewrite(self, text: str, language: str, narrator_gender: str) -> str | None:
        try:
            import requests
            prompt = self._build_prompt(language, narrator_gender) + text
            resp   = requests.post(
                self.ollama_url,
                json={"model": self.ollama_model, "prompt": prompt, "stream": False},
                timeout=180,
            )
            if resp.status_code == 200:
                result = resp.json().get("response", "").strip()
                if result:
                    logger.info("Naturalizacao concluida via Ollama (%s)", language)
                    return result
            else:
                logger.warning("Ollama retornou status %d (%s)", resp.status_code, language)
        except Exception as e:
            logger.warning("Ollama falhou (%s): %s", language, e)
        return None

    # Palavras/expressoes formais ou literarias que o LLM (naturalizer ou
    # tradutor) deixa passar de forma inconsistente — as vezes reescreve o
    # resto da frase mas mantem essa palavra especifica intacta (ja
    # observado com "genuinamente", "datavam de" e "verossimil" sobrevivendo
    # a naturalizacao mesmo com instrucao explicita no prompt contra isso).
    # Aplicado SEMPRE em cima do resultado do LLM, nao so como fallback —
    # rede de seguranca deterministica pra quando o prompt sozinho nao basta.
    _KNOWN_FIXES = {
        "pt": [
            (r"\bcontactá-lo\b",        "falar com ele"),
            (r"\bcontactá-la\b",        "falar com ela"),
            (r"\bcontatá-lo\b",         "falar com ele"),
            (r"\bcontatá-la\b",         "falar com ela"),
            (r"\bNo entanto,?\b",       "Mas"),
            (r"\bTodavia,?\b",          "Mas"),
            (r"\bOutrossim,?\b",        "Alem disso,"),
            (r"\bafirmando que\b",      "dizendo que"),
            (r"\boptei por\b",          "decidi"),
            (r"\bpara mim\b",           "pra mim"),
            (r"\bpara você\b",          "pra você"),
            (r"\bpara nós\b",           "pra gente"),
            (r"\bposteriormente\b",     "depois"),
            (r"\bconsequentemente\b",   "então"),
            (r"\bportanto\b",           "então"),
            (r"\bentretanto\b",         "mas"),
            (r"\bRecusei-me a\b",       "Não ia"),
            (r"\bNão vou lhe\b",        "Não vou"),
            (r"\bSentia-me\b",          "Me sentia"),
            (r"\bcomunicou à\b",        "contou pra"),
            (r"\bcomunicou a\b",        "contou pra"),
            (r"\bgenuinamente\b",       "de verdade"),
            (r"\bdatavam de\b",         "eram de"),
            (r"\bdatava de\b",          "era de"),
            (r"\bverossímil\b",         "convincente"),
            (r"\bverossímeis\b",        "convincentes"),
            (r"\bevidentemente\b",      "claramente"),
            (r"\bporque por que\b",     "por que"),
            (r"\bPorque por que\b",     "Por que"),
        ],
        "es": [
            (r"\bNo obstante,?\b",      "Pero"),
            (r"\bpor ende,?\b",         "entonces,"),
            (r"\bmanifestó que\b",      "dijo que"),
            (r"\bsin embargo,?\b",      "pero"),
            (r"\bposteriormente\b",     "después"),
            (r"\bconsecuentemente\b",   "entonces"),
            (r"\bMe negué a\b",         "No iba a"),
            (r"\ble comunicó a\b",      "le contó a"),
            (r"\bgenuinamente\b",       "de verdad"),
            (r"\bverosímil\b",          "convincente"),
            (r"\bevidentemente\b",      "claramente"),
        ],
        "en": [
            (r"\bHowever,?\b",          "But"),
            (r"\bNevertheless,?\b",     "Still,"),
            (r"\bI proceeded to\b",     "I"),
            (r"\bI opted to\b",         "I decided to"),
            (r"\bsubsequently\b",       "then"),
            (r"\bconsequently\b",       "so"),
            (r"\btherefore\b",          "so"),
            (r"\bI refused to lend\b",  "I wasn't lending"),
            (r"\bShe informed\b",       "She told"),
            (r"\bI felt guilty\b",      "I felt bad"),
        ],
    }

    def _apply_known_fixes(self, text: str, language: str) -> str:
        """Aplica a lista de substituicoes formal->casual conhecidas. Sempre
        roda, independente de Groq/Ollama terem gerado o texto ou nao."""
        for pattern, replacement in self._KNOWN_FIXES.get(language, self._KNOWN_FIXES["en"]):
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    def _rule_based_rewrite(self, text: str, language: str) -> str:
        text = self._apply_known_fixes(text, language)
        from utils import telemetry
        telemetry.record_fallback("naturalizer", language, "Groq e Ollama indisponiveis")
        logger.info("Naturalizacao via regras (%s)", language)
        return text

    # ── INTERFACE PUBLICA ─────────────────────────────────────────────────────

    def naturalize(self, text: str, language: str, narrator_gender: str = "unknown") -> str:
        """
        Reescreve o script para narracao viral.
        NAO gera hook — apenas reescreve o corpo da historia.
        Ordem: Groq → Ollama → regras. A lista de substituicoes conhecidas
        (_apply_known_fixes) roda em cima do resultado de QUALQUER uma
        dessas fontes, como rede de seguranca — o LLM segue a instrucao de
        "nao seja formal" de forma inconsistente.
        """
        if not self.enabled or not text.strip():
            return text

        if len(text) > 6000:
            return self._naturalize_chunked(text, language, narrator_gender)

        result = self._groq_rewrite(text, language, narrator_gender)
        if result:
            return self._apply_known_fixes(result, language)

        result = self._ollama_rewrite(text, language, narrator_gender)
        if result:
            return self._apply_known_fixes(result, language)

        return self._rule_based_rewrite(text, language)

    # Tamanho maximo de cada lote ao agrupar paragrafos para naturalizacao em
    # partes. NAO naturalizar paragrafo-a-paragrafo isolado — isso gerava ~30
    # chamadas Groq sem contexto entre si para uma historia longa, causando
    # inflacao de texto (cada chamada isolada nao sabe quanto "espaco" resta
    # na historia toda) e quebra de continuidade entre trechos. Agrupar em
    # lotes maiores preserva muito mais contexto por chamada.
    _NATURALIZE_BATCH_CHARS = 3500

    def _group_paragraphs(self, text: str) -> list[str]:
        """Agrupa paragrafos consecutivos em lotes ate _NATURALIZE_BATCH_CHARS,
        sem nunca quebrar um paragrafo no meio."""
        paragraphs = text.split("\n\n")
        batches: list[str] = []
        current = ""
        for para in paragraphs:
            if not para.strip():
                continue
            if current and len(current) + len(para) + 2 > self._NATURALIZE_BATCH_CHARS:
                batches.append(current)
                current = para
            else:
                current = f"{current}\n\n{para}" if current else para
        if current:
            batches.append(current)
        return batches

    def _naturalize_chunked(self, text: str, language: str, narrator_gender: str) -> str:
        batches = self._group_paragraphs(text)
        logger.info(
            "Naturalizacao em lotes (%s): %d paragrafo(s) agrupados em %d lote(s) "
            "(evita naturalizar cada paragrafo isolado, sem contexto)",
            language, len(text.split("\n\n")), len(batches),
        )
        naturalized = [self.naturalize(batch, language, narrator_gender) for batch in batches]
        return "\n\n".join(naturalized)
    
