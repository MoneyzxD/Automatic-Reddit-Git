#!/usr/bin/env python3
"""
main.py
=======
Orquestrador principal do Reddit Stories Pipeline — v3.

Fluxo por historia (1 historia por execucao):
    0.  Preflight      -> LanguageTool obrigatorio, antes da extracao (exceto dry-run)
    1.  Extracao       -> Reddit com sessao logada
    2.  Filtragem      -> score 0-100
    3.  Siglas EN      -> expansao de siglas no texto original (28F -> 28-year-old woman)
    3.5 Perfil        -> resolve e trava o narrador uma vez, antes de adaptar
    4.  Adaptacao      -> limpeza narrativa via Groq (fallback: regras)
    4.5 Validacao      -> valida script adaptado (EN) antes de traduzir
    5.  Traducao       -> script por idioma
    5.5 Validacao      -> valida script traduzido (por idioma)
    6.  Siglas PT/ES   -> expansao de siglas no texto traduzido
    8.  Naturalizacao  -> LLM com genero correto desde o inicio
    9.5 Guardiao       -> revisa naturalizacao contra traducao aprovada e perfil travado
    10. Titulo         -> gerador viral baseado no titulo original do Reddit
    10.5 Guardiao      -> revisa titulo, hook inicial e encerramento contra fatos validados
    11. Hook           -> titulo injetado como primeira frase do script
    12. Split          -> partes de ate 2:45 (teto de Short do YouTube), com hook repetido e encerramento
    12.5 Guardiao      -> revisa todas as partes completas
    12.6 Metadados     -> SEO localizado por parte, antes de voz/renderizacao
    12.7 Guardiao      -> revisa descricoes localizadas
    12.9 Gate final    -> revisa exatamente a parte completa imediatamente antes da voz
    13. Voz            -> edge-tts com voz do genero correto
    14. Legendas       -> ASS animado palavra por palavra
    15. Video          -> FFmpeg 1080x1920 + ASS + background automatico (Shorts/)
    16. Thumbnail      -> Pillow (JPG estatica + .mov card com fade)
    18. Organizacao    -> exporta/enfileira somente depois de concluir todas as partes do idioma

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
from stages.narrator_profile import NarratorProfile
from stages.script_guardian import QualityRejected, QualityUnavailable, ScriptReview, ReviewIssue

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


def resolve_story_narrator(resolver, story_id: str, title: str, source_text: str) -> NarratorProfile:
    """Resolve uma unica identidade a partir da fonte anterior a adaptacao."""
    return resolver.resolve(story_id=story_id, title=title, original_text=source_text)


def attach_narrator_profile(payload: dict, profile: NarratorProfile) -> dict:
    """Enriquece uma copia do payload sem alterar o perfil nem o chamador."""
    if profile.narration_gender not in ("male", "female"):
        raise ValueError("Genero da narracao deve ser male ou female")
    return {
        **payload,
        "narrator_gender": profile.narration_gender,
        "narrator_profile_id": profile.profile_id,
        "narrator_confidence": profile.confidence,
        "narrator_method": profile.decision_method,
    }


def review_and_generate_audio(*, guardian, voice_generator, source_text: str,
                              part_script: str, language: str, story_id: str,
                              profile: NarratorProfile, part_number: int,
                              audio_path: Path) -> tuple[str, bool]:
    """A última revisão recebe exatamente a parte que será narrada."""
    review = guardian.review_and_fix(
        source_text=source_text, candidate_text=part_script, language=language,
        stage="pre_tts", story_id=story_id, profile=profile,
        final_gate=True, part=part_number,
    )
    if review.status != "approved":
        raise (QualityUnavailable if review.status == "unavailable" else QualityRejected)(review)
    approved = review.approved_text
    return approved, voice_generator.generate(
        approved, language, audio_path, narrator_gender=profile.narration_gender,
    )


def quarantine_review(base_dir: Path, review: ScriptReview, candidate_text: str, *,
                      story_id: str, language: str, stage: str,
                      profile: NarratorProfile, source_text: str,
                      part_number: int | None = None) -> Path:
    """Persiste a revisão atomicamente, dentro da raiz e com a política do log."""
    from dataclasses import asdict
    import hashlib
    import os
    import tempfile
    from utils.telemetry import append_quality_report

    for value in (story_id, language, stage):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("Identificador inseguro para quarentena")
    if part_number is not None and (type(part_number) is not int or part_number < 1):
        raise ValueError("Número de parte inválido")
    root = Path(base_dir).resolve()
    directory = root / "data" / "quarantine" / story_id
    suffix = f"_part{part_number}" if part_number is not None else ""
    destination = directory / f"{language}_{stage}{suffix}.json"
    if not destination.resolve().is_relative_to(root):
        raise ValueError("Quarentena fora da raiz do projeto")
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "story_id": story_id, "language": language, "stage": stage,
        "part_number": part_number, "profile_id": profile.profile_id,
        "profile": asdict(profile), "source_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        "candidate_sha256": hashlib.sha256(candidate_text.encode("utf-8")).hexdigest(),
        "candidate_text": candidate_text,
        "review": {**asdict(review), "report_path": str(review.report_path) if review.report_path else None},
    }
    with tempfile.NamedTemporaryFile(dir=directory, prefix=".review-", suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        append_quality_report(temporary, payload)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def run_pipeline(
    config: dict, languages: list, dry_run: bool = False,
    test_story: bool = False, max_parts: int | None = None,
) -> None:
    from stages.adapter import StoryAdapter
    from stages.translator import ScriptTranslator, TranslationFailed
    from stages.naturalizer import ScriptNaturalizer
    from stages.narrator_profile import NarratorProfileResolver, save_profile
    from stages.titler import TitleGenerator
    from stages.splitter import split_story
    from stages.voice import VoiceGenerator
    from stages.word_timing import load_word_boundaries
    from stages.subtitle import SubtitleGenerator
    from stages.video import VideoRenderer
    from stages.thumbnail import ThumbnailGenerator
    from stages.metadata import MetadataGenerator
    from stages.organizer import FileOrganizer
    from stages.script_guardian import ScriptGuardian
    from utils.db import PipelineDB
    from utils import environment as env, telemetry
    from scheduler.notifier import notify_pipeline_result

    languages = list(dict.fromkeys("pt" if lang == "pt-br" else lang for lang in languages))
    logger = logging.getLogger("pipeline.main")
    pipeline_started_at = datetime.now()
    telemetry.reset()
    logger.info("Ambiente: %s", env.describe(BASE_DIR))
    guardian = None if dry_run else ScriptGuardian(config.get("script_quality", {}), base_dir=BASE_DIR)
    if guardian:
        try:
            guardian.assert_ready()
        except QualityUnavailable:
            notify_pipeline_result("failure", {
                "stage": "preflight", "dependency": "LanguageTool / guardião",
                "reason": "Dependência obrigatória indisponível; lote interrompido",
            }, config)
            raise

    video_config = {**config.get("video", {}), "background_dir": str(env.background_dir(BASE_DIR))}
    db = PipelineDB(env.db_path(BASE_DIR))
    adapter_config = {**config.get("adapter", {})}
    if dry_run:
        adapter_config["llm_enabled"] = False
    adapter = StoryAdapter(adapter_config)
    translator = ScriptTranslator(config.get("translator", {}))
    naturalizer = ScriptNaturalizer(config.get("naturalizer", {}))
    title_gen = TitleGenerator(config.get("naturalizer", {}))
    voice_gen = VoiceGenerator(config.get("voice", {}))
    sub_gen = SubtitleGenerator(config.get("subtitles", {}))
    vid_ren = VideoRenderer(video_config)
    thumb_gen = ThumbnailGenerator(config.get("thumbnail", {}))
    meta_gen = MetadataGenerator(config.get("metadata", {}))
    organizer = FileOrganizer(config, db)
    scripts_dir = BASE_DIR / "data" / "scripts"
    parts_attempted = parts_done = 0
    quality_skipped = False

    if test_story:
        story = TEST_STORY
    else:
        from stages.extractor import RedditExtractor
        from stages.filter import StoryFilter
        extractor = RedditExtractor(config.get("extraction", {}))
        f_filter = StoryFilter(config.get("filtering", {}), db)
        if not dry_run:
            extractor.run(get_subreddits(config))
        else:
            logger.info("[dry-run] Extração ignorada")
        approved = f_filter.run(BASE_DIR / "data" / "raw")
        if not approved:
            logger.warning("Nenhuma história aprovada. Verifique data/raw/")
            return
        story = approved[0]
    if not dry_run:
        db.insert_story(story)

    story_id = story["id"]
    story_title = story.get("title", story_id)
    expanded_source = expand_acronyms_translated(expand_age_gender_en(story.get("text", "")), "en")
    resolver = NarratorProfileResolver(config.get("narrator_profile", {}), semantic_enabled=not dry_run)
    profile = resolve_story_narrator(resolver, story_id, story_title, expanded_source)
    narrator_gender = profile.narration_gender
    story_for_adapter = attach_narrator_profile({**story, "text": expanded_source}, profile)
    profile_trace = (f"profile_id={profile.profile_id}; genero={narrator_gender}; "
                     f"metodo={profile.decision_method}; confianca={profile.confidence:.2f}")
    logger.info("Perfil do narrador: %s", profile_trace)
    if not dry_run:
        save_profile(profile, BASE_DIR)
    adapted = attach_narrator_profile(adapter.adapt(story_for_adapter), profile)
    clean_script = adapted["full_script"]
    context = {}

    def checkpoint(source, candidate, language, stage, part=None):
        context.update(source_text=source, candidate_text=candidate, language=language,
                       stage=stage, part_number=part)
        review = guardian.review_and_fix(
            source_text=source, candidate_text=candidate, language=language,
            stage=stage, story_id=story_id, profile=profile, part=part,
        )
        if review.status != "approved":
            raise (QualityUnavailable if review.status == "unavailable" else QualityRejected)(review)
        save_script_trace(scripts_dir, story_id, language, stage, review.approved_text)
        return review

    def translation_text(result, source, language, stage):
        candidate = result.text or "".join(chunk.translated_text or "" for chunk in result.chunks)
        context.update(source_text=source, candidate_text=candidate, language=language,
                       stage=stage, part_number=None)
        try:
            return result.require_text()
        except TranslationFailed:
            review = ScriptReview(result.status, candidate, (
                ReviewIssue("language", "critical", "Tradução não aprovada", origin="translation"),
            ), (), 0, False, "")
            raise (QualityUnavailable if result.status == "unavailable" else QualityRejected)(review) from None

    def failed_review(error):
        nonlocal quality_skipped
        quality_skipped = True
        quarantine_path = quarantine_review(
            BASE_DIR, error.review, context["candidate_text"], story_id=story_id,
            language=context["language"], stage=context["stage"], profile=profile,
            source_text=context["source_text"], part_number=context["part_number"],
        )
        dependency = ""
        if isinstance(error, QualityUnavailable):
            origins = {issue.origin for issue in error.review.issues}
            dependency = ("Tradução" if "translation" in origins else
                          "LanguageTool" if any("LanguageTool" in issue.message for issue in error.review.issues)
                          else "Revisão semântica / glossário")
        notify_pipeline_result("failure" if dependency else "partial", {
            "story_title": story_title, "language": context["language"], "stage": context["stage"],
            "part": context["part_number"], "profile_method": profile.decision_method,
            "profile_confidence": f"{profile.confidence:.2f}",
            "issue_categories": ", ".join(sorted({issue.category for issue in error.review.issues})),
            "quarantine_path": str(quarantine_path.relative_to(BASE_DIR.resolve())),
            "dependency": dependency, "reason": "Indisponibilidade obrigatória" if dependency else "Conteúdo reprovado",
        }, config)

    factual_context = ""
    if not dry_run:
        save_script_trace(scripts_dir, story_id, "en", "Perfil do narrador", profile_trace, reset=True)
        try:
            review = checkpoint(expanded_source, clean_script, "en", "adaptation")
            clean_script, factual_context = review.approved_text, review.factual_context
            adapted["full_script"] = clean_script
        except QualityRejected as error:
            failed_review(error)
            return
        except QualityUnavailable as error:
            failed_review(error)
            raise

    lang_order = [lang for lang in ("pt", "es", "en") if lang in languages]
    lang_order += [lang for lang in languages if lang not in lang_order]
    for lang in lang_order:
        try:
            lang_script = clean_script
            lang_facts = factual_context
            if not dry_run:
                context.update(source_text=clean_script, candidate_text="", language=lang,
                               stage="translation", part_number=None)
                try:
                    translations = translator.translate_all(
                        script_text=clean_script, story_id=story_id, scripts_dir=scripts_dir,
                        languages=[lang], source_lang="en", force=test_story,
                    )
                except TranslationFailed as error:
                    translation_text(error.result, clean_script, lang, "translation")
                    raise
                lang_script = translation_text(translations[lang], clean_script, lang, "translation")
                review = checkpoint(clean_script, lang_script, lang, "translation")
                approved_translation = review.approved_text
                expanded_translation = expand_acronyms_translated(approved_translation, lang)
                naturalized = naturalizer.naturalize(expanded_translation, lang, narrator_gender)
                review = checkpoint(approved_translation, naturalized, lang, "naturalization")
                lang_script, lang_facts = review.approved_text, review.factual_context

            validated_story = lang_script
            derived_source = validated_story + (f"\n\nFatos validados:\n{lang_facts}" if lang_facts else "")
            if dry_run:
                title_for_lang = hook_for_lang = story_title
                closing_hook_for_lang = ""
            else:
                context.update(source_text=story_title, candidate_text="", language=lang,
                               stage="title_translation", part_number=None)
                try:
                    translated_title = translator.translate_title(story_title, "en", lang)
                except TranslationFailed as error:
                    translation_text(error.result, story_title, lang, "title_translation")
                    raise
                title_args = dict(story_text=validated_story, language=lang, original_title=translated_title,
                                  narrator_gender=narrator_gender, factual_context=lang_facts)
                title_for_lang = checkpoint(
                    derived_source, title_gen.generate(**title_args, hook_type=random.choice(["short", "narrative"])),
                    lang, "title").approved_text
                hook_for_lang = checkpoint(
                    derived_source, title_gen.generate_hook(**title_args), lang, "opening_hook").approved_text
                closing_hook_for_lang = checkpoint(
                    derived_source, title_gen.generate_closing_hook(**title_args), lang, "closing_hook").approved_text
                lang_script = checkpoint(
                    derived_source, inject_title_as_hook(validated_story, hook_for_lang),
                    lang, "injected_hook").approved_text

            adapted_for_split = attach_narrator_profile(
                {**adapted, "full_script": lang_script, "language": lang}, profile)
            parts = split_story(adapted_for_split, lang, hook_text=hook_for_lang,
                                closing_hook_text=closing_hook_for_lang)
            limit = min(3, max_parts) if max_parts is not None else 3
            if len(parts) > limit:
                logger.warning("História ignorada em %s: %d partes para limite de %d", lang, len(parts), limit)
                continue
            prepared = []
            for part_data in parts:
                part_num, total = part_data["part_number"], part_data["total_parts"]
                suffix = f"_pt{part_num}of{total}" if total > 1 else ""
                stem = f"{FileOrganizer.slugify(title_for_lang)}_{datetime.now():%Y%m%d}_{lang}{suffix}"
                if dry_run:
                    logger.info("[dry-run] %s — %.1f min", stem, part_data["estimated_min"])
                    continue
                part_script = checkpoint(derived_source, part_data["full_script"], lang, "split_part", part_num).approved_text
                meta = meta_gen.generate(
                    attach_narrator_profile({**story, "title": title_for_lang}, profile), lang,
                    part_number=part_num, total_parts=total, hook=hook_for_lang,
                    narrator_gender=narrator_gender, localized_script=part_script, factual_context=lang_facts,
                )
                meta = attach_narrator_profile(meta, profile)
                description = checkpoint(derived_source, meta["description"], lang, "metadata", part_num).approved_text
                meta = meta_gen.rebuild_after_validation(meta, description, meta.get("hashtags", []))
                prepared.append((part_num, total, stem, part_script, meta))
            if dry_run:
                continue

            # Todas as partes/metadados são aprovados antes de qualquer trabalho caro.
            completed = []
            language_complete = True
            for part_num, total, stem, part_script, meta in prepared:
                parts_attempted += 1
                audio_path = BASE_DIR / "data" / "audio" / lang / (stem + ".mp3")
                context.update(source_text=derived_source, candidate_text=part_script, language=lang,
                               stage="pre_tts", part_number=part_num)
                part_script, audio_ok = review_and_generate_audio(
                    guardian=guardian, voice_generator=voice_gen, source_text=derived_source,
                    part_script=part_script, language=lang, story_id=story_id, profile=profile,
                    part_number=part_num, audio_path=audio_path,
                )
                if not audio_ok:
                    notify_pipeline_result("failure", {"story_title": story_title, "language": lang,
                                           "stage": "Voz", "reason": "Geração de áudio falhou"}, config)
                    language_complete = False
                    break
                # O hook narrado também pode receber uma correção no gate final.
                narrated_hook = part_script.split("\n\n", 1)[0].strip()
                meta["hook"] = narrated_hook
                meta = meta_gen.rebuild_after_validation(meta, meta["description"], meta.get("hashtags", []))
                meta_path = scripts_dir / lang / (stem + "_meta.json")
                meta_gen.save(meta, meta_path)
                final_path = scripts_dir / lang / f"{story_id}_part{part_num}_final.txt"
                final_path.write_text(part_script, encoding="utf-8")
                hook_words = len(narrated_hook.split())
                boundaries = load_word_boundaries(voice_gen.get_boundaries_path(audio_path))
                if boundaries and len(boundaries) >= hook_words > 0:
                    last = boundaries[hook_words - 1]
                    hook_duration = float(last["start"]) + float(last["duration"])
                else:
                    hook_duration = hook_words / 2.8 + 1.5
                ass_path = BASE_DIR / "data" / "subtitles" / lang / (stem + ".ass")
                subtitle_ok = sub_gen.generate(audio_path, lang, ass_path, script_text=part_script,
                                               skip_before=hook_duration)
                if not subtitle_ok:
                    notify_pipeline_result("failure", {"story_title": story_title, "language": lang,
                                           "stage": "Legendas", "reason": "Geração de legendas falhou"}, config)
                    language_complete = False
                    break
                if not ass_path.exists():
                    ass_path = None
                thumb_dir = BASE_DIR / "data" / "thumbnails" / lang
                thumb_path = thumb_dir / (stem + "_thumb.jpg")
                if not thumb_gen.generate(narrated_hook, lang, thumb_path):
                    thumb_path = None
                card_path = thumb_gen.render_hook_card_video(
                    hook_text=narrated_hook, lang=lang, output_path=thumb_dir / (stem + "_card.mov"),
                    hook_duration=hook_duration, fade_in=0.5, fade_out=0.5, fps=30,
                    audio_duration=get_audio_duration(audio_path),
                )
                if not card_path:
                    card_path = thumb_gen.render_hook_card(narrated_hook, lang, thumb_dir / (stem + "_card.png"))
                video_path = BASE_DIR / "data" / "videos" / lang / (stem + ".mp4")
                if not vid_ren.render(audio_path=audio_path, subtitle_path=ass_path, output_path=video_path,
                                      story_id=story_id, hook_card_path=card_path, hook_duration=hook_duration):
                    notify_pipeline_result("failure", {"story_title": story_title, "language": lang,
                                           "stage": "Vídeo", "reason": "Renderização falhou"}, config)
                    language_complete = False
                    break
                completed.append(dict(story_id=story_id, language=lang, part=part_num, total=total,
                                      video_path=video_path, thumbnail_path=thumb_path,
                                      metadata_path=meta_path, story_title=title_for_lang))
            # O organizer também enfileira: adiar a chamada impede publicar uma língua parcial.
            # ponytail: commit por item; transação em lote se for necessário tolerar queda durante a escrita da fila.
            if language_complete and len(completed) == len(prepared):
                for output in completed:
                    organizer.organize_output(**output)
                    parts_done += 1
        except QualityRejected as error:
            failed_review(error)
            continue
        except QualityUnavailable as error:
            failed_review(error)
            raise

    duration = (datetime.now() - pipeline_started_at).total_seconds() / 60
    logger.info("Pipeline concluído. Consumo de LLM:\n%s", telemetry.format_summary())
    if not dry_run and parts_attempted:
        event = ("success" if parts_done == parts_attempted and not quality_skipped else
                 "partial" if parts_done else "failure")
        notify_pipeline_result(event, {
            "story_title": story_title, "language": ", ".join(languages).upper(),
            "parts_done": f"{parts_done}/{parts_attempted}", "duration": f"{duration:.1f} min",
            "token_usage": f"{telemetry.total_tokens()} tokens / {telemetry.total_calls()} chamadas",
        }, config)
        if telemetry.had_fallback():
            from scheduler.notifier import send_admin_alert
            send_admin_alert(telemetry.format_fallback_alert(), config)


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


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reddit Stories Pipeline v3")
    parser.add_argument("--lang",        nargs="+",      default=["pt"])
    parser.add_argument("--dry-run",     action="store_true")
    parser.add_argument(
        "--test-story",
        action="store_true",
        help="Pula etapas 1 e 2 usando a historia de teste definida em TEST_STORY",
    )
    parser.add_argument(
        "--max-parts",
        type=int,
        choices=(1, 2, 3),
        default=None,
        help="so renderiza a historia se ela couber inteira neste numero de partes",
    )
    args = parser.parse_args(argv)

    config = load_config()
    setup_logging(BASE_DIR / "data" / "logs")
    try:
        run_pipeline(
            config, args.lang, dry_run=args.dry_run,
            test_story=args.test_story, max_parts=args.max_parts,
        )
    except QualityUnavailable:
        logging.getLogger("pipeline.main").error("Dependência obrigatória indisponível; lote interrompido")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
