"""평가 실행.

  python -m eval.run              규칙 기반 분석 평가 (API 호출 없음)
  python -m eval.run --ai         AI 통역 평가: 호출할 샘플 수만 알려 주고 끝낸다
  python -m eval.run --ai --yes   실제로 호출한다 (샘플마다 1~2번, 크레딧을 씀)

정답(gold)이 있는 data/samples/*.json만 쓴다. txt 시험본은 정답이 없다고 보고 넣지 않는다.
"""
import argparse
import sys

from core import llm
from core.ai_analyze import analyze_ai
from core.analyze import analyze_rule
from core.glossary import load_glossary
from core.risks import load_risks
from core.samples import load_samples
from eval.metrics import score, total


def pct(h: int, t: int) -> str:
    return f"{h}/{t} ({h / t:.0%})" if t else "-"


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--ai", action="store_true", help="AI 통역을 평가 (실제 호출)")
    ap.add_argument("--yes", action="store_true", help="--ai일 때 실제 호출에 동의")
    args = ap.parse_args(argv)

    samples = [s for s in load_samples() if s.gold]
    glossary, risks = load_glossary(), load_risks()
    print(f"정답 있는 샘플 {len(samples)}개: {', '.join(s.id for s in samples)}")

    if args.ai:
        provider = llm.get_provider()
        if provider is None:
            print("API 키가 없어요. CHATKHU_API_KEY를 설정하세요.")
            return 2
        if not args.yes:
            print(f"AI 평가는 샘플 {len(samples)}개를 각각 호출해요 (형식 오류면 샘플당 1번 더). "
                  "진행하려면 --yes를 붙이세요.")
            return 2
        results = [analyze_ai(s.text, provider, glossary, risks) for s in samples]
        mode = "AI 통역"
    else:
        results = [analyze_rule(s.text, glossary, risks) for s in samples]
        mode = "규칙 기반"

    scores = [score(a, s) for a, s in zip(results, samples)]
    print(f"\n## {mode} 평가\n")
    print("| 샘플 | 종류 | 금리 | 기간 | 금액 | 숫자 합계 | 위험 재현 | 찾은 위험 구절 |")
    print("|---|---|---|---|---|---|---|---|")
    for sc, a in zip(scores, results):
        n = sc.number_hits
        h, t = sum(x for x, _ in n.values()), sum(y for _, y in n.values())
        cell = lambda k: pct(*n[k]) if k in n else "제외"
        mode_note = "" if a.source == "ai" or mode == "규칙 기반" else " (대체됨)"
        print(f"| {sc.sample}{mode_note} | {'O' if sc.doc_type_ok else 'X'} | {cell('금리')} | {cell('기간')} | "
              f"{cell('금액')} | {pct(h, t)} | {pct(sc.risk_hit, sc.risk_total)} | {sc.found_risks} |")
    tt = total(scores)
    print(f"| **합계** | {pct(*tt['doc_type'])} | {pct(*tt['numbers']['금리'])} | {pct(*tt['numbers']['기간'])} | "
          f"{pct(*tt['numbers']['금액'])} | **{pct(*tt['number_hit'])}** | **{pct(*tt['risk_hit'])}** | |")
    if mode == "AI 통역":
        used = sum(a.prompt_tokens + a.completion_tokens for a in results)
        print(f"\n토큰 합계 {used:,} · 규칙 기반으로 대체된 샘플 {sum(a.source != 'ai' for a in results)}개")
    print("\n### 못 맞힌 항목")
    for sc in scores:
        for m in sc.misses:
            print(f"- {sc.sample}: {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
