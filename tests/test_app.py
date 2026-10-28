"""화면 스모크 테스트: 브라우저 없이 Streamlit 앱을 실행해 오류 없이 그려지는지 본다."""
import pytest
from streamlit.testing.v1 import AppTest

import config
from core import limits, llm
from core.glossary import load_glossary
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


# ---------- 퀴즈 (사전으로만 출제, LLM 없음) ----------

def _quiz_radios(at: AppTest):
    return [r for r in at.radio if r.key and r.key.startswith("quiz")]


def _score(at: AppTest) -> str:
    return next(m.value for m in at.markdown if "이번 문제" in m.value).replace("**", "")


def _answer_all(at: AppTest, correct: bool) -> AppTest:
    """세션의 퀴즈 정답을 보고 모두 맞히거나 모두 틀린다."""
    for i, q in enumerate(at.session_state.quiz):
        r = _quiz_radios(at)[i]
        r.set_value(q.answer if correct else (q.answer + 1) % len(q.options)).run()
    return at


def test_quiz_shows_three_questions_from_dictionary():
    at = _app()
    at.selectbox[0].select("학자금 대출 안내").run()
    assert len(_quiz_radios(at)) == 3
    meanings = {e.meaning for e in load_glossary().entries}
    for q in at.session_state.quiz:
        assert set(q.options) <= meanings


def test_quiz_answer_feedback_score_and_understanding():
    at = _app()
    at.selectbox[0].select("학자금 대출 안내").run()
    first = at.session_state.quiz[0]
    _quiz_radios(at)[0].set_value(first.answer).run()
    assert any(s.value.startswith("정답이에요.") for s in at.success)
    assert _quiz_radios(at)[0].disabled  # 고른 답은 바꿀 수 없다 (처음 답만 센다)
    _quiz_radios(at)[1].set_value((at.session_state.quiz[1].answer + 1) % 3).run()
    assert any(e.value.startswith("아쉬워요. 정답은") for e in at.error)
    assert "이번 문제 1/3" in _score(at)
    stats = at.session_state.quiz_stats
    assert sum(t for _, t in stats.values()) == 2 and sum(c for c, _ in stats.values()) == 1


def test_quiz_retry_makes_new_round_and_keeps_session_totals():
    at = _app()
    at.selectbox[0].select("학자금 대출 안내").run()
    _answer_all(at, correct=True)
    assert _score(at) == "이번 문제 3/3 · 이 문서 누적 3/3"
    next(b for b in at.button if b.label == "다시 풀기").click().run()
    assert all(r.value is None and not r.disabled for r in _quiz_radios(at))
    _answer_all(at, correct=False)
    assert _score(at) == "이번 문제 0/3 · 이 문서 누적 3/6"
    assert sum(t for _, t in at.session_state.quiz_stats.values()) == 6


def test_understanding_bars_accumulate_across_documents():
    at = _app()
    at.selectbox[0].select("학자금 대출 안내").run()
    _answer_all(at, correct=True)
    at.selectbox[0].select("대학생 카드 안내").run()
    _answer_all(at, correct=False)
    stats = at.session_state.quiz_stats
    assert sum(t for _, t in stats.values()) == 6  # 문서를 바꿔도 세션 안에서 누적
    assert len(at.session_state.doc_scores) == 2
    texts = [p.proto.text for p in at.get("progress")]
    assert any(t.startswith("대출 · ") and "정답" in t for t in texts)


# ---------- 긴 문서 ----------

def test_char_count_and_truncation_notice(monkeypatch):
    monkeypatch.setattr(config, "MAX_DOC_CHARS", 30)
    monkeypatch.setattr(llm, "get_provider", lambda: FakeProvider(reply()))
    at = _app()
    at.text_area[0].input("짧은 글").run()
    assert "4자 / AI 통역 30자까지" in _captions(at)
    at = _ai_click(at, DOC)
    assert "30자를 넘어서 AI 통역은 앞부분 30자만 해요" in _captions(at)
    assert any("앞부분 30자만 통역했어요" in w.value for w in at.warning)


# ---------- 용어장 (사이드바, 세션 누적) ----------

def _wordbook(at: AppTest) -> list[str]:
    return [m.value for m in at.sidebar.markdown]


def test_wordbook_empty_then_accumulates_across_documents():
    at = _app()
    assert any("아직 모은 용어가 없어요" in c.value for c in at.sidebar.caption)
    at.selectbox[0].select("학자금 대출 안내").run()
    n_loan = len(at.session_state.wordbook)
    assert n_loan > 0
    at.selectbox[0].select("대학생 카드 안내").run()
    assert len(at.session_state.wordbook) > n_loan  # 문서를 바꿔도 세션 안에서 계속 쌓인다
    assert any("만난 문서: 대학생 카드 안내" in c.value for c in at.sidebar.caption)


def test_wordbook_category_filter():
    at = _app()
    at.selectbox[0].select("학자금 대출 안내").run()
    at.selectbox[0].select("대학생 카드 안내").run()
    at.sidebar.radio(key="wb_filter").set_value("카드").run()
    assert _wordbook(at) and all(" · 카드" in m for m in _wordbook(at))
    at.sidebar.radio(key="wb_filter").set_value("기타").run()
    shown = _wordbook(at)
    assert all(" · 기타" in m for m in shown)


def test_wordbook_marks_ai_meaning_unverified(monkeypatch):
    answer = {**GOOD, "terms": [{"term": "우대금리", "meaning": "AI가 쓴 뜻", "category": "예적금"},
                                {"term": "납입", "meaning": "돈을 넣는 것", "category": "예적금"},
                                {"term": "복리", "meaning": "원문에 없음", "category": "예적금"}]}
    monkeypatch.setattr(llm, "get_provider", lambda: FakeProvider(reply(answer)))
    at = _ai_click(_app(), DOC)
    book = _wordbook(at)
    assert any(m.startswith("**납입**") and "AI 설명(미검증)" in m and "돈을 넣는 것" in m for m in book)
    woo = next(m for m in book if m.startswith("**우대금리**"))
    assert "AI 설명(미검증)" not in woo and "AI가 쓴 뜻" not in woo  # 사전 뜻을 쓴다
    assert load_glossary().lookup("우대금리").meaning in woo
    assert not any(m.startswith("**복리**") for m in book)  # 원문에 없는 용어는 모으지 않는다


# ---------- 예시 문서: 미리 통역한 결과 (API 안 부름) ----------

def _precompute(sample_id: str):
    import random
    from core import precomputed
    from core.ai_analyze import analyze_ai
    from core.risks import load_risks
    s = next(x for x in load_samples() if x.id == sample_id)
    a = analyze_ai(s.text, FakeProvider(reply(usage=(1500, 900))), load_glossary(), load_risks(), rng=random.Random(0))
    precomputed.save(s, a)
    return s


def test_example_shows_precomputed_without_call(monkeypatch):
    s = _precompute("p2")
    p = FakeProvider()  # 답이 없어서 불리면 실패한다
    monkeypatch.setattr(llm, "get_provider", lambda: p)
    at = _app()
    at.selectbox[0].select(s.name).run()
    assert any("미리 통역한 결과" in i.value for i in at.info)
    assert "만들 때 쓴 토큰 2,400개" in _captions(at) and "이번에 쓴 토큰 0개" in _captions(at)
    next(b for b in at.button if b.label == "AI로 통역하기").click().run()  # 같은 예시로 AI를 눌러도
    assert p.prompts == [] and any("미리 통역한 결과" in i.value for i in at.info)


def test_example_without_precomputed_does_not_call(monkeypatch):
    p = FakeProvider()
    monkeypatch.setattr(llm, "get_provider", lambda: p)
    at = _app()
    s = next(x for x in load_samples() if x.id == "r1")
    at.selectbox[0].select(s.name).run()
    next(b for b in at.button if b.label == "AI로 통역하기").click().run()
    assert p.prompts == []
    assert any("예시 문서는 미리 통역해 둔 결과만" in w.value for w in at.warning)


def test_pasted_document_still_calls_api(monkeypatch):
    _precompute("p2")
    p = FakeProvider(reply())
    monkeypatch.setattr(llm, "get_provider", lambda: p)
    _ai_click(_app(), DOC)
    assert len(p.prompts) == 1


# ---------- AI 호출 한도 ----------

def _paste_and_ai(at: AppTest, text: str) -> AppTest:
    at.text_area[0].input(text).run()
    next(b for b in at.button if b.label == "AI로 통역하기").click().run()
    return at


def test_session_limit_blocks_sixth_call(monkeypatch):
    p = FakeProvider(*[reply() for _ in range(6)])
    monkeypatch.setattr(llm, "get_provider", lambda: p)
    at = _app()
    for i in range(5):
        _paste_and_ai(at, f"{DOC}\n{i}번째")  # 서로 다른 문서라 저장된 결과를 쓰지 않는다
    assert len(p.prompts) == 5 and "이번 세션 0/5회" in _captions(at)
    _paste_and_ai(at, f"{DOC}\n여섯 번째")
    assert len(p.prompts) == 5
    assert any(w.value == limits.LIMIT_MESSAGE for w in at.warning)


def test_daily_limit_blocks_even_new_session(monkeypatch):
    monkeypatch.setattr(config, "AI_DAILY_LIMIT", 1)
    p = FakeProvider(reply(), reply())
    monkeypatch.setattr(llm, "get_provider", lambda: p)
    _paste_and_ai(_app(), DOC)
    at = _paste_and_ai(_app(), DOC + " 다른 사람")  # 새 세션
    assert len(p.prompts) == 1 and any(w.value == limits.LIMIT_MESSAGE for w in at.warning)
    assert "오늘 전체 0회" in _captions(at)


def test_examples_and_cache_do_not_use_quota(monkeypatch):
    p = FakeProvider(reply())
    monkeypatch.setattr(llm, "get_provider", lambda: p)
    at = _paste_and_ai(_app(), DOC)
    next(b for b in at.button if b.label == "AI로 통역하기").click().run()  # 같은 문서: 저장된 결과
    at.selectbox[0].select("학자금 대출 안내").run()
    assert at.session_state.ai_session.used == 1 and limits.DAILY.used() == 1


def test_limit_caption_shows_config_numbers():
    at = _app()
    assert "이번 세션 5/5회 · 오늘 전체 60회" in _captions(at)
