"""환각 방지: AI가 원문을 인용했다고 한 글(문장, 용어, 위험 구절)이 원문에 실제로 있는지 대조한다.

숫자 대조는 core/extract.check_numbers가 맡는다. 여기서는 글자 대조만 한다.
띄어쓰기와 줄바꿈 차이, 인용 끝의 마침표는 봐준다. 그 밖에 한 글자라도 다르면 '원문에서 확인 안 됨'이다.
"""
import re

from core.glossary import Glossary
from core.schema import Pair, Risk, Term

_EDGE_PUNCT = " \t\n.,;:·'\"‘’“”"


def quote_pattern(quote: str) -> re.Pattern | None:
    """글자 사이 띄어쓰기를 허용하는 정규식. 인용이 비면 None."""
    chars = re.sub(r"\s+", "", quote.strip(_EDGE_PUNCT))
    if not chars:
        return None
    return re.compile(r"\s*".join(re.escape(ch) for ch in chars))


def find_quote(quote: str, text: str) -> str | None:
    """원문에 실제로 나온 표기를 돌려준다. 없으면 None."""
    p = quote_pattern(quote)
    m = p.search(text) if p else None
    return m.group(0) if m else None


def _surfaces(words: list[str], text: str) -> list[str]:
    out: list[str] = []
    for w in words:
        p = quote_pattern(w)
        for m in p.finditer(text) if p else []:
            if m.group(0) not in out:
                out.append(m.group(0))
    return out


def verify_pairs(pairs: list[Pair], text: str) -> list[Pair]:
    return [p.model_copy(update={"found": find_quote(p.original, text) is not None}) for p in pairs]


def verify_risks(risks: list[Risk], text: str) -> list[Risk]:
    return [r.model_copy(update={"found": find_quote(r.phrase, text) is not None}) for r in risks]


def verify_terms(terms: list[Term], text: str, glossary: Glossary | None = None) -> list[Term]:
    """원문 표기(surfaces)를 채운다. 사전에 있는 용어면 별칭 표기도 찾고, 분야는 사전 값을 따른다."""
    out: list[Term] = []
    for t in terms:
        entry = glossary.lookup(t.term) if glossary else None
        words = [t.term, *t.surfaces] + ([entry.term, *entry.aliases] if entry else [])
        surfaces = _surfaces(words, text)
        update = {"surfaces": surfaces, "found": bool(surfaces)}
        if entry:
            update["category"] = entry.category
        out.append(t.model_copy(update=update))
    return out
