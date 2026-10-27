"""분석 결과의 모양을 정하는 pydantic 모델.

LLM 응답 검증(LLMAnalysis)과 화면에 넘기는 최종 결과(Analysis)를 같은 부품으로 만든다.
그래야 규칙 기반 분석과 AI 분석이 화면 코드에서 똑같이 다뤄진다.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DocType = Literal["savings", "deposit", "loan", "card", "other"]
Category = Literal["예적금", "대출", "카드", "기타"]
Level = Literal["high", "mid"]

CATEGORIES: tuple[str, ...] = ("예적금", "대출", "카드", "기타")
KIND_NAME = {"savings": "적금", "deposit": "예금", "loan": "대출", "card": "카드", "other": "기타"}


def _coerce_category(cls, v: object) -> object:
    # LLM이 "예금"처럼 목록 밖 분야를 써도 재시도까지 갈 일은 아니므로 '기타'로 받는다
    return v if v in CATEGORIES else "기타"


class _Base(BaseModel):
    # LLM은 camelCase(docType)로, 파이썬 코드는 snake_case(doc_type)로 쓸 수 있게 한다
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)


class Term(_Base):
    term: str = Field(min_length=1)
    meaning: str = Field(min_length=1)
    category: Category = "기타"

    coerce_category = field_validator("category", mode="before")(_coerce_category)


class Risk(_Base):
    phrase: str = Field(min_length=1)
    why: str = Field(min_length=1)
    level: Level = "mid"

    @field_validator("level", mode="before")
    @classmethod
    def _level(cls, v: object) -> object:
        return "high" if v == "high" else "mid"


class Pair(_Base):
    original: str = Field(min_length=1)
    easy: str = Field(min_length=1)


class Rate(_Base):
    label: str = "금리"
    value: float = Field(ge=0, le=100)


class Numbers(_Base):
    """문서에서 읽어 낸 숫자. 없는 값은 None."""

    rates: list[Rate] = Field(default_factory=list)
    months: int | None = Field(default=None, ge=1, le=600)
    amount: int | None = Field(default=None, ge=0)  # 월 납입액, 예치금, 대출 원금 중 해당하는 것 (원)
    fee: int | None = Field(default=None, ge=0)  # 카드 연회비 (원)
    discount_rate: float | None = Field(default=None, alias="discountRate", ge=0, le=100)  # %
    cap: int | None = Field(default=None, ge=0)  # 월 할인 한도 (원)
    spend: int | None = Field(default=None, ge=0)  # 전월 실적 기준 (원)


class QuizItem(_Base):
    q: str = Field(min_length=1)
    options: list[str] = Field(min_length=2, max_length=4)
    answer: int = Field(ge=0)
    why: str = ""
    category: Category = "기타"

    coerce_category = field_validator("category", mode="before")(_coerce_category)

    @model_validator(mode="after")
    def _answer_in_range(self) -> "QuizItem":
        if self.answer >= len(self.options):
            raise ValueError("answer가 보기 개수를 벗어났습니다")
        return self


class LLMAnalysis(_Base):
    """LLM에게 요구하는 JSON 형식. 검증에 실패하면 재시도 또는 규칙 기반으로 대체한다."""

    doc_type: DocType = Field(default="other", alias="docType")
    verdict: str = Field(min_length=1)
    pairs: list[Pair] = Field(default_factory=list, max_length=8)
    terms: list[Term] = Field(default_factory=list, max_length=12)
    risks: list[Risk] = Field(default_factory=list, max_length=8)
    numbers: Numbers = Field(default_factory=Numbers)
    quiz: list[QuizItem] = Field(default_factory=list, max_length=5)

    @field_validator("doc_type", mode="before")
    @classmethod
    def _doc_type(cls, v: object) -> object:
        return v if v in KIND_NAME else "other"


class NumberCheck(_Base):
    """읽어 낸 숫자 하나가 원문에 실제로 있는지 대조한 결과 (환각 방지)."""

    field: str  # 예: "rates[0]", "months"
    label: str  # 화면 표시용 이름
    value: float
    found: bool  # False면 '원문에서 확인 안 됨' 경고, 계산기에 자동 입력하지 않음


class Analysis(_Base):
    """화면에 넘기는 최종 결과."""

    source: Literal["ai", "rule"]
    fallback_reason: str | None = None  # AI 대신 규칙 기반을 쓴 이유 (화면에 표시)
    kind: DocType
    verdict: str
    pairs: list[Pair] = Field(default_factory=list)
    terms: list[Term] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    numbers: Numbers = Field(default_factory=Numbers)
    number_checks: list[NumberCheck] = Field(default_factory=list)
    quiz: list[QuizItem] = Field(default_factory=list)
