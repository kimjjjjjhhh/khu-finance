"""앱 전체에서 쓰는 상수.

API 키는 여기에 적지 않는다. 환경변수 CHATKHU_API_KEY에서 실행할 때만 읽는다.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
GLOSSARY_PATH = DATA_DIR / "glossary.json"
RISKS_PATH = DATA_DIR / "risks.json"
SAMPLES_DIR = DATA_DIR / "samples"
PROMPTS_DIR = ROOT / "prompts"
PRECOMPUTED_DIR = DATA_DIR / "precomputed"  # 예시 문서의 미리 통역한 AI 결과
LOG_DIR = ROOT / "logs"
USAGE_LOG_PATH = LOG_DIR / "llm_usage.log"  # 토큰 사용량만 남긴다 (문서 본문, 키는 남기지 않음)

MODEL_NAME = "claude-sonnet-5-5"

DEFAULT_BASE_URL = "https://factchat-cloud.mindlogic.ai/v1/gateway"

# 이자소득세 15.4% (소득세 14% + 지방소득세 1.4%)
INTEREST_TAX_RATE = 0.154

# 프롬프트에 넣을 문서 최대 길이 (너무 긴 문서는 잘라서 보낸다)
MAX_DOC_CHARS = 4000  # 넘으면 막지 않고 앞부분만 보내고 화면에 알린다

# LLM 호출 설정
LLM_TIMEOUT_SEC = 60
LLM_MAX_TOKENS = 6000  # 응답 길이 상한. 쓴 만큼만 과금되므로 잘림 방지에 여유를 둔다 (1,708자 약관 실측 출력 3,264)
LLM_TEMPERATURE = 0.2

# AI 호출 한도 (실제로 API에 보낸 요청 수 기준, 재시도 포함)
AI_SESSION_LIMIT = 5  # 브라우저 세션 하나당
AI_DAILY_LIMIT = 150  # 서버 전체 하루 (서버를 다시 시작하면 0부터)


def base_url() -> str:
    return os.environ.get("CHATKHU_BASE_URL") or DEFAULT_BASE_URL


def api_key() -> str | None:
    """키가 없으면 None. 값은 절대 출력하거나 저장하지 않는다."""
    key = os.environ.get("CHATKHU_API_KEY", "").strip()
    return key or None
