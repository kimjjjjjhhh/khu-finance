"""예시 문서 AI 통역 결과 미리 만들기 (실제 호출, 크레딧을 씀).

  python -m scripts.precompute           만들 샘플과 호출 수만 알려 주고 끝낸다
  python -m scripts.precompute --yes     실제로 호출해서 data/precomputed/에 저장한다
  python -m scripts.precompute --yes p2  한 샘플만 다시 만든다

규칙 기반으로 대체됐거나 답이 잘린(partial) 결과는 저장하지 않는다.
"""
import argparse
import sys

import config
from core import llm, precomputed
from core.ai_analyze import analyze_ai
from core.glossary import load_glossary
from core.risks import load_risks
from core.samples import load_samples

DEFAULT_IDS = ("p1", "p2", "p3")  # 화면의 예시 문서 3종


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*", default=list(DEFAULT_IDS))
    ap.add_argument("--yes", action="store_true", help="실제 호출에 동의")
    args = ap.parse_args(argv)

    samples = {s.id: s for s in load_samples()}
    targets = [samples[i] for i in args.ids if i in samples]
    if missing := [i for i in args.ids if i not in samples]:
        print(f"없는 샘플: {', '.join(missing)}")
        return 2
    print(f"대상 {len(targets)}개: {', '.join(s.id for s in targets)} -> {config.PRECOMPUTED_DIR}")
    if not args.yes:
        print(f"샘플마다 1번 호출해요 (형식 오류면 1번 더). 진행하려면 --yes를 붙이세요.")
        return 2
    provider = llm.get_provider()
    if provider is None:
        print("API 키가 없어요. CHATKHU_API_KEY를 설정하세요.")
        return 2

    glossary, risks = load_glossary(), load_risks()
    failed = 0
    for s in targets:
        a = analyze_ai(s.text, provider, glossary, risks)
        tokens = f"입력 {a.prompt_tokens:,} · 출력 {a.completion_tokens:,}"
        if a.source != "ai" or a.partial:
            print(f"- {s.id}: 저장 안 함 ({a.fallback_reason or '응답 잘림'}) · {tokens}")
            failed += 1
            continue
        p = precomputed.save(s, a)
        checks = (f"문장 {sum(x.found for x in a.pairs)}/{len(a.pairs)} · 용어 {sum(x.found for x in a.terms)}/{len(a.terms)}"
                  f" · 위험 {sum(x.found for x in a.risks)}/{len(a.risks)} · 숫자 {sum(c.found for c in a.number_checks)}"
                  f"/{len(a.number_checks)}")
        print(f"- {s.id}: 저장 {p.name} · {tokens} · 원문 대조 {checks}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
