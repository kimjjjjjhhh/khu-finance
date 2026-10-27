import pytest

from core.extract import check_numbers, extract_numbers, numbers_in_text
from core.schema import Numbers, Rate


@pytest.mark.parametrize(
    "text, value",
    [("월 30만 원", 300_000), ("15,000원", 15_000), ("1만원", 10_000), ("5천만 원", 50_000_000),
     ("최대 500만 원", 5_000_000), ("1억 원", 100_000_000)],
)
def test_money_formats(text, value):
    assert value in numbers_in_text(text).amounts


def test_years_count_as_months():
    t = numbers_in_text("상환기간 10년, 거치 6개월")
    assert {120, 6} <= t.months


def test_rule_extraction_labels_rates_by_nearest_word():
    n = extract_numbers(
        "기본금리는 연 3.0%이며, 최대 연 1.5%의 우대금리가 추가되어 최고 연 4.5%까지. "
        "중도해지 시 중도해지이율 연 0.5%만 적용. 이자소득세 15.4%가 원천징수됩니다.")
    assert [(r.label, r.value) for r in n.rates] == [
        ("기본금리", 3.0), ("우대금리", 1.5), ("최고금리", 4.5), ("중도해지이율", 0.5)]  # 세율 15.4%는 빠진다


def test_percent_point_is_not_a_rate():
    n = extract_numbers("우대금리 연 1.5%p를 더해 적용합니다.")
    assert n.rates == []


def test_card_numbers():
    n = extract_numbers("연회비: 국내 전용 15,000원. 전월 실적 30만 원 이상일 때 10%를 청구할인. 월 할인 한도는 1만 원입니다.")
    assert (n.fee, n.spend, n.discount_rate, n.cap) == (15_000, 300_000, 10.0, 10_000)


def test_monthly_amount_preferred():
    n = extract_numbers("가입 대상 만 19세. 계약 기간: 12개월. 월 최대 30만 원까지 납입. 1인당 5천만 원까지 보호.")
    assert n.months == 12
    assert n.amount == 300_000


def test_empty_text_gives_empty_numbers():
    n = extract_numbers("숫자가 없는 문서입니다.")
    assert n == Numbers()


# ---------- 환각 방지: 원문 대조 ----------

def test_check_numbers_flags_values_not_in_text():
    text = "기본금리는 연 3.0%이며, 기간은 12개월, 월 30만 원."
    n = Numbers(rates=[Rate(label="기본금리", value=3), Rate(label="최고금리", value=4.5)],
                months=24, amount=300_000)
    found = {c.field: c.found for c in check_numbers(n, text)}
    assert found == {"rates[0]": True, "rates[1]": False, "months": False, "amount": True}


def test_check_numbers_matches_different_notation():
    # AI가 300000으로 답해도 원문 '30만 원'과 같은 값으로 인정한다
    n = Numbers(amount=300_000, fee=15_000)
    assert all(c.found for c in check_numbers(n, "월 30만 원, 연회비 15,000원"))


def test_check_numbers_skips_missing_fields():
    assert check_numbers(Numbers(), "아무 문서") == []
