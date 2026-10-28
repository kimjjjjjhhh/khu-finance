"""AI 호출 한도 (LLM 없음)."""
from datetime import date

import pytest

import config
from core import limits
from core.llm import LLMError
from tests.fakes import FakeProvider, reply


def test_daily_counter_resets_on_new_day():
    day = [date(2026, 10, 29)]
    c = limits.DailyCounter(today=lambda: day[0])
    assert c.take(2) and c.take(2) and not c.take(2)
    assert c.used() == 2
    day[0] = date(2026, 10, 30)
    assert c.used() == 0 and c.take(2)


def test_limited_provider_counts_requests_and_stops_at_session_limit(monkeypatch):
    monkeypatch.setattr(config, "AI_SESSION_LIMIT", 2)
    s = limits.SessionCounter()
    p = limits.LimitedProvider(FakeProvider(reply(), reply(), reply()), s, limits.DailyCounter())
    p.complete("s", "u")
    p.complete("s", "u")
    with pytest.raises(LLMError) as ei:
        p.complete("s", "u")
    assert ei.value.kind == "limit" and str(ei.value) == limits.LIMIT_MESSAGE
    assert s.used == 2 and len(p.inner.prompts) == 2  # 한도를 넘은 요청은 보내지 않는다


def test_daily_limit_is_shared_across_sessions(monkeypatch):
    monkeypatch.setattr(config, "AI_DAILY_LIMIT", 3)
    daily = limits.DailyCounter()
    a, b = limits.SessionCounter(), limits.SessionCounter()
    limits.LimitedProvider(FakeProvider(reply(), reply()), a, daily).complete("s", "u")
    pb = limits.LimitedProvider(FakeProvider(reply(), reply(), reply()), b, daily)
    pb.complete("s", "u")
    pb.complete("s", "u")
    assert not limits.can_call(a, daily) and not limits.can_call(limits.SessionCounter(), daily)
    with pytest.raises(LLMError):
        pb.complete("s", "u")


def test_defaults():
    assert (config.AI_SESSION_LIMIT, config.AI_DAILY_LIMIT) == (5, 150)
