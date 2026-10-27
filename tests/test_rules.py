"""용어 찾기, 위험 조항, 퀴즈, 규칙 기반 분석."""
import random

import pytest

from core.analyze import analyze_rule, calculator_inputs, detect_kind
from core.glossary import Glossary, load_glossary
from core.quiz import make_quiz
from core.risks import RiskMatcher, load_risks
from core.samples import prototype_samples
from core.schema import GlossEntry, NumberCheck, RiskRule, Term


def entry(term, meaning="뜻", category="기타", aliases=()):
    return GlossEntry(term=term, meaning=meaning, category=category, aliases=list(aliases))


# ---------- 용어 ----------

def test_longest_term_wins():
    g = Glossary([entry("예금"), entry("예금자보호")])
    assert [t.term for t in g.find_terms("예금자보호법에 따라")] == ["예금자보호"]


def test_spacing_variants_and_surfaces():
    g = Glossary([entry("전월실적")])
    [t] = g.find_terms("전월 실적 30만 원, 전월실적 기준")
    assert t.term == "전월실적"
    assert t.surfaces == ["전월 실적", "전월실적"]  # 하이라이트는 원문 표기 그대로 해야 한다


def test_headword_beats_other_entrys_alias():
    g = Glossary([entry("현금서비스", "A", aliases=["단기카드대출"]), entry("단기카드대출", "B", aliases=["현금서비스"])])
    assert [t.meaning for t in g.find_terms("현금서비스")] == ["A"]
    assert [t.meaning for t in g.find_terms("단기카드대출")] == ["B"]


def test_alias_maps_to_headword():
    g = Glossary([entry("만기", aliases=["만기일"])])
    [t] = g.find_terms("만기일에 지급")
    assert (t.term, t.surfaces) == ("만기", ["만기일"])


# ---------- 위험 조항 ----------

def test_risks_found_in_text_order_without_duplicates():
    m = RiskMatcher([
        RiskRule(keyword="수수료", level="mid", why="w1", patterns=[r"수수료"]),
        RiskRule(keyword="연체", level="high", why="w2", patterns=[r"연체"]),
        RiskRule(keyword="수수료2", level="mid", why="w3", patterns=[r"수수료"]),
    ])
    risks = m.find("연체하면 수수료가 붙어요")
    assert [(r.phrase, r.level) for r in risks] == [("연체", "high"), ("수수료", "mid")]


def test_rule_without_patterns_never_matches():
    m = RiskMatcher([RiskRule(keyword="대출 한도 과대 광고", level="high", why="w", patterns=[])])
    assert m.find("대출 한도 최대 1억 원") == []


# ---------- 퀴즈 ----------

def test_quiz_has_three_valid_questions():
    g = load_glossary()
    terms = g.find_terms("기본금리와 우대금리, 중도해지, 리볼빙")
    quiz = make_quiz(terms, g, rng=random.Random(1))
    assert len(quiz) == 3
    for q in quiz:
        assert len(q.options) == 3 and len(set(q.options)) == 3
        term = q.q.split("’")[0].lstrip("‘")
        assert q.options[q.answer] == g.lookup(term).meaning


def test_quiz_fills_from_glossary_when_few_terms():
    g = load_glossary()
    assert len(make_quiz([], g, rng=random.Random(0))) == 3


def test_quiz_never_uses_alias_twin_as_distractor():
    g = Glossary([
        entry("현금서비스", "카드로 현금을 빌림", "카드", ["단기카드대출"]),
        entry("단기카드대출", "카드로 짧게 현금 대출", "카드", ["현금서비스"]),
        entry("연회비", "해마다 내는 돈", "카드"),
        entry("리볼빙", "일부만 내고 이월", "카드"),
    ])
    for seed in range(20):
        [q] = make_quiz([Term(term="현금서비스", meaning="카드로 현금을 빌림", category="카드")], g, n=1,
                        rng=random.Random(seed))
        assert "카드로 짧게 현금 대출" not in q.options


# ---------- 분석과 계산기 ----------

@pytest.mark.parametrize(
    "text, kind",
    [("자유적금, 예금자보호법", "savings"), ("원리금균등상환", "loan"), ("연회비 1만 원", "card"),
     ("정기예금 예치기간", "deposit"), ("안녕하세요", "other")],
)
def test_detect_kind(text, kind):
    assert detect_kind(text) == kind


@pytest.fixture(scope="module")
def deps():
    return load_glossary(), load_risks(), prototype_samples()


def test_prototype_sample_uses_prepared_translation(deps):
    g, r, samples = deps
    s = samples[0]
    a = analyze_rule(s.text, g, r, samples, rng=random.Random(0))
    assert a.source == "rule"
    assert a.verdict == s.verdict
    assert len(a.pairs) == 4
    assert {"중도해지", "자동 연장"} <= {x.phrase for x in a.risks}


def test_pasted_text_gets_default_verdict(deps):
    g, r, samples = deps
    a = analyze_rule("이 대출은 변동금리입니다.", g, r, samples, fallback_reason="키 없음")
    assert a.kind == "loan" and a.pairs == [] and a.fallback_reason == "키 없음"


def test_empty_document_does_not_crash(deps):
    g, r, samples = deps
    a = analyze_rule("   ", g, r, samples)
    assert a.terms == [] and a.risks == [] and len(a.quiz) == 3


def test_calculator_prefill_from_document(deps):
    g, r, samples = deps
    a = analyze_rule(samples[1].text, g, r, samples)  # 학자금 대출: 최대 200만 원, 연 1.7%, 10년
    ci = calculator_inputs(a)
    assert ci.kind == "loan"
    assert (ci.values["rate"], ci.values["months"]) == (1.7, 120)
    assert ci.from_doc == {"rate", "months"}
    # 대출 금액은 내가 빌릴 돈과 다를 수 있어서 칸에 넣지 않고 버튼으로만 보여 준다
    assert ("amount", 2_000_000, "문서의 최대 한도 200만 원") in [(x.name, x.value, x.label) for x in ci.suggestions]


def _ci(text, deps):
    g, r, samples = deps
    return calculator_inputs(analyze_rule(text, g, r, samples))


def test_savings_amount_with_limit_word_is_button_only(deps):
    ci = _ci("적금 월 최대 30만 원까지, 기본금리 연 3.0%, 12개월", deps)
    assert "amount" not in ci.from_doc
    assert [x.label for x in ci.suggestions if x.name == "amount"] == ["문서의 최대 한도 30만 원"]


def test_plain_savings_amount_is_filled(deps):
    ci = _ci("정기적금 월 30만 원, 기본금리 연 3.0%, 기간 12개월", deps)
    assert ci.values["amount"] == 300_000 and "amount" in ci.from_doc
    assert not [x for x in ci.suggestions if x.name == "amount"]


def test_card_spend_condition_is_note_and_button(deps):
    ci = _ci("카드 연회비 15,000원. 전월 실적 30만 원 이상이면 10% 청구할인, 월 할인 한도 1만 원", deps)
    assert "spend" not in ci.from_doc and ci.values["spend"] == 300_000  # 예시값 (우연히 같은 값이어도 표시는 예시값)
    assert ci.notes == ["혜택 조건: 지난달 30만 원 이상 사용"]
    assert ("spend", 300_000) in [(x.name, x.value) for x in ci.suggestions]
    assert {"fee", "discount_rate", "cap"} <= ci.from_doc


def test_rate_buttons_skip_fees_and_duplicates(deps):
    ci = _ci("리볼빙 수수료 연 17.9%. 대출 기본금리 연 5.5%, 금리 연 5.5%~9.9%", deps)
    labels = [x.label for x in ci.suggestions if x.name == "rate"]
    assert "수수료율 17.9%" not in labels
    assert [x.value for x in ci.suggestions if x.name == "rate"].count(5.5) == 1


def test_calculator_skips_unverified_numbers(deps):
    # 원문에서 확인 안 된 숫자는 계산기에 넣지 않는다 (원칙 3)
    g, r, samples = deps
    a = analyze_rule(samples[0].text, g, r, samples)
    a.number_checks = [c if c.field != "months" else NumberCheck(**{**c.model_dump(), "found": False})
                       for c in a.number_checks]
    ci = calculator_inputs(a)
    assert "months" not in ci.from_doc
    assert ci.values["months"] == 12  # 예시 기본값


def test_calculator_does_not_use_penalty_rate_as_main_rate(deps):
    g, r, samples = deps
    a = analyze_rule("적금 중도해지이율 연 0.5%", g, r, samples)
    assert "rate" not in calculator_inputs(a).from_doc
