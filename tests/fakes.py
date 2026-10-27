"""테스트용 가짜 LLM. 정해 둔 답을 차례로 돌려주고, 받은 프롬프트를 기록한다."""
import json

from core.llm import LLMError, LLMResponse, Usage

DOC = (
    "[가상 자료]\n기본금리는 연 3.0%이며, 우대금리 연 1.5%p를 더해 최고 연 4.5%를 적용합니다.\n"
    "계약 기간: 12개월. 월 최대 30만 원까지 납입할 수 있습니다.\n"
    "만기 전에 해지하면 중도해지이율(연 0.5%)이 적용됩니다."
)

GOOD = {
    "docType": "savings",
    "verdict": "최고 4.5%는 조건을 다 채워야 받아요.",
    "pairs": [
        # 줄바꿈·띄어쓰기만 다른 인용은 원문에 있는 것으로 본다
        {"original": "만기 전에 해지하면  중도해지이율(연 0.5%)이 적용됩니다.", "easy": "중간에 깨면 0.5%만 받아요."},
        {"original": "가입 즉시 10만 원을 드립니다.", "easy": "지어낸 문장"},
    ],
    "terms": [
        {"term": "우대금리", "meaning": "조건을 채우면 더 주는 금리", "category": "예적금"},
        {"term": "중도 해지", "meaning": "만기 전에 끊는 것", "category": "예적금"},
        {"term": "복리", "meaning": "이자에 이자가 붙는 것", "category": "예적금"},
    ],
    "risks": [
        {"phrase": "중도해지이율(연 0.5%)", "why": "이자가 거의 없어요", "level": "high"},
        {"phrase": "원금 손실 가능", "why": "지어낸 위험", "level": "high"},
    ],
    "numbers": {
        "rates": [{"label": "기본금리", "value": 3.0}, {"label": "최고금리", "value": 5.0}],
        "months": 12,
        "amount": 300000,
    },
}


def reply(obj=GOOD, usage=(100, 50), finish_reason="stop") -> LLMResponse:
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    return LLMResponse(text=text, usage=Usage(*usage), finish_reason=finish_reason)


def cut(obj=GOOD, keep: str = "") -> LLMResponse:
    """max_tokens에 걸려 잘린 답. keep 글자가 처음 나오는 곳 바로 뒤에서 자른다."""
    text = json.dumps(obj, ensure_ascii=False)
    return reply(text[:text.index(keep) + len(keep)], usage=(1000, 4000), finish_reason="length")


class FakeProvider:
    model = "fake-model"

    def __init__(self, *replies):
        """replies: LLMResponse 또는 LLMError. 호출할 때마다 하나씩 꺼낸다."""
        self.replies = list(replies)
        self.prompts: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> LLMResponse:
        self.prompts.append((system, user))
        r = self.replies.pop(0)
        if isinstance(r, LLMError):
            raise r
        return r
