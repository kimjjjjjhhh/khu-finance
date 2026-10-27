"""원문 하이라이트."""
from core.highlight import find_marks, highlight_html
from core.schema import Risk, Term

TEXT = "만기 전에 중도해지하면 중도해지이율이 적용됩니다.\n<b>우대금리</b>는 조건부입니다."


def term(t, surfaces, found=True):
    return Term(term=t, meaning=f"{t} 뜻", surfaces=surfaces, found=found)


def test_risk_wins_over_overlapping_term():
    marks = find_marks(TEXT, [term("중도해지", ["중도해지"])],
                       [Risk(phrase="중도해지이율이 적용", why="이자가 거의 없어요", level="high")])
    kinds = [(TEXT[m.start:m.end], m.kind) for m in marks]
    assert kinds == [("중도해지", "term"), ("중도해지이율이 적용", "risk")]


def test_unverified_items_are_not_marked():
    marks = find_marks(TEXT, [term("우대금리", ["우대금리"], found=False)],
                       [Risk(phrase="원금 손실", why="w", found=False)])
    assert marks == []


def test_html_is_escaped_and_has_tips():
    h = highlight_html(TEXT, [term("우대금리", ["우대금리"])], [])
    assert "&lt;b&gt;" in h and "<b>" not in h  # 원문 속 태그가 그대로 실행되면 안 된다
    assert '<span class="hl hl-term" tabindex="0">우대금리<span class="tip">우대금리 · 우대금리 뜻</span></span>' in h
    assert "<br>" in h
    assert "<script" not in h
