"""금융 통역사 - Streamlit 화면.

화면만 담당한다. 분석, 계산, 검증 로직은 전부 core/에 있다.
실행: streamlit run app.py
"""
import streamlit as st

from core import calc
from core.analyze import analyze_rule, calculator_inputs
from core.glossary import load_glossary
from core.risks import load_risks
from core.samples import load_samples
from core.schema import KIND_NAME, Analysis

DISCLAIMER = (
    "금융 통역사는 금융 문서를 이해하도록 돕는 **학습 도구**이며, 상품 추천·투자 자문·법률 자문이 아닙니다. "
    "예시 문서와 숫자는 시연용 **가상 자료**입니다. 실제 가입 전에는 금융회사의 공식 상품설명서를 꼭 확인하세요."
)

st.set_page_config(page_title="금융 통역사", page_icon="💬", layout="wide")


@st.cache_resource
def deps():
    # 사전과 규칙은 한 번만 읽어서 모든 사용자 요청에 재사용한다
    return load_glossary(), load_risks(), load_samples()


glossary, risks, samples = deps()
ss = st.session_state
ss.setdefault("doc", "")
ss.setdefault("analysis", None)
ss.setdefault("run", 0)  # 분석할 때마다 늘려서 계산기 입력칸을 새 값으로 초기화한다


def run_analysis() -> None:
    text = ss.doc.strip()
    if not text:
        ss.analysis = None
        ss.error = "통역할 문서를 먼저 붙여넣어 주세요."
        return
    ss.error = None
    ss.analysis = analyze_rule(text, glossary, risks, samples)
    ss.run += 1


def pick_sample() -> None:
    s = next((x for x in samples if x.name == ss.sample_pick), None)
    if s:
        ss.doc = s.text
        run_analysis()


# ---------- 입력 ----------
st.title("금융 통역사")
st.caption("어려운 금융 문서를 붙여넣으면 내 말로 바꿔 주고, 읽은 만큼 금융 실력이 쌓여요.")

if glossary.from_fallback or risks.from_fallback:
    st.info("data/ 폴더의 사전 파일을 찾지 못해 프로토타입 내장 데이터를 쓰고 있어요.")

with st.container(border=True):
    st.selectbox(
        "예시 문서 (가상 자료)",
        [s.name for s in samples],
        index=None,
        placeholder="예시 문서를 고르거나, 아래에 직접 붙여넣으세요",
        key="sample_pick",
        on_change=pick_sample,
    )
    st.text_area("통역할 문서", key="doc", height=200,
                 placeholder="대출 안내문, 카드 혜택, 예·적금 약관 등을 붙여넣으세요. 문서는 저장되지 않아요.")
    c1, c2, _ = st.columns([1, 1, 4])
    c1.button("빠른 분석", type="primary", on_click=run_analysis, width="stretch")
    c2.button("AI로 통역하기", disabled=True, help="2일차에 연결합니다", width="stretch")
    if ss.get("error"):
        st.warning(ss.error)

a: Analysis | None = ss.analysis
if a is None:
    st.markdown("위에서 예시 문서를 고르거나 문서를 붙여넣고 **빠른 분석**을 눌러 보세요.")
    st.divider()
    st.caption(DISCLAIMER)
    st.stop()


# ---------- 결과: 왼쪽 ----------
def show_calculator(a: Analysis) -> None:
    ci = calculator_inputs(a)
    r = ss.run
    kinds = ["savings", "deposit", "loan", "card"]
    kind = st.selectbox("계산 종류", kinds, index=kinds.index(ci.kind), format_func=KIND_NAME.get, key=f"kind{r}")

    def num(label: str, name: str, step: float = 1.0, min_value: float = 0.0, fmt: str = "%d"):
        src = "문서에서 읽음" if name in ci.from_doc else "예시값"
        v = ci.values[name] if ci.values[name] is not None else 0
        cast = float if fmt != "%d" else int
        return st.number_input(f"{label} · {src}", min_value=cast(min_value), value=cast(v), step=cast(step),
                               format=fmt, key=f"{name}{r}")

    if kind in ("savings", "deposit", "loan"):
        amount_label = {"savings": "월 납입액 (원)", "deposit": "맡기는 돈 (원)", "loan": "대출 원금 (원)"}[kind]
        c1, c2, c3 = st.columns(3)
        with c1:
            amount = num(amount_label, "amount", step=10_000)
        with c2:
            rate = num("연 금리 (%)", "rate", step=0.1, fmt="%.2f")
        with c3:
            months = num("기간 (개월)", "months", min_value=1)

        verified = [x for i, x in enumerate(a.numbers.rates)
                    if any(c.field == f"rates[{i}]" and c.found for c in a.number_checks)]
        if verified:
            def set_rate(v: float) -> None:
                ss[f"rate{r}"] = float(v)

            st.caption("문서에서 찾은 금리를 눌러 넣어 보세요")
            cols = st.columns(min(len(verified), 4))
            for i, x in enumerate(verified):
                cols[i % len(cols)].button(f"{x.label} {x.value:g}%", key=f"rb{r}_{i}", on_click=set_rate, args=(x.value,))

        if kind == "loan":
            res = calc.loan(amount, rate, months)
            st.metric("매달 갚는 돈", calc.won(res.monthly))
            st.markdown(f"빌린 돈 {calc.won(res.principal)} · 총 이자 {calc.won(res.interest)} · "
                        f"총 갚는 돈 {calc.won(res.total_paid)}")
            st.caption("원리금균등상환으로 계산했어요. 변동금리면 금리가 바뀔 때 달라져요.")
        else:
            taxed = st.checkbox("이자소득세 15.4% 빼고 계산", value=True, key=f"tax{r}")
            res = (calc.savings if kind == "savings" else calc.deposit)(amount, rate, months, taxed)
            st.metric("만기에 받는 돈" + (" (세후)" if taxed else ""), calc.won(res.total))
            st.markdown(f"낸 원금 {calc.won(res.principal)} · 이자 {calc.won(res.interest)} · "
                        f"세금 -{calc.won(res.tax)} · 세후 연 금리 {res.net_rate:.2f}%")
            if kind == "savings":
                st.caption("적금은 돈이 한 달씩 차례로 들어가서, 같은 금리여도 예금보다 받는 이자가 훨씬 적어요.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            fee = num("연회비 (원)", "fee", step=1_000)
            disc = num("할인율 (%)", "discount_rate", step=0.5, fmt="%.1f")
        with c2:
            spend = num("월 할인 대상 사용액 (원)", "spend", step=10_000)
            cap = num("월 할인 한도 (원, 0 = 한도 없음)", "cap", step=1_000)
        res = calc.card(spend, disc, cap or None, fee)
        st.metric("1년 순이익 (할인 - 연회비)", calc.won(res.net))
        st.markdown(f"월 할인액 {calc.won(res.per_month)} · 1년 할인액 {calc.won(res.annual)} · 연회비 -{calc.won(res.fee)}")
        st.caption("이 사용 패턴에서는 " + ("연회비가 더 커요." if res.net < 0 else "할인이 연회비보다 커요."))


left, right = st.columns([1.2, 1], gap="large")

with left:
    st.subheader("한 줄 통역")
    badge = "AI 통역" if a.source == "ai" else "규칙 기반 분석"
    st.caption(badge + (f" · {a.fallback_reason}" if a.fallback_reason else ""))
    st.markdown(f"#### {a.verdict}")

    st.subheader("이 문서의 용어")
    if a.terms:
        for t in a.terms:
            st.markdown(f"- **{t.term}** ({t.category}) · {t.meaning}")
    else:
        st.caption("사전에 있는 용어를 찾지 못했어요.")

    with st.expander("원문 보기"):
        st.text(ss.doc)

with right:
    st.subheader("조심할 조항")
    if a.risks:
        for x in a.risks:
            (st.error if x.level == "high" else st.warning)(
                f"**{'주의' if x.level == 'high' else '확인'} · {x.phrase}**  \n{x.why}")
    else:
        st.success("눈에 띄는 불리한 조항을 찾지 못했어요. 그래도 원문을 끝까지 읽어 보세요.")

    st.subheader("읽어 낸 숫자")
    if a.number_checks:
        st.table([{"항목": c.label, "값": f"{c.value:g}", "원문 확인": "확인됨" if c.found else "⚠ 원문에서 확인 안 됨"}
                  for c in a.number_checks])
    else:
        st.caption("문서에서 숫자를 찾지 못했어요. 계산기에 직접 넣어 보세요.")

    st.subheader("내 금액으로 계산")
    with st.container(border=True):
        show_calculator(a)

# ---------- 문장별 통역 ----------
st.subheader("문장별 통역")
if a.pairs:
    h1, h2 = st.columns(2)
    h1.caption("금융어 · 원문")
    h2.caption("일상어 · 통역")
    for p in a.pairs:
        c1, c2 = st.columns(2)
        c1.markdown(p.original)
        c2.markdown(f"**{p.easy}**")
        st.divider()
else:
    st.caption("문장별 통역은 ‘AI로 통역하기’를 쓸 때 만들어져요. 지금은 프로토타입 예시 문서 3종에서 볼 수 있어요.")

st.divider()
st.caption(DISCLAIMER)
