"""①~⑤ 마커 자동 밑줄 (변형문제 어법/어휘 밑줄 문제) 단위 테스트.

발문이 '밑줄 친 ①~⑤'인데 지문엔 번호만 있고 밑줄(<u>)이 없던 문제를 해결한다.
choices에 적힌 대상 표현으로 지문의 마커 직후 표현을 정확히 밑줄 처리한다.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from naeshin_engine.make_exam_pdf import (  # noqa: E402
    extract_circled_map, apply_circled_underlines,
)


# ── extract_circled_map: choices → {마커: 대상표현} ──
def test_extract_circled_map_single_words():
    choices = ['① possess', '② from', '③ to be']
    assert extract_circled_map(choices) == {'①': 'possess', '②': 'from', '③': 'to be'}


def test_extract_circled_map_multiword_phrase():
    choices = ['⑤ has been called', '① have only just discovered']
    assert extract_circled_map(choices) == {
        '⑤': 'has been called', '①': 'have only just discovered',
    }


def test_extract_circled_map_ignores_non_numbered():
    # 어법ABC 식 '① (A) save — (B) who' 같은 건 대상 추출에 안 쓰지만 깨지지 않아야
    choices = ['boom', '① ok']
    assert extract_circled_map(choices) == {'①': 'ok'}


# ── apply_circled_underlines: 지문 마커 직후 표현 밑줄 ──
def test_apply_underline_single_word_glued():
    text = "You may ①possess — some talent"
    out = apply_circled_underlines(text, {'①': 'possess'})
    assert out == "You may ①<u>possess</u> — some talent"


def test_apply_underline_multiword_phrase():
    text = "the work ⑤has been called art today"
    out = apply_circled_underlines(text, {'⑤': 'has been called'})
    assert out == "the work ⑤<u>has been called</u> art today"


def test_apply_underline_multiple_markers():
    text = "①helped and ②resisted change"
    out = apply_circled_underlines(text, {'①': 'helped', '②': 'resisted'})
    assert out == "①<u>helped</u> and ②<u>resisted</u> change"


def test_apply_underline_marker_absent_in_text_is_skipped():
    # circled_map에 ④ 있어도 지문에 ④ 마커가 없으면 건드리지 않는다 (5강 Q2 마커누락 케이스)
    text = "①helped only"
    out = apply_circled_underlines(text, {'①': 'helped', '④': 'ridiculous'})
    assert out == "①<u>helped</u> only"


def test_apply_underline_marker_with_space_after():
    # 지문이 '① possess'처럼 마커 뒤 공백이 있어도 표현만 감싼다(마커·공백은 밖)
    text = "may ① possess things"
    out = apply_circled_underlines(text, {'①': 'possess'})
    assert out == "may ① <u>possess</u> things"


def test_apply_underline_expr_not_matching_is_skipped():
    # choices 표현이 지문 마커 직후와 다르면(추출오류 등) 잘못 밑줄하지 않는다
    text = "①apple pie"
    out = apply_circled_underlines(text, {'①': 'banana'})
    assert out == "①apple pie"


def test_apply_underline_preserves_text_without_markers():
    text = "no markers here at all"
    out = apply_circled_underlines(text, {'①': 'possess'})
    assert out == "no markers here at all"
