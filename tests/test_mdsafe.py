"""마크다운 이스케이프."""
import pytest

from core.mdsafe import esc


@pytest.mark.parametrize("raw, escaped", [
    ("연 5.5~9.9%", r"연 5\.5\~9\.9%"),
    ("$100 할인, $200 적립", r"\$100 할인, \$200 적립"),
    ("*우대* _조건_ `코드`", r"\*우대\* \_조건\_ \`코드\`"),
    ("# 제목\n> 인용", "\\# 제목\n\\> 인용"),
    ("- 목록 :red[빨강]", r"\- 목록 \:red\[빨강\]"),
    ("<b>태그</b> &amp;", r"\<b\>태그\</b\> \&amp;"),
])
def test_escape(raw, escaped):
    assert esc(raw) == escaped


def test_korean_untouched():
    assert esc("중도해지하면 이자가 거의 없어요") == "중도해지하면 이자가 거의 없어요"
