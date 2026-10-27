"""샘플 문서 불러오기. 모두 가상 자료다."""
import json
import re
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


def load_text_sample(path: Path) -> Sample:
    """data/samples/*.txt 한 개 (긴 문서 시험본). scripts/live_check.py만 쓴다.

    앱의 샘플 목록과 평가는 .json만 읽으므로 txt는 거기에 나타나지 않는다.
    형식은 data/raw/samples_raw.txt와 같다: 첫 줄은 이름, 'json'만 있는 줄 뒤는 정답이다.
    정답은 평가에 쓰지 않고, AI가 보면 안 되므로 본문에서 잘라 버린다.
    """
    raw = path.read_text(encoding="utf-8").strip()
    name, _, rest = raw.partition("\n")
    body = re.split(r"^\s*json\s*$", rest, maxsplit=1, flags=re.M)[0].strip()
    return Sample(id=path.stem, name=name.strip(), origin="raw", text=body or name)
