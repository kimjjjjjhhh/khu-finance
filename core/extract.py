"""원문에서 숫자(금리, 기간, 금액)를 찾는다.

두 가지 용도로 쓴다.
1) 규칙 기반 분석: extract_numbers()가 원문에서 직접 숫자를 뽑는다.
2) 환각 방지: check_numbers()가 AI가 뽑은 숫자가 원문에 실제로 있는지 대조한다.
같은 파서를 쓰므로 '30만 원'과 300000처럼 표기가 달라도 같은 값으로 본다.
"""
import re
from dataclasses import dataclass, field

from core.schema import NumberCheck, Numbers, Rate

_NUM = r"(?<![\d.])(\d[\d,]*(?:\.\d+)?)"
_MONEY_RE = re.compile(_NUM + r"\s*(억|천만|백만|만|천)?\s*원")
_UNIT = {None: 1, "천": 1_000, "만": 10_000, "백만": 1_000_000, "천만": 10_000_000, "억": 100_000_000}
_RATE_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*%")
_MONTHS_RE = re.compile(r"(?<![\d.])(\d+)\s*개월")
_YEARS_RE = re.compile(r"(?<![\d.])(\d+)\s*년")

# 금리 이름 붙이기: 숫자 앞 30자, 뒤 8자 안에서 가장 가까운 단어로 정한다
_LABEL_RULES = [
    ("중도해지이율", r"중도\s*해지"),
    ("연체이자", r"연체"),
    ("우대금리", r"우대"),
    ("기본금리", r"기본"),
    ("최고금리", r"최고"),
    ("적용금리", r"적용\s*금리"),
    ("수수료율", r"리볼빙|수수료"),
    ("할인율", r"할인|캐시백|적립"),
]
_TAX_CONTEXT = re.compile(r"소득세|세율|원천징수")  # 15.4% 같은 세율은 금리가 아니다


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def _money_at(m: re.Match) -> int:
    return round(_num(m.group(1)) * _UNIT[m.group(2)])


@dataclass
class TextNumbers:
    """원문에 나오는 모든 숫자 (표기 상관없이 값으로 정리)."""

    rates: set[float] = field(default_factory=set)
    amounts: set[int] = field(default_factory=set)
    months: set[int] = field(default_factory=set)


def numbers_in_text(text: str) -> TextNumbers:
    found = TextNumbers()
    # %p(퍼센트포인트)도 원문에 있는 숫자이므로 대조할 때는 포함한다
    found.rates = {round(_num(m.group(1)), 6) for m in _RATE_RE.finditer(text)}
    found.amounts = {_money_at(m) for m in _MONEY_RE.finditer(text)}
    found.months = {int(m.group(1)) for m in _MONTHS_RE.finditer(text)}
    found.months |= {int(m.group(1)) * 12 for m in _YEARS_RE.finditer(text) if int(m.group(1)) <= 50}
    return found


def check_numbers(numbers: Numbers, text: str) -> list[NumberCheck]:
    """읽어 낸 숫자마다 원문에 있는지 표시한다. found=False는 '원문에서 확인 안 됨'."""
    t = numbers_in_text(text)
    checks = [
        NumberCheck(field=f"rates[{i}]", label=r.label, value=r.value, found=round(r.value, 6) in t.rates)
        for i, r in enumerate(numbers.rates)
    ]
    singles = [
        ("months", "기간(개월)", numbers.months, t.months),
        ("amount", "금액(원)", numbers.amount, t.amounts),
        ("fee", "연회비(원)", numbers.fee, t.amounts),
        ("discount_rate", "할인율(%)", numbers.discount_rate, t.rates),
        ("cap", "월 할인 한도(원)", numbers.cap, t.amounts),
        ("spend", "전월 실적(원)", numbers.spend, t.amounts),
    ]
    for name, label, value, pool in singles:
        if value is not None:
            key = round(value, 6) if pool is t.rates else value
            checks.append(NumberCheck(field=name, label=label, value=value, found=key in pool))
    return checks


def _rate_label(text: str, start: int, end: int) -> str | None:
    before = text[max(0, start - 30):start]
    after = text[end:end + 8]
    if _TAX_CONTEXT.search(before[-12:] + after):
        return None
    best, best_dist = "금리", None
    for label, pat in _LABEL_RULES:
        dists = [len(before) - m.end() for m in re.finditer(pat, before)]
        dists += [m.start() for m in re.finditer(pat, after)]
        if dists and (best_dist is None or min(dists) < best_dist):
            best, best_dist = label, min(dists)
    return best


def _first_money(pattern: str, text: str) -> int | None:
    m = re.search(pattern + _MONEY_RE.pattern, text)
    return round(_num(m.group(1)) * _UNIT[m.group(2)]) if m else None


def extract_numbers(text: str) -> Numbers:
    """규칙 기반 숫자 추출 (프로토타입 extractNums 이식)."""
    rates: list[Rate] = []
    for m in _RATE_RE.finditer(text):
        if text[m.end():m.end() + 1] == "p":  # '연 1.5%p'는 더해 주는 폭이지 금리 자체가 아니다
            continue
        label = _rate_label(text, m.start(), m.end())
        value = _num(m.group(1))
        if label and value <= 100 and not any(r.value == value and r.label == label for r in rates):
            rates.append(Rate(label=label, value=value))

    months = None
    if mo := _MONTHS_RE.search(text):
        months = int(mo.group(1))
    else:
        years = [int(y.group(1)) for y in _YEARS_RE.finditer(text) if 1 <= int(y.group(1)) <= 50]
        months = years[0] * 12 if years else None

    # 금액: '월 (최대) N만 원'을 먼저 찾고, 없으면 처음 나오는 만 원 단위 금액
    amount = _first_money(r"월\s*(?:최대\s*)?", text)
    if amount is None:
        big = [m for m in _MONEY_RE.finditer(text) if m.group(2) in ("만", "백만", "천만", "억")]
        amount = _money_at(big[0]) if big else None

    disc = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:를\s*|의\s*)?(?:청구\s*할인|캐시백|할인|적립)", text)
    return Numbers(
        rates=rates,
        months=months if months and months <= 600 else None,
        amount=amount,
        fee=_first_money(r"연회비[^0-9\n]{0,15}", text),
        discount_rate=_num(disc.group(1)) if disc else None,
        cap=_first_money(r"한도\s*(?:는|:)?\s*", text),
        spend=_first_money(r"실적\s*", text),
    )
