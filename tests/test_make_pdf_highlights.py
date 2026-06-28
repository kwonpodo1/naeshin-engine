"""
make_pdf 중첩 하이라이트 렌더러 — 구간(interval) 기반 색칠.

핵심 불변식:
  - 겹침/near-miss 없는 문장: 기존 평면 출력과 동일(_render_flat 경로).
  - 중첩(단어가 절 안): 안쪽(짧은) 색이 이김 → nested 마크업.
  - 따옴표 near-miss(닫는 따옴표 안 문장부호): relaxed 매치로 색칠.
  - 진짜 부재 구절: 색 없음.

실행: python -X utf8 -m pytest tests/test_make_pdf_highlights.py -v
"""
from naeshin_engine import make_pdf as M


def _markup(en, highlights, num="01", star=False):
    s = {"en": en, "highlights": highlights, "num": num}
    if star:
        s["star"] = True
    return M._render_en_markup(s)


def test_locate_no_overlap():
    spans, needs, missed = M._locate_spans(
        M._xml_escape("I like big cats"),
        [("big", "blue", "a"), ("cats", "green", "b")],
    )
    assert needs is False and missed == [] and len(spans) == 2


def test_locate_nested_overlap():
    spans, needs, missed = M._locate_spans(
        M._xml_escape("Did you know that"),
        [("you", "blue", "a"), ("Did you know", "orange", "b")],
    )
    assert needs is True


def test_nonoverlap_markup_matches_flat():
    en = "I like big cats today"
    hls = [("big", "blue", "a"), ("cats", "green", "b")]
    esc = M._xml_escape(en)
    flat = M._render_flat({"en": en, "num": "01"}, esc, hls)
    assert _markup(en, hls) == flat   # 비겹침 → 평면과 동일


def test_nested_inner_color_wins():
    en = "to work out your mind here"
    hls = [("to work out your mind", "green", "절"), ("work", "orange", "동사")]
    body = _markup(en, hls)
    orange = M.c2h(M.COLOR_MAP["orange"])
    green = M.c2h(M.COLOR_MAP["green"])
    assert f'<font color="{orange}"><b>work</b></font>' in body   # 안쪽 단어 주황
    assert green in body                                          # 바깥 절 초록 존재


def test_near_miss_relaxed_quote_colored():
    en = 'her flight had been “delayed.”'
    hls = [('had been “delayed”', "blue", "인용")]   # 마침표가 따옴표 안 → 리터럴 불일치
    spans, needs, missed = M._locate_spans(M._xml_escape(en), hls)
    assert missed == [] and needs is True            # relaxed 로 찾음
    body = _markup(en, hls)
    blue = M.c2h(M.COLOR_MAP["blue"])
    assert blue in body and "delayed" in body        # 색칠됨


def test_duplicate_phrase_two_occurrences():
    en = "make it or make it again"
    hls = [("make", "blue", "1"), ("make", "orange", "2")]
    spans, needs, missed = M._locate_spans(M._xml_escape(en), hls)
    assert missed == [] and len(spans) == 2          # 두 occurrence 각각
    assert spans[0][:2] != spans[1][:2]


def test_truly_absent_phrase_no_color():
    en = "a plain sentence"
    hls = [("nonexistent phrase", "blue", "x")]
    spans, needs, missed = M._locate_spans(M._xml_escape(en), hls)
    assert len(missed) == 1 and spans == []
