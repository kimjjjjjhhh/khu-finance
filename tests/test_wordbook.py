"""용어장: 세션 누적, 사전 뜻 우선, 미검증 표시."""
from core.glossary import Glossary
from core.schema import GlossEntry, Term
from core.wordbook import add_terms, entries

G = Glossary([
    GlossEntry(term="전월실적", category="카드", meaning="사전 뜻: 지난달 사용액", aliases=["전월 실적"]),
    GlossEntry(term="변동금리", category="대출", meaning="사전 뜻: 바뀌는 금리"),
])


def test_dictionary_meaning_wins_over_ai_meaning():
    book = {}
    add_terms(book, [Term(term="전월 실적", meaning="AI 뜻", category="기타", surfaces=["전월 실적"])], G, "문서A")
    [e] = entries(book)
    assert (e.term, e.category, e.meaning, e.verified) == ("전월실적", "카드", "사전 뜻: 지난달 사용액", True)


def test_unknown_term_keeps_ai_meaning_marked_unverified():
    book = {}
    add_terms(book, [Term(term="납입", meaning="돈을 넣는 것", category="예적금")], G, "문서A")
    [e] = entries(book)
    assert e.meaning == "돈을 넣는 것" and not e.verified


def test_unfound_terms_are_not_collected():
    book = {}
    add_terms(book, [Term(term="복리", meaning="m", found=False)], G, "문서A")
    assert book == {}


def test_accumulates_documents_without_duplicates():
    book = {}
    add_terms(book, [Term(term="변동금리", meaning="x")], G, "문서A")
    add_terms(book, [Term(term="변동금리", meaning="y"), Term(term="변동 금리", meaning="z")], G, "문서B")
    add_terms(book, [Term(term="변동금리", meaning="x")], G, "문서A")
    [e] = entries(book)
    assert e.docs == ["문서A", "문서B"]


def test_later_dictionary_hit_replaces_unverified_entry():
    book = {}
    add_terms(book, [Term(term="변동 금리", meaning="AI 뜻")], Glossary([]), "문서A")
    add_terms(book, [Term(term="변동금리", meaning="AI 뜻")], G, "문서B")
    [e] = entries(book)
    assert e.verified and e.docs == ["문서A", "문서B"]


def test_filter_and_order():
    book = {}
    add_terms(book, [Term(term="변동금리", meaning="x"), Term(term="전월실적", meaning="x"),
                     Term(term="가나다", meaning="AI", category="예적금")], G, "문서A")
    assert [e.term for e in entries(book)] == ["가나다", "변동금리", "전월실적"]
    assert [e.term for e in entries(book, "카드")] == ["전월실적"]
    assert entries(book, "기타") == []
