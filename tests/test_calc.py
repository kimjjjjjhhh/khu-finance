import pytest

from core import calc


# ---------- 과제에서 정한 검증값 ----------

def test_savings_verification_value():
    # 월 30만 원, 연 3%, 12개월, 세후 -> 3,649,491원
    r = calc.savings(300_000, 3.0, 12, taxed=True)
    assert r.principal == 3_600_000
    assert r.interest == pytest.approx(58_500)  # 300,000 x 0.03/12 x 78
    assert r.tax == pytest.approx(9_009)  # 58,500 x 15.4%
    assert calc.won(r.total) == "3,649,491원"


def test_loan_verification_value():
    # 200만 원, 연 1.7%, 120개월 -> 월 약 18,135원
    r = calc.loan(2_000_000, 1.7, 120)
    assert calc.won(r.monthly) == "18,135원"
    assert r.total_paid == pytest.approx(r.monthly * 120)
    assert r.interest == pytest.approx(r.total_paid - 2_000_000)


# ---------- 적금, 예금 ----------

def test_savings_pretax_has_no_tax():
    r = calc.savings(300_000, 3.0, 12, taxed=False)
    assert r.tax == 0
    assert r.total == pytest.approx(3_658_500)
    assert r.net_rate == pytest.approx(3.0)


def test_savings_one_month_equals_one_month_of_interest():
    # n=1이면 n(n+1)/2 = 1 -> 한 달치 이자
    r = calc.savings(100_000, 12.0, 1, taxed=False)
    assert r.interest == pytest.approx(1_000)


def test_savings_earns_less_than_deposit_of_same_total():
    # 같은 금리, 같은 총액이어도 적금은 돈이 나눠 들어가서 이자가 적다 (화면 안내 문구의 근거)
    s = calc.savings(100_000, 3.0, 12, taxed=False)
    d = calc.deposit(1_200_000, 3.0, 12, taxed=False)
    assert s.interest < d.interest


def test_deposit_simple_interest():
    # 100만 원, 연 3.2%, 12개월 (샘플 3번 정기예금)
    r = calc.deposit(1_000_000, 3.2, 12, taxed=False)
    assert r.interest == pytest.approx(32_000)
    assert r.total == pytest.approx(1_032_000)


def test_deposit_partial_year_and_tax():
    r = calc.deposit(5_000_000, 3.0, 6, taxed=True)
    assert r.interest == pytest.approx(75_000)
    assert r.tax == pytest.approx(11_550)
    assert r.net_rate == pytest.approx(3.0 * 0.846)


def test_zero_rate_gives_zero_interest():
    assert calc.savings(300_000, 0, 12).interest == 0
    assert calc.deposit(1_000_000, 0, 12).interest == 0


# ---------- 대출 ----------

def test_loan_zero_rate_splits_principal_evenly():
    r = calc.loan(1_200_000, 0, 12)
    assert r.monthly == pytest.approx(100_000)
    assert r.interest == pytest.approx(0)


def test_loan_one_month_pays_principal_plus_one_month_interest():
    r = calc.loan(1_000_000, 12.0, 1)
    assert r.monthly == pytest.approx(1_010_000)


def test_loan_higher_rate_means_higher_payment():
    assert calc.loan(5_000_000, 9.9, 36).monthly > calc.loan(5_000_000, 5.5, 36).monthly


# ---------- 카드 ----------

def test_card_cap_applies():
    # 프로토타입 카드 예시: 30만 원 x 10% = 3만 원이지만 한도 1만 원, 연회비 15,000원
    r = calc.card(300_000, 10.0, 10_000, 15_000)
    assert r.per_month == 10_000
    assert r.annual == 120_000
    assert r.net == 105_000


def test_card_under_cap():
    r = calc.card(50_000, 10.0, 10_000, 15_000)
    assert r.per_month == pytest.approx(5_000)
    assert r.net == pytest.approx(45_000)


def test_card_no_cap_vs_zero_cap():
    # None은 한도 없음, 0은 할인 0원. 둘을 섞으면 안 된다
    assert calc.card(300_000, 10.0, None, 0).per_month == pytest.approx(30_000)
    assert calc.card(300_000, 10.0, 0, 0).per_month == 0


def test_card_net_can_be_negative():
    r = calc.card(10_000, 5.0, None, 15_000)
    assert r.net < 0
    assert calc.won(r.net) == "-9,000원"


# ---------- 잘못된 입력 ----------

@pytest.mark.parametrize(
    "call",
    [
        lambda: calc.savings(-1, 3.0, 12),
        lambda: calc.savings(300_000, -3.0, 12),
        lambda: calc.savings(300_000, 3.0, 0),
        lambda: calc.deposit(1_000_000, 3.0, 0),
        lambda: calc.loan(1_000_000, 3.0, 0),
        lambda: calc.loan(-1, 3.0, 12),
        lambda: calc.card(-1, 10.0, None, 0),
        lambda: calc.card(300_000, 10.0, -1, 0),
    ],
)
def test_invalid_inputs_raise(call):
    with pytest.raises(ValueError):
        call()


# ---------- 표시 ----------

@pytest.mark.parametrize(
    "n, expected",
    [(0, "0원"), (2.5, "3원"), (18_135.23, "18,135원"), (1_000_000, "1,000,000원")],
)
def test_won_rounds_half_up(n, expected):
    assert calc.won(n) == expected
