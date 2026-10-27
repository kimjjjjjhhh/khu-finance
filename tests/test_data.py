"""데이터 파일과 분리 스크립트, 파일이 없을 때의 대체 동작."""
import json

import config
from core.glossary import load_glossary
from core.risks import load_risks
from core.samples import load_samples
from scripts.split_raw import RAW_PATTERNS, gold_issues, split_samples

RAW = """1. 테스트 적금
[가상 자료]
가입 기간은 12개월이며 기본금리는 연 3.0%입니다. 매월 1만 원 이상 납입.
json

{"rates":[{"label":"기본금리","value":3.0}],"months":12,"amount":100000,"risks":["없는 문장"]}

2. 깨진 블록
정답 없음
"""


def test_split_samples_parses_and_flags_problems():
    samples, problems = split_samples(RAW)
    assert [s.id for s in samples] == ["r1"]
    assert samples[0].text.startswith("[가상 자료]")
    assert any("깨진 블록" in p for p in problems)
    issues = samples[0].gold_issues
    assert any(i.startswith("amount=100000") for i in issues)  # 원문은 1만 원
    assert any(i.startswith("risks") for i in issues)
    assert not any(i.startswith("months") or i.startswith("rates") for i in issues)


def test_gold_issues_empty_when_all_found():
    assert gold_issues("연 3.0%, 12개월, 월 30만 원", {"rates": [{"label": "x", "value": 3}],
                                                   "months": 12, "amount": 300000}) == []


def test_generated_files_load_without_fallback():
    g, r, s = load_glossary(), load_risks(), load_samples()
    assert not g.from_fallback and len(g.entries) >= 80
    assert not r.from_fallback and len(r.rules) >= 20
    assert len(s) == 8
    assert all("가상 자료" in x.text for x in s)  # 원칙 6


def test_every_raw_red_flag_has_patterns_entry():
    flags = json.loads((config.DATA_DIR / "raw" / "glossary_raw.json").read_text(encoding="utf-8"))["red_flags"]
    assert {f["keyword"] for f in flags} <= set(RAW_PATTERNS)


def test_missing_files_fall_back_to_prototype(tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text("", encoding="utf-8")
    assert load_glossary(tmp_path / "none.json").from_fallback
    assert load_glossary(empty).from_fallback
    assert load_risks(empty).from_fallback
    assert [x.id for x in load_samples(tmp_path)] == ["p1", "p2", "p3"]


def test_text_sample_drops_answer_key_and_is_not_in_app_list(tmp_path):
    from core.samples import load_samples, load_text_sample
    f = tmp_path / "long.txt"
    f.write_text('긴 약관\n[가상 자료]\n제1조 본문입니다.\njson\n\n{"months": 48}\n', encoding="utf-8")
    (tmp_path / "a.json").write_text('{"id": "a", "name": "A", "origin": "raw", "text": "[가상 자료] 본문"}',
                                     encoding="utf-8")
    s = load_text_sample(f)
    assert (s.id, s.name, s.text) == ("long", "긴 약관", "[가상 자료]\n제1조 본문입니다.")
    assert s.gold is None  # 정답은 읽지 않는다 (평가에 넣지 않음)
    assert [x.id for x in load_samples(tmp_path)] == ["a"]  # 앱 목록은 .json만
