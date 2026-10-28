"""예시 문서의 미리 통역한 결과 저장과 불러오기 (LLM 없음)."""
import random

from core import precomputed
from core.ai_analyze import analyze_ai
from core.analyze import analyze_rule
from core.glossary import load_glossary
from core.risks import load_risks
from core.schema import Sample
from tests.fakes import FakeProvider, reply

S = Sample(id="p9", name="예시", origin="prototype", text="[가상 자료]\n기본금리는 연 3.0%이며 12개월")


def _ai(text=S.text):
    return analyze_ai(text, FakeProvider(reply()), load_glossary(), load_risks(), rng=random.Random(0))


def test_roundtrip_marks_precomputed():
    precomputed.save(S, _ai())
    got = precomputed.load_all([S])
    [a] = got.values()
    assert a.precomputed and a.source == "ai" and a.text == S.text
    assert precomputed.text_key(S.text + "\n") in got  # 앞뒤 공백 차이는 같은 문서


def test_stale_or_rule_results_are_ignored():
    precomputed.save(S, _ai(text="예전 본문"))  # 샘플을 고친 뒤 다시 만들지 않은 경우
    assert precomputed.load_all([S]) == {}
    precomputed.save(S, analyze_rule(S.text, load_glossary(), load_risks()))
    assert precomputed.load_all([S]) == {}


def test_missing_or_broken_file():
    assert precomputed.load_all([S]) == {}
    precomputed.path_for(S.id).parent.mkdir(parents=True, exist_ok=True)
    precomputed.path_for(S.id).write_text("{깨진", encoding="utf-8")
    assert precomputed.load_all([S]) == {}


def test_precompute_script_needs_yes(monkeypatch, capsys):
    from core import llm
    from scripts.precompute import main
    p = FakeProvider()
    monkeypatch.setattr(llm, "get_provider", lambda: p)
    assert main([]) == 2
    out = capsys.readouterr().out
    assert "p1, p2, p3" in out and "--yes" in out and p.prompts == []


def test_precompute_script_saves_only_good_results(monkeypatch):
    from core import llm
    from scripts.precompute import main
    monkeypatch.setattr(llm, "get_provider", lambda: FakeProvider(reply(), reply("아님"), reply("{}")))
    assert main(["--yes", "p1", "p2"]) == 1  # p2는 두 번 다 형식 오류 -> 저장 안 함
    assert precomputed.path_for("p1").exists() and not precomputed.path_for("p2").exists()
