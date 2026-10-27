"""prompts/ 폴더의 프롬프트 파일을 읽어 LLM에 보낼 글을 만든다."""
from dataclasses import dataclass
from pathlib import Path

import config

TRUNCATED_NOTE = "\n...(문서가 길어 뒷부분은 생략함)"
RETRY_NOTE = (
    "\n\n직전 답변은 형식 검사를 통과하지 못했습니다 ({error}). "
    "위 형식의 JSON 객체 하나만, 다른 글 없이 다시 보내 주세요."
)


@dataclass(frozen=True)
class Prompt:
    system: str
    user: str
    truncated: bool  # 문서가 MAX_DOC_CHARS보다 길어 잘랐는지 (화면에 알린다)


def _read(name: str, folder: Path) -> str:
    return (folder / name).read_text(encoding="utf-8").strip()


def build_prompt(text: str, folder: Path | None = None, max_chars: int | None = None) -> Prompt:
    folder = folder or config.PROMPTS_DIR
    max_chars = max_chars or config.MAX_DOC_CHARS
    doc = text.strip()
    truncated = len(doc) > max_chars
    if truncated:
        doc = doc[:max_chars] + TRUNCATED_NOTE
    # 프롬프트 안에 JSON 중괄호가 많아서 str.format 대신 자리 하나만 바꾼다
    user = _read("interpret.txt", folder).replace("{document}", doc)
    return Prompt(system=_read("system.txt", folder), user=user, truncated=truncated)


def retry_prompt(prompt: Prompt, error: str) -> Prompt:
    return Prompt(system=prompt.system, user=prompt.user + RETRY_NOTE.format(error=error[:200]),
                  truncated=prompt.truncated)
