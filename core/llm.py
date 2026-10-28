"""LLM 호출. 화면과 분석 코드는 LLMProvider 인터페이스만 알고, 실제 API는 여기서만 부른다.

- 키는 config.api_key()로 환경변수에서만 읽는다. 키 값은 출력, 로그, 예외 메시지 어디에도 넣지 않는다.
- 호출마다 토큰 사용량(response.usage)을 logs/llm_usage.log에 한 줄씩 남긴다. 문서 본문은 남기지 않는다.
- 테스트는 FakeProvider 같은 가짜 구현을 넘겨서 실제 호출 없이 돌린다.
"""
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

import config


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(self.prompt_tokens + other.prompt_tokens, self.completion_tokens + other.completion_tokens)


@dataclass(frozen=True)
class LLMResponse:
    text: str
    usage: Usage
    finish_reason: str = "stop"  # length면 max_tokens에 걸려 답이 중간에 잘린 것


class LLMError(Exception):
    """호출 자체가 실패한 경우 (인증, 한도, 네트워크 등). 재시도하지 않고 규칙 기반으로 넘어간다."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind  # auth / rate_limit / timeout / connection / api / empty


class LLMProvider(Protocol):
    model: str

    def complete(self, system: str, user: str) -> LLMResponse: ...


def log_usage(model: str, usage: Usage, finish_reason: str = "", path: Path | None = None) -> None:
    """토큰 수만 남긴다. 로그를 못 써도 통역은 계속돼야 하므로 오류는 삼킨다."""
    path = path or config.USAGE_LOG_PATH
    line = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total,
        "finish_reason": finish_reason,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass


class OpenAICompatProvider:
    """ChatKHU API Gateway(OpenAI 호환)로 부르는 구현."""

    def __init__(self, api_key: str, base_url: str | None = None, model: str = config.MODEL_NAME, client=None):
        self.model = model
        if client is None:
            from openai import OpenAI

            # SDK 자동 재시도는 끈다. 재시도는 ai_analyze에서 형식 오류일 때만 1번 한다 (크레딧 절약)
            client = OpenAI(api_key=api_key, base_url=base_url or config.base_url(),
                            timeout=config.LLM_TIMEOUT_SEC, max_retries=0)
        self._client = client

    def complete(self, system: str, user: str) -> LLMResponse:
        import openai

        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                max_tokens=config.LLM_MAX_TOKENS,
                temperature=config.LLM_TEMPERATURE,
            )
        # 예외 메시지(str(e))는 요청 정보를 담을 수 있어서 쓰지 않고, 정해 둔 문구만 돌려준다
        except openai.AuthenticationError:
            raise LLMError("auth", "API 키가 맞지 않아요") from None
        except openai.PermissionDeniedError:
            raise LLMError("auth", "이 키로는 모델을 쓸 수 없어요") from None
        except openai.RateLimitError:
            raise LLMError("rate_limit", "요청이 많거나 크레딧이 부족해요") from None
        except openai.APITimeoutError:
            raise LLMError("timeout", "AI 응답이 너무 늦어요") from None
        except openai.APIConnectionError:
            raise LLMError("connection", "AI 서버에 연결하지 못했어요") from None
        except openai.APIError as e:
            status = getattr(e, "status_code", None)
            raise LLMError("api", f"AI 서버 오류{f' ({status})' if status else ''}") from None

        try:
            u = resp.usage
            usage = Usage(getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0)
            choice = resp.choices[0] if resp.choices else None
            finish = (getattr(choice, "finish_reason", None) or "stop") if choice else "stop"
            text = (choice.message.content or "") if choice else ""
        except (AttributeError, IndexError, TypeError):
            # 게이트웨이나 프록시가 오류 페이지(HTML)를 200으로 보내면 SDK가 응답 객체 대신 문자열을 준다
            raise LLMError("api", "AI 서버가 알 수 없는 형식으로 답했어요") from None
        log_usage(self.model, usage, finish)
        if not isinstance(text, str) or not text.strip():
            raise LLMError("empty", "AI가 빈 답을 보냈어요")
        return LLMResponse(text=text, usage=usage, finish_reason=finish)


def get_provider() -> LLMProvider | None:
    """키가 없으면 None. 호출하는 쪽이 규칙 기반으로 대체한다."""
    key = config.api_key()
    return OpenAICompatProvider(key) if key else None
