import pytest
from pydantic import ValidationError

from core.schema import LLMAnalysis, QuizItem, Term

VALID = {
    "docType": "savings",
    "verdict": "조건을 채워야 최고 금리를 받아요.",
    "pairs": [{"original": "기본금리는 연 3.0%", "easy": "기본은 3%예요."}],
    "terms": [{"term": "우대금리", "meaning": "조건을 채우면 더 주는 금리", "category": "예적금"}],
    "risks": [{"phrase": "중도해지", "why": "이자가 거의 없어요.", "level": "high"}],
    "numbers": {"rates": [{"label": "기본금리", "value": 3.0}], "months": 12, "amount": 300000,
                "fee": None, "discountRate": None, "cap": None},
    "quiz": [{"q": "단리란?", "options": ["a", "b", "c"], "answer": 2, "why": "", "category": "예적금"}],
}


def test_valid_llm_json_parses_with_camel_case():
    a = LLMAnalysis.model_validate(VALID)
    assert a.doc_type == "savings"
    assert a.numbers.months == 12
    assert a.numbers.discount_rate is None


def test_unknown_values_are_coerced_not_rejected():
    # 사소한 표기 차이로 재시도까지 하지 않도록 기본값으로 받는다
    data = {**VALID, "docType": "적금", "risks": [{"phrase": "x", "why": "y", "level": "low"}]}
    a = LLMAnalysis.model_validate(data)
    assert a.doc_type == "other"
    assert a.risks[0].level == "mid"
    assert Term(term="예금", meaning="m", category="저축").category == "기타"


def test_quiz_answer_out_of_range_is_rejected():
    with pytest.raises(ValidationError):
        QuizItem(q="?", options=["a", "b"], answer=2)


@pytest.mark.parametrize(
    "patch",
    [
        {"verdict": ""},  # 한 줄 통역 없음
        {"numbers": {"months": 0}},  # 0개월
        {"numbers": {"rates": [{"label": "금리", "value": 300}]}},  # 300%는 금리가 아님
        {"numbers": {"amount": -1}},
    ],
)
def test_invalid_llm_json_is_rejected(patch):
    with pytest.raises(ValidationError):
        LLMAnalysis.model_validate({**VALID, **patch})
