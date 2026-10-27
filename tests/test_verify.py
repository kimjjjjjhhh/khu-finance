"""환각 방지: 인용문 원문 대조."""
from core.glossary import Glossary
from core.schema import GlossEntry, Pair, Risk, Term
from core.verify import find_quote, verify_pairs, verify_risks, verify_terms

TEXT = "전월 실적 30만 원 이상일 때\n청구할인해 드립니다. 리볼빙을 신청하면 연 17.9%의 수수료가 붙습니다."


def test_find_quote_ignores_spacing_and_edge_punctuation():
    assert find_quote("전월실적 30만 원 이상일 때 청구할인", TEXT) == "전월 실적 30만 원 이상일 때\n청구할인"
    assert find_quote("‘리볼빙을 신청하면’.", TEXT) == "리볼빙을 신청하면"


def test_find_quote_rejects_changed_words():
    assert find_quote("연 19.9%의 수수료", TEXT) is None
    assert find_quote("   ", TEXT) is None


def test_verify_pairs_and_risks():
    pairs = verify_pairs([Pair(original="청구할인해 드립니다.", easy="a"),
                          Pair(original="연회비가 없습니다.", easy="b")], TEXT)
    assert [p.found for p in pairs] == [True, False]
    risks = verify_risks([Risk(phrase="연 17.9%의 수수료", why="w", level="high"),
                          Risk(phrase="연 17.9% 이자", why="w")], TEXT)
    assert [r.found for r in risks] == [True, False]


def test_verify_terms_fills_surfaces_and_glossary_category():
    g = Glossary([GlossEntry(term="전월실적", category="카드", meaning="m", aliases=["전월 실적"])])
    terms = verify_terms([Term(term="전월실적", meaning="AI 뜻", category="기타"),
                          Term(term="연회비", meaning="m")], TEXT, g)
    assert terms[0].found and terms[0].surfaces == ["전월 실적"]
    assert terms[0].category == "카드"  # 분야는 사전 값을 따른다 (이해도 집계가 흔들리지 않게)
    assert terms[0].meaning == "AI 뜻"
    assert not terms[1].found and terms[1].surfaces == []
