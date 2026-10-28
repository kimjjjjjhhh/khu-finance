"""평가 지표. 분석 결과(Analysis)와 정답(gold)을 비교한다.

숫자 추출 정확도: 정답 숫자 중 맞힌 비율. 금리는 이름이 달라도(최저금리/적용금리) 값이 같으면 맞힌 것으로 본다.
  원문에서 확인 안 된 정답(gold_issues)은 평가에서 뺀다.
  분석이 원문 대조에 실패한 숫자(found=False)는 화면에서 쓰지 않으므로 맞혀도 틀린 것으로 센다.
위험 조항 재현율: 정답 위험 문장 중 찾아낸 비율. 찾은 구절(원문에서 확인된 것)이 정답 문장 안에 있거나,
  정답 문장이 찾은 구절 안에 있으면 찾은 것으로 본다 (띄어쓰기 무시).
"""
import re
from dataclasses import dataclass, field

from core.schema import Analysis, Sample


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s).strip(".,")


@dataclass
class Score:
    sample: str
    doc_type_ok: bool
    number_hits: dict[str, list[int]] = field(default_factory=dict)  # 종류 -> [맞힘, 정답 수]
    risk_hit: int = 0
    risk_total: int = 0
    found_risks: int = 0  # 분석이 내놓은 (원문 확인된) 위험 구절 수
    misses: list[str] = field(default_factory=list)  # 못 맞힌 정답 (원인 분석용)


def score(a: Analysis, s: Sample) -> Score:
    g = s.gold or {}
    skip = {i.split("=")[0] for i in s.gold_issues}
    ok = {c.field for c in a.number_checks if c.found}
    sc = Score(sample=s.id, doc_type_ok=a.kind == g.get("docType"))

    rates = {round(r.value, 6) for i, r in enumerate(a.numbers.rates) if f"rates[{i}]" in ok}
    hit = [0, 0]
    for r in g.get("rates", []):
        hit[1] += 1
        if round(float(r["value"]), 6) in rates:
            hit[0] += 1
        else:
            sc.misses.append(f"금리 {r['label']} {r['value']}")
    sc.number_hits["금리"] = hit
    for name, label in (("months", "기간"), ("amount", "금액")):
        if g.get(name) is None or name in skip:
            continue
        got = getattr(a.numbers, name)
        right = got == g[name] and name in ok
        sc.number_hits[label] = [int(right), 1]
        if not right:
            sc.misses.append(f"{label} 정답 {g[name]} / 분석 {got}")

    phrases = [_norm(r.phrase) for r in a.risks if r.found]
    sc.found_risks = len(phrases)
    for sent in g.get("risks", []):
        n = _norm(sent)
        sc.risk_total += 1
        if any(p and (p in n or n in p) for p in phrases):
            sc.risk_hit += 1
        else:
            sc.misses.append(f"위험 '{sent[:30]}…'")
    return sc


def total(scores: list[Score]) -> dict:
    nums = {}
    for sc in scores:
        for k, (h, t) in sc.number_hits.items():
            nums.setdefault(k, [0, 0])
            nums[k][0] += h
            nums[k][1] += t
    nh, nt = sum(h for h, _ in nums.values()), sum(t for _, t in nums.values())
    rh, rt = sum(s.risk_hit for s in scores), sum(s.risk_total for s in scores)
    return {"numbers": nums, "number_acc": nh / nt if nt else 0.0, "number_hit": (nh, nt),
            "risk_recall": rh / rt if rt else 0.0, "risk_hit": (rh, rt),
            "doc_type": (sum(s.doc_type_ok for s in scores), len(scores))}
