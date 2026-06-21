"""ko 공백 오타 판정의 형태소 게이트 — 체커·수정기 공유 단일 원천 (auto·studio 공유 패키지).

단일 소스: naeshin_engine/ko_spacing_core.py — auto(scripts shim)·studio 가 이 모듈을 가져다 쓴다.

'kiwi.space() 가 제거하려는 공백'이 진짜 어절중간 오타인지(보조용언/완결어절 경계가 아닌지)
판정한다. 체커는 이 판정으로 extra_space 오탐(본용언+보조용언 띄어쓰기)을 억제하고, 수정기는
같은 판정으로 자동수정 대상을 고른다 → 두 도구의 기준이 절대 어긋나지 않는다.
"""
from __future__ import annotations

try:
    from kiwipiepy import Kiwi
except ImportError:
    Kiwi = None

# 좌측 어절이 이미 완결됐음을 뜻하는 어미/조사 태그. 좌측이 이 태그로 끝나면 별개 어절.
_CLOSED_TAGS = {
    "EP", "EF", "EC", "ETN", "ETM",                                  # 어미
    "JKS", "JKC", "JKG", "JKO", "JKB", "JKV", "JKQ", "JX", "JC",      # 조사
}

_kiwi = None


def get_kiwi():
    """프로세스 단위 Kiwi 싱글턴. kiwipiepy 미설치 시 None."""
    global _kiwi
    if Kiwi is None:
        return None
    if _kiwi is None:
        _kiwi = Kiwi()
    return _kiwi


def content_gaps(s: str) -> list[bool]:
    """content 문자 k 와 k+1 사이 공백 유무 리스트. 길이 = content_len - 1."""
    res: list[bool] = []
    pending = started = False
    for c in s:
        if c == " ":
            if started:
                pending = True
        else:
            if started:
                res.append(pending)
            started = True
            pending = False
    return res


def gap_is_typo(kiwi, left: str, right: str) -> bool:
    """좌우 어절 결합이 '어절 중간 오타 복원'인지 형태소로 판정."""
    if not left or not right:
        return False
    try:
        joined_tok = kiwi.tokenize(left + right)
        left_tok = kiwi.tokenize(left)
    except Exception:
        return False
    if any(t.tag == "VX" for t in joined_tok):   # 보조용언 결합 = false positive
        return False
    if not left_tok or left_tok[-1].tag in _CLOSED_TAGS:  # 좌측이 완결된 어절 = 별개
        return False
    return True


def extra_space_genuine_count(ko: str, fixed: str | None = None) -> int:
    """kiwi.space 가 ko 에서 '제거'하려는 갭 중, 형태소상 진짜 어절중간 오타인 갭 수.

    extra_space 케이스에서 이 값이 0 이면 제거 제안이 전부 보조용언/완결어절 경계 = kiwi 오탐.
    `fixed` 를 주면 kiwi.space 재호출을 생략한다(체커가 이미 계산한 결과 재사용).
    """
    kiwi = get_kiwi()
    if kiwi is None or not ko:
        return 0
    if fixed is None:
        try:
            fixed = kiwi.space(ko)
        except Exception:
            return 0
    if fixed == ko or ko.replace(" ", "") != fixed.replace(" ", ""):
        return 0
    parts = ko.split(" ")
    # 단일 공백 구분만 처리 (다중·선행·후행 공백이면 0).
    if sum(len(p) for p in parts) + (len(parts) - 1) != len(ko):
        return 0
    kg = content_gaps(ko)
    fg = content_gaps(fixed)
    if len(kg) != len(fg):
        return 0
    n = 0
    for i in range(1, len(parts)):
        left, right = parts[i - 1], parts[i]
        gi = sum(len(p) for p in parts[:i]) - 1   # 이 공백의 content-gap 인덱스
        if 0 <= gi < len(kg) and kg[gi] and not fg[gi] and gap_is_typo(kiwi, left, right):
            n += 1
    return n


def missing_space_is_style(ko: str, fixed: str | None = None) -> bool:
    """kiwi 가 공백 '추가'를 제안한 자리가 전부 보조용언(VX) 경계면 naeshin 붙여쓰기 스타일 → 억제.

    보여주다→보여 주다, 해주다→해 주다, 물어보다→물어 보다 류(본용언+보조용언 붙여쓰기 허용).
    한자어+하·복합명사·진짜 어절 경계는 보수적으로 유지(억제 안 함) — extra_space 게이트의 대칭.
    """
    kiwi = get_kiwi()
    if kiwi is None or not ko:
        return False
    if fixed is None:
        try:
            fixed = kiwi.space(ko)
        except Exception:
            return False
    if fixed == ko or ko.replace(" ", "") != fixed.replace(" ", ""):
        return False
    if fixed.count(" ") <= ko.count(" "):   # missing_space(공백 추가)만 대상
        return False
    content = ko.replace(" ", "")
    try:
        toks = kiwi.tokenize(content)
    except Exception:
        return False
    vx_starts = {t.start for t in toks if t.tag == "VX"}   # 보조용언 시작 위치(content 인덱스)
    kg = content_gaps(ko)
    fg = content_gaps(fixed)
    if len(kg) != len(fg):
        return False
    added = [gi for gi in range(len(kg)) if not kg[gi] and fg[gi]]
    if not added:
        return False
    # 추가하려는 공백이 '전부' 보조용언 경계여야 스타일로 간주(하나라도 아니면 유지).
    return all((gi + 1) in vx_starts for gi in added)
