"""모든 테스트 공통: 실제 LLM 호출이 절대 일어나지 않게 막는다 (크레딧 절약).

실제 호출 확인은 scripts/live_check.py로 따로 한다.
"""
import openai
import pytest

import config
from core import limits


class _NoNetworkClient:
    def __init__(self, *args, **kwargs):
        raise AssertionError("테스트에서 실제 OpenAI 클라이언트를 만들면 안 됩니다. 가짜 Provider를 쓰세요.")


@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch, tmp_path):
    monkeypatch.delenv("CHATKHU_API_KEY", raising=False)
    monkeypatch.setattr(openai, "OpenAI", _NoNetworkClient)
    monkeypatch.setattr(config, "USAGE_LOG_PATH", tmp_path / "llm_usage.log")
    # 실제 data/precomputed/ 파일이 생겨도 테스트 결과가 바뀌지 않게 빈 폴더를 쓴다
    monkeypatch.setattr(config, "PRECOMPUTED_DIR", tmp_path / "precomputed")
    limits.DAILY.reset()  # 하루 횟수는 프로세스 전체에서 공유되므로 테스트마다 비운다
