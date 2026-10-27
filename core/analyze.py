"""규칙 기반 분석. LLM이 없거나 실패했을 때 쓰는 대체 경로이자, 1일차의 기본 분석."""
import random
import re
from dataclasses import dataclass, field

from core import calc, fallback
from core.extract import check_numbers, extract_numbers, money_context
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
        text=text,
        fallback_reason=fallback_reason,
        kind=kind,
        verdict=sample.verdict if sample else fallback.DEFAULT_VERDICT[kind],
        pairs=sample.pairs if sample else [],
        terms=terms,
        risks=risks.find(text),
        numbers=numbers,
        number_checks=check_numbers(numbers, text),
        quiz=make_quiz(terms, glossary, kind, rng=rng),
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
_NOT_INTEREST = {"수수료율", "할인율"}


@dataclass
class Suggestion:
    """뜻이 확실하지 않아 칸에 바로 넣지 않고, 사용자가 눌러서 넣게 하는 문서 속 숫자."""

    name: str  # 넣을 칸 (amount, rate, spend ...)
    value: float
    label: str  # 버튼 글


@dataclass
class CalcInputs:
    kind: str  # savings / deposit / loan / card
    values: dict  # amount, rate, months, fee, discount_rate, spend, cap
    from_doc: set[str] = field(default_factory=set)  # 문서에서 읽어 와 채운 칸 (나머지는 예시 기본값)
    suggestions: list[Suggestion] = field(default_factory=list)  # '문서에서 찾은 숫자' 버튼
    notes: list[str] = field(default_factory=list)  # 계산 조건 안내 (예: 카드 혜택 조건)


# 금액 앞뒤에 이런 말이 있으면 실제로 넣을 돈이 아니라 상한·하한이다
_AMOUNT_MEANING = [("최대 한도", r"최대|한도|까지|이하"), ("최소 금액", r"최소|이상")]


def _amount_meaning(text: str, value: int) -> str | None:
    """'최대 한도', '최소 금액'처럼 뜻이 한정된 금액이면 그 이름, 아니면 None."""
    ctx = money_context(text, value) or ""
    return next((name for name, pat in _AMOUNT_MEANING if re.search(pat, ctx)), None)


def calculator_inputs(a: Analysis) -> CalcInputs:
    """원문에서 확인된 숫자만 쓴다 (원칙 3). 확인 안 된 숫자는 버튼으로도 보여 주지 않는다.

    뜻이 확실한 숫자(금리, 기간, 연회비, 할인율, 할인 한도)는 칸에 바로 넣고,
    뜻이 불확실한 숫자는 버튼으로만 보여 준다.
    - 대출 금액: 대부분 '최대 한도'라서 내가 빌릴 돈과 다르다. 항상 버튼.
    - 예적금 금액: '최대', '이상' 같은 말이 붙은 한도·최소액이면 버튼, 아니면 바로 넣는다.
    - 카드 전월 실적: 혜택 조건이지 내 사용액이 아니다. 안내 문구와 버튼.
    """
    ok = {c.field for c in a.number_checks if c.found}
    n = a.numbers
    kind = a.kind if a.kind != "other" else "savings"
    out = CalcInputs(kind=kind, values={**_CALC_DEFAULTS.get(kind, _CALC_DEFAULTS["savings"]), **_CARD_DEFAULTS})

    def fill(name: str, value) -> None:
        out.values[name] = value
        out.from_doc.add(name)

    verified_rates = [r for i, r in enumerate(n.rates) if f"rates[{i}]" in ok]
    for label in _RATE_PREFERENCE:
        rate = next((r.value for r in verified_rates if r.label == label), None)
        if rate is not None:
            fill("rate", rate)
            break
    seen: set[float] = set()
    for r in verified_rates:
        # 수수료율, 할인율은 이자율이 아니라서 '연 금리' 칸 버튼으로 내지 않는다
        if r.label not in _NOT_INTEREST and r.value not in seen:
            seen.add(r.value)
            out.suggestions.append(Suggestion("rate", r.value, f"{r.label} {r.value:g}%"))

    for name in ("months", "fee", "discount_rate", "cap"):
        if (v := getattr(n, name)) is not None and name in ok:
            fill(name, v)

    if n.amount is not None and "amount" in ok:
        meaning = _amount_meaning(a.text, n.amount)
        if kind == "loan" or meaning:
            out.suggestions.append(Suggestion("amount", n.amount, f"문서의 {meaning or '금액'} {calc.won_short(n.amount)}"))
        else:
            fill("amount", n.amount)

    if n.spend is not None and "spend" in ok:
        out.notes.append(f"혜택 조건: 지난달 {calc.won_short(n.spend)} 이상 사용")
        out.suggestions.append(Suggestion("spend", n.spend, f"사용액 칸에 {calc.won_short(n.spend)} 넣기"))
    return out
