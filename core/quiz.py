"""읽은 문서의 용어로 3지선다 퀴즈 만들기와 채점 (프로토타입 makeQuiz 이식). LLM을 쓰지 않는다.

출제 원칙
- 문제 용어, 정답, 오답 보기는 모두 검증된 사전(data/glossary.json)에서만 가져온다.
  AI가 쓴 용어 뜻은 원문 대조로 검증할 수 없어서 쓰지 않는다.
- 문서에 나온 사전 용어를 먼저 내고, 모자라면 문서와 같은 분야의 다른 사전 용어로 채운다.
"""
import random
from collections import Counter

from core.glossary import Glossary
from core.schema import CATEGORIES, DocType, GlossEntry, QuizItem, Term

KIND_CATEGORY = {"savings": "예적금", "deposit": "예적금", "loan": "대출", "card": "카드"}


def doc_entries(terms: list[Term], glossary: Glossary) -> list[GlossEntry]:
    """문서 용어 중 사전에 있는 항목만, 중복 없이 나온 순서대로."""
    out: list[GlossEntry] = []
    for t in terms:
        e = next((x for x in map(glossary.lookup, [t.term, *t.surfaces]) if x), None)
        if e and e not in out:
            out.append(e)
    return out


def quiz_category(kind: DocType, entries: list[GlossEntry]) -> str | None:
    """채울 때 쓸 분야. 문서 종류로 정하고, '기타' 문서면 문서 용어에 가장 많은 분야."""
    if kind in KIND_CATEGORY:
        return KIND_CATEGORY[kind]
    counts = Counter(e.category for e in entries)
    return counts.most_common(1)[0][0] if counts else None


def make_quiz(
    terms: list[Term],
    glossary: Glossary,
    kind: DocType = "other",
    n: int = 3,
    rng: random.Random | None = None,
) -> list[QuizItem]:
    rng = rng or random.Random()
    found = doc_entries(terms, glossary)
    picked = [(e, True) for e in rng.sample(found, min(n, len(found)))]

    if len(picked) < n:
        # 같은 분야 용어부터 채우고, 그래도 모자라면 다른 분야에서
        cat = quiz_category(kind, found)
        rest = [e for e in glossary.entries if e not in found]
        same = [e for e in rest if e.category == cat]
        other = [e for e in rest if e.category != cat]
        for pool in (same, other):
            need = n - len(picked)
            picked += [(e, False) for e in rng.sample(pool, min(need, len(pool)))]

    quiz = []
    for e, from_doc in picked:
        # 별칭을 공유하는 항목(현금서비스/단기카드대출)은 뜻이 거의 같아 오답으로 쓰면 정답이 둘이 된다
        related = glossary.related(e) | {e.term}
        pool = [g for g in glossary.entries if g.term not in related and g.meaning != e.meaning]
        same = [g for g in pool if g.category == e.category]  # 같은 분야 오답이 더 헷갈려서 학습에 좋다
        wrong = rng.sample(same if len(same) >= 2 else pool, min(2, len(pool)))
        options = [e.meaning] + [g.meaning for g in wrong]
        rng.shuffle(options)
        quiz.append(QuizItem(
            q=f"‘{e.term}’의 뜻으로 알맞은 것은?",
            options=options,
            answer=options.index(e.meaning),
            why=f"‘{e.term}’: {e.meaning}",
            category=e.category,
            from_doc=from_doc,
        ))
    return quiz


# ---------- 채점과 세션 누적 (저장은 하지 않음) ----------

def new_stats() -> dict[str, list[int]]:
    """분야 -> [맞은 수, 푼 수]"""
    return {c: [0, 0] for c in CATEGORIES}


def tally(stats: dict[str, list[int]], item: QuizItem, choice: int) -> bool:
    """답 하나를 누적하고 정답 여부를 돌려준다."""
    ok = choice == item.answer
    s = stats.setdefault(item.category, [0, 0])
    s[0] += ok
    s[1] += 1
    return ok
