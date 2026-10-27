"""용어 사전: 불러오기와 원문에서 용어 찾기."""
import json
import re
from pathlib import Path

import config
from core import fallback
from core.schema import GlossEntry, Term


def _key(word: str) -> str:
    return re.sub(r"\s+", "", word)


def _word_pattern(word: str) -> str:
    # 글자 사이 띄어쓰기를 허용한다: '전월실적'으로 '전월 실적'도 찾는다
    return r"\s*".join(re.escape(ch) for ch in _key(word))


class Glossary:
    def __init__(self, entries: list[GlossEntry], from_fallback: bool = False):
        self.entries = entries
        self.from_fallback = from_fallback
        # 단어 -> 항목 번호. 별칭을 먼저 넣고 표제어로 덮어써서, 다른 항목의 별칭보다 표제어가 이긴다
        # (예: '현금서비스'는 '단기카드대출'의 별칭이기도 하지만 '현금서비스' 항목으로 찾는다)
        self._index: dict[str, int] = {}
        for i, e in enumerate(entries):
            for a in e.aliases:
                self._index.setdefault(_key(a), i)
        owned: set[str] = set()
        for i, e in enumerate(entries):
            k = _key(e.term)
            if k not in owned:  # 표제어가 중복이면 먼저 나온 항목을 쓴다
                self._index[k] = i
                owned.add(k)
        # 긴 단어를 앞에 둬서 '예금자보호'가 '예금'보다 먼저 잡히게 한다
        words = sorted(self._index, key=len, reverse=True)
        self._re = re.compile("|".join(_word_pattern(w) for w in words)) if words else None

    def find_terms(self, text: str) -> list[Term]:
        """원문에 나온 용어를 나온 순서대로 돌려준다. surfaces에는 원문 표기 그대로 담는다."""
        found: dict[int, Term] = {}
        if self._re is None:
            return []
        for m in self._re.finditer(text):
            i = self._index[_key(m.group(0))]
            e = self.entries[i]
            t = found.setdefault(i, Term(term=e.term, meaning=e.meaning, category=e.category))
            if m.group(0) not in t.surfaces:
                t.surfaces.append(m.group(0))
        return list(found.values())

    def lookup(self, word: str) -> GlossEntry | None:
        i = self._index.get(_key(word))
        return None if i is None else self.entries[i]

    def related(self, entry: GlossEntry) -> set[str]:
        """표제어나 별칭을 공유하는 항목들의 표제어. 퀴즈에서 정답과 비슷한 오답을 빼는 데 쓴다."""
        words = {_key(entry.term), *map(_key, entry.aliases)}
        return {
            e.term for e in self.entries
            if words & {_key(e.term), *map(_key, e.aliases)}
        }


def parse_entries(raw: list) -> tuple[list[GlossEntry], list[str]]:
    """형식이 맞는 항목만 받고, 틀린 항목은 이유를 돌려준다 (고쳐 쓰지 않는다)."""
    entries, errors = [], []
    for n, item in enumerate(raw):
        try:
            entries.append(GlossEntry.model_validate(item))
        except Exception as ex:  # pydantic ValidationError 등
            errors.append(f"{n}번째 항목 {item!r}: {ex.__class__.__name__}")
    return entries, errors


def load_glossary(path: Path = config.GLOSSARY_PATH) -> Glossary:
    """data/glossary.json을 읽는다. 없거나 비어 있으면 프로토타입 내장 사전을 쓴다."""
    try:
        entries, _ = parse_entries(json.loads(path.read_text(encoding="utf-8")))
        if entries:
            return Glossary(entries)
    except (OSError, ValueError):
        pass
    entries, _ = parse_entries(fallback.GLOSS)
    return Glossary(entries, from_fallback=True)
