"""위험 조항 규칙: 불러오기와 원문에서 찾기."""
import json
import re
from pathlib import Path

import config
from core import fallback
from core.schema import Risk, RiskRule


class RiskMatcher:
    def __init__(self, rules: list[RiskRule], from_fallback: bool = False):
        # '주의(high)' 규칙을 먼저 검사해서, 같은 말이 걸리면 더 강한 경고가 남게 한다
        self.rules = sorted(rules, key=lambda r: r.level != "high")
        self.from_fallback = from_fallback
        self._compiled = [(r, [re.compile(p) for p in r.patterns]) for r in self.rules]

    def find(self, text: str) -> list[Risk]:
        """규칙마다 처음 걸린 말을 phrase로 담고, 원문에 나온 순서대로 돌려준다."""
        hits: list[tuple[int, Risk]] = []
        seen: set[str] = set()
        for rule, pats in self._compiled:
            for p in pats:
                m = p.search(text)
                if m and m.group(0) not in seen:
                    seen.add(m.group(0))
                    hits.append((m.start(), Risk(phrase=m.group(0), why=rule.why, level=rule.level)))
                    break
        return [r for _, r in sorted(hits, key=lambda h: h[0])]


def parse_rules(raw: list) -> tuple[list[RiskRule], list[str]]:
    rules, errors = [], []
    for n, item in enumerate(raw):
        try:
            rule = RiskRule.model_validate(item)
            for p in rule.patterns:
                re.compile(p)
            rules.append(rule)
        except Exception as ex:  # 형식 오류나 잘못된 정규식
            errors.append(f"{n}번째 항목 {item!r}: {ex.__class__.__name__}")
    return rules, errors


def load_risks(path: Path = config.RISKS_PATH) -> RiskMatcher:
    """data/risks.json을 읽는다. 없거나 비어 있으면 프로토타입 내장 규칙을 쓴다."""
    try:
        rules, _ = parse_rules(json.loads(path.read_text(encoding="utf-8")))
        if rules:
            return RiskMatcher(rules)
    except (OSError, ValueError):
        pass
    rules, _ = parse_rules([{**r, "origin": "prototype"} for r in fallback.RISKS])
    return RiskMatcher(rules, from_fallback=True)
