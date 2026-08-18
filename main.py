#!/usr/bin/env python3
"""
main.py
=======
Orquestrador principal do Reddit Stories Pipeline — v3.

Fluxo por historia (1 historia por execucao):
    1.  Extracao       -> Reddit JSON publico
    2.  Filtragem      -> score 0-100
    3.  Siglas EN      -> expansao de siglas no texto original (28F -> 28-year-old woman)
    4.  Adaptacao      -> limpeza narrativa via Groq (fallback: regras)
    4.5 Validacao      -> valida script adaptado (EN) antes de traduzir
    5.  Traducao       -> script por idioma
    5.5 Validacao      -> valida script traduzido (por idioma)
    6.  Siglas PT/ES   -> expansao de siglas no texto traduzido
    7.  Deteccao genero-> ANTES da naturalizacao
    8.  Naturalizacao  -> LLM com genero correto desde o inicio
    9.  Validacao      -> corrige erros de genero que escaparam da naturalizacao
    9.5 Validacao      -> valida script final (adaptacao+traducao+genero+naturalizacao)
    10. Titulo         -> gerador viral baseado no titulo original do Reddit
    10.5 Validacao     -> valida titulo + hook
    11. Hook           -> titulo injetado como primeira frase do script
    12. Split          -> partes de ate 2:45 (teto de Short do YouTube), com hook repetido e encerramento
    13. Voz            -> edge-tts com voz do genero correto
    14. Legendas       -> ASS animado palavra por palavra
    15. Video          -> FFmpeg 1080x1920 + ASS + background automatico (Shorts/)
    16. Thumbnail      -> Pillow (JPG estatica + .mov card com fade)
    17. Metadados      -> SEO por idioma
    17.5 Validacao     -> valida descricao + tags
    18. Organizacao    -> exports/{lang}/{slug}_{data}_{lang}.mp4

Execucao normal:
    python main.py --lang pt
    python main.py --lang pt en es
    python main.py --dry-run

Execucao de teste rapido (pula etapas 1 e 2):
    python main.py --test-story --lang pt
"""
import argparse
import logging
import random
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import yaml

BASE_DIR = Path(__file__).parent


# ── HISTORIAS DE TESTE ────────────────────────────────────────────────────────
# Escolha qual usar na linha TEST_STORY = ... no final deste bloco:
#   TEST_STORY = TEST_STORY_SHORT   → 1 parte  (~2 min)  — teste rapido
#   TEST_STORY = TEST_STORY_SPLIT   → 3 partes (~17 min) — teste do splitter

TEST_STORY_SHORT = {
    "id":           "test_001",
    "title":        "AITA for refusing to lend money to my sister after she insulted my job",
    "text": (
        "I (28F) work as a nurse. My sister (32F) has always looked down on my career, "
        "saying things like 'you could have been a doctor' and 'nurses are just assistants'. "
        "Last month she called me at work to ask for a $3000 loan because her car broke down. "
        "I told her I needed to think about it. That same evening, at a family dinner, "
        "she made a comment in front of everyone saying my job was 'glorified babysitting'. "
        "I decided right then that I would not lend her the money. "
        "She found out the next day and told our mom I was being petty and cruel. "
        "My mom says I should separate her comments from the loan request. "
        "My dad says I was right to say no. "
        "I feel guilty but also like she crossed a line. AITA?"
    ),
    "subreddit":    "AITA",
    "score":        95,
    "upvote_ratio": 0.94,
    "num_comments": 312,
    "url":          "https://reddit.com/r/AmItheAsshole/test",
    "created_utc":  0,
    "author":       "test_user",
    "is_test":      True,
}

TEST_STORY_SPLIT = {
    "id":           "test_split_001",
    "title":        "AITA for choosing divorce over reconciliation when my husband ended the affair and was actively trying to fix our marriage",
    "text": (
        "I am a 34-year-old woman and I have been with my husband Daniel for eleven years, married for seven. "
        "We have three children together: twins who just turned eight and a five-year-old son. "
        "For most of our marriage I would have described us as genuinely happy. "
        "We had problems like any couple but we talked about them, we compromised, we showed up for each other. "
        "Or at least I thought we did.\n\n"

        "Daniel works as a regional sales manager for a logistics company. "
        "The job requires some travel, maybe one week per month, sometimes two. "
        "I work remotely as a financial analyst and I handle most of the household management, "
        "school pickups, appointments, pediatric visits, parent-teacher meetings, all of it. "
        "It is a lot but I did not mind because I believed we were a team and because he was present "
        "and engaged when he was home. On weekends he would take the twins to soccer practice and spend "
        "Saturday afternoons building things in the garage with our youngest. "
        "He coached bedtime stories with different voices for each character. "
        "I loved that man. I want to be clear about that before I tell you what happened.\n\n"

        "About two years ago I noticed things starting to shift. He was less talkative at dinner. "
        "He stopped initiating conversations about our future, things we used to love planning together "
        "like vacations and eventually buying a bigger house with a yard the kids could actually run around in. "
        "When I brought it up he said he was just stressed about work and quarterly targets. "
        "The company had gone through a restructuring and his team had been cut by two people. "
        "I believed him because that explanation had always been true before and because I had no reason not to.\n\n"

        "Then about eighteen months ago his travel started increasing. Three weeks a month, sometimes more. "
        "He always had explanations. A new client in Atlanta. A distribution problem in Phoenix. "
        "A training conference in Seattle. A regional rollout in Houston that kept getting extended. "
        "The explanations were always plausible and detailed and I trusted him because that is what "
        "eleven years of partnership had built between us. I trusted him the way you trust the floor "
        "beneath your feet. You do not think about it. You just walk.\n\n"

        "I started noticing the small things about eight months ago. "
        "He would leave the room to take certain phone calls, walking out to the backyard or stepping "
        "into the garage and pulling the door mostly closed behind him. "
        "His phone was always face down on the table. He started going to bed earlier than usual and "
        "would be on his phone in the dark when he thought I was asleep. "
        "When I asked who he was texting so late he said it was a colleague dealing with a work crisis "
        "and he was just being supportive. I told myself that was the kind of person Daniel was. "
        "Supportive. Available. Good.\n\n"

        "I told my sister Laura what I was noticing and she said I was probably overthinking it. "
        "She said Daniel had always been devoted and that stress does weird things to people. "
        "She reminded me of a period three years ago when I had gone through something similar, "
        "pulling back and being distracted, and how Daniel had just been patient and waited for me to "
        "come back to myself. My friend Camille said the opposite. She said I should trust my gut and "
        "that the gut does not lie. She said she had ignored her gut for two years in her first marriage "
        "and those were two years she would never get back. "
        "I was stuck between the two of them and honestly between two versions of myself, "
        "the one who trusted and the one who was terrified of what trusting blindly might cost me.\n\n"

        "In February I found out. I had borrowed his laptop to finish a quarterly report because mine "
        "was running a system update and I accidentally opened his email instead of the browser. "
        "His inbox was open. I saw a thread at the top with a name I did not recognize, "
        "a woman named Priya who worked at one of his client companies in Houston. "
        "Something made me stop. I do not know what it was exactly. Maybe the thread was just too long. "
        "Maybe something about the subject line felt off. I clicked on it and I read for about four minutes "
        "and in those four minutes eleven years rearranged themselves into something I did not recognize.\n\n"

        "The emails went back fourteen months. They were detailed and intimate and affectionate in a way "
        "that was unmistakably personal. Inside jokes. References to specific conversations. "
        "Her asking about his kids by name. Him talking about his marriage in a way that made me sound "
        "like a roommate he had grown tired of. There was nothing explicitly graphic but there did not "
        "need to be. The emotional intimacy alone was enough to make it clear that what they had was "
        "not professional and had not been for a very long time.\n\n"

        "I did not say anything that night. I could not. I just closed the laptop and went upstairs and "
        "sat on the bathroom floor for about two hours while he watched television downstairs completely "
        "unaware that anything had changed. I kept reading the same three sentences in my head over and over. "
        "Fourteen months. He had been doing this for fourteen months while I was doing school runs and "
        "managing our finances and planning birthday parties and believing in us. "
        "I had planned a surprise anniversary dinner in October, four months into whatever this was with Priya, "
        "and he had cried at the table and told me I was the best thing that had ever happened to him.\n\n"

        "The next morning I waited until the kids left for school and I told him what I had found. "
        "He did not deny it. He started crying immediately and said he was sorry and that it had gotten "
        "out of hand and that he never meant for it to go so far. "
        "I asked him how far it had gone and he admitted they had met in person during his Houston trips. "
        "Not just emails. Actual meetings at an actual hotel. Months of them. "
        "I asked him how many times and he said he did not know exactly. "
        "I asked him if he loved her and he said he did not know. "
        "That was somehow worse than yes would have been.\n\n"

        "I asked him to leave the house that day. He did. He went to stay with his brother Kevin and "
        "I spent the next three days barely functioning. "
        "I dropped my son off at preschool on the second morning and sat in the parking lot for forty minutes "
        "because I could not make myself drive away and I could not make myself go back inside and "
        "I did not know what to do with my body. "
        "My mother came to stay with me and help with the kids and she was incredible. "
        "She did not push me to make any decisions. She did not tell me what I should do or what she would do. "
        "She just kept the household running while I tried to figure out how to breathe normally again.\n\n"

        "After about two weeks Daniel asked if we could talk. "
        "He said he had ended things with Priya completely and permanently and had blocked her on everything. "
        "He showed me a final message he had sent her, a long one, and asked me to read it. "
        "It was clear and unambiguous. "
        "He said he was committed to doing whatever it took to repair what he had broken. "
        "He had already started individual therapy and he asked if I would consider couples counseling with him.\n\n"

        "I agreed to try. Part of me agreed because I genuinely did not know what I wanted and I thought "
        "the structure of therapy might help me figure it out. "
        "Part of me agreed because I looked at my three children and could not yet imagine explaining to them "
        "why their family was changing. "
        "We started seeing a couples therapist named Dr. Osei who came recommended by my individual therapist "
        "and who was honest and direct in a way I appreciated immediately.\n\n"

        "Daniel worked hard in those sessions. He was open about things I expected him to be defensive about. "
        "He admitted that he had been pulling away emotionally long before Priya, "
        "that he had felt invisible in our partnership in ways he had never communicated to me, "
        "that he had felt like the support staff for a household rather than a full participant in a marriage. "
        "He said instead of bringing that to me he had turned toward something easier and more immediately "
        "validating. Someone who had no history with him, no expectations, no accumulated weight of everyday life.\n\n"

        "That was hard to hear. I wanted to be angry without any complication. "
        "I wanted the story to be simple. "
        "But Dr. Osei helped me see that understanding why something happened is not the same as excusing it "
        "and I could hold both truths at once. "
        "I could understand what Daniel said about feeling invisible while also holding him completely "
        "responsible for the choice he made. He could have talked to me. He could have asked for more. "
        "He could have gone to therapy on his own a long time ago. He chose not to. And then he chose Priya.\n\n"

        "We did four months of therapy together. "
        "There were sessions that felt like real breakthroughs and sessions that felt like we were just "
        "performing reconciliation for each other. "
        "There was one afternoon in May where we talked for three hours in Dr. Osei's office and I drove home "
        "feeling like maybe we could actually do this. "
        "There were other evenings where I watched Daniel fall asleep on his side of our bed and felt nothing "
        "but an enormous and exhausting distance between us that I did not know how to cross.\n\n"

        "In June I told Daniel I needed more time and more distance to figure out what I actually wanted. "
        "He moved back in with Kevin. The kids knew something was wrong but we had been careful to keep "
        "the details away from them and had told them only that mom and dad were working through some "
        "grown-up problems and that both of us loved them completely and that would never change.\n\n"

        "Then in July my eight-year-old daughter came to me one evening while I was putting her brother to bed "
        "and asked me quietly if daddy had done something bad. "
        "I asked her what made her think that and she said because sometimes when you think we are asleep "
        "we can hear you crying in the bathroom and daddy looks like someone told him his dog died "
        "every time he drops us off.\n\n"

        "I told her that grown-ups sometimes have hard problems to work through just like kids do and that "
        "both her dad and I loved her and her brothers more than anything in the world. "
        "She nodded very seriously and then said she hoped we figured it out because she did not like "
        "living with two houses in her head even when we were all in the same place.\n\n"

        "Two houses in her head even when we were all in the same place. "
        "I have thought about that sentence every single day since she said it.\n\n"

        "In September I made my decision. I told Daniel I wanted to file for divorce. "
        "He was devastated. He said he felt like he had done everything I asked and that I was punishing him "
        "for making real progress. I told him I was not punishing him. "
        "I told him I believed he was genuinely sorry and genuinely trying and that none of that changed "
        "what I knew about myself, which was that I could not rebuild trust in this marriage. "
        "Not because he had not tried. But because something in me had closed in a way I could not force "
        "open no matter how much I wanted to.\n\n"

        "His mother called me and said I was making a terrible mistake and that good men who make mistakes "
        "and fight to fix them deserve a second chance. "
        "She said her own marriage had survived worse and they had been together for forty years. "
        "My father said he supported whatever I decided. "
        "Laura said she was sorry she had told me I was overthinking it eight months ago and that she loved "
        "me no matter what. "
        "Camille helped me find a divorce attorney and came with me to the first consultation "
        "and held my hand in the waiting room.\n\n"

        "The divorce is in process now. We have agreed on joint custody and Daniel has been cooperative "
        "and reasonable throughout, which I am genuinely grateful for. "
        "He is a good father even though he was not a faithful husband, and my children need him present "
        "and stable and not resentful and I have tried very hard to make space for that.\n\n"

        "The people in my life have been divided in ways I did not expect. "
        "My mother-in-law and Daniel's sister think I should have stayed. "
        "Several of my coworkers who know only the surface of the situation have said things like "
        "at least he tried or no marriage is perfect when what they mean is that I should have accepted "
        "an imperfect marriage as good enough.\n\n"

        "But my therapist asked me something in our last session that I keep coming back to. "
        "She asked me what I would tell my daughter to do if she were in my position twenty years from now. "
        "And I sat there for a long time before I could answer. "
        "Because the answer that came to me was not stay if he is trying hard enough. "
        "The answer was that she should never have to negotiate for basic honesty in her own home. "
        "That she should never have to wonder if the person sleeping next to her is also somewhere else entirely. "
        "That she should build a life where she does not have to choose between what she deserves "
        "and what feels survivable.\n\n"

        "I want my children to grow up watching their parents be whole people. "
        "Even if those people are not together. "
        "I would rather they see me choose my own integrity than watch me shrink myself into someone "
        "who can live with something I cannot actually live with.\n\n"

        "Some nights I still wonder if I made the right call. "
        "I wonder if I gave up on something that could have been repaired. "
        "But then I remember sitting on the bathroom floor at two in the morning not from grief anymore "
        "but from exhaustion. From the effort of constantly monitoring myself, "
        "measuring how much I had healed against some invisible benchmark that kept moving further away "
        "every time I thought I was getting close. "
        "And I remember thinking that a marriage should not feel like recovery. It should feel like home.\n\n"

        "Maybe I am wrong. Maybe in five years I will look back and wish I had held on longer. "
        "But right now, four months out, I feel something I have not felt in over a year. "
        "I feel like myself again. And I had forgotten how much I missed her.\n\n"

        "I do not know if the person I am becoming on the other side of this decision is braver or just "
        "more tired. But she is honest. And right now that feels like enough.\n\n"

        "AITA for choosing divorce over reconciliation when my husband had already ended the affair, "
        "was in therapy, and was actively working to repair our marriage?"
    ),
    "subreddit":    "relationship_advice",
    "score":        98,
    "upvote_ratio": 0.96,
    "num_comments": 847,
    "url":          "https://reddit.com/r/relationship_advice/test_split",
    "created_utc":  0,
    "author":       "test_user_split",
    "is_test":      True,
}

TEST_STORY_MALE = {
    "id":           "test_male_001",
    "title":        "AITA for cutting off my son financially after I found out the surgery he needed the money for never happened",
    "text": (
        "I am a 52-year-old man and I have two adult children, Marcus and Elena. For most of "
        "their lives I tried to be the kind of father who shows up when it actually matters, "
        "not just for birthdays and holidays.\n\n"

        "Eight months ago Marcus called me in a panic. He said his wife needed emergency "
        "surgery and their insurance would not cover enough of it. He asked if I could lend "
        "him fifteen thousand dollars and promised he would pay me back within a year once "
        "his bonus came through at work. I did not hesitate. I have savings specifically for "
        "situations like this, and I transferred the money the same day.\n\n"

        "For a while everything seemed normal. Marcus thanked me repeatedly and told me his "
        "wife was recovering well. I sent flowers to their house and asked how she was doing "
        "every couple of weeks. He always had an update ready. Physical therapy going fine. "
        "Doctors happy with the progress. I believed every word of it because why would I "
        "not.\n\n"

        "Three months ago I ran into my daughter-in-law's sister at a grocery store, someone "
        "I had met a handful of times at family events. She asked me how I was holding up, "
        "and when I said things were fine, she looked confused and asked what I meant. I "
        "explained that I had heard about the surgery and wanted to make sure everyone was "
        "doing okay. She stared at me for a long moment and then said she had no idea what "
        "surgery I was talking about. Her sister, my daughter-in-law, had not had any "
        "surgery. Not that year, not ever.\n\n"

        "I did not say anything to Marcus right away. I needed a few days to process it, "
        "because my mind kept trying to build an innocent explanation and failing every "
        "time. Eventually I called him and asked directly. He was quiet for a long time "
        "before he admitted the truth. There was no surgery. He had gotten into serious debt "
        "from online sports betting, more than he had ever told any of us, and he used the "
        "story about his wife because he knew I would say yes immediately if her health were "
        "involved. He knew I would hesitate if he just told me he needed money to cover a "
        "gambling debt.\n\n"

        "I asked him how long this had been going on and he said almost two years. Two years "
        "of hiding it from his wife, from his job, from all of us, and finally using an "
        "invented medical emergency to bail himself out one more time.\n\n"

        "I told him I needed time before I decided anything, and a week later I told him I "
        "would not be lending or giving him any more money going forward, and that I needed "
        "him to get real help for the gambling before we talked about anything else. I also "
        "told him I could not, in good conscience, pretend nothing happened, so I would not "
        "be attending his birthday dinner that weekend, which the rest of the family had "
        "already planned around.\n\n"

        "That decision blew up faster than I expected. My daughter-in-law found out "
        "everything during the fallout and is furious at both of us for different reasons. "
        "Elena, my daughter, thinks I am punishing Marcus publicly instead of handling it "
        "privately, and says skipping the birthday dinner humiliated him in front of people "
        "who did not need to know anything. My ex-wife called me and said addiction is a "
        "disease and I am supposed to be the parent who does not give up on his kids no "
        "matter what.\n\n"

        "Marcus has not spoken to me since. He sent one message saying I destroyed his "
        "marriage, because word about the real reason I skipped his birthday got back to his "
        "wife before he was ready to explain it himself.\n\n"

        "I keep replaying the moment I transferred that money without a second thought. I am "
        "not angry about the fifteen thousand dollars. I am angry that my son looked me in "
        "the eye, more than once, and built an entire fake medical crisis around his wife's "
        "body to keep the story believable, and that I only found out by accident from a "
        "stranger at a grocery store.\n\n"

        "I want to help him get better. I am just not willing to keep funding a lie while I "
        "do it.\n\n"

        "AITA for cutting off my son financially and for skipping his birthday after I found "
        "out the surgery he needed the money for never happened?"
    ),
    "subreddit":    "AmItheAsshole",
    "score":        96,
    "upvote_ratio": 0.95,
    "num_comments": 540,
    "url":          "https://reddit.com/r/AmItheAsshole/test_male",
    "created_utc":  0,
    "author":       "test_user_male",
    "is_test":      True,
}

# ← AQUI você escolhe qual historia rodar com --test-story:
# TEST_STORY = TEST_STORY_SHORT   # 1 parte  (~2 min)  — teste rapido
# TEST_STORY = TEST_STORY_SPLIT   # 3 partes (~17 min) — teste do splitter
TEST_STORY = TEST_STORY_MALE      # 1 parte  (~4-5 min) — narrador masculino, tema diferente (nao traicao/divorcio)
# ─────────────────────────────────────────────────────────────────────────────


# ── EXPANSAO DE SIGLAS REDDIT ─────────────────────────────────────────────────

REDDIT_AGE_GENDER_EN = [
    (r"\((\d+)F\)",  "{1}-year-old woman"),
    (r"\((\d+)M\)",  "{1}-year-old man"),
    (r"\b(\d+)F\b",  "{1}-year-old woman"),
    (r"\b(\d+)M\b",  "{1}-year-old man"),
]

REDDIT_ACRONYMS = {
    "pt": {
        r"\bAITA\b":  "Eu errei",
        r"\bAITAH\b": "Eu errei",
        r"\bWIBTA\b": "Eu estaria errada",
        r"\bTIFU\b":  "Eu estraguei tudo",
        r"\bNTA\b":   "Voce nao errou",
        r"\bYTA\b":   "Voce errou",
        r"\bESH\b":   "Todo mundo errou",
        r"\bNAH\b":   "Ninguem errou",
        r"\bSO\b":    "parceiro",
        r"\bMIL\b":   "sogra",
        r"\bFIL\b":   "sogro",
        r"\bSIL\b":   "cunhada",
        r"\bBIL\b":   "cunhado",
        r"\bNC\b":    "sem contato",
        r"\bLC\b":    "contato limitado",
    },
    "en": {
        r"\bSO\b":    "partner",
        r"\bMIL\b":   "mother-in-law",
        r"\bFIL\b":   "father-in-law",
        r"\bSIL\b":   "sister-in-law",
        r"\bBIL\b":   "brother-in-law",
        r"\bNC\b":    "no contact",
        r"\bLC\b":    "limited contact",
    },
    "es": {
        r"\bAITA\b":  "me equivoque",
        r"\bWIBTA\b": "estaria mal",
        r"\bSO\b":    "pareja",
        r"\bMIL\b":   "suegra",
        r"\bFIL\b":   "suegro",
        r"\bSIL\b":   "cunada",
        r"\bBIL\b":   "cunado",
        r"\bNC\b":    "sin contacto",
        r"\bLC\b":    "contacto limitado",
    },
}


def expand_age_gender_en(text: str) -> str:
    """Expande marcadores de idade+genero em ingles. Roda ANTES do adapter."""
    for pattern, repl_template in REDDIT_AGE_GENDER_EN:
        def make_replacer(tmpl):
            def replacer(m):
                result = tmpl
                for i, g in enumerate(m.groups(), 1):
                    result = result.replace("{" + str(i) + "}", g or "")
                return result
            return replacer
        text = re.sub(pattern, make_replacer(repl_template), text, flags=re.IGNORECASE)
    return text


def expand_acronyms_translated(text: str, language: str) -> str:
    """Expande siglas fixas do Reddit no texto ja traduzido."""
    acronyms = REDDIT_ACRONYMS.get(language, {})
    for pattern, replacement in acronyms.items():
        text = re.sub(pattern, replacement, text)
    return text


def inject_title_as_hook(script: str, title: str) -> str:
    """
    Injeta o hook de engajamento como abertura separada do script.
    Pausa longa entre hook e historia para soar como introducao separada.
    """
    title_clean = title.strip()

    # Evitar duplicacao
    if script.strip().startswith(title_clean[:30]):
        return script

    # Tres quebras forcam pausa maior no edge-tts antes da historia comecar
    hook_line = f"{title_clean}\n\n\n"
    return hook_line + script


def get_audio_duration(audio_path: Path) -> float | None:
    """
    Lê a duração real do áudio via ffprobe.
    Usado para estender o card overlay (.mov) com frames transparentes
    ate o fim do video, evitando que o FFmpeg congele o ultimo frame
    visivel do card (bug do "fantasma").
    Retorna duração em segundos (float) ou None se falhar.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        duration = float(result.stdout.strip())
        return duration
    except Exception as e:
        logging.getLogger("pipeline.main").warning(
            "Nao foi possivel ler duracao do audio (%s): %s", audio_path.name, e
        )
        return None

# ─────────────────────────────────────────────────────────────────────────────

def save_script_trace(
    scripts_dir: Path, story_id: str, lang: str, stage: str,
    text: str, reset: bool = False,
) -> None:
    """
    Salva um snapshot do script em cada etapa importante do pipeline, num
    unico arquivo por historia+idioma (data/scripts/{lang}/{story_id}_trace.txt).

    Existe pra permitir comparar exatamente onde o texto mudou (palavra
    duplicada, frase cortada, etc) sem precisar adivinhar pelo log — cada
    etapa some acrescenta seu proprio bloco, na ordem em que rodou.
    reset=True reinicia o arquivo (usado na primeira etapa de cada
    historia/idioma, pra nao misturar com o trace de uma execucao anterior).
    """
    trace_dir = scripts_dir / lang
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_path = trace_dir / f"{story_id}_trace.txt"
    mode = "w" if reset else "a"
    with open(trace_path, mode, encoding="utf-8") as f:
        f.write(f"{'=' * 70}\n{stage}\n{'=' * 70}\n{text}\n\n")


def load_config() -> dict:
    with open(BASE_DIR / "config" / "settings.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    with open(BASE_DIR / "config" / "subreddits.yaml", encoding="utf-8") as f:
        subs = yaml.safe_load(f)
    cfg["subreddits_config"] = subs
    cfg["base_dir"] = str(BASE_DIR)
    return cfg


def get_subreddits(cfg: dict) -> list:
    subs = []
    for cat in cfg.get("subreddits_config", {}).get("categories", {}).values():
        subs.extend(cat.get("subreddits", []))
    return list(dict.fromkeys(subs))


def run_pipeline(
    config: dict,
    languages: list,
    dry_run: bool = False,
    test_story: bool = False,
) -> None:
    from stages.adapter         import StoryAdapter
    from stages.translator      import ScriptTranslator
    from stages.naturalizer     import ScriptNaturalizer
    from stages.gender_detector import GenderDetector
    from stages.titler          import TitleGenerator
    from stages.splitter        import split_story
    from stages.voice           import VoiceGenerator
    from stages.subtitle        import SubtitleGenerator
    from stages.video           import VideoRenderer
    from stages.thumbnail       import ThumbnailGenerator
    from stages.metadata        import MetadataGenerator
    from stages.organizer       import FileOrganizer
    from stages.validator       import ValidatorEngine
    from utils.db               import PipelineDB
    from scheduler.notifier     import notify_pipeline_result

    # Normaliza pt-br → pt para uso interno no pipeline
    languages = ["pt" if l == "pt-br" else l for l in languages]

    logger = logging.getLogger("pipeline.main")
    pipeline_started_at = datetime.now()

    # Ambiente (local/VM x runner efemero) — resolve onde vivem backgrounds
    # e banco. Sem variavel de ambiente definida, tudo aponta para os
    # caminhos locais de sempre.
    from utils import environment as env
    from utils import telemetry
    telemetry.reset()   # contadores de token/fallback zerados por execucao
    logger.info("Ambiente: %s", env.describe(BASE_DIR))

    # Configuracao do VideoRenderer com pasta de backgrounds
    video_config = config.get("video", {})
    video_config["background_dir"] = str(env.background_dir(BASE_DIR))

    db          = PipelineDB(env.db_path(BASE_DIR))
    adapter     = StoryAdapter(config.get("adapter", {}))
    translator  = ScriptTranslator(config.get("translator", {}))
    naturalizer = ScriptNaturalizer(config.get("naturalizer", {}))
    gender_det  = GenderDetector(config.get("gender_detector", {}))
    title_gen   = TitleGenerator(config.get("naturalizer", {}))
    voice_gen   = VoiceGenerator(config.get("voice", {}))
    sub_gen     = SubtitleGenerator(config.get("subtitles", {}))
    vid_ren     = VideoRenderer(video_config)
    thumb_gen   = ThumbnailGenerator(config.get("thumbnail", {}))
    meta_gen    = MetadataGenerator(config.get("metadata", {}))
    organizer   = FileOrganizer(config, db)
    validator   = ValidatorEngine(config.get("validator", {}), base_dir=BASE_DIR)

    scripts_dir = BASE_DIR / "data" / "scripts"

    # Contadores para o resumo final no Telegram (notify_pipeline_result)
    parts_attempted = 0
    parts_done      = 0

    # ── ETAPAS 1 e 2 — Extracao e Filtragem ──────────────────────────────────
    if test_story:
        logger.info("=" * 60)
        logger.info("[TEST-STORY] Pulando etapas 1 e 2 — usando historia de teste")
        story = TEST_STORY
        db.insert_story(story)
    else:
        from stages.extractor import RedditExtractor
        from stages.filter    import StoryFilter

        extractor = RedditExtractor(config.get("extraction", {}))
        f_filter  = StoryFilter(config.get("filtering", {}), db)
        raw_dir   = BASE_DIR / "data" / "raw"

        logger.info("=" * 60)
        logger.info("ETAPA 1 — Extracao de historias")
        subreddits = get_subreddits(config)
        if not dry_run:
            extractor.run(subreddits)
        else:
            logger.info("[dry-run] Extracao ignorada")

        logger.info("ETAPA 2 — Filtragem e ranking")
        approved = f_filter.run(raw_dir)
        if not approved:
            logger.warning("Nenhuma historia aprovada. Verifique data/raw/")
            return

        story = approved[0]
        db.insert_story(story)

    story_id    = story["id"]
    story_title = story.get("title", story_id)

    logger.info("=" * 60)
    logger.info("Processando: %s", story_title[:70])

    # ── ETAPA 3 — Expansao de siglas no texto original (ingles) ──────────────
    logger.info("ETAPA 3 — Expansao de siglas Reddit (texto original)")
    story_for_adapter         = story.copy()
    story_for_adapter["text"] = expand_age_gender_en(story.get("text", ""))
    logger.info(
        "Siglas expandidas: '%s...'",
        story_for_adapter["text"][:100].replace("\n", " "),
    )

    # ── ETAPA 4 — Adaptacao via Groq (fallback: regras) ──────────────────────
    logger.info("ETAPA 4 — Adaptacao e limpeza do script")
    adapted      = adapter.adapt(story_for_adapter)
    clean_script = adapted["full_script"]
    logger.info("Adaptado via: %s", adapted.get("adapted_by", "unknown"))
    if not dry_run:
        save_script_trace(scripts_dir, story_id, "en", "ETAPA 4 — Adaptado (EN)", clean_script, reset=True)

    # ── ETAPA 4.5 — Validacao do script adaptado (EN, antes de traduzir) ────
    if not dry_run:
        logger.info("ETAPA 4.5 — Validacao do script adaptado (en)")
        clean_script = validator.validate_and_fix_script(
            clean_script, language="en", narrator_gender="unknown",
            story_id=story_id, story_title=story_title,
        )
        adapted["full_script"] = clean_script
        save_script_trace(scripts_dir, story_id, "en", "ETAPA 4.5 — Validado (EN)", clean_script)

    # ── ETAPA 5 — Traducao por idioma ────────────────────────────────────────
    logger.info("ETAPA 5 — Traducao para: %s", ", ".join(languages).upper())
    if dry_run:
        translated_scripts = {lang: clean_script for lang in languages}
        logger.info("[dry-run] Traducao simulada")
    else:
        translated_scripts = translator.translate_all(
            script_text=clean_script,
            story_id=story_id,
            scripts_dir=scripts_dir,
            languages=languages,
            source_lang="en",
            force=test_story,
        )

    # Ordem de prioridade: PT -> ES -> EN
    lang_order = []
    for priority_lang in ["pt-br", "pt", "es", "en"]:
        if priority_lang in languages:
            lang_order.append(priority_lang)
    for lang in languages:
        if lang not in lang_order:
            lang_order.append(lang)

    for lang in lang_order:
        lang_script = translated_scripts.get(lang, clean_script)
        logger.info("=" * 60)
        logger.info("IDIOMA: %s", lang.upper())
        if not dry_run:
            save_script_trace(scripts_dir, story_id, lang, "ETAPA 5 — Traduzido", lang_script, reset=True)

        # ── ETAPA 5.5 — Validacao do script traduzido (por idioma) ───────────
        if not dry_run:
            logger.info("ETAPA 5.5 — Validacao da traducao (%s)", lang)
            lang_script = validator.validate_and_fix_script(
                lang_script, language=lang, narrator_gender="unknown",
                story_id=story_id, story_title=story_title,
            )
            save_script_trace(scripts_dir, story_id, lang, "ETAPA 5.5 — Validado (traducao)", lang_script)

        # ── ETAPA 6 — Expansao de siglas no texto traduzido ──────────────────
        logger.info("ETAPA 6 — Expansao de siglas Reddit (%s)", lang)
        lang_script = expand_acronyms_translated(lang_script, lang)
        if not dry_run:
            save_script_trace(scripts_dir, story_id, lang, "ETAPA 6 — Siglas expandidas", lang_script)

        # ── ETAPA 7 — Deteccao de genero (ANTES da naturalizacao) ────────────
        logger.info("ETAPA 7 — Deteccao de genero (%s)", lang)
        if not dry_run:
            gender_info     = gender_det.detect(lang_script, lang)
            narrator_gender = gender_info.get("narrator_gender", "unknown")
            logger.info(
                "Genero detectado: %s (confianca=%.2f)",
                narrator_gender,
                gender_info.get("narrator_confidence", 0),
            )
        else:
            narrator_gender = "unknown"

        # ── ETAPA 8 — Naturalizacao com genero correto desde o inicio ────────
        logger.info(
            "ETAPA 8 — Naturalizacao (%s, genero=%s)", lang, narrator_gender,
        )
        if not dry_run:
            lang_script = naturalizer.naturalize(lang_script, lang, narrator_gender)
            save_script_trace(scripts_dir, story_id, lang, f"ETAPA 8 — Naturalizado (genero={narrator_gender})", lang_script)

        # ── ETAPA 9 — Validacao de genero pos-naturalizacao ──────────────────
        if not dry_run and narrator_gender != "unknown":
            logger.info(
                "ETAPA 9 — Validacao de genero (%s, genero=%s)", lang, narrator_gender,
            )
            lang_script = gender_det.validate_and_fix(lang_script, narrator_gender, lang)
            save_script_trace(scripts_dir, story_id, lang, "ETAPA 9 — Genero corrigido", lang_script)

        # ── ETAPA 9.5 — Validacao final do script (adaptacao+traducao+genero) ─
        if not dry_run:
            logger.info("ETAPA 9.5 — Validacao final do script (%s)", lang)
            lang_script = validator.validate_and_fix_script(
                lang_script, language=lang, narrator_gender=narrator_gender,
                story_id=story_id, story_title=story_title,
            )
            save_script_trace(scripts_dir, story_id, lang, "ETAPA 9.5 — Validado final", lang_script)

        # ── ETAPA 10 — Titulo descritivo (para slug) + Hook de engajamento ───
        if dry_run:
            title_for_lang        = story_title
            hook_for_lang          = story_title
            closing_hook_for_lang  = ""
        else:
            logger.info("ETAPA 10 — Gerando titulo e hook (%s)", lang)
            translated_title = translator.translate_title(story_title, "en", lang)

            hook_type      = random.choice(["short", "narrative"])
            title_for_lang = title_gen.generate(
                story_text=lang_script,
                language=lang,
                original_title=translated_title,
                hook_type=hook_type,
            )
            logger.info("Titulo arquivo (%s): %s", lang, title_for_lang)

            hook_for_lang = title_gen.generate_hook(
                story_text=lang_script,
                language=lang,
                original_title=translated_title,
            )
            logger.info("Hook engajamento (%s): %s", lang, hook_for_lang)

            # ── ETAPA 10.5 — Validacao do titulo + hook ───────────────────────
            logger.info("ETAPA 10.5 — Validacao do titulo/hook (%s)", lang)
            title_for_lang, hook_for_lang = validator.validate_and_fix_title_hook(
                title_for_lang, hook_for_lang, lang_script, lang, story_id,
                story_title=story_title, narrator_gender=narrator_gender,
            )
            logger.info("Titulo/hook validados (%s): %s | %s", lang, title_for_lang, hook_for_lang)

            # ── Hook de encerramento (CTA) — gerado uma vez, usado na ultima parte
            closing_hook_for_lang = title_gen.generate_closing_hook(
                story_text=lang_script,
                language=lang,
                original_title=translated_title,
            )
            logger.info("Hook encerramento (%s): %s", lang, closing_hook_for_lang)

        # ── ETAPA 11 — Injetar hook de engajamento no início do script ────────
        if not dry_run:
            logger.info("ETAPA 11 — Injetando hook de engajamento")
            lang_script = inject_title_as_hook(lang_script, hook_for_lang)
            save_script_trace(scripts_dir, story_id, lang, "ETAPA 11 — Script final com hook (narrado)", lang_script)

        # ── ETAPA 11.5 — Salvar script final narrado ──────────────────────────
        if not dry_run:
            final_script_dir = BASE_DIR / "data" / "scripts" / lang
            final_script_dir.mkdir(parents=True, exist_ok=True)
            final_script_path = final_script_dir / f"{story_id}_final.txt"
            final_script_path.write_text(lang_script, encoding="utf-8")
            logger.info("Script final salvo: %s", final_script_path.name)

        # ── ETAPA 12 — Split ─────────────────────────────────────────────────
        adapted_for_split                = adapted.copy()
        adapted_for_split["full_script"] = lang_script
        adapted_for_split["language"]    = lang
        parts = split_story(
            adapted_for_split,
            lang,
            hook_text=hook_for_lang,
            closing_hook_text=closing_hook_for_lang,
        )
        logger.info("%d parte(s) para %s", len(parts), lang.upper())

        for part_data in parts:
            part_num = part_data["part_number"]
            total    = part_data["total_parts"]
            date_str = datetime.now().strftime("%Y%m%d")
            slug     = FileOrganizer.slugify(title_for_lang)
            part_sfx = f"_pt{part_num}of{total}" if total > 1 else ""
            stem     = f"{slug}_{date_str}_{lang}{part_sfx}"

            if dry_run:
                logger.info("[dry-run] %s — %.1f min", stem, part_data["estimated_min"])
                continue

            parts_attempted += 1
            part_script = part_data["full_script"]

            # ── ETAPA 13 — Voz com genero correto ────────────────────────────
            logger.info("ETAPA 13 — Voz: %s (genero=%s)", stem, narrator_gender)
            audio_dir  = BASE_DIR / "data" / "audio" / lang
            audio_path = audio_dir / (stem + ".mp3")
            audio_ok   = voice_gen.generate(
                part_script, lang, audio_path,
                narrator_gender=narrator_gender,
            )
            if not audio_ok:
                logger.error("Falha na voz — pulando %s", stem)
                notify_pipeline_result("failure", {
                    "story_title": title_for_lang or story_title,
                    "language":    lang,
                    "stage":       "Voz (ETAPA 13, edge-tts)",
                    "reason":      f"geracao de audio falhou para {stem}",
                }, config)
                continue

            # ── ETAPA 14 — Subtitulos ASS animados ──────────────────────────
            logger.info("ETAPA 14 — Subtitulos ASS word-by-word")
            sub_dir  = BASE_DIR / "data" / "subtitles" / lang
            ass_path = sub_dir / (stem + ".ass")
            sub_gen.generate(audio_path, lang, ass_path, script_text=part_script)
            if not ass_path.exists():
                logger.warning("ASS nao gerado — video sem legenda")
                ass_path = None

            # ── ETAPA 16 — Thumbnail JPG + Card .mov animado ─────────────────
            logger.info("ETAPA 16 — Thumbnail estatica + Card hook overlay animado")
            thumb_dir  = BASE_DIR / "data" / "thumbnails" / lang
            thumb_path = thumb_dir / (stem + "_thumb.jpg")

            thumb_ok = thumb_gen.generate(hook_for_lang, lang, thumb_path)
            if not thumb_ok:
                logger.warning("Thumbnail nao gerada — continuando sem ela")
                thumb_path = None

            # Estima duração do hook pela contagem de palavras
            # (~2.8 palavras/s para narração natural + 1.5s de margem)
            hook_words    = len(hook_for_lang.split())
            hook_duration = hook_words / 2.8 + 1.5

            # Lê duração real do áudio para evitar fantasma do card overlay
            audio_duration = get_audio_duration(audio_path)
            if audio_duration:
                logger.info("Duracao do audio: %.2fs", audio_duration)
            else:
                logger.warning(
                    "Duracao do audio nao disponivel — .mov sem extensao transparente"
                )

            # Gera card .mov com fade-in e fade-out via Pillow
            card_mov_path = thumb_dir / (stem + "_card.mov")
            card_mov_path = thumb_gen.render_hook_card_video(
                hook_text      = hook_for_lang,
                lang           = lang,
                output_path    = card_mov_path,
                hook_duration  = hook_duration,
                fade_in        = 0.5,
                fade_out       = 0.5,
                fps            = 30,
                audio_duration = audio_duration,
            )
            if not card_mov_path:
                # Fallback: PNG estático sem fade
                logger.warning("Card .mov falhou — tentando fallback PNG estatico")
                card_png_path = thumb_dir / (stem + "_card.png")
                card_mov_path = thumb_gen.render_hook_card(
                    hook_for_lang, lang, card_png_path,
                )
                if not card_mov_path:
                    logger.warning("Card PNG tambem falhou — video sem card overlay")

            # ── ETAPA 15 — Video com background + card overlay ───────────────
            logger.info("ETAPA 15 — Renderizando video (background: Shorts/ + card overlay)")

            vid_dir    = BASE_DIR / "data" / "videos" / lang
            video_path = vid_dir / (stem + ".mp4")
            vid_ok     = vid_ren.render(
                audio_path     = audio_path,
                subtitle_path  = ass_path,
                output_path    = video_path,
                story_id       = story_id,
                hook_card_path = card_mov_path,   # .mov com alpha (ou .png fallback)
                hook_duration  = hook_duration,
            )
            if not vid_ok:
                logger.error("Falha no video — verifique FFmpeg e pasta background/Shorts/")
                notify_pipeline_result("failure", {
                    "story_title": title_for_lang or story_title,
                    "language":    lang,
                    "stage":       "Video (ETAPA 15, FFmpeg)",
                    "reason":      f"renderizacao falhou para {stem} — verifique FFmpeg/background",
                }, config)
                continue

            # ── ETAPA 17 — Metadados ─────────────────────────────────────────
            logger.info("ETAPA 17 — Metadados SEO")
            meta_dir  = BASE_DIR / "data" / "scripts" / lang
            meta_path = meta_dir / (stem + "_meta.json")
            meta      = meta_gen.generate(
                story,
                lang,
                part_num,
                total,
                hook=hook_for_lang,
                narrator_gender=narrator_gender,
            )
            meta["title"]           = title_for_lang
            meta["narrator_gender"] = narrator_gender

            # ── ETAPA 17.5 — Validacao de metadados (descricao + tags) ───
            logger.info("ETAPA 17.5 — Validacao de metadados (%s)", lang)
            meta_description_orig = meta.get("description", "")
            meta_tags_orig         = meta.get("hashtags", [])

            new_description, new_tags = validator.validate_and_fix_metadata(
                meta_description_orig, meta_tags_orig, part_script, lang, story_id,
                story_title=story_title,
            )

            if new_description != meta_description_orig or new_tags != meta_tags_orig:
                logger.info("Metadados corrigidos — reconstruindo blocos youtube/tiktok (%s)", lang)
                meta = meta_gen.rebuild_after_validation(meta, new_description, new_tags)

            meta_gen.save(meta, meta_path)

            # ── ETAPA 18 — Organizacao ───────────────────────────────────────
            logger.info("ETAPA 18 — Export: %s", stem)
            organizer.organize_output(
                story_id       = story_id,
                language       = lang,
                part           = part_num,
                total          = total,
                video_path     = video_path,
                thumbnail_path = thumb_path,
                metadata_path  = meta_path,
                story_title    = title_for_lang,
            )
            parts_done += 1

    logger.info("=" * 60)
    logger.info("Pipeline concluido. Exports em: data/exports/")

    # ── Consumo de LLM da execucao inteira (todos os estagios) ────────────────
    duration_min = (datetime.now() - pipeline_started_at).total_seconds() / 60
    logger.info("=" * 60)
    logger.info("CONSUMO DE LLM NESTA EXECUCAO:\n%s", telemetry.format_summary())
    tokens_totais = telemetry.total_tokens()
    if tokens_totais and duration_min > 0:
        logger.info(
            "Media: %.0f tokens/min ao longo de %.1f min (teto do free tier: 8000 TPM)",
            tokens_totais / duration_min, duration_min,
        )

    # ── Aviso final de alto nivel (Telegram) ──────────────────────────────────
    # Ate aqui, sucesso/falha so existiam no log local — isso e o unico ponto
    # que resume a execucao inteira pro operador, sem precisar abrir o log.
    if not dry_run:
        event = "success" if parts_done == parts_attempted and parts_done > 0 else (
            "partial" if parts_done > 0 else "failure"
        )
        notify_pipeline_result(event, {
            "story_title": story_title,
            "language":    ", ".join(languages).upper(),
            "parts_done":  f"{parts_done}/{parts_attempted}",
            "duration":    f"{duration_min:.1f} min",
            "token_usage": f"{tokens_totais} tokens / {telemetry.total_calls()} chamadas "
                           f"(validador: {validator.get_token_usage_summary()})",
        }, config)

        # ── Alerta separado: pipeline rodou sem LLM em algum estagio ──────────
        # Este e o unico aviso de que a qualidade caiu — sem ele, o fallback
        # para regras e invisivel (ja aconteceu de verdade quando a Groq
        # descontinuou os modelos llama).
        if telemetry.had_fallback():
            from scheduler.notifier import send_admin_alert
            alerta = telemetry.format_fallback_alert()
            alerta += f"\n\nHistoria: {story_title[:60]}"
            try:
                if send_admin_alert(alerta, config):
                    logger.info("Alerta de fallback enviado no Telegram")
                else:
                    logger.warning("Alerta de fallback NAO enviado (Telegram indisponivel)")
            except Exception as e:
                logger.warning("Falha ao enviar alerta de fallback: %s", e)


def silenciar_loggers_sensiveis() -> None:
    """
    Sobe o nivel de loggers de bibliotecas HTTP para WARNING.

    CRITICO PARA REPOSITORIO PUBLICO: o httpx loga a URL completa em nivel
    INFO, e a URL da API do Telegram contem o token do bot:
        POST https://api.telegram.org/bot<TOKEN>/sendMessage
    Logs de execucao do GitHub Actions em repositorio publico sao visiveis
    para qualquer pessoa — sem isso, o token do bot vaza a cada execucao.
    """
    for nome in ("httpx", "httpcore", "urllib3", "telegram", "googleapiclient.discovery"):
        logging.getLogger(nome).setLevel(logging.WARNING)


def setup_logging(log_dir: Path, level: str = "INFO") -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / ("pipeline_" + datetime.now().strftime("%Y%m%d") + ".log")
    fmt      = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    silenciar_loggers_sensiveis()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reddit Stories Pipeline v3")
    parser.add_argument("--lang",        nargs="+",      default=["pt"])
    parser.add_argument("--dry-run",     action="store_true")
    parser.add_argument(
        "--test-story",
        action="store_true",
        help="Pula etapas 1 e 2 usando a historia de teste definida em TEST_STORY",
    )
    args = parser.parse_args()

    config = load_config()
    setup_logging(BASE_DIR / "data" / "logs")
    run_pipeline(config, args.lang, dry_run=args.dry_run, test_story=args.test_story)