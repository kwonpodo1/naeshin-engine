"""ko 필드 공백 오타 자동 수정 — 보수적 규칙 R1~R7 (순수 텍스트→텍스트, auto·studio 공유).

단일 소스: naeshin_engine/ko_spacing.py. CLI(파일 스캔·--apply)는 auto scripts/fix_ko_spacing.py
가 보유하고, 이 모듈은 문자열 in → 문자열 out 의 apply_safe 만 공유한다.
studio 는 Claude 생성/추출 한국어에 apply_safe 를 적용해 같은 품질을 받는다.

kiwipiepy 전체 space() 결과를 통째로 쓰지 않는다. 한 문장에 삭제·추가 교정이 섞이면
false positive 를 구분할 수 없기 때문이다. 대신 확실히 오타인 패턴만 regex 로 처리하고,
어절 중간 공백(R6/R7)은 kiwi 형태소 게이트(ko_spacing_core)로 판정한 것만 적용한다.

자동 수정 규칙:
  R1. 영문/숫자 + 공백 + 한국어 조사 (예: "Berlin 에서" → "Berlin에서")
  R2. 숫자 + 공백 + 한국어 의존명사  (예: "1924 년" → "1924년")
  R3. 닫는 따옴표/괄호 + 공백 + 한국어 조사 (예: "말씀) 은" → "말씀)은")
  R4. 어절 어간 + 공백 + 종결어미 (예: "편해졌 다." → "편해졌다.")
  R5. 한자어 명사(2~4자) + 공백 + 하/되/시 활용 (예: "확보 하기" → "확보하기").
      kiwi 형태소 분석으로 NNG + XSV/XSA 결합 확인된 케이스만 적용.
  R6. 1글자 prefix + 공백 + 2~5자 suffix (예: "주 어지는" → "주어지는",
      "행 해졌다" → "행해졌다", "맞 지만" → "맞지만"). kiwi 로 흡수/결합
      확인된 경우만 적용 (용언어간+어미, 명사→용언 흡수, 명사+XSV 파생).
  R7. kiwi.space() 가 '삭제'하려는 갭(=어절 분절 오타) 중 형태소 게이트를
      통과한 것만 공백 제거. R1~R6 의 정규식이 구조적으로 못 잡는 잔여를 덮는다.
      (예: "능 력을"→"능력을"[단일명사], "설명 했지만"→"설명했지만"[다중자 좌측],
       "안전 성과"→"안전성과"[명사 분할], "1924 년에"→"1924년에"[조사 뒤].)
      게이트 = 결합형에 보조용언(VX) 없음 + 좌측 어절이 어미/조사로 끝나지 않음.
      → 본용언+보조용언("있어야 한다")·진짜 2어절("사회 과학자")·관형사+명사
        ("한 번")은 배제. 삽입(missing_space)은 절대 반영하지 않는다.
"""
from __future__ import annotations

import re

from naeshin_engine.ko_spacing_core import (
    get_kiwi as _get_kiwi,
    content_gaps as _content_gaps,
    gap_is_typo as _gap_is_typo,
)

PARTICLES = (
    r"(?:의|에|에서|에게|에게서|이|가|을|를|은|는|과|와|로|으로|도|만|부터|까지"
    r"|처럼|마저|조차|라고|라는|이라|이라고|까지|보다|께|께서|에도)"
)
UNITS = r"(?:년|월|일|시|분|초|개|명|마리|번|차|회|장|권|위|살|세|인|건|편|쪽|급|등|호|종|대|도)"

# lookahead에 한글을 허용하면 명사 첫글자 ("이스라엘"의 "이")가 조사로 잘못 매치된다.
# 조사/의존명사 뒤는 공백·문장부호·문장끝만 허용한다.
_TAIL = r"(?=[\s,.!?:;\"'’”)\]]|$)"

# R1: 영문/숫자 + 한국어 조사
ASCII_PARTICLE = re.compile(rf"([A-Za-z0-9])\s+({PARTICLES}){_TAIL}")
# R2: 숫자 + 한국어 의존명사
NUM_UNIT = re.compile(rf"(\d)\s+({UNITS})(?=[\s,.!?:;]|$)")
# R3: 닫는 따옴표/괄호 + 한국어 조사
CLOSE_PARTICLE = re.compile(rf"([)\]\}}”’\"'])\s+({PARTICLES}){_TAIL}")

# R4: 어절 중간 종결어미 — "편해졌 다.", "선구자였 다", "피어났 다." 류
# "다" 뒤가 문장부호·닫힘부호·문장끝일 때만 (부사 "다"와 구분).
# 앞 어절이 1~4자 한글이어야 (너무 길면 문장 통째로 오인 위험).
KO_TERMINAL = re.compile(
    r"(?<![가-힣])([가-힣]{1,4})\s+(다|던|네|지|요|야|까)(?=[.?!,;:)\]\"'’”]|$)"
)

# R5: 한자어 명사(2~4자) + 공백 + 하/되/시 활용 — kiwi 분석으로 NNG+XSV/XSA 결합된 경우만.
# 예: "확보 하기" → "확보하기", "개발 되는" → "개발되는"
R5_PATTERN = re.compile(
    r"(?<![가-힣])([가-힣]{2,4})\s+((?:하|되|시)[가-힣]{1,5})(?=[\s,.!?:;]|$)"
)

# R6: 1글자 prefix + 공백 + 2~5자 suffix — 어절 중간 공백의 가장 어려운 케이스.
# kiwi 분석으로 흡수/결합 여부 판정:
#   A) prefix 용언어간(VV/VA) + 어미 suffix (예: "맞 지만" → "맞지만")
#   B) prefix 명사 + 흡수되는 suffix → 단일 용언 (예: "주 어지는" → "주어지는")
#   C) prefix 명사 + NNG 합성 + XSV/XSA (예: "약 화시켜" → "약화시켜")
R6_PATTERN = re.compile(
    r"(?<![가-힣])([가-힣])\s+([가-힣]{2,5})(?=[\s,.!?:;]|$)"
)


def _is_noun_hada_typo(prefix: str, suffix: str) -> bool:
    """prefix (명사) + suffix (하/되/시 활용) 가 kiwi 상 단일 용언으로 흡수되면 오타."""
    kiwi = _get_kiwi()
    if kiwi is None:
        return False
    try:
        p_tok = kiwi.tokenize(prefix)
        j_tok = kiwi.tokenize(prefix + suffix)
    except Exception:
        return False
    if len(p_tok) != 1 or p_tok[0].tag != "NNG":
        return False
    if len(j_tok) < 2:
        return False
    if j_tok[0].form != prefix or j_tok[0].tag != "NNG":
        return False
    return j_tok[1].tag in ("XSV", "XSA")


def apply_r5(text: str) -> str:
    def repl(m: re.Match) -> str:
        prefix, suffix = m.group(1), m.group(2)
        if _is_noun_hada_typo(prefix, suffix):
            return prefix + suffix
        return m.group(0)

    return R5_PATTERN.sub(repl, text)


# kiwi 가 단독 분석 시 NNG 로 잘못 잡는 1글자 조사·어미·지시어 — R6 에서 제외.
# 예: "의" → NNG("의결"의 일부)로 분석되어 "것 의 결함" → "것 의결함" false positive 발생.
_AMBIGUOUS_SINGLE = set("의가이은는을를과와도만로야까나네며겠랑자")


def _is_single_char_mid_typo(prefix: str, suffix: str) -> bool:
    """
    1글자 prefix + suffix 조합이 어절 중간 공백 오타인지 판정.
      A) VV/VA 어간 + 어미  → 단일 용언 + 어미로 분석
      B) NNG + 흡수  → VV/VA 로 흡수 (prefix 보다 긴 첫 토큰)
      C) NNG + NNG 합성 + XSV/XSA  (예: 약화시키다)
    """
    if prefix in _AMBIGUOUS_SINGLE:
        return False
    kiwi = _get_kiwi()
    if kiwi is None:
        return False
    try:
        p_tok = kiwi.tokenize(prefix)
        j_tok = kiwi.tokenize(prefix + suffix)
    except Exception:
        return False
    if len(p_tok) != 1 or len(j_tok) < 2:
        return False
    p_tag = p_tok[0].tag
    first = j_tok[0]

    # 케이스 A: 용언어간 단독 + 어미
    if p_tag in ("VV", "VA"):
        return (
            first.form == prefix
            and first.tag == p_tag
            and j_tok[1].tag.startswith("E")
        )

    # 케이스 B/C: 명사 prefix
    if p_tag != "NNG":
        return False
    # 첫 토큰이 prefix 로 시작하고 길어야 흡수로 간주
    if not first.form.startswith(prefix) or len(first.form) <= len(prefix):
        return False
    if first.tag in ("VV", "VA"):
        return True
    if first.tag == "NNG" and j_tok[1].tag in ("XSV", "XSA"):
        return True
    return False


def apply_r6(text: str) -> str:
    def repl(m: re.Match) -> str:
        prefix, suffix = m.group(1), m.group(2)
        if _is_single_char_mid_typo(prefix, suffix):
            return prefix + suffix
        return m.group(0)

    return R6_PATTERN.sub(repl, text)


# R7: 어절 중간 공백 — kiwi.space() 의 '삭제' 제안 중 형태소 게이트 통과분만 적용.
# 게이트 primitives(_get_kiwi·_content_gaps·_gap_is_typo)는 ko_spacing_core 에서 import한다.
# 체커 run_quality_check 가 같은 판정을 공유하도록 단일 원천으로 둔다.


def apply_r7(text: str) -> str:
    kiwi = _get_kiwi()
    if kiwi is None or not text or not text.strip():
        return text
    try:
        fixed = kiwi.space(text)
    except Exception:
        return text
    if fixed == text:
        return text
    # kiwi.space 가 공백 외 문자를 바꿨거나 정렬이 깨지면 보수적으로 미적용
    if text.replace(" ", "") != fixed.replace(" ", ""):
        return text
    kg = _content_gaps(text)
    fg = _content_gaps(fixed)
    if len(kg) != len(fg):
        return text
    parts = text.split(" ")
    # 단일 공백 구분만 처리 (다중·선행·후행 공백이면 미적용)
    if sum(len(p) for p in parts) + (len(parts) - 1) != len(text):
        return text
    out = parts[0]
    for i in range(1, len(parts)):
        left, right = parts[i - 1], parts[i]
        gi = sum(len(p) for p in parts[:i]) - 1   # 이 공백의 content-gap 인덱스
        deletes = 0 <= gi < len(kg) and kg[gi] and not fg[gi]
        if deletes and _gap_is_typo(kiwi, left, right):
            out += right
        else:
            out += " " + right
    return out


def apply_safe(s: str) -> str:
    out = ASCII_PARTICLE.sub(r"\1\2", s)
    out = NUM_UNIT.sub(r"\1\2", out)
    out = CLOSE_PARTICLE.sub(r"\1\2", out)
    out = KO_TERMINAL.sub(r"\1\2", out)
    out = apply_r5(out)
    out = apply_r6(out)
    out = apply_r7(out)
    return out
