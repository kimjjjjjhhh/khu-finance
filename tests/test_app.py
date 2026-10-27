"""화면 스모크 테스트: 브라우저 없이 Streamlit 앱을 실행해 오류 없이 그려지는지 본다."""
import pytest
from streamlit.testing.v1 import AppTest

import config
from core.samples import load_samples


def _app() -> AppTest:
    at = AppTest.from_file(str(config.ROOT / "app.py"), default_timeout=30)
    at.run()
    return at


def test_empty_state():
    at = _app()
    assert not at.exception
    assert any("빠른 분석" in m.value for m in at.markdown)


def test_analyze_without_text_shows_warning():
    at = _app()
    at.button[0].click().run()
    assert at.warning[0].value == "통역할 문서를 먼저 붙여넣어 주세요."


@pytest.mark.parametrize("name", [s.name for s in load_samples()])
def test_every_sample_renders(name):
    at = _app()
    at.selectbox[0].select(name).run()
    assert not at.exception
    assert at.metric, "계산 결과가 보여야 한다"


def test_loan_sample_shows_verification_value():
    at = _app()
    at.selectbox[0].select("학자금 대출 안내").run()
    # 200만 원, 연 1.7%, 120개월 -> 월 18,135원 (문서에서 읽은 값이 계산기에 채워짐)
    assert at.metric[0].value == "18,135원"


def test_pasted_text_and_edit_number():
    at = _app()
    at.text_area[0].input("정기적금 월 30만 원, 기본금리 연 3.0%, 기간 12개월").run()
    at.button[0].click().run()
    assert not at.exception
    assert at.metric[0].value == "3,649,491원"  # 과제 검증값과 같은 조건
    at.number_input(key="months1").set_value(24).run()
    assert at.metric[0].value != "3,649,491원"  # 사용자가 고친 값으로 다시 계산
