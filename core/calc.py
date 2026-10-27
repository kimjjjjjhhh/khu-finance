"""계산기. LLM은 숫자를 읽기만 하고, 계산은 전부 여기서 한다.

금리는 화면에 보이는 그대로 % 숫자(3.0 = 연 3%)로 받는다.
반올림은 화면에서 표시할 때만 한다. 중간에 반올림하면 오차가 쌓이기 때문이다.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from config import INTEREST_TAX_RATE


def _check(**values: float) -> None:
    for name, v in values.items():
        if v < 0:
            raise ValueError(f"{name}은(는) 0 이상이어야 합니다: {v}")


def _check_months(months: int) -> None:
    if months < 1:
        raise ValueError(f"기간은 1개월 이상이어야 합니다: {months}")


@dataclass(frozen=True)
class DepositResult:
    principal: float  # 낸 원금 합계
    interest: float  # 세전 이자
    tax: float  # 이자소득세
    total: float  # 만기에 받는 돈
    net_rate: float  # 세후 연 금리 (%)


@dataclass(frozen=True)
class LoanResult:
    principal: float
    monthly: float  # 매달 갚는 돈
    total_paid: float
    interest: float  # 총 이자


@dataclass(frozen=True)
class CardResult:
    per_month: float  # 월 할인액 (한도 적용 후)
    annual: float  # 연 할인액
    fee: float  # 연회비
    net: float  # 연 순이익 (음수면 손해)


def savings(monthly: float, rate_pct: float, months: int, taxed: bool = True) -> DepositResult:
    """적금, 단리, 매달 같은 금액 납입.

    첫 달 돈은 n개월, 둘째 달 돈은 n-1개월 ... 마지막 달 돈은 1개월 동안 이자가 붙으므로
    이자 = 월납입액 x 연이율/12 x (n + (n-1) + ... + 1) = 월납입액 x 연이율/12 x n(n+1)/2
    """
    _check(월납입액=monthly, 금리=rate_pct)
    _check_months(months)
    r = rate_pct / 100
    principal = monthly * months
    interest = monthly * r / 12 * months * (months + 1) / 2
    return _with_tax(principal, interest, rate_pct, taxed)


def deposit(principal: float, rate_pct: float, months: int, taxed: bool = True) -> DepositResult:
    """예금, 단리. 이자 = 원금 x 연이율 x 개월/12"""
    _check(원금=principal, 금리=rate_pct)
    _check_months(months)
    interest = principal * rate_pct / 100 * months / 12
    return _with_tax(principal, interest, rate_pct, taxed)


def _with_tax(principal: float, interest: float, rate_pct: float, taxed: bool) -> DepositResult:
    t = INTEREST_TAX_RATE if taxed else 0.0
    tax = interest * t
    return DepositResult(
        principal=principal,
        interest=interest,
        tax=tax,
        total=principal + interest - tax,
        net_rate=rate_pct * (1 - t),
    )


def loan(principal: float, rate_pct: float, months: int) -> LoanResult:
    """대출, 원리금균등상환. 월상환 = P*i / (1 - (1+i)^-N), i = 연이율/12"""
    _check(원금=principal, 금리=rate_pct)
    _check_months(months)
    i = rate_pct / 100 / 12
    # 금리 0%면 공식의 분모가 0이 되므로 원금을 개월 수로 나눈다
    monthly = principal / months if i == 0 else principal * i / (1 - (1 + i) ** -months)
    total = monthly * months
    return LoanResult(principal=principal, monthly=monthly, total_paid=total, interest=total - principal)


def card(monthly_spend: float, discount_pct: float, monthly_cap: float | None, annual_fee: float) -> CardResult:
    """카드. 연 순이익 = min(월사용액 x 할인율, 월한도) x 12 - 연회비

    monthly_cap이 None이면 한도 없음. 0이면 할인이 0원이라는 뜻이다.
    """
    _check(월사용액=monthly_spend, 할인율=discount_pct, 연회비=annual_fee)
    per_month = monthly_spend * discount_pct / 100
    if monthly_cap is not None:
        _check(월한도=monthly_cap)
        per_month = min(per_month, monthly_cap)
    annual = per_month * 12
    return CardResult(per_month=per_month, annual=annual, fee=annual_fee, net=annual - annual_fee)


def won(n: float) -> str:
    """화면 표시용: 3649491.0 -> '3,649,491원' (0.5는 올림. 파이썬 round()는 짝수 쪽으로 반올림한다)"""
    return f"{int(Decimal(str(n)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)):,}원"
