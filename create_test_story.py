#!/usr/bin/env python3
"""
create_test_story.py
====================
Cria uma história de teste em data/raw/ para validar
o pipeline completo sem depender do Reddit.

Uso:
    python create_test_story.py
    python create_test_story.py --lang pt
    python create_test_story.py --story 2
"""
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).parent
RAW_DIR  = BASE_DIR / "data" / "raw"

# ── HISTÓRIAS DE TESTE ────────────────────────────────────────────────────────
STORIES = {
    1: {
        "id": "test_story_001",
        "subreddit": "AITAH",
        "title": "AITA for refusing to give my sister half of my inheritance?",
        "text": (
            "My parents passed away last year within months of each other. "
            "It was the hardest period of my life. They left me their house and their savings. "
            "My sister was left out of the will completely, and I know why — she had borrowed "
            "large sums of money from my parents over the years and never paid any of it back. "
            "My parents told me privately, multiple times, that they considered those loans her "
            "inheritance and that the rest should go to me.\n\n"
            "After the funeral, my sister came to me and said she felt it was unfair. "
            "She said our parents were old-fashioned and that I should do the right thing "
            "and split everything with her fifty-fifty. I told her I understood she was grieving "
            "but that I was going to respect our parents wishes.\n\n"
            "She stopped talking to me after that. Then came the family pressure. "
            "Aunts, uncles, cousins — everyone started calling me selfish and greedy. "
            "One aunt told me I was destroying the family over money. "
            "My boyfriend thinks I am completely in the right. "
            "My best friend thinks I should give her at least something just to keep the peace.\n\n"
            "The thing is, I know my sister. If I give her anything now, "
            "she will come back for more. She has a pattern of borrowing and never returning. "
            "She owes other family members money too. "
            "And my parents made their wishes very clear to me while they were alive.\n\n"
            "I keep second-guessing myself because I do love my sister. "
            "We were close growing up. But I also feel like I would be betraying my parents "
            "if I went against what they wanted. "
            "Am I really the bad guy here? Was I wrong to refuse?\n\n"
            "Edit: Thank you all for the responses. "
            "To clarify — the loans totaled over forty thousand dollars over ten years. "
            "My parents documented everything. I have the paperwork."
        ),
        "score": 14200,
        "upvote_ratio": 0.96,
        "num_comments": 512,
        "created_utc": 1700000000,
    },
    2: {
        "id": "test_story_002",
        "subreddit": "MaliciousCompliance",
        "title": "My boss told me to follow the rules exactly. So I did.",
        "text": (
            "I worked at a large retail store for about three years. "
            "For most of that time my manager and I had a decent relationship — "
            "not close, but professional and respectful.\n\n"
            "That changed when a new district manager came in. "
            "My manager, trying to impress the new boss, started enforcing every minor rule "
            "with an iron fist. Things that nobody had cared about for years suddenly became "
            "write-up worthy offenses.\n\n"
            "One day he called me into his office and told me, in front of HR, "
            "that I needed to follow the employee handbook to the letter. "
            "No exceptions. No shortcuts. Exactly as written.\n\n"
            "I smiled and said absolutely.\n\n"
            "What my manager did not know — or had forgotten — was that the employee handbook "
            "had a clause requiring management to provide a ten-minute break "
            "for every two hours of work, and a thirty-minute unpaid lunch for shifts over five hours. "
            "These breaks had to be logged by a supervisor. "
            "In practice, nobody tracked this. We just took breaks when we could.\n\n"
            "Starting the next day, I began requesting my breaks exactly on schedule. "
            "Every two hours I walked to my manager and told him I was taking my handbook-mandated break "
            "and needed him to log it. During busy periods. During rushes. Every single time.\n\n"
            "Within two days other employees noticed and started doing the same thing. "
            "The manager was running around logging breaks instead of managing the floor.\n\n"
            "By the end of the week he called me back into his office. "
            "He said we could go back to the old informal system. "
            "I said I just wanted to follow the handbook. Exactly as written.\n\n"
            "He never micromanaged me again."
        ),
        "score": 28500,
        "upvote_ratio": 0.98,
        "num_comments": 743,
        "created_utc": 1700000100,
    },
    3: {
        "id": "test_story_003",
        "subreddit": "relationship_advice",
        "title": "I found out my partner of 5 years has been lying about something major",
        "text": (
            "I have been with my partner for five years. "
            "We live together, we have a dog together, we have talked about marriage. "
            "I thought I knew everything about them.\n\n"
            "Two weeks ago I was helping them organize some documents — "
            "tax stuff, nothing dramatic — and I found something that did not add up. "
            "A degree certificate from a university I had never heard them mention. "
            "In a field completely unrelated to their current job.\n\n"
            "I did not say anything right away. I started paying attention instead. "
            "Little things that had always seemed slightly off suddenly made more sense. "
            "The way they avoided certain topics. The vague answers about their past. "
            "The friends from that era who I had never met.\n\n"
            "After a week of quietly piecing things together I sat them down and asked directly. "
            "At first they deflected. Then they got defensive. "
            "Then, when I told them what I had found, they broke down.\n\n"
            "The truth was that they had studied something completely different from what they told me, "
            "had a whole chapter of their life they had hidden "
            "because they were ashamed of some choices they made back then. "
            "No other relationship. No criminal record. Just a past they had buried.\n\n"
            "I do not know how to feel. On one hand I understand shame. "
            "I understand wanting to leave parts of yourself behind. "
            "On the other hand, five years. Five years and they did not trust me enough.\n\n"
            "We have been talking every night since. They are in tears every time. "
            "They say they were terrified of losing me if I knew the truth.\n\n"
            "My question is — is this something people recover from? "
            "Has anyone been through something like this and come out the other side? "
            "I love them. But I keep thinking: what else do I not know?"
        ),
        "score": 9800,
        "upvote_ratio": 0.92,
        "num_comments": 384,
        "created_utc": 1700000200,
    },
}


def create_story(story_num: int = 1) -> Path:
    """Cria o JSON da história de teste em data/raw/."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if story_num not in STORIES:
        print(f"  Story {story_num} não existe. Opções: {list(STORIES.keys())}")
        story_num = 1

    story = STORIES[story_num].copy()
    story["extracted_at"] = datetime.now(timezone.utc).isoformat()
    story["url"]          = f"https://reddit.com/r/{story['subreddit']}/test"
    story["word_count"]   = len(story["text"].split())

    out_path = RAW_DIR / f"{story['id']}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(story, f, ensure_ascii=False, indent=2)

    return out_path


def main():
    parser = argparse.ArgumentParser(description="Cria história de teste para o pipeline")
    parser.add_argument("--story", type=int, default=1,
                        choices=[1, 2, 3],
                        help="Número da história (1=herança, 2=trabalho, 3=relacionamento)")
    args = parser.parse_args()

    print("\n  Reddit Stories Pipeline — Criador de História de Teste")
    print("  " + "─" * 50)

    path = create_story(args.story)
    story = STORIES[args.story]

    print(f"\n  ✓  História criada em: {path}")
    print(f"     ID         : {story['id']}")
    print(f"     Subreddit  : r/{story['subreddit']}")
    print(f"     Título     : {story['title'][:60]}...")
    print(f"     Palavras   : {len(story['text'].split())}")
    print(f"     Score      : {story['score']:,} pts ({story['upvote_ratio']*100:.0f}% upvotes)")

    est_min = len(story["text"].split()) / 130
    print(f"     Duração est: {est_min:.1f} min de narração")

    print(f"\n  PRÓXIMO PASSO:")
    print(f"     python main.py --lang pt")
    print(f"\n  Para testar os 3 idiomas:")
    print(f"     python main.py --lang pt en es")
    print(f"\n  Histórias disponíveis:")
    for n, s in STORIES.items():
        marker = " ←" if n == args.story else ""
        print(f"     --story {n}  {s['title'][:55]}...{marker}")
    print()


if __name__ == "__main__":
    main()
