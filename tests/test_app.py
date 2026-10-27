"""화면 스모크 테스트: 브라우저 없이 Streamlit 앱을 실행해 오류 없이 그려지는지 본다."""
import pytest
from streamlit.testing.v1 import AppTest

import config
from core import llm
from core.mdsafe import esc
from core.samples import load_samples
from tests.fakes import DOC, GOOD, FakeProvider, cut, reply


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


def _sources(at: AppTest) -> list[str]:
    """계산기 칸 아래 표시 (문서에서 읽음 / 예시값 / 내가 입력)를 화면 순서대로."""
    return [c.value for c in at.caption if c.value in ("문서에서 읽음", "예시값", "내가 입력")]


def test_loan_sample_shows_verification_value():
    at = _app()
    at.selectbox[0].select("학자금 대출 안내").run()
    # 금액 칸은 예시값, 금리·기간은 문서에서 읽음. 문서의 '최대 200만 원'은 버튼으로만
    assert _sources(at) == ["예시값", "문서에서 읽음", "문서에서 읽음"]
    next(b for b in at.button if b.label == "문서의 최대 한도 200만 원").click().run()
    assert at.number_input(key="amount1").value == 2_000_000
    assert _sources(at) == ["문서에서 읽음"] * 3
    # 200만 원, 연 1.7%, 120개월 -> 월 18,135원 (과제 검증값)
    assert at.metric[0].value == "18,135원"


def test_card_spend_condition_shown_separately():
    at = _app()
    at.selectbox[0].select("대학생 카드 안내").run()
    assert any(i.value == esc("혜택 조건: 지난달 30만 원 이상 사용") for i in at.info)
    # 연회비, 할인율, 한도는 문서에서 / 사용액은 예시값
    assert _sources(at) == ["문서에서 읽음", "문서에서 읽음", "예시값", "문서에서 읽음"]
    next(b for b in at.button if b.label == "사용액 칸에 30만 원 넣기").click().run()
    assert at.number_input(key="spend1").value == 300_000
    assert _sources(at)[2] == "문서에서 읽음"


def test_pasted_text_and_edit_number():
    at = _app()
    at.text_area[0].input("정기적금 월 30만 원, 기본금리 연 3.0%, 기간 12개월").run()
    at.button[0].click().run()
    assert not at.exception
    assert at.metric[0].value == "3,649,491원"  # 과제 검증값과 같은 조건
    at.number_input(key="months1").set_value(24).run()
    assert at.metric[0].value != "3,649,491원"  # 사용자가 고친 값으로 다시 계산
    assert _sources(at) == ["문서에서 읽음", "문서에서 읽음", "내가 입력"]


def test_changed_document_keeps_old_result_with_notice():
    at = _app()
    at.selectbox[0].select("학자금 대출 안내").run()
    assert not any("문서가 바뀌었어요" in i.value for i in at.info)
    at.text_area[0].input("완전히 다른 문서").run()
    assert any("문서가 바뀌었어요. 다시 통역해 주세요" in i.value for i in at.info)


# ---------- AI 통역 (가짜 Provider, 실제 호출 없음) ----------

def _ai_click(at: AppTest, text: str) -> AppTest:
    at.text_area[0].input(text).run()
    next(b for b in at.button if b.label == "AI로 통역하기").click().run()
    return at


def _captions(at: AppTest) -> str:
    return "\n".join(c.value for c in at.caption)


def test_ai_without_key_shows_rule_mode():
    at = _ai_click(_app(), DOC)
    assert not at.exception
    assert any("규칙 기반 모드" in m.value for m in at.markdown)
    assert "API 키" in at.warning[0].value
    assert "토큰 0개" in _captions(at)


def test_ai_result_tokens_and_warnings(monkeypatch):
    p = FakeProvider(reply(usage=(1200, 345)))
    monkeypatch.setattr(llm, "get_provider", lambda: p)
    at = _ai_click(_app(), DOC)
    assert not at.exception
    caps = _captions(at)
    assert "AI 통역" in caps
    assert "이번 통역에 쓴 토큰 1,545개 (입력 1,200 · 출력 345)" in caps
    assert any("원문에서 확인 안 됨" in m.value for m in at.markdown)  # 지어낸 문장에 경고
    # 원문에 있는 기본금리 3.0%만 계산기에 들어가고, 지어낸 최고금리 5.0%는 안 들어간다
    assert at.number_input(key="rate1").value == 3.0
    assert _sources(at) == ["예시값", "문서에서 읽음", "문서에서 읽음"]  # '월 최대 30만 원'은 버튼으로만


def test_ai_text_markdown_is_escaped(monkeypatch):
    weird = {**GOOD, "verdict": "금리 연 5.5~9.9%, 수수료 ~ $100 $200 *주의*",
             "pairs": [{"original": "기본금리는 연 3.0%이며", "easy": "보통 3%예요 ~ :red[빨강] _강조_"}]}
    monkeypatch.setattr(llm, "get_provider", lambda: FakeProvider(reply(weird)))
    at = _ai_click(_app(), DOC)
    md = [m.value for m in at.markdown]
    assert r"#### 금리 연 5\.5\~9\.9%, 수수료 \~ \$100 \$200 \*주의\*" in md
    assert r"**보통 3%예요 \~ \:red\[빨강\] \_강조\_**" in md


def test_ai_same_document_uses_cache(monkeypatch):
    p = FakeProvider(reply(), reply())
    monkeypatch.setattr(llm, "get_provider", lambda: p)
    at = _ai_click(_app(), DOC)
    next(b for b in at.button if b.label == "AI로 통역하기").click().run()
    assert len(p.prompts) == 1  # 같은 문서는 다시 부르지 않는다
    assert "추가로 쓴 토큰은 없어요" in _captions(at)


def test_ai_bad_answers_fall_back(monkeypatch):
    p = FakeProvider(reply("아님", usage=(10, 2)), reply("{}", usage=(10, 2)))
    monkeypatch.setattr(llm, "get_provider", lambda: p)
    at = _ai_click(_app(), DOC)
    assert any("규칙 기반 모드" in m.value for m in at.markdown)
    assert "형식" in at.warning[0].value
    assert "토큰 24개" in _captions(at)  # 실패했어도 쓴 토큰은 보여 준다


def test_ai_cut_answer_shows_notice(monkeypatch):
    monkeypatch.setattr(llm, "get_provider", lambda: FakeProvider(cut(keep='"level": "high"}')))
    at = _ai_click(_app(), DOC)
    assert not at.exception
    assert any("응답이 길어 일부가 생략됐어요" in m.value for m in at.info)
