"""AI 통역: 프롬프트 -> LLM 호출 -> JSON 검증 (형식 오류면 1번 재시도) -> 원문 대조.

답이 max_tokens에 걸려 잘리면(finish_reason=length) 재시도하지 않는다. 같은 요청은 또 잘려서 크레딧만 쓴다.
대신 잘린 JSON에서 끝까지 쓰인 항목만 살려 쓰고 화면에 '일부 생략'을 알린다.
키가 없거나, 호출이 실패하거나, 재시도해도 형식이 틀리면 규칙 기반 분석으로 대체한다.
대체 이유는 Analysis.fallback_reason에 담겨 화면에 '규칙 기반 모드'와 함께 표시된다.
"""
import json
import logging
import random
import re

from pydantic import ValidationError

from core.analyze import analyze_rule
from core.extract import check_numbers
from core.glossary import Glossary
from core.llm import LLMError, LLMProvider, Usage
from core.prompts import build_prompt, retry_prompt
from core.quiz import make_quiz
from core.risks import RiskMatcher
from core.schema import Analysis, LLMAnalysis, Pair, Rate, Risk, Sample, Term
from core.verify import verify_pairs, verify_risks, verify_terms

MAX_ATTEMPTS = 2  # 처음 1번 + 형식 오류 시 재시도 1번
UNAVAILABLE = "지금은 AI 통역을 쓸 수 없어요. 예시 문서나 빠른 분석을 이용해 주세요"
log = logging.getLogger(__name__)


def unavailable(cause: str) -> str:
    """화면에 보일 대체 이유. cause는 정해 둔 문구만 넣는다 (예외 메시지에는 키나 주소가 섞일 수 있음)."""
    return f"{UNAVAILABLE} (원인: {cause})"


NO_KEY_REASON = unavailable("API 키가 설정되지 않았어요")
CUT_OFF_REASON = unavailable("AI 응답이 길어 잘렸고, 쓸 수 있는 부분이 없었어요")
BAD_FORMAT_REASON = unavailable("AI 답변 형식이 맞지 않았어요 (재시도 후에도 실패)")
UNEXPECTED_REASON = unavailable("예상하지 못한 오류")


def parse_llm_json(text: str) -> LLMAnalysis:
    """응답에서 JSON 객체를 꺼내 검증한다. 실패하면 ValueError (ValidationError, JSONDecodeError 포함)."""
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("JSON 객체를 찾지 못함")
    return LLMAnalysis.model_validate(json.loads(t[start:end + 1]))


def close_truncated_json(text: str) -> dict | None:
    """중간에 잘린 JSON에서 마지막으로 끝까지 쓰인 값까지만 남기고 괄호를 닫아 읽는다. 못 읽으면 None."""
    start = text.find("{")
    if start < 0:
        return None
    t = text[start:]
    stack: list[str] = []
    cuts: list[tuple[int, str]] = []  # (여기까지 자르면, 이 닫는 괄호를 붙인다)
    in_str = esc = False
    for i, ch in enumerate(t):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if not stack:
                break
            stack.pop()
            cuts.append((i + 1, _closers(stack)))
            if not stack:
                break
        elif ch == ",":
            cuts.append((i, _closers(stack)))  # 쉼표 앞까지는 값 하나가 끝까지 쓰인 상태다
    for end, closers in reversed(cuts):
        try:
            obj = json.loads(t[:end] + closers)
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _closers(stack: list[str]) -> str:
    return "".join("}" if c == "{" else "]" for c in reversed(stack))


def _valid(model, item) -> bool:
    try:
        model.model_validate(item)
        return True
    except ValidationError:
        return False


def salvage_truncated(text: str) -> LLMAnalysis | None:
    """잘린 답에서 살릴 수 있는 부분만 검증해 돌려준다. 한 줄 통역(verdict)마저 없으면 None."""
    obj = close_truncated_json(re.sub(r"^```(?:json)?\s*", "", text.strip()))
    if obj is None:
        return None
    # 잘린 자리의 마지막 항목은 필드가 빠졌을 수 있으므로 항목 단위로 버린다
    for key, model in (("pairs", Pair), ("terms", Term), ("risks", Risk)):
        if isinstance(obj.get(key), list):
            obj[key] = [x for x in obj[key] if _valid(model, x)]
    nums = obj.get("numbers")
    if isinstance(nums, dict) and isinstance(nums.get("rates"), list):
        nums["rates"] = [x for x in nums["rates"] if _valid(Rate, x)]
    try:
        return LLMAnalysis.model_validate(obj)
    except ValidationError:
        return None


def _error_summary(e: ValueError) -> str:
    if isinstance(e, ValidationError):
        return "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()[:3])
    if isinstance(e, json.JSONDecodeError):
        return "JSON 문법 오류"
    return str(e)


def analyze_ai(
    text: str,
    provider: LLMProvider | None,
    glossary: Glossary,
    risks: RiskMatcher,
    samples: list[Sample] = (),
    rng: random.Random | None = None,
) -> Analysis:
    usage = Usage()

    def fallback(reason: str) -> Analysis:
        a = analyze_rule(text, glossary, risks, samples, fallback_reason=reason, rng=rng)
        # 실패했어도 이미 쓴 토큰은 보여 준다
        return a.model_copy(update={"prompt_tokens": usage.prompt_tokens,
                                    "completion_tokens": usage.completion_tokens})

    if provider is None:
        return fallback(NO_KEY_REASON)

    prompt = build_prompt(text)
    parsed: LLMAnalysis | None = None
    partial = False
    for attempt in range(MAX_ATTEMPTS):
        try:
            resp = provider.complete(prompt.system, prompt.user)
        except LLMError as e:
            # 한도 초과는 한도 안내를 그대로, 나머지(연결, 시간 초과, 인증 등)는 'AI 통역을 쓸 수 없어요'로
            return fallback(str(e) if e.kind == "limit" else unavailable(str(e)))
        except Exception as e:  # noqa: BLE001  어떤 오류에도 앱이 멈추지 않게 하는 마지막 안전망
            log.warning("AI 호출 중 예상하지 못한 오류: %s", type(e).__name__)  # 메시지는 남기지 않음
            return fallback(UNEXPECTED_REASON)
        usage += resp.usage
        try:
            parsed = parse_llm_json(resp.text)
            break
        except ValueError as e:
            if resp.finish_reason == "length":
                parsed = salvage_truncated(resp.text)
                if parsed is None:
                    return fallback(CUT_OFF_REASON)
                partial = True
                break
            prompt = retry_prompt(prompt, _error_summary(e))
    if parsed is None:
        return fallback(BAD_FORMAT_REASON)

    terms = verify_terms(parsed.terms, text, glossary)
    return Analysis(
        source="ai",
        text=text,
        kind=parsed.doc_type,
        verdict=parsed.verdict,
        pairs=verify_pairs(parsed.pairs, text),
        terms=terms,
        risks=verify_risks(parsed.risks, text),
        numbers=parsed.numbers,
        number_checks=check_numbers(parsed.numbers, text),
        # 퀴즈는 LLM 없이 사전으로 만든다. 원문에서 확인된 용어 중 사전에 있는 것만, 뜻도 사전 것을 쓴다
        quiz=make_quiz([t for t in terms if t.found], glossary, parsed.doc_type, rng=rng),
        truncated=prompt.truncated,
        partial=partial,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
    )
