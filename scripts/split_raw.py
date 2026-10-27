"""data/raw/의 원본을 앱이 쓰는 파일로 나누고, 데이터 문제를 docs/data_report.md로 보고한다.

실행: python -m scripts.split_raw

원본 내용은 고쳐 쓰지 않는다. 형식 오류 항목은 빼고, 의심스러운 항목은 보고서에만 적는다.
risks.json에는 원문에서 찾기 위한 patterns(정규식)를 추가하는데, 무엇을 추가했는지 보고서에 남긴다.
"""
import json
import re
from collections import defaultdict

import config
from core import fallback
from core.extract import numbers_in_text
from core.glossary import parse_entries
from core.risks import parse_rules
from core.samples import prototype_samples
from core.schema import Sample

RAW_DIR = config.DATA_DIR / "raw"
REPORT = config.ROOT / "docs" / "data_report.md"

# raw red_flags의 keyword는 '연체이자율 과도하게 높음'처럼 상황 이름이라 원문에 그대로 나오지 않는다.
# 그래서 원문에서 그 상황을 알아볼 수 있는 말을 정규식으로 붙인다. 빈 목록은 규칙으로 찾을 수 없다는 뜻.
RAW_PATTERNS: dict[str, list[str]] = {
    "중도해지 시 이율 대폭 감소": [r"중도\s*해지"],
    "우대금리 조건 과다": [r"우대\s*(?:금리|이율|조건)"],
    "중도상환수수료 장기 부과": [r"중도\s*상환\s*(?:수수료|해약금)"],
    "연체이자율 과도하게 높음": [r"연체"],
    "변동금리 전환 조항": [r"변동\s*금리"],
    "리볼빙 자동 전환": [r"리볼빙"],
    "연대보증 요구": [r"연대\s*보증"],
    "최소결제금액만 안내": [r"최소\s*결제"],
    "가산금리 비공개": [r"가산\s*금리"],
    "대출 한도 과대 광고": [],
    "청약철회 불가 조항": [r"청약\s*철회[^.\n]{0,15}(?:불가|제한|할\s*수\s*없)"],
    "보이스피싱 유도형 문구": [r"안전\s*계좌", r"선입금|먼저\s*입금"],
    "자동 연장·갱신 조항": [r"자동\s*(?:연장|재예치|갱신)"],
    "수수료 안내 불명확": [r"수수료"],
    "전월실적 조건 복잡": [r"전월\s*실적"],
    "부가서비스 축소 가능 문구": [r"(?:사전\s*고지|예고)\s*없이", r"부가\s*서비스[^.\n]{0,15}(?:축소|변경|중단)"],
    "약관 변경 시 개별 통보 생략": [r"개별\s*(?:통지|통보)[^.\n]{0,10}(?:생략|없이)"],
    "신용점수 하락 유발 조항": [r"신용\s*(?:점수|정보)에\s*(?:불리|등록|영향)"],
    "공동인증서 외부 유출 요구": [r"인증서[^.\n]{0,15}(?:보내|전송|알려)", r"인증서\s*비밀번호"],
    "대출 끼워팔기": [r"(?:함께|동시에|추가로)\s*가입[^.\n]{0,10}(?:조건|필수|해야)"],
}
# raw에 없지만 프로토타입에 있던 규칙. origin='prototype'으로 표시해 추가한다
PROTOTYPE_EXTRA = ("현금서비스", "연회비")

# 사람이 읽고 판단한 의심 항목 (자동 검사로는 못 잡는 것)
MANUAL_NOTES = {
    "glossary": [
        "`변동금리`, `고정금리`가 '예적금' 분야로 되어 있음. 주로 대출 문서에 나오며 프로토타입에서는 '대출'이었음.",
        "`원금`, `원리금`이 '예적금' 분야로 되어 있음. 대출에서도 쓰는 말이라 분야별 이해도 집계가 한쪽으로 쏠릴 수 있음.",
        "`중도해지`의 별칭이 `중도해지이율`. 하나는 행위, 하나는 금리라 다른 개념임. 원문 '중도해지이율'이 '중도해지' 뜻으로 표시됨.",
        "`최소결제금액` 뜻풀이가 '리볼빙에서 …'로 한정됨. 리볼빙과 상관없이 쓰는 말임.",
        "`햇살론`은 실제 상품 이름이고 '정부 지원 저금리'라는 설명이 붙어 있음. 원칙 6(실제 상품 정보를 지어내지 않음)과 맞는지 확인 필요.",
        "`이자소득세` 뜻풀이에 세율(15.4%)이 없음 (프로토타입에는 있었음). 틀린 것은 아님.",
        "`신용점수`의 별칭 `신용등급`은 2021년부터 점수제로 바뀐 옛 표현. 틀린 것은 아님.",
    ],
    "risks": [
        "keyword 20개가 모두 상황 이름(예: '연체이자율 과도하게 높음')이라 원문 문자열과 맞출 수 없음 → patterns 추가로 해결.",
        "'대출 한도 과대 광고'는 문장 하나로 판단할 수 없어 patterns를 비워 둠 (AI 분석에서만 찾음).",
        "'우대금리 조건 과다'가 raw에서는 high, 프로토타입에서는 mid. raw 값(high)을 따름.",
        "'수수료 안내 불명확'의 patterns는 '수수료'라는 말만 보므로, 수수료가 분명히 안내된 문서에도 걸림.",
    ],
    "samples": [
        "4번: 제목은 '햇살 신용대출'인데 본문 상품명은 '새내기 신용대출'. 또 '상환일로부터 3년 이내'는 문맥상 '대출일로부터'로 보임.",
        "1번 amount=10000은 '매월 1만 원 이상'의 최소 납입액, 4번 amount=5000000은 '최대 500만 원' 한도. 계산기 기본값으로 쓰기에는 의미가 다름.",
        "4번 rates의 '최저금리' 5.5는 '기본금리' 5.5와 같은 값. 원문에 '최저금리'라는 말은 없음.",
        "정답 JSON에 연회비, 할인 한도 등 카드 숫자 필드가 없어 카드 계산기 값은 평가할 수 없음.",
    ],
}


def split_samples(raw: str) -> tuple[list[Sample], list[str]]:
    """'N. 이름' 줄로 문서를 나누고, 'json' 줄 뒤를 정답으로 읽는다."""
    samples, problems = [], []
    blocks = re.split(r"^(?=\d+\.\s)", raw.strip(), flags=re.M)
    for block in filter(str.strip, blocks):
        head, _, rest = block.partition("\n")
        m = re.match(r"(\d+)\.\s*(.+)", head.strip())
        parts = re.split(r"^\s*json\s*$", rest, maxsplit=1, flags=re.M)
        if not m or len(parts) != 2:
            problems.append(f"형식을 알 수 없는 블록: {head.strip()[:30]!r}")
            continue
        sid, name = f"r{m.group(1)}", m.group(2).strip()
        text = parts[0].strip()
        try:
            gold = json.loads(parts[1])
        except json.JSONDecodeError as ex:
            problems.append(f"{sid} {name}: 정답 JSON 오류 ({ex.msg})")
            gold = None
        if "[가상 자료]" not in text:
            problems.append(f"{sid} {name}: '[가상 자료]' 표시 없음")
        samples.append(Sample(id=sid, name=name, origin="raw", text=text, gold=gold,
                              gold_issues=gold_issues(text, gold) if gold else []))
    return samples, problems


def gold_issues(text: str, gold: dict) -> list[str]:
    """정답 숫자와 위험 문장이 원문에 실제로 있는지 대조한다. 여기 걸린 항목은 평가에서 뺀다."""
    t = numbers_in_text(text)
    issues = []
    for r in gold.get("rates", []):
        if round(float(r["value"]), 6) not in t.rates:
            issues.append(f"rates.{r['label']}={r['value']}: 원문에서 확인 안 됨")
    if gold.get("months") is not None and gold["months"] not in t.months:
        issues.append(f"months={gold['months']}: 원문에서 확인 안 됨")
    if gold.get("amount") is not None and gold["amount"] not in t.amounts:
        issues.append(f"amount={gold['amount']}: 원문에서 확인 안 됨")
    for s in gold.get("risks", []):
        if s not in text:
            issues.append(f"risks '{s[:20]}…': 원문에 글자 그대로 없음")
    return issues


def glossary_checks(raw_terms: list) -> tuple[list, list[str]]:
    entries, errors = parse_entries(raw_terms)
    report = [f"형식 오류로 제외: {e}" for e in errors]

    kept, seen = [], set()
    for e in entries:
        if e.term in seen:
            report.append(f"표제어 중복으로 뒤쪽 제외: `{e.term}`")
            continue
        seen.add(e.term)
        kept.append(e)

    owners: dict[str, list[str]] = defaultdict(list)
    for e in kept:
        if e.term in e.aliases:
            report.append(f"`{e.term}`: 별칭에 자기 자신이 들어 있음")
        for w in {e.term, *e.aliases}:
            owners[w].append(e.term)
    for w, terms in owners.items():
        if len(terms) > 1:
            report.append(f"`{w}`를 여러 항목이 씀: {', '.join(f'`{t}`' for t in terms)} (표제어 쪽으로 찾음)")

    short = []
    for e in kept:
        inside = [o.term for o in kept if o.term != e.term and e.term in o.term]
        if len(e.term) <= 2 and inside:
            short.append(f"`{e.term}`({', '.join(inside[:4])}{' …' if len(inside) > 4 else ''})")
    if short:
        report.append("다른 용어 안에 들어 있는 짧은 용어 (긴 용어를 먼저 잡도록 처리함): " + ", ".join(short))
    return kept, report


def risk_rules(raw_flags: list) -> tuple[list[dict], list[str]]:
    report = []
    rules = []
    for f in raw_flags:
        pats = RAW_PATTERNS.get(f.get("keyword"))
        if pats is None:
            report.append(f"patterns를 정하지 않은 새 keyword: `{f.get('keyword')}` (규칙으로 찾을 수 없음)")
            pats = []
        rules.append({**f, "patterns": pats, "origin": "raw"})
    for r in fallback.RISKS:
        if r["keyword"] in PROTOTYPE_EXTRA:
            rules.append({**r, "origin": "prototype"})
            report.append(f"프로토타입 규칙 추가: `{r['keyword']}` ({r['level']})")
    valid, errors = parse_rules(rules)
    report += [f"형식 오류로 제외: {e}" for e in errors]
    return [r.model_dump() for r in valid], report


def main() -> None:
    glossary_raw = json.loads((RAW_DIR / "glossary_raw.json").read_text(encoding="utf-8"))
    samples_raw = (RAW_DIR / "samples_raw.txt").read_text(encoding="utf-8")

    terms, g_report = glossary_checks(glossary_raw.get("terms", []))
    rules, r_report = risk_rules(glossary_raw.get("red_flags", []))
    raw_samples, s_report = split_samples(samples_raw)

    config.GLOSSARY_PATH.write_text(
        json.dumps([t.model_dump() for t in terms], ensure_ascii=False, indent=1), encoding="utf-8")
    config.RISKS_PATH.write_text(json.dumps(rules, ensure_ascii=False, indent=1), encoding="utf-8")
    config.SAMPLES_DIR.mkdir(exist_ok=True)
    all_samples = prototype_samples() + raw_samples
    for s in all_samples:
        (config.SAMPLES_DIR / f"{s.id}.json").write_text(
            s.model_dump_json(indent=1), encoding="utf-8")

    lines = [
        "# 데이터 점검 보고서",
        "",
        "> 자동 생성 파일입니다. `python -m scripts.split_raw`를 다시 실행하면 새로 만들어집니다.",
        "> 원본(data/raw/)은 수정하지 않았습니다.",
        "",
        f"- 용어: 원본 {len(glossary_raw.get('terms', []))}개 → glossary.json {len(terms)}개",
        f"- 위험 신호: 원본 {len(glossary_raw.get('red_flags', []))}개 → risks.json {len(rules)}개 (프로토타입 규칙 포함)",
        f"- 샘플: 프로토타입 {len(all_samples) - len(raw_samples)}개 + 원본 {len(raw_samples)}개 → data/samples/",
        "",
        "## 용어 사전", "", "### 자동 검사", *[f"- {x}" for x in g_report or ["문제 없음"]],
        "", "### 검토 메모", *[f"- {x}" for x in MANUAL_NOTES["glossary"]],
        "",
        "## 위험 조항", "", "### 자동 검사", *[f"- {x}" for x in r_report or ["문제 없음"]],
        "", "### 검토 메모", *[f"- {x}" for x in MANUAL_NOTES["risks"]],
        "", "### 추가한 patterns", "",
        "| keyword | level | patterns |", "|---|---|---|",
        # 표 안의 '|'는 칸 구분으로 읽히므로 이스케이프한다
        *[f"| {r['keyword']} | {r['level']} | "
          f"{' / '.join('`' + p.replace('|', chr(92) + '|') + '`' for p in r['patterns']) or '(없음: AI만)'} |"
          for r in rules],
        "",
        "## 샘플", "", "### 자동 검사", *[f"- {x}" for x in s_report or ["형식 문제 없음"]],
        *[f"- {s.id} {s.name}: {i} → **평가에서 제외**" for s in raw_samples for i in s.gold_issues],
        "", "### 검토 메모", *[f"- {x}" for x in MANUAL_NOTES["samples"]],
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"용어 {len(terms)}개, 위험 규칙 {len(rules)}개, 샘플 {len(all_samples)}개를 썼습니다.")
    print(f"보고서: {REPORT.relative_to(config.ROOT)}")


if __name__ == "__main__":
    main()
