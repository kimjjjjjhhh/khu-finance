"""AI 호출 횟수 제한 (크레딧 보호). 세션당 config.AI_SESSION_LIMIT, 서버 전체 하루 config.AI_DAILY_LIMIT.

세는 단위는 실제로 API에 보낸 요청 하나다 (형식 오류 재시도도 1번으로 센다).
미리 통역한 결과, 저장된 결과, 키 없음은 요청을 보내지 않으므로 세지 않는다.
하루 횟수는 서버 프로세스 메모리에만 있어서, 서버를 다시 시작하면 0부터 센다.
"""
import threading
from dataclasses import dataclass
from datetime import date
from typing import Callable

import config
from core.llm import LLMError, LLMProvider, LLMResponse

LIMIT_MESSAGE = "오늘 AI 통역 한도에 도달했어요. 예시 문서나 빠른 분석을 이용해 주세요"


class DailyCounter:
    """서버 전체가 함께 쓰는 하루 횟수. 날짜가 바뀌면 0부터 다시 센다."""

    def __init__(self, today: Callable[[], date] = date.today):
        self._today = today
        self._lock = threading.Lock()  # 여러 사용자 세션이 동시에 늘려도 틀리지 않게
        self._day: date | None = None
        self._count = 0

    def _roll(self) -> None:
        if self._day != self._today():
            self._day, self._count = self._today(), 0

    def used(self) -> int:
        with self._lock:
            self._roll()
            return self._count

    def take(self, limit: int) -> bool:
        with self._lock:
            self._roll()
            if self._count >= limit:
                return False
            self._count += 1
            return True

    def reset(self) -> None:
        with self._lock:
            self._day, self._count = None, 0


DAILY = DailyCounter()  # 모듈은 서버 프로세스에서 한 번만 읽히므로 모든 세션이 이 하나를 함께 쓴다


@dataclass
class SessionCounter:
    used: int = 0


def session_left(s: SessionCounter) -> int:
    return max(0, config.AI_SESSION_LIMIT - s.used)


def daily_left(daily: DailyCounter = DAILY) -> int:
    return max(0, config.AI_DAILY_LIMIT - daily.used())


def can_call(s: SessionCounter, daily: DailyCounter = DAILY) -> bool:
    return session_left(s) > 0 and daily_left(daily) > 0


class LimitedProvider:
    """요청을 보내기 직전에 세션, 하루 한도를 확인하고 센다. 넘으면 LLMError('limit')로 규칙 기반 대체."""

    def __init__(self, inner: LLMProvider, session: SessionCounter, daily: DailyCounter = DAILY):
        self.inner, self.model, self.session, self.daily = inner, inner.model, session, daily

    def complete(self, system: str, user: str) -> LLMResponse:
        if session_left(self.session) <= 0 or not self.daily.take(config.AI_DAILY_LIMIT):
            raise LLMError("limit", LIMIT_MESSAGE)
        self.session.used += 1
        return self.inner.complete(system, user)
