"""프롬프트 파일 읽기와 문서 넣기."""
from core.prompts import TRUNCATED_NOTE, build_prompt, retry_prompt


def test_document_is_inserted_once():
    p = build_prompt("기본금리 연 3.0%")
    assert p.user.count("기본금리 연 3.0%") == 1
    assert "{document}" not in p.user
    assert '"verdict"' in p.user  # JSON 형식 설명은 그대로 남는다
    assert "지어내지 않습니다" in p.system
    assert not p.truncated


def test_long_document_is_truncated():
    p = build_prompt("가" * 50, max_chars=10)
    assert p.truncated
    assert "가" * 10 + TRUNCATED_NOTE in p.user
    assert "가" * 11 not in p.user


def test_retry_prompt_mentions_error():
    p = retry_prompt(build_prompt("문서"), "verdict 없음")
    assert p.user.endswith("다시 보내 주세요.")
    assert "verdict 없음" in p.user
