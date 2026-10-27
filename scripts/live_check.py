"""실제 LLM 호출 확인 (크레딧을 씀). pytest와 분리해 두었고, 직접 실행할 때만 호출한다.

실행: python -m scripts.live_check [샘플 id, 기본 p1]
샘플 id는 data/samples의 .json(p1, r4 ...) 또는 .txt 파일 이름(예: long_loan_terms)이다.
키는 환경변수 CHATKHU_API_KEY에서만 읽고, 화면에는 있는지 없는지만 표시한다.
"""
import sys
from urllib.parse import urlparse

import config
from core import llm
from core.ai_analyze import analyze_ai
from core.glossary import load_glossary
from core.risks import load_risks
from core.samples import load_samples, load_text_sample


class CountingProvider:
    """호출 횟수와 호출별 토큰을 세는 감싸개."""

    def __init__(self, inner: llm.LLMProvider):
        self.inner, self.model, self.calls = inner, inner.model, []

    def complete(self, system: str, user: str) -> llm.LLMResponse:
        r = self.inner.complete(system, user)
        self.calls.append(r)
        return r


def main(sample_id: str = "p1") -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # 파이프로 받아도 한글이 깨지지 않게
    provider = llm.get_provider()
    print(f"모델: {config.MODEL_NAME}")
    print(f"게이트웨이: {urlparse(config.base_url()).netloc}")
    print(f"API 키: {'설정됨' if provider else '없음'}")
    if provider is None:
        print("CHATKHU_API_KEY 환경변수를 설정한 뒤 다시 실행하세요.")
        return 2

    samples = load_samples()
    txts = {f.stem: f for f in sorted(config.SAMPLES_DIR.glob("*.txt"))}
    sample = next((s for s in samples if s.id == sample_id), None)
    if sample is None and sample_id in txts:
        sample = load_text_sample(txts[sample_id])  # 정답 블록은 잘라 내고 본문만 보낸다
    if sample is None:
        print(f"샘플 '{sample_id}'가 없어요. 가능한 값: {', '.join([s.id for s in samples] + list(txts))}")
        return 2

    counting = CountingProvider(provider)
    a = analyze_ai(sample.text, counting, load_glossary(), load_risks())
    print(f"샘플: {sample.id} {sample.name} ({len(sample.text)}자)")
    for i, r in enumerate(counting.calls, 1):
        u = r.usage
        print(f"  호출 {i}: 입력 {u.prompt_tokens:,} · 출력 {u.completion_tokens:,} 토큰 · "
              f"finish_reason={r.finish_reason} (출력 상한 {config.LLM_MAX_TOKENS:,})")
    print(f"합계 토큰: {a.prompt_tokens + a.completion_tokens:,}")

    if a.source != "ai":
        print(f"결과: 실패 -> 규칙 기반 모드 ({a.fallback_reason})")
        return 1

    def ratio(items) -> str:
        return f"{sum(x.found for x in items)}/{len(items)}"

    print("결과: 성공 (스키마 검증 통과" + (", 재시도 1번" if len(counting.calls) > 1 else "")
          + (", 응답이 잘려 일부만 사용" if a.partial else "") + ")")
    print(f"  개수: 문장 {len(a.pairs)} · 용어 {len(a.terms)} · 위험 {len(a.risks)}")
    print(f"  종류: {a.kind} · 한 줄 통역: {a.verdict}")
    print(f"  원문 대조 (확인/전체): 문장 {ratio(a.pairs)} · 용어 {ratio(a.terms)} · "
          f"위험 {ratio(a.risks)} · 숫자 {ratio(a.number_checks)}")
    for c in a.number_checks:
        if not c.found:
            print(f"  ! 원문에서 확인 안 된 숫자: {c.label} {c.value:g}")
    for kind, items, quote in (("문장", a.pairs, "original"), ("용어", a.terms, "term"), ("위험", a.risks, "phrase")):
        for x in items:
            if not x.found:
                print(f"  ! 원문에서 확인 안 된 {kind}: {getattr(x, quote)!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:2]))
