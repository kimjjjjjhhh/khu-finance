"""LLM Provider: 가짜 클라이언트로 응답, 토큰 로그, 오류 변환을 확인한다 (실제 호출 없음)."""
import json
from types import SimpleNamespace

import httpx2 as httpx  # openai SDK 3.x가 쓰는 HTTP 라이브러리
import openai
import pytest

import config
from core.llm import LLMError, OpenAICompatProvider, Usage, get_provider

SECRET = "sk-test-SECRET-should-never-appear"


class FakeClient:
    """openai.OpenAI의 chat.completions.create 모양만 흉내 낸다."""

    def __init__(self, content="{}", usage=(120, 30), error=None, finish_reason="stop"):
        self.calls = []
        self._content, self._usage, self._error = content, usage, error
        self._finish = finish_reason
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content), finish_reason=self._finish)],
            usage=SimpleNamespace(prompt_tokens=self._usage[0], completion_tokens=self._usage[1]),
        )


def _status_error(cls, code):
    req = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    return cls(f"bad key {SECRET}", response=httpx.Response(code, request=req), body=None)


def test_complete_returns_text_and_usage():
    client = FakeClient(content='{"verdict": "ok"}', usage=(100, 20))
    r = OpenAICompatProvider(SECRET, client=client).complete("sys", "user")
    assert r.text == '{"verdict": "ok"}'
    assert r.usage == Usage(100, 20) and r.usage.total == 120
    sent = client.calls[0]
    assert sent["model"] == config.MODEL_NAME  # 모델 이름은 config 상수 하나에서만 온다
    assert [m["role"] for m in sent["messages"]] == ["system", "user"]


def test_usage_is_logged_without_key_or_text():
    OpenAICompatProvider(SECRET, client=FakeClient(content="문서 본문 비밀", usage=(7, 3))).complete("s", "u")
    line = json.loads(config.USAGE_LOG_PATH.read_text(encoding="utf-8").strip())
    assert line["prompt_tokens"] == 7 and line["completion_tokens"] == 3 and line["total_tokens"] == 10
    assert line["finish_reason"] == "stop"
    raw = config.USAGE_LOG_PATH.read_text(encoding="utf-8")
    assert SECRET not in raw and "문서 본문" not in raw


@pytest.mark.parametrize("error, kind", [
    (_status_error(openai.AuthenticationError, 401), "auth"),
    (_status_error(openai.RateLimitError, 429), "rate_limit"),
    (_status_error(openai.InternalServerError, 500), "api"),
    (openai.APITimeoutError(httpx.Request("POST", "https://example.invalid")), "timeout"),
])
def test_errors_become_llm_error_without_secret(error, kind):
    with pytest.raises(LLMError) as ei:
        OpenAICompatProvider(SECRET, client=FakeClient(error=error)).complete("s", "u")
    assert ei.value.kind == kind
    assert SECRET not in str(ei.value)
    assert ei.value.__cause__ is None  # 원래 예외(키가 섞일 수 있음)를 달고 다니지 않는다


def test_empty_answer_is_error():
    with pytest.raises(LLMError) as ei:
        OpenAICompatProvider(SECRET, client=FakeClient(content="  ")).complete("s", "u")
    assert ei.value.kind == "empty"


def test_no_key_means_no_provider():
    assert get_provider() is None


def test_real_client_is_blocked_in_tests(monkeypatch):
    monkeypatch.setenv("CHATKHU_API_KEY", SECRET)
    with pytest.raises(AssertionError):
        get_provider()


def test_finish_reason_length_is_passed_on():
    r = OpenAICompatProvider(SECRET, client=FakeClient(content='{"verdict": "잘', finish_reason="length")).complete("s", "u")
    assert r.finish_reason == "length"
    assert json.loads(config.USAGE_LOG_PATH.read_text(encoding="utf-8"))["finish_reason"] == "length"


def test_max_tokens_comes_from_config(monkeypatch):
    monkeypatch.setattr(config, "LLM_MAX_TOKENS", 1234)
    client = FakeClient()
    OpenAICompatProvider(SECRET, client=client).complete("s", "u")
    assert client.calls[0]["max_tokens"] == 1234



def test_non_json_gateway_page_becomes_llm_error():
    # 게이트웨이나 프록시가 HTML 오류 페이지를 200으로 주면 SDK는 응답 객체 대신 문자열을 돌려준다
    class HtmlClient(FakeClient):
        def _create(self, **kwargs):
            return "<html>gateway error https://factchat-cloud.mindlogic.ai</html>"

    with pytest.raises(LLMError) as ei:
        OpenAICompatProvider(SECRET, client=HtmlClient()).complete("s", "u")
    assert ei.value.kind == "api" and "mindlogic" not in str(ei.value) and ei.value.__cause__ is None
