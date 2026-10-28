"""평가 지표 (LLM 없음)."""
from core.schema import Analysis, NumberCheck, Numbers, Rate, Risk, Sample
from eval.metrics import score, total
from eval.run import main

GOLD = {"docType": "loan", "rates": [{"label": "최저금리", "value": 5.5}, {"label": "최고금리", "value": 9.9}],
        "months": 36, "amount": 5000000,
        "risks": ["연체 시 연체이자율이 적용됩니다", "중도상환 시 수수료가 부과됩니다"]}


def sample(issues=()):
    return Sample(id="x", name="x", origin="raw", text="t", gold=GOLD, gold_issues=list(issues))


def analysis(rates=(5.5, 9.9), months=36, amount=5000000, unfound=(), risks=("연체이자율",), kind="loan"):
    n = Numbers(rates=[Rate(label="금리", value=v) for v in rates], months=months, amount=amount)
    checks = [NumberCheck(field=f"rates[{i}]", label="금리", value=v, found=f"rates[{i}]" not in unfound)
              for i, v in enumerate(rates)]
    checks += [NumberCheck(field=f, label=f, value=getattr(n, f), found=f not in unfound)
               for f in ("months", "amount") if getattr(n, f) is not None]
    return Analysis(source="rule", kind=kind, verdict="v", numbers=n, number_checks=checks,
                    risks=[Risk(phrase=p, why="w") for p in risks])


def test_rate_matched_by_value_not_label():
    sc = score(analysis(), sample())
    assert sc.number_hits == {"금리": [2, 2], "기간": [1, 1], "금액": [1, 1]} and sc.doc_type_ok


def test_unverified_number_counts_as_miss():
    sc = score(analysis(unfound=("months", "rates[1]")), sample())
    assert sc.number_hits["기간"] == [0, 1] and sc.number_hits["금리"] == [1, 2]


def test_gold_issue_fields_are_excluded():
    sc = score(analysis(amount=None), sample(issues=["amount=5000000: 원문에서 확인 안 됨"]))
    assert "금액" not in sc.number_hits


def test_risk_recall_by_containment_ignoring_spaces():
    sc = score(analysis(risks=("연체 이자율이 적용", "원금 손실")), sample())
    assert (sc.risk_hit, sc.risk_total, sc.found_risks) == (1, 2, 2)
    assert any("중도상환" in m for m in sc.misses)


def test_total():
    t = total([score(analysis(), sample()), score(analysis(rates=(), kind="card"), sample())])
    assert t["number_hit"] == (6, 8) and t["doc_type"] == (1, 2) and t["risk_hit"] == (2, 4)


def test_ai_mode_without_yes_makes_no_call(capsys):
    assert main(["--ai"]) == 2  # 테스트 환경에는 키가 없다
    assert "API 키가 없어요" in capsys.readouterr().out


def test_rule_mode_runs(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "## 규칙 기반 평가" in out and "**합계**" in out


def test_ai_mode_with_key_but_no_yes_makes_no_call(monkeypatch, capsys):
    from core import llm
    from tests.fakes import FakeProvider
    p = FakeProvider()  # 답이 없어서 불리면 실패한다
    monkeypatch.setattr(llm, "get_provider", lambda: p)
    assert main(["--ai"]) == 2
    assert p.prompts == [] and "--yes" in capsys.readouterr().out
