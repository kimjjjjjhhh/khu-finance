"""샘플 문서 불러오기. 모두 가상 자료다."""
import json
from pathlib import Path

import config
from core import fallback
from core.schema import Pair, Sample


def prototype_samples() -> list[Sample]:
    return [
        Sample(id=s["id"], name=s["name"], origin="prototype", text=s["text"], verdict=s["verdict"],
               pairs=[Pair(original=o, easy=e) for o, e in s["pairs"]])
        for s in fallback.SAMPLES
    ]


def load_samples(folder: Path = config.SAMPLES_DIR) -> list[Sample]:
    """data/samples/*.json을 읽는다. 하나도 없으면 프로토타입 샘플 3종을 쓴다."""
    samples = []
    for f in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            samples.append(Sample.model_validate_json(f.read_text(encoding="utf-8")))
        except ValueError:
            continue  # 깨진 파일 하나 때문에 앱 전체가 멈추지 않게 건너뛴다
    return samples or prototype_samples()
