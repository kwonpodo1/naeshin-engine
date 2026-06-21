"""공유 패키지 ko_spacing 회귀/품질 테스트 — auto 동작 보존 + studio 반영 근거.

apply_safe(텍스트→텍스트) 와 형태소 게이트(core)를 검증한다.
auto tests/test_fix_ko_spacing.py + test_ko_spacing_precision.py 의 순수 로직 부분을
패키지로 가져온 것 (checker·CLI 부분은 auto 전용이라 제외).

POSITIVE 의 뒤쪽 묶음은 studio 실데이터(동일 Claude)에서 나온 실제 공백 오타 —
패키지 apply_safe 가 그대로 고치므로 studio 가 받을 가치의 근거가 된다.

실행: python -X utf8 -m pytest tests/test_ko_spacing.py -v
"""
from naeshin_engine.ko_spacing import apply_safe
from naeshin_engine.ko_spacing_core import (
    extra_space_genuine_count,
    missing_space_is_style,
)


# apply_safe 가 고쳐야 하는 진짜 어절 중간/조사 공백 오타 (auto 회귀 케이스)
POSITIVE = [
    ("정보를 전달하는 능 력을 향상하는 데도 도움",
     "정보를 전달하는 능력을 향상하는 데도 도움"),          # 1글자+단일명사 (R7)
    ("우리가 무서운 것 과 기묘한 것을 설명",
     "우리가 무서운 것과 기묘한 것을 설명"),               # 의존명사 것 + 조사
    ("상상 속 의 입구를 향해",
     "상상 속의 입구를 향해"),                          # 명사 속 + 조사
    ("세상을 묘사하 여, 즉 그것을",
     "세상을 묘사하여, 즉 그것을"),                       # 하-어간(XSV) + 어미
    ("공간이 없음을 설명 했지만, 그 여자는",
     "공간이 없음을 설명했지만, 그 여자는"),               # 명사+했 (다중자 좌측, R7)
    ("시판 전에 그 안전 성과 효과를 평가",
     "시판 전에 그 안전성과 효과를 평가"),                 # 명사 분할(안전성)
    ("박사 과정을 졸업했고, 1924 년에 박사 학위를",
     "박사 과정을 졸업했고, 1924년에 박사 학위를"),         # 숫자+의존명사+조사
    ("계급의 다수는 열악 한 환경에서",
     "계급의 다수는 열악한 환경에서"),                     # 어근(XR)+하+ㄴ
    # --- studio 실데이터(동일 Claude)에서 나온 실제 오타 — 반영 가치 근거 ---
    ("효율적일 것이라고 가정 하는 것이 논리적",
     "효율적일 것이라고 가정하는 것이 논리적"),             # 한자어+하 (R5)
    ("최근에 Qukkon 에 도착한 금광 채굴자",
     "최근에 Qukkon에 도착한 금광 채굴자"),               # 영문 고유명사 + 조사 (R1)
]

# 절대 바뀌면 안 되는 것 — 보조용언/진짜 2어절/관형사+명사
NEGATIVE = [
    "단기적인 규모로 이루어져야 한다.",     # 본용언+보조용언 (하다)
    "별도의 승강장이 사용되어야 하고 교통이",  # 보조용언
    "탐구와 이해를 가능하게 하지만 이것은",    # 가능하게 + 하다(보조)
    "되찾아야 할 짐이 있을",                # 보조용언 할
    "밝게 해 주는 새로운 길",               # 밝게(부사형) + 해(독립용언)
    "사회 과학자들이 문화를 연구",           # 진짜 두 명사
    "그 일을 할 수 있다",                  # 의존명사 수 + 있다
    "한 번 더 시도",                       # 한 번(횟수) ≠ 한번(시도)
    "도울 수 없음을 기억",                  # 수 없음
]


def test_positive_fixes():
    for src, want in POSITIVE:
        got = apply_safe(src)
        assert got == want, f"{src!r} -> {got!r} (기대 {want!r})"


def test_negative_unchanged():
    for src in NEGATIVE:
        got = apply_safe(src)
        assert got == src, f"불변이어야 하는데 변경됨: {src!r} -> {got!r}"


def test_idempotent():
    """두 번 적용해도 결과 동일 (수렴)."""
    for src, _ in POSITIVE:
        once = apply_safe(src)
        twice = apply_safe(once)
        assert once == twice, f"비멱등: {src!r} | 1회 {once!r} | 2회 {twice!r}"


def test_r1_r6_preserved():
    """R1·R3·R5 기본 동작 회귀 안전망."""
    cases = [
        ("Berlin 에서 시작", "Berlin에서 시작"),       # R1 ASCII+조사
        ("말씀) 은 옳다", "말씀)은 옳다"),               # R3 닫는부호+조사
        ("확보 하기 위해", "확보하기 위해"),             # R5 한자어명사+하
    ]
    for src, want in cases:
        got = apply_safe(src)
        assert got == want, f"R1-R6 회귀: {src!r} -> {got!r} (기대 {want!r})"


# --- 형태소 게이트 (core) — 체커가 의존하는 판정 ---
AUX = "단기적인 규모로 이루어져야 한다."                    # 본용언+보조용언 = 정상
GENUINE1 = "효율적일 것이라고 가정 하는 것이 논리적으로 보일 수 있지만"
GENUINE2 = "가장 많이 연구 된 기술들 중 하나이다."
AUX_SPLIT = "그것을 보여주다"                              # kiwi: 보여 주다 (보조용언)
COMPOUND_SPLIT = "총가격이 올랐다"                          # kiwi: 총 가격이 (복합명사)


def test_core_suppresses_auxiliary_verb():
    assert extra_space_genuine_count(AUX) == 0


def test_core_counts_genuine_typo():
    assert extra_space_genuine_count(GENUINE1) >= 1
    assert extra_space_genuine_count(GENUINE2) >= 1


def test_missing_space_aux_is_style():
    assert missing_space_is_style(AUX_SPLIT) is True
    assert missing_space_is_style(COMPOUND_SPLIT) is False
