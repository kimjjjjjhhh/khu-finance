"""AI나 원문에서 온 글을 st.markdown에 넣기 전에 마크다운 기호를 무력화한다.

Streamlit 마크다운은 ~ 두 개 사이를 취소선, $ 두 개 사이를 수식, :color[...]를 색 글씨로 바꾼다.
'연 5.5~9.9%' 같은 금융 문구가 깨지지 않도록 ASCII 문장부호를 모두 백슬래시로 이스케이프한다.
CommonMark는 모든 ASCII 문장부호의 이스케이프를 허용하므로 보이는 글자는 그대로다.
"""
import re

_PUNCT = re.compile(r"""([\\`*_{}\[\]()#+\-.!|~$<>:&="'])""")


def esc(s: str) -> str:
    return _PUNCT.sub(lambda m: "\\" + m.group(1), s)
