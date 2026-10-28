"""용어장: 통역할 때마다 만난 용어를 세션 안에 모은다 (저장하지 않음).

뜻은 검증된 사전(data/glossary.json)에 있으면 사전 것을 쓴다.
사전에 없는 용어는 AI가 쓴 뜻을 그대로 두되 verified=False로 표시해 화면에 'AI 설명(미검증)'을 붙인다.
원문에서 확인 안 된 용어(found=False)는 AI가 지어냈을 수 있으므로 모으지 않는다.
"""
import re
from dataclasses import dataclass, field

from core.glossary import Glossary
from core.schema import CATEGORIES, Term


@dataclass
class WordEntry:
    term: str
    category: str
    meaning: str
    verified: bool  # True: 사전 뜻, False: AI 설명(미검증)
    docs: list[str] = field(default_factory=list)  # 이 용어를 만난 문서 이름 (만난 순서)


def add_terms(book: dict[str, WordEntry], terms: list[Term], glossary: Glossary, doc: str) -> None:
    for t in terms:
        if not t.found:
            continue
        e = next((x for x in map(glossary.lookup, [t.term, *t.surfaces]) if x), None)
        if e:
            key, new = e.term, WordEntry(e.term, e.category, e.meaning, verified=True)
        else:
            key, new = re.sub(r"\s+", "", t.term), WordEntry(t.term, t.category, t.meaning, verified=False)
        cur = book.get(key)
        if cur is None or (new.verified and not cur.verified):
            new.docs = cur.docs if cur else []
            book[key] = cur = new
        if doc not in cur.docs:
            cur.docs.append(doc)


def entries(book: dict[str, WordEntry], category: str | None = None) -> list[WordEntry]:
    """분야 순서(예적금, 대출, 카드, 기타), 같은 분야 안에서는 가나다순."""
    rows = [e for e in book.values() if category in (None, e.category)]
    return sorted(rows, key=lambda e: (CATEGORIES.index(e.category), e.term))
