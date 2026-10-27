"""원문 하이라이트 HTML 만들기. 용어는 노란색, 위험 구절은 붉은색, 누르면 뜻이 펼쳐진다.

JS 없이 CSS만 쓴다 (st.html은 스크립트를 실행하지 않음). 누르면 tabindex 덕에 포커스가 생기고,
:focus일 때 풀이를 보여 준다. 원문에 없는 인용(found=False)은 표시하지 않는다.
"""
import html
import re
from dataclasses import dataclass

from core.schema import Risk, Term
from core.verify import quote_pattern

STYLE = """<style>
.hl-doc { line-height: 1.9; white-space: normal; word-break: keep-all; overflow-wrap: anywhere; }
.hl { position: relative; border-radius: 4px; padding: 1px 2px; cursor: pointer; outline: none; }
.hl-term { background: rgba(250, 204, 21, .38); }
.hl-risk { background: rgba(239, 68, 68, .22); border-bottom: 2px solid rgba(220, 38, 38, .85); }
.hl-risk.mid { border-bottom-style: dashed; }
.hl:focus { box-shadow: 0 0 0 2px rgba(59, 130, 246, .7); }
.hl .tip { display: none; position: absolute; left: 0; top: 1.9em; z-index: 10; width: max-content; max-width: 280px;
  padding: 6px 10px; border-radius: 6px; background: #1f2937; color: #f9fafb; font-size: .85rem; line-height: 1.45;
  white-space: normal; box-shadow: 0 4px 12px rgba(0, 0, 0, .25); }
.hl:hover .tip, .hl:focus .tip { display: block; }
.hl-legend { font-size: .8rem; opacity: .8; margin-bottom: .4rem; }
</style>"""


@dataclass(frozen=True)
class Mark:
    start: int
    end: int
    kind: str  # term / risk
    tip: str
    level: str = ""


def find_marks(text: str, terms: list[Term], risks: list[Risk]) -> list[Mark]:
    """겹치면 위험 구절이 이기고, 같은 종류끼리는 긴 쪽이 이긴다."""
    cands: list[Mark] = []
    for r in risks:
        p = quote_pattern(r.phrase) if r.found else None
        for m in p.finditer(text) if p else []:
            label = "주의" if r.level == "high" else "확인"
            cands.append(Mark(m.start(), m.end(), "risk", f"{label} · {r.why}", r.level))
    for t in terms:
        for s in t.surfaces if t.found else []:
            for m in re.finditer(re.escape(s), text):
                cands.append(Mark(m.start(), m.end(), "term", f"{t.term} · {t.meaning}"))

    cands.sort(key=lambda c: (c.kind != "risk", -(c.end - c.start), c.start))
    taken: list[Mark] = []
    for c in cands:
        if all(c.end <= t.start or c.start >= t.end for t in taken):
            taken.append(c)
    return sorted(taken, key=lambda c: c.start)


def highlight_html(text: str, terms: list[Term], risks: list[Risk]) -> str:
    out, pos = [], 0
    for m in find_marks(text, terms, risks):
        out.append(html.escape(text[pos:m.start]))
        cls = f"hl hl-{m.kind} {m.level}".strip()
        out.append(f'<span class="{cls}" tabindex="0">{html.escape(text[m.start:m.end])}'
                   f'<span class="tip">{html.escape(m.tip)}</span></span>')
        pos = m.end
    out.append(html.escape(text[pos:]))
    body = "".join(out).replace("\n", "<br>")
    legend = ('<div class="hl-legend"><span class="hl hl-term">용어</span> '
              '<span class="hl hl-risk">조심할 조항</span> 표시를 누르면 뜻이 보여요.</div>')
    return f'{STYLE}{legend}<div class="hl-doc">{body}</div>'
