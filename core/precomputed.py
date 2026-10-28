"""예시 문서의 AI 통역 결과를 미리 저장해 두고 불러온다. 예시를 고르면 API를 부르지 않고 이 결과를 쓴다.

파일: data/precomputed/<샘플 id>.json (Analysis 그대로). 만드는 법: python -m scripts.precompute --yes
불러올 때 원문이 지금 샘플 본문과 다르면 (샘플을 고친 뒤 다시 만들지 않은 경우) 쓰지 않는다.
"""
import hashlib
from pathlib import Path

import config
from core.schema import Analysis, Sample


def text_key(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def path_for(sample_id: str, folder: Path | None = None) -> Path:
    return (folder or config.PRECOMPUTED_DIR) / f"{sample_id}.json"


def save(sample: Sample, a: Analysis, folder: Path | None = None) -> Path:
    p = path_for(sample.id, folder)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(a.model_dump_json(indent=2, by_alias=False), encoding="utf-8")
    return p


def load_all(samples: list[Sample], folder: Path | None = None) -> dict[str, Analysis]:
    """원문 해시 -> 미리 통역한 결과. 파일이 없거나 깨졌거나 원문이 바뀐 샘플은 빠진다."""
    out: dict[str, Analysis] = {}
    for s in samples:
        p = path_for(s.id, folder)
        try:
            a = Analysis.model_validate_json(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if a.source == "ai" and a.text.strip() == s.text.strip():
            out[text_key(s.text)] = a.model_copy(update={"precomputed": True})
    return out
