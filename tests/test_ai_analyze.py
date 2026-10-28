"""AI 통역 흐름: 가짜 Provider로 검증, 재시도, 대체, 환각 경고를 확인한다 (실제 호출 없음)."""
import random

import pytest

import config
from core.ai_analyze import (CUT_OFF_REASON, NO_KEY_REASON, UNAVAILABLE, UNEXPECTED_REASON, analyze_ai,
                              parse_llm_json, unavailable)
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
    assert ci.values["rate"] == 3.0 and ci.values["months"] == 12
    assert {"rate", "months"} <= ci.from_doc
    # '월 최대 30만 원'은 한도라서 버튼으로만
    assert "amount" not in ci.from_doc
    assert ("amount", 300_000) in [(x.name, x.value) for x in ci.suggestions]
    assert 5.0 not in [x.value for x in ci.suggestions]  # 지어낸 금리는 버튼으로도 안 보여 준다


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
    assert a.source == "rule" and a.fallback_reason == unavailable("요청이 많거나 크레딧이 부족해요")
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


def test_numbers_first_survive_cut_in_pairs(deps):
    # 프롬프트 순서대로 numbers가 앞에 오면, pairs에서 잘려도 숫자는 남는다
    ordered = {k: GOOD[k] for k in ("docType", "verdict", "numbers", "pairs", "terms", "risks")}
    a = run(FakeProvider(cut(ordered, keep='"easy": "중간에 깨면 0.5%만 받아요."}')), deps)
    assert a.partial and a.numbers.months == 12 and len(a.numbers.rates) == 2
    assert len(a.pairs) == 1 and a.terms == [] and a.risks == []



# ---------- 호출 실패 (배포 서버에서 연결, 시간 초과, 인증 오류) ----------

class Boom:
    """complete()에서 정해 둔 예외를 던지는 Provider."""
    model = "fake"

    def __init__(self, error):
        self.error, self.calls = error, 0

    def complete(self, system, user):
        self.calls += 1
        raise self.error


# 키처럼 생긴 가짜 값과 주소가 섞인 오류 메시지. 파일에 그대로 적으면 비밀 값 검사에 걸리므로 실행할 때 조립한다
LEAKY = "sk-" + "live-REALLOOKING" + "KEY-0001 https://factchat-cloud.mindlogic.ai/v1/gateway"


@pytest.mark.parametrize("kind, msg", [("connection", "AI 서버에 연결하지 못했어요"),
                                       ("timeout", "AI 응답이 너무 늦어요"),
                                       ("auth", "API 키가 맞지 않아요")])
def test_call_failures_fall_back_with_notice(deps, kind, msg):
    p = Boom(LLMError(kind, msg))
    a = run(p, deps)
    assert a.source == "rule" and a.fallback_reason.startswith(UNAVAILABLE)
    assert p.calls == 1  # 호출 실패는 재시도하지 않는다
    assert a.terms and a.number_checks  # 규칙 기반 결과로 채워진다


def test_unexpected_error_falls_back_without_leaking(deps):
    a = run(Boom(RuntimeError(LEAKY)), deps)
    assert a.source == "rule" and a.fallback_reason == UNEXPECTED_REASON
    assert "sk-live" not in a.model_dump_json() and "mindlogic" not in a.model_dump_json()


def test_limit_error_keeps_limit_message(deps):
    from core.limits import LIMIT_MESSAGE
    a = run(Boom(LLMError("limit", LIMIT_MESSAGE)), deps)
    assert a.fallback_reason == LIMIT_MESSAGE
