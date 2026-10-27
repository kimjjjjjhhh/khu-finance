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

MODEL_NAME = "claude-sonnet-5-5"

DEFAULT_BASE_URL = "https://factchat-cloud.mindlogic.ai/v1/gateway"

# 이자소득세 15.4% (소득세 14% + 지방소득세 1.4%)
INTEREST_TAX_RATE = 0.154

# 프롬프트에 넣을 문서 최대 길이 (너무 긴 문서는 잘라서 보낸다)
MAX_DOC_CHARS = 6000


def base_url() -> str:
    return os.environ.get("CHATKHU_BASE_URL") or DEFAULT_BASE_URL


def api_key() -> str | None:
    """키가 없으면 None. 값은 절대 출력하거나 저장하지 않는다."""
    key = os.environ.get("CHATKHU_API_KEY", "").strip()
    return key or None
