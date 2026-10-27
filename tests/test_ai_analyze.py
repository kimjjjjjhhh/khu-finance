"""AI 통역 흐름: 가짜 Provider로 검증, 재시도, 대체, 환각 경고를 확인한다 (실제 호출 없음)."""
import random

import pytest

import config
from core.ai_analyze import CUT_OFF_REASON, NO_KEY_REASON, analyze_ai, parse_llm_json
from core.analyze import calculator_inputs
from core.glossary import load_glossary
from core.llm import LLMError
from core.prompts import RETRY_NOTE
from core.risks import load_risks
from tests.fakes import DOC, GOOD, FakeProvider, cut, reply


@pytest.fixture(scope="module")
def deps():
    return load_glossary(), load_risks()


def run(provider, deps, text=DOC):
    g, r = deps
    return analyze_ai(text, provider, g, r, rng=random.Random(0))


def test_parse_accepts_code_fence_and_extra_text():
    a = parse_llm_json('여기 있어요\n```json\n{"verdict": "v"}\n```')
    assert a.verdict == "v" and a.doc_type == "other"


@pytest.mark.parametrize("bad", ["JSON이 아님", '{"verdict": ""}', '{"pairs": []}', '{"verdict": "v",'])
def test_parse_rejects_bad(bad):
    with pytest.raises(ValueError):
        parse_llm_json(bad)


def test_success(deps):
    p = FakeProvider(reply(usage=(1000, 400)))
    a = run(p, deps)
    assert a.source == "ai" and a.fallback_reason is None
    assert a.kind == "savings" and a.verdict == GOOD["verdict"]
    assert (a.prompt_tokens, a.completion_tokens) == (1000, 400)
    assert len(p.prompts) == 1
    assert DOC in p.prompts[0][1]


def test_hallucinated_quotes_are_flagged(deps):
    a = run(FakeProvider(reply()), deps)
    assert [x.found for x in a.pairs] == [True, False]
    assert [x.found for x in a.risks] == [True, False]
    found = {t.term: t.found for t in a.terms}
    assert found == {"우대금리": True, "중도 해지": True, "복리": False}
    # AI가 띄어 쓴 '중도 해지'도 원문 표기 '중도해지'로 하이라이트한다
    assert "중도해지" in next(t for t in a.terms if t.term == "중도 해지").surfaces
    # 퀴즈는 원문에서 확인된 용어로만 만든다
    assert all("복리" not in q.q for q in a.quiz)


def test_hallucinated_number_not_autofilled(deps):
    a = run(FakeProvider(reply()), deps)
    checks = {(c.label, c.value): c.found for c in a.number_checks}
    assert checks[("기본금리", 3.0)] and not checks[("최고금리", 5.0)]
    ci = calculator_inputs(a)
    assert ci.values["rate"] == 3.0 and ci.values["months"] == 12 and ci.values["amount"] == 300_000
    assert {"rate", "months", "amount"} <= ci.from_doc


def test_made_up_amount_falls_back_to_example(deps):
    bad = {**GOOD, "numbers": {"rates": [{"label": "기본금리", "value": 9.9}], "amount": 777000}}
    ci = calculator_inputs(run(FakeProvider(reply(bad)), deps))
    assert ci.values["rate"] != 9.9 and ci.values["amount"] != 777000
    assert not ({"rate", "amount"} & ci.from_doc)


def test_retry_once_then_success(deps):
    p = FakeProvider(reply('{"verdict": ""}', usage=(900, 10)), reply(usage=(950, 300)))
    a = run(p, deps)
    assert a.source == "ai"
    assert len(p.prompts) == 2
    assert RETRY_NOTE.split("(")[0] in p.prompts[1][1]
    assert (a.prompt_tokens, a.completion_tokens) == (1850, 310)  # 두 번 쓴 토큰을 합친다


def test_two_bad_answers_fall_back_to_rule(deps):
    p = FakeProvider(reply("아님", usage=(10, 1)), reply("{}", usage=(10, 1)), reply())
    a = run(p, deps)
    assert a.source == "rule"
    assert "형식" in a.fallback_reason
    assert len(p.prompts) == 2  # 재시도는 1번까지만
    assert a.prompt_tokens == 20
    assert a.terms and a.risks  # 규칙 기반 결과가 채워진다


def test_no_key_falls_back_without_call(deps):
    a = run(None, deps)
    assert a.source == "rule" and a.fallback_reason == NO_KEY_REASON
    assert a.prompt_tokens == a.completion_tokens == 0


def test_call_error_falls_back_without_retry(deps):
    p = FakeProvider(LLMError("rate_limit", "요청이 많거나 크레딧이 부족해요"), reply())
    a = run(p, deps)
    assert a.source == "rule" and a.fallback_reason == "요청이 많거나 크레딧이 부족해요"
    assert len(p.prompts) == 1


def test_long_document_marked_truncated(deps, monkeypatch):
    monkeypatch.setattr(config, "MAX_DOC_CHARS", 50)
    a = run(FakeProvider(reply()), deps)
    assert a.truncated


# ---------- 응답이 잘린 경우 (finish_reason=length) ----------

def test_close_truncated_json_keeps_complete_values():
    from core.ai_analyze import close_truncated_json
    assert close_truncated_json('{"a": 1, "b": [1, 2, {"c": "잘린 문') == {"a": 1, "b": [1, 2]}
    assert close_truncated_json('{"a": "쉼표, 와 \\"따옴표\\" 포함", "b": tr') == {"a": '쉼표, 와 "따옴표" 포함'}
    assert close_truncated_json('{"verd') is None


def test_cut_answer_uses_what_arrived_without_retry(deps):
    # 위험 조항 첫 항목까지 받고 잘림: 숫자는 못 받았다
    p = FakeProvider(cut(keep='"why": "이자가 거의 없어요", "level": "high"}'), reply())
    a = run(p, deps)
    assert len(p.prompts) == 1  # 잘리면 재시도하지 않는다
    assert a.source == "ai" and a.partial
    assert len(a.pairs) == 2 and len(a.terms) == 3 and len(a.risks) == 1
    assert a.numbers.rates == [] and a.number_checks == []
    assert a.completion_tokens == 4000


def test_cut_inside_item_drops_only_that_item(deps):
    p = FakeProvider(cut(keep='{"term": "복리", "meaning": "이자에'))
    a = run(p, deps)
    assert a.partial and [t.term for t in a.terms] == ["우대금리", "중도 해지"]


def test_cut_before_verdict_falls_back(deps):
    p = FakeProvider(cut(keep='"docType": "savings", "verdict": "최고'), reply())
    a = run(p, deps)
    assert a.source == "rule" and a.fallback_reason == CUT_OFF_REASON
    assert len(p.prompts) == 1


def test_length_but_complete_json_is_not_partial(deps):
    a = run(FakeProvider(reply(finish_reason="length")), deps)
    assert a.source == "ai" and not a.partial
