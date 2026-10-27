"""읽은 문서의 용어로 3지선다 퀴즈 만들기 (프로토타입 makeQuiz 이식)."""
import random

from core.glossary import Glossary
from core.schema import GlossEntry, QuizItem, Term


def make_quiz(terms: list[Term], glossary: Glossary, n: int = 3, rng: random.Random | None = None) -> list[QuizItem]:
    rng = rng or random.Random()
    entries = [glossary.lookup(t.term) or GlossEntry(term=t.term, category=t.category, meaning=t.meaning)
               for t in terms]
    # 문서에서 찾은 용어가 n개보다 적으면 사전에서 채운다
    if len(entries) < n:
        have = {e.term for e in entries}
        extra = [e for e in glossary.entries if e.term not in have]
        entries += rng.sample(extra, min(n - len(entries), len(extra)))

    quiz = []
    for e in rng.sample(entries, min(n, len(entries))):
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
        ))
    return quiz
