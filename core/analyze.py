"""규칙 기반 분석. LLM이 없거나 실패했을 때 쓰는 대체 경로이자, 1일차의 기본 분석."""
import random
import re
from dataclasses import dataclass, field

from core import fallback
from core.extract import check_numbers, extract_numbers
from core.glossary import Glossary
from core.quiz import make_quiz
from core.risks import RiskMatcher
from core.schema import Analysis, DocType, Sample


def detect_kind(text: str) -> DocType:
    # 순서가 중요하다: 적금 설명서에도 '예금자보호'가 나오므로 적금을 먼저 본다
    if "적금" in text:
        return "savings"
    if re.search(r"대출|상환", text):
        return "loan"
    if re.search(r"카드|연회비|리볼빙", text):
        return "card"
    if re.search(r"예금|예치", text):
        return "deposit"
    return "other"


def analyze_rule(
    text: str,
    glossary: Glossary,
    risks: RiskMatcher,
    samples: list[Sample] = (),
    fallback_reason: str | None = None,
    rng: random.Random | None = None,
) -> Analysis:
    kind = detect_kind(text)
    terms = glossary.find_terms(text)
    numbers = extract_numbers(text)
    # 프로토타입 샘플은 미리 써 둔 통역이 있어서 LLM 없이도 시연할 수 있다
    sample = next((s for s in samples if s.verdict and s.text.strip() == text.strip()), None)
    return Analysis(
        source="rule",
        fallback_reason=fallback_reason,
        kind=kind,
        verdict=sample.verdict if sample else fallback.DEFAULT_VERDICT[kind],
        pairs=sample.pairs if sample else [],
        terms=terms,
        risks=risks.find(text),
        numbers=numbers,
        number_checks=check_numbers(numbers, text),
        quiz=make_quiz(terms, glossary, rng=rng),
    )


# ---------- 계산기 미리 채우기 ----------

_CALC_DEFAULTS = {
    "savings": {"amount": 300_000, "rate": 3.0, "months": 12},
    "deposit": {"amount": 5_000_000, "rate": 3.0, "months": 12},
    "loan": {"amount": 2_000_000, "rate": 4.0, "months": 36},
}
_CARD_DEFAULTS = {"fee": 15_000, "discount_rate": 5.0, "spend": 300_000, "cap": None}
# 계산기의 '연 금리'로 쓸 만한 이름 순서. 중도해지이율, 연체이자 같은 것은 기본값으로 쓰지 않는다
_RATE_PREFERENCE = ("기본금리", "적용금리", "금리")


@dataclass
class CalcInputs:
    kind: str  # savings / deposit / loan / card
    values: dict  # amount, rate, months, fee, discount_rate, spend, cap
    from_doc: set[str] = field(default_factory=set)  # 문서에서 읽어 와 채운 칸 (나머지는 예시 기본값)


def calculator_inputs(a: Analysis) -> CalcInputs:
    """원문에서 확인된 숫자만 계산기에 채운다. 확인 안 된 숫자는 넣지 않고 기본값을 쓴다 (원칙 3)."""
    ok = {c.field for c in a.number_checks if c.found}
    n = a.numbers
    kind = a.kind if a.kind != "other" else "savings"
    values: dict = {**_CALC_DEFAULTS.get(kind, _CALC_DEFAULTS["savings"]), **_CARD_DEFAULTS}
    from_doc: set[str] = set()

    verified_rates = [r for i, r in enumerate(n.rates) if f"rates[{i}]" in ok]
    for label in _RATE_PREFERENCE:
        rate = next((r.value for r in verified_rates if r.label == label), None)
        if rate is not None:
            values["rate"] = rate
            from_doc.add("rate")
            break

    for name in ("months", "amount", "fee", "discount_rate", "spend", "cap"):
        v = getattr(n, name)
        if v is not None and name in ok:
            values[name] = v
            from_doc.add(name)
    return CalcInputs(kind=kind, values=values, from_doc=from_doc)
