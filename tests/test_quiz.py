"""퀴즈 출제 원칙: 사전 용어와 사전 뜻만, 문서 용어 우선, 모자라면 같은 분야로 채움. LLM 없음."""
import random

import pytest

from core.glossary import Glossary, load_glossary
from core.quiz import make_quiz, new_stats, quiz_category, tally
from core.schema import GlossEntry, Term


def entry(term, meaning, category):
    return GlossEntry(term=term, meaning=meaning, category=category)


G = Glossary([
    entry("기본금리", "조건 없이 받는 이자율", "예적금"),
    entry("우대금리", "조건을 채우면 더 주는 이자율", "예적금"),
    entry("만기", "계약이 끝나는 날", "예적금"),
    entry("변동금리", "시장에 따라 바뀌는 금리", "대출"),
    entry("거치기간", "원금을 미뤄 두는 기간", "대출"),
    entry("상환기간", "나눠 갚는 기간", "대출"),
    entry("연체이자", "늦게 갚으면 붙는 이자", "대출"),
    entry("연회비", "해마다 내는 돈", "카드"),
    entry("리볼빙", "일부만 내고 이월", "카드"),
])
DICT_MEANINGS = {e.meaning for e in G.entries}


def term(t, meaning="AI가 쓴 뜻 (검증 안 됨)"):
    return Term(term=t, meaning=meaning)


@pytest.mark.parametrize("seed", range(10))
def test_only_dictionary_terms_and_meanings(seed):
    terms = [term("변동금리"), term("사전에없는용어"), term("거치기간")]
    quiz = make_quiz(terms, G, "loan", rng=random.Random(seed))
    assert len(quiz) == 3
    for q in quiz:
        assert set(q.options) <= DICT_MEANINGS  # 정답, 오답 모두 사전 뜻
        assert "AI가 쓴 뜻 (검증 안 됨)" not in q.options and "AI가 쓴" not in q.why
        assert "사전에없는용어" not in q.q


def test_document_terms_come_first():
    quiz = make_quiz([term("변동금리"), term("거치기간")], G, "loan", rng=random.Random(0))
    asked = {q.q.split("’")[0].lstrip("‘"): q.from_doc for q in quiz}
    assert asked["변동금리"] and asked["거치기간"]
    assert sum(q.from_doc for q in quiz) == 2


@pytest.mark.parametrize("seed", range(10))
def test_fill_from_same_category(seed):
    quiz = make_quiz([term("변동금리")], G, "loan", rng=random.Random(seed))
    filled = [q for q in quiz if not q.from_doc]
    assert len(filled) == 2 and all(q.category == "대출" for q in filled)


def test_fill_falls_back_to_other_categories_when_field_runs_out():
    quiz = make_quiz([term("연회비")], G, "card", n=3, rng=random.Random(0))
    cats = [q.category for q in quiz]
    assert cats.count("카드") == 2 and len(quiz) == 3  # 카드 용어는 2개뿐이라 하나는 다른 분야


def test_surface_alias_maps_to_dictionary_entry():
    g = Glossary([GlossEntry(term="전월실적", category="카드", meaning="지난달 사용액", aliases=["전월 실적"]),
                  entry("연회비", "해마다 내는 돈", "카드"), entry("리볼빙", "일부만 내고 이월", "카드")])
    [q] = make_quiz([Term(term="전월 실적 조건", meaning="x", surfaces=["전월 실적"])], g, "card", n=1,
                    rng=random.Random(0))
    assert q.from_doc and q.options[q.answer] == "지난달 사용액"


def test_other_kind_uses_most_common_document_category():
    assert quiz_category("other", [G.lookup("변동금리"), G.lookup("거치기간"), G.lookup("연회비")]) == "대출"
    assert quiz_category("deposit", []) == "예적금"
    assert quiz_category("other", []) is None


def test_real_glossary_quiz_meanings_are_dictionary_meanings():
    g = load_glossary()
    meanings = {e.meaning for e in g.entries}
    for seed in range(5):
        for q in make_quiz([term("우대금리"), term("리볼빙")], g, "card", rng=random.Random(seed)):
            assert set(q.options) <= meanings


def test_tally_accumulates_by_category():
    stats = new_stats()
    [q] = make_quiz([term("변동금리")], G, "loan", n=1, rng=random.Random(0))
    assert tally(stats, q, q.answer) is True
    assert tally(stats, q, (q.answer + 1) % len(q.options)) is False
    assert stats["대출"] == [1, 2] and stats["카드"] == [0, 0]
