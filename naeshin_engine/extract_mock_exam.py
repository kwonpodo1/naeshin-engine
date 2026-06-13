"""
평가원·학력평가 모의고사 PDF 파서 (1차 버전)

기능:
  - 원본 PDF → 문제별 {instruction, body, choices}
  - 답지 PDF → 문제별 {answer_number, korean_translation}
  - 두 파일 매칭 → 구조화 데이터

현재 범위:
  - 독해 영역(18~45번)만 처리 (듣기 1~17번은 대상 외)
  - 18~24·26번 "본문 그대로 추출" 유형은 완성
  - 나머지 유형(어법·빈칸·순서·삽입 등)은 지시문·본문 추출까지만 지원

Usage:
    python scripts/extract_mock_exam.py <original_pdf> <answer_pdf>
"""

import sys
import re
import json
from collections import Counter

import fitz


# ── 1. 레이아웃 인식 ────────────────────────────────────────────────────

def _effective_words_for_columns(words, page_width):
    """컬럼 경계 '탐지'를 방해하는 토큰 제외: 전폭 괘선/표(span>50%폭) + 상단
    헤더 밴드(y<160). 경계 좌표 산출용으로만 쓰며, 실제 컬럼 분할은 원본 words로 한다.
    제외 후 아무것도 안 남으면(비정상) 원본으로 폴백."""
    eff = [w for w in words
           if (w[2] - w[0]) <= 0.5 * page_width and w[1] >= 160]
    return eff if eff else words


def detect_column_boundaries(words, page_width, bin_size=4, valley_ratio=0.30,
                             min_gutter=8, min_col_width=90):
    """단어 occupancy(덮는 영역) projection에서 '그 페이지 최대 밀도 대비 현저히
    빈 수직 띠'를 컬럼 gutter로 검출한다. 절대 단어수 임계가 아니라 페이지별
    적응 임계라 가로 2단·세로 3단 등 레이아웃 차이에 robust.

    - 전폭 괘선/상단 헤더는 _effective_words_for_columns 로 경계 탐지에서 제외.
    - gutter = 연속 저밀도(<최대*valley_ratio) 띠 중 폭 >= min_gutter.
    - 양옆 컬럼 폭이 둘 다 min_col_width 이상인 경계만 인정(페이지 가장자리 잡음 차단).
    실제 컬럼 분할(split_words_by_columns)은 원본 words를 쓰므로 여기선 경계 좌표만 낸다.
    """
    if not words:
        return []
    eff = _effective_words_for_columns(words, page_width)
    nb = int(page_width // bin_size) + 2
    cover = [0] * nb
    for w in eff:
        a = max(0, int(w[0] // bin_size))
        b = min(nb - 1, int(w[2] // bin_size))
        for i in range(a, b + 1):
            cover[i] += 1
    mx = max(cover) if cover else 0
    if mx == 0:
        return []
    thr = mx * valley_ratio
    mb = int(60 // bin_size)
    gaps, cur = [], []
    for i in range(mb, nb - mb):
        if cover[i] < thr:
            cur.append(i)
        else:
            if len(cur) * bin_size >= min_gutter:
                gaps.append(cur)
            cur = []
    if len(cur) * bin_size >= min_gutter:
        gaps.append(cur)
    # 경계 = valley 전체의 기하 중점이 아니라 '최소밀도 코어(가장 깊은 골)'의
    # 중심. 한쪽 컬럼 가장자리가 점점 옅어지는 taper가 valley에 섞여도 경계가
    # 그쪽으로 끌려가지 않게 해, 골짜기 근처 stray 토큰이 옆 컬럼으로 새는 것을 막는다.
    bnds = []
    for g in gaps:
        lo = min(cover[i] for i in g)
        core = [i for i in g if cover[i] == lo]
        best, run = [core[0]], [core[0]]
        for i in core[1:]:
            if i == run[-1] + 1:
                run.append(i)
            else:
                if len(run) > len(best):
                    best = run
                run = [i]
        if len(run) > len(best):
            best = run
        bnds.append((min(best) + max(best)) / 2 * bin_size)
    edges = [60] + bnds + [page_width - 60]
    out = []
    for j, b in enumerate(bnds):
        if (b - edges[j]) >= min_col_width and (edges[j + 2] - b) >= min_col_width:
            out.append(round(b, 1))
    return out


def split_words_by_columns(words, boundaries):
    """words를 컬럼별로 분리. boundaries 비면 [words] 단일 컬럼."""
    if not boundaries:
        return [list(words)]
    cols = [[] for _ in range(len(boundaries) + 1)]
    for w in words:
        cx = (w[0] + w[2]) / 2
        idx = 0
        for b in boundaries:
            if cx > b:
                idx += 1
            else:
                break
        cols[idx].append(w)
    return cols


def group_words_to_lines(words, y_tol=4):
    """y좌표 근접으로 words를 한 line으로 묶기."""
    if not words:
        return []
    sw = sorted(words, key=lambda w: (w[1], w[0]))
    lines = [[sw[0]]]
    for w in sw[1:]:
        if abs(w[1] - lines[-1][-1][1]) <= y_tol:
            lines[-1].append(w)
        else:
            lines.append([w])
    return lines


# PyMuPDF가 한글 글자 사이 미세 간격을 단어 경계로 토큰화("있습니" "다")하는
# 것을 되돌리는 병합 임계값(px). extract_passages._INTRA_GAP_PX와 같은 근거
# (TEMP_measure_gaps 분포 측정)로 결정. 측정 결과: 모의고사·EBS 해설 PDF 모두
# 한글-한글 인접쌍의 진짜 띄어쓰기 gap이 -0.72px까지 내려가고(EBS 표지·머리글
# 폰트), 실제 "있습니|다" 글자-사이-오인 분포는 측정 코퍼스에서 관측되지 않음.
# 안전한 더 낮은 임계값이 없으므로 1.0px 유지(extract_passages와 동일) — 과병합은
# 누락보다 나쁘다(kiwi 2차 방어가 분리를 못 되돌림).
_INTRA_GAP_PX = 1.0

_DIGIT_TOKEN_RE = re.compile(r'^[0-9][0-9,]*$')


def _is_hangul_token(text):
    return any('가' <= c <= '힣' for c in text)


def line_to_text(line_words):
    """x순 정렬 후 공백 join. 단, 한글(또는 숫자)+한글 토큰 사이 gap이
    _INTRA_GAP_PX 이하면 글자-사이 오인 토큰화로 보고 공백 없이 병합."""
    sw = sorted(line_words, key=lambda w: w[0])
    if not sw:
        return ''
    parts = [sw[0][4]]
    prev_x1 = sw[0][2]
    for w in sw[1:]:
        text = w[4]
        gap = w[0] - prev_x1
        prev = parts[-1]
        if (gap <= _INTRA_GAP_PX and _is_hangul_token(text)
                and (_is_hangul_token(prev) or _DIGIT_TOKEN_RE.match(prev))):
            parts[-1] = prev + text
        else:
            parts.append(text)
        prev_x1 = w[2]
    return ' '.join(parts).strip()


def extract_layout_aware_lines(pdf_path):
    """PDF → 컬럼 분리된 줄 리스트. 페이지마다 자동 경계 탐지."""
    doc = fitz.open(pdf_path)
    all_lines = []
    for page in doc:
        words = page.get_text('words')
        if not words:
            continue
        boundaries = detect_column_boundaries(words, page.rect.width)
        columns = split_words_by_columns(words, boundaries)
        for col in columns:
            for line in group_words_to_lines(col):
                text = line_to_text(line)
                if text:
                    all_lines.append(text)
    doc.close()
    return all_lines


# ── 2. 원본 PDF 파서 ──────────────────────────────────────────────────

Q_PATTERN = re.compile(r'^(\d{1,2})\.(\s+|$)')
CHOICE_PATTERN = re.compile(r'^[①②③④⑤]')
# 원본 PDF의 공통 지시문 줄 (뒤에 지시문 텍스트 필수): "[36 ~ 37] 다음 ..."
# 물결표는 반각(~), 전각(～), 유니코드 wave dash(〜) 모두 흡수 — 회차마다 다름
GROUP_INSTRUCTION_PATTERN = re.compile(r'^\[(\d+)\s*[~～〜]\s*(\d+)\]\s*(.+)')
# 답지 PDF는 "[41 ~ 42]" 단독 줄로 나옴 — 뒤 텍스트 불요
GROUP_HEADER_PATTERN = re.compile(r'^\[(\d+)\s*[~～〜]\s*(\d+)\]\s*$')


# 본문 안에 ①~⑤ 마커가 있는 유형 (별도 선택지 라인 없음)
# 지시문에 이 키워드 중 하나가 있으면 CHOICE_PATTERN 분리를 비활성화
INLINE_MARKER_INSTR_KEYWORDS = ('어법상', '낱말의 쓰임', '전체 흐름과 관계 없는')

# 페이지번호 등 노이즈 줄 (한 자리 또는 두 자리 숫자만 있는 줄)
PAGE_NUMBER_PATTERN = re.compile(r'^\d{1,2}$')


def parse_original(pdf_path, range_start=18, range_end=45):
    """원본 PDF → 문제별 dict. range_start~range_end만 대상."""
    lines = extract_layout_aware_lines(pdf_path)

    # 각 문제 번호의 줄 인덱스 수집
    question_starts = {}
    for i, line in enumerate(lines):
        m = Q_PATTERN.match(line)
        if m:
            n = int(m.group(1))
            if range_start <= n <= range_end and n not in question_starts:
                question_starts[n] = i

    # 그룹 지시문 수집 + 그룹 본문 영역 식별
    # [36~37], [38~39]는 각 문제별로 개별 본문이 있음
    # [41~42], [43~45]는 그룹 헤더 아래에 공통 본문 (장문독해)
    group_instructions = {}  # {문제번호: 공통지시문}
    group_header_positions = []  # [(idx, g_start, g_end), ...]
    group_header_indices = []   # 모든 그룹 헤더 줄 인덱스 (블록 끊기용)
    for i, line in enumerate(lines):
        m = GROUP_INSTRUCTION_PATTERN.match(line)
        if m:
            g_start, g_end = int(m.group(1)), int(m.group(2))
            # 다음 줄까지 합쳐야 하는 경우(줄 바꿈)
            instr = m.group(3).strip()
            # 다음 줄이 문제 번호로 시작하지 않고 짧으면 이어붙임
            if i + 1 < len(lines):
                nxt = lines[i + 1]
                if not Q_PATTERN.match(nxt) and not CHOICE_PATTERN.match(nxt):
                    instr += ' ' + nxt.strip()
            for n in range(g_start, g_end + 1):
                group_instructions[n] = instr
            group_header_positions.append((i, g_start, g_end))
            group_header_indices.append(i)

    # 장문독해(공통 본문) 그룹 본문 추출 — 그룹의 첫 번째 문제 전까지의 영역
    # 그룹 헤더 바로 다음부터 (지시문이 2줄로 이어진 경우 그 다음) g_start번 문제 시작 전까지
    shared_bodies = {}  # {문제번호: shared body 텍스트}
    for g_idx, g_start, g_end in group_header_positions:
        body_begin = g_idx + 1
        # 지시문이 다음 줄로 이어진 경우 한 줄 skip
        if body_begin < len(lines):
            nxt = lines[body_begin]
            if (not Q_PATTERN.match(nxt) and not CHOICE_PATTERN.match(nxt)
                    and not GROUP_INSTRUCTION_PATTERN.match(nxt)
                    and len(nxt) < 50 and ('오.' in nxt or '?' in nxt)):
                body_begin += 1
        body_end = question_starts.get(g_start, body_begin)
        body_block = lines[body_begin:body_end]
        # 본문의 각주(* …) 와 페이지번호 노이즈 제거
        body_block = [ln for ln in body_block
                      if not ln.lstrip().startswith('*')
                      and not PAGE_NUMBER_PATTERN.match(ln.strip())]
        shared_body = '\n'.join(body_block).strip()
        # 짧으면(그룹 헤더 직후 바로 문제 — [36~37] 같은 개별 본문 그룹) 공유 안 함
        if len(shared_body) >= 200:
            for n in range(g_start, g_end + 1):
                shared_bodies[n] = shared_body

    # 각 문제의 본문 블록 자르기
    sorted_nums = sorted(question_starts.keys())
    results = {}
    for idx, n in enumerate(sorted_nums):
        start = question_starts[n]
        end = question_starts[sorted_nums[idx + 1]] if idx + 1 < len(sorted_nums) else len(lines)
        # 그룹 헤더가 (start, end) 사이에 있으면 그 직전까지로 끊기
        # → [31~34] 가 30번 끝에 누수되는 것 방지, [41~42] 가 40번 끝에 누수되는 것도 방지
        for gi in group_header_indices:
            if start < gi < end:
                end = gi
                break
        block = lines[start:end]
        if not block:
            continue

        # 개별 지시문 (본인 줄 뒤에 문장이 이어지면 합침)
        first_line = block[0]
        individual_instr = Q_PATTERN.sub('', first_line).strip()

        # 그룹 지시문이 있는 문제는 항상 그룹 지시문을 instruction으로 사용
        # (예: 31번 첫 줄 "31. Research shows that..." 의 본문 부분은 본문 첫 줄로 살림)
        if n in group_instructions:
            instruction = group_instructions[n]
            # first_line 의 본문 잔여가 있으면 본문 시작으로 살리기 ("36." 같이 비면 skip)
            if individual_instr:
                block_for_body = [individual_instr] + list(block[1:])
            else:
                block_for_body = list(block[1:])
        elif not individual_instr:
            instruction = ''
            block_for_body = list(block[1:])
        else:
            instruction = individual_instr
            # 지시문이 다음 줄로 이어진 경우 (예: "21. 밑줄 친 ... 의미하는 바로" + "가장 적절한 것은? [3점]")
            if len(block) > 1:
                nxt = block[1].strip()
                if nxt and not CHOICE_PATTERN.match(nxt) and \
                   not re.match(r'^(Dear|To|[A-Z])', nxt) and \
                   len(nxt) < 60 and ('?' in nxt or '.' in nxt[-3:] or '오.' in nxt):
                    instruction = instruction + ' ' + nxt
                    block_for_body = list(block[2:])
                else:
                    block_for_body = list(block[1:])
            else:
                block_for_body = []

        # 본문 안에 ①~⑤ 마커가 있는 유형은 CHOICE_PATTERN 분리를 하지 않음
        # (본문 자체가 선택지 역할 → 별도 선택지 라인 없음)
        is_inline_marker_type = any(kw in instruction for kw in INLINE_MARKER_INSTR_KEYWORDS)

        if is_inline_marker_type:
            body_lines = block_for_body
            choice_lines = []
        else:
            choice_indices = [i for i, line in enumerate(block_for_body)
                              if CHOICE_PATTERN.match(line)]
            if choice_indices:
                body_lines = block_for_body[:choice_indices[0]]
                choice_lines = block_for_body[choice_indices[0]:]
            else:
                body_lines = block_for_body
                choice_lines = []

        # 본문에서 각주(* …) 와 페이지번호 노이즈 제거
        body_lines = [ln for ln in body_lines
                      if not ln.lstrip().startswith('*')
                      and not PAGE_NUMBER_PATTERN.match(ln.strip())]

        own_body = '\n'.join(body_lines).strip()
        # 장문독해 그룹의 문제는 그룹 본문을 우선 사용 (개별 본문은 선택지뿐이므로)
        if n in shared_bodies:
            final_body = shared_bodies[n]
        else:
            final_body = own_body

        results[n] = {
            'instruction': instruction,
            'body': final_body,
            'choices': '\n'.join(choice_lines).strip(),
        }

    return results


# ── 3. 답지 PDF 파서 ──────────────────────────────────────────────────

# 해설 헤더: "30. [출제의도] ..." (시도교육청 학력평가) 또는 "1. [출제 의도] ..." (평가원 모의평가)
# 두 가지 모두 흡수하기 위해 [출제\s*의도]
ANSWER_HEADING = re.compile(r'^(\d{1,2})\.\s*\[출제\s*의도\]')
# 한 줄에 "번호 기호 번호 기호 ..." 형태의 정답표
# 시도교육청: "1 ① 2 ③" / 평가원 모의평가: "01. ④ 02. ①"
ANSWER_PAIR = re.compile(r'(\d{1,2})\.?\s+([①②③④⑤])')


def is_vocab_line(line):
    """단어풀이 줄 판정. 본문 해석과 구분."""
    line = line.strip()
    if not line or len(line) > 45:
        return False
    # 영어 알파벳이나 ~ 로 시작 (~ 는 관용구 표현)
    if not re.match(r'^[a-zA-Z~]', line):
        return False
    # 문장 구두점이 있으면 본문. 단어풀이는 구두점 거의 없음.
    if any(p in line for p in ',.!?"'):
        return False
    # 한글 포함 필수
    if not re.search(r'[가-힣]', line):
        return False
    return True


# 평가원 모의평가 답지의 명시적 섹션 라벨 (시도교육청에는 보통 없음)
_EXPLICIT_SECTION_RE = re.compile(r'^\[(해석|풀이|Words and Phrases|어휘|Solution)\]\s*$')
# [해석] 라벨 뒤에 해석 첫 줄이 같은 줄에 붙는 경우(도표 문항 등): "[해석] 위 도표는 …"
# 단독 "[해석]" 도 group(1)='' 로 매치하므로 기존 동작과 호환.
_HAESEOK_INLINE = re.compile(r'^\[해석\]\s*(.*)$')

# 해석 블록 종료 신호 — 어휘/풀이 섹션 라벨(인라인 허용) 또는 다음 장문 그룹 헤더.
# 기존 _EXPLICIT_SECTION_RE 는 단독 라인(예 '[어휘]')만 잡아서, 시도교육청 답지의
# '[어구] pulse 박자 ...' 인라인 어휘 라벨과 '[41~42]' 그룹 헤더 뒤에 오는 다음 장문
# 지문 해석이 한 문제의 korean_translation 에 누수됐다(6월 고2 40번 → 41~42 석유 지문
# 혼입). '어구'(시도교육청)·'어휘'(평가원) 모두 라벨 뒤 텍스트가 붙는 형태까지 흡수.
_TRANSLATION_CUTOFF_RE = re.compile(
    r'^\[(풀이|Words\s*(?:and|&)\s*Phrases|어휘|어구|Solution|Vocabulary)\]'
)


def _is_translation_cutoff(line):
    """해석 종료 신호 여부 — 어휘/풀이 섹션 라벨(인라인 허용) 또는 [X~Y] 그룹 헤더."""
    s = line.strip()
    return bool(_TRANSLATION_CUTOFF_RE.match(s) or GROUP_HEADER_PATTERN.match(s))


def _split_translation_vocab(block):
    """block에서 한국어 해석과 vocab 섹션을 분리. 해석 lines 리스트 반환.

    두 가지 모드:
    1. 명시적 섹션 라벨이 있는 경우(평가원 모의평가): [해석] ~ 다음 [...] 직전까지만 채택
    2. 라벨이 없는 경우(시도교육청 학력평가): 기존 vocab 휴리스틱
    """
    # 페이지번호 노이즈 라인(단독 1~2자리 숫자) 사전 제거
    # → "...연구와 전\n4\n이 가능한 기술..." 같은 본문 사이 누수 방지
    block = [ln for ln in block if not PAGE_NUMBER_PATTERN.match(ln.strip())]

    # 모드 1: 명시적 [해석] 섹션이 있으면 그 안만 추출 ([해석] 인라인 첫 줄 포함)
    interp_start = None
    interp_inline = ''
    next_section = None
    for j, ln in enumerate(block):
        s = ln.strip()
        if interp_start is None:
            mh = _HAESEOK_INLINE.match(s)
            if mh:
                interp_start = j + 1
                interp_inline = mh.group(1).strip()
            continue
        # [해석] 이후 다른 섹션([풀이]/[Words and Phrases]/[어휘]/[어구]…)이나
        # 다음 장문 그룹 헤더([X~Y]) 시작 = 해석 끝
        if _is_translation_cutoff(s):
            next_section = j
            break
    if interp_start is not None:
        end = next_section if next_section is not None else len(block)
        out = block[interp_start:end]
        if interp_inline:
            out = [interp_inline] + out
        return out

    # 모드 2: 명시적 [해석] 없음 → vocab 휴리스틱.
    # 단, [풀이]/[Words and Phrases]/[어구] 등 섹션 라벨(인라인 포함)이나 다음 장문
    # 그룹 헤더([X~Y])를 만나면 거기서 해석 종료(다음 지문 해석 누수 차단).
    translation_lines = []
    for j, ln in enumerate(block):
        if _is_translation_cutoff(ln):
            return translation_lines
        if is_vocab_line(ln):
            if j + 1 < len(block) and is_vocab_line(block[j + 1]):
                return translation_lines
            if j == len(block) - 1:
                return translation_lines
        translation_lines.append(ln)
    return translation_lines


def _extract_solution_section(block):
    """block 안 [풀이] 섹션 텍스트 추출 (다음 [...] 또는 끝까지). 평가원 답지 전용.
    시도교육청 학력평가에는 [풀이] 라벨이 없으므로 빈 문자열 반환.
    """
    block = [ln for ln in block if not PAGE_NUMBER_PATTERN.match(ln.strip())]
    sol_start = None
    next_section = None
    for j, ln in enumerate(block):
        m = _EXPLICIT_SECTION_RE.match(ln.strip())
        if m:
            label = m.group(1)
            if label == '풀이' and sol_start is None:
                sol_start = j + 1
            elif sol_start is not None:
                next_section = j
                break
    if sol_start is None:
        return ''
    end = next_section if next_section is not None else len(block)
    return '\n'.join(block[sol_start:end]).strip()


def parse_answer_sheet(pdf_path, range_start=18, range_end=45):
    """답지 PDF → 문제별 {answer_number, korean_translation}."""
    lines = extract_layout_aware_lines(pdf_path)

    # "해 설" 전까지의 영역에서 정답표 수집
    answer_map = {}
    for i, line in enumerate(lines):
        if line.strip() == '해 설':
            break
        for m in ANSWER_PAIR.finditer(line):
            n = int(m.group(1))
            if 1 <= n <= 45 and n not in answer_map:
                answer_map[n] = m.group(2)

    # 각 문제 해설 블록 찾기
    heading_positions = {}
    for i, line in enumerate(lines):
        m = ANSWER_HEADING.match(line)
        if m:
            n = int(m.group(1))
            if range_start <= n <= range_end and n not in heading_positions:
                heading_positions[n] = i

    # 그룹 헤더 [X ~ Y] 위치 — 장문독해 답지에서 공통 해석이 그룹 헤더 아래 있음
    # 답지는 단독 줄(GROUP_HEADER_PATTERN)로 나오지만, 안전하게 둘 다 수용
    group_header_positions = []  # [(idx, g_start, g_end)]
    for i, line in enumerate(lines):
        m = GROUP_HEADER_PATTERN.match(line) or GROUP_INSTRUCTION_PATTERN.match(line)
        if m:
            g_start, g_end = int(m.group(1)), int(m.group(2))
            group_header_positions.append((i, g_start, g_end))

    # 장문독해 그룹의 공통 해석 블록 = 그룹 헤더 다음 ~ 그룹의 첫 문제 heading 전
    shared_translations = {}  # {문제번호: 해석}
    for g_idx, g_start, g_end in group_header_positions:
        block_start = g_idx + 1
        first_q_heading = heading_positions.get(g_start, len(lines))
        if first_q_heading <= block_start:
            continue
        block = lines[block_start:first_q_heading]
        translation_lines = _split_translation_vocab(block)
        shared_trans = '\n'.join(translation_lines).strip()
        # 짧으면 개별 본문이 있는 그룹 ([36~37] 등) — 공유 해석 아님
        if len(shared_trans) >= 200:
            for n in range(g_start, g_end + 1):
                shared_translations[n] = shared_trans

    sorted_nums = sorted(heading_positions.keys())
    results = {}
    for idx, n in enumerate(sorted_nums):
        start = heading_positions[n]
        end = heading_positions[sorted_nums[idx + 1]] if idx + 1 < len(sorted_nums) else len(lines)
        block = lines[start + 1:end]  # heading 제외

        # 장문독해 그룹 문제는 shared_translations 우선 사용
        if n in shared_translations:
            trans = shared_translations[n]
        else:
            translation_lines = _split_translation_vocab(block)
            trans = '\n'.join(translation_lines).strip()

        # 평가원 답지의 [풀이] 섹션도 별도로 보관 — 정답 단어 교체 fallback 에 사용
        # 시도교육청 학력평가에는 빈 문자열
        solution = _extract_solution_section(block)

        results[n] = {
            'answer_number': answer_map.get(n, ''),
            'korean_translation': trans,
            'solution': solution,
        }

    return results


# ── 4. 매칭 & 산출 ────────────────────────────────────────────────────

# "본문 그대로 추출" 유형 (정답 반영 불필요)
EASY_TYPES = {18, 19, 20, 21, 22, 23, 24, 26}


def merge(original_data, answer_data):
    out = {}
    for n in sorted(original_data.keys()):
        out[n] = {
            **original_data[n],
            **answer_data.get(n, {}),
            'is_easy_type': n in EASY_TYPES,
        }
    return out


# ── 5. 메인 ────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print('Usage: python scripts/extract_mock_exam.py <original_pdf> <answer_pdf>')
        sys.exit(1)

    original_pdf, answer_pdf = sys.argv[1], sys.argv[2]

    print(f'[1/3] 원본 파싱... ({original_pdf})')
    original_data = parse_original(original_pdf)
    print(f'       -> {len(original_data)}개 문제')

    print(f'[2/3] 답지 파싱... ({answer_pdf})')
    answer_data = parse_answer_sheet(answer_pdf)
    print(f'       -> {len(answer_data)}개 해설, 정답표 {sum(1 for v in answer_data.values() if v["answer_number"])}개')

    print('[3/3] 매칭 & 출력...')
    merged = merge(original_data, answer_data)

    # JSON으로 저장 (검토용)
    out_path = 'output/mock_exam_extracted.json'
    import os
    os.makedirs('output', exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f'       -> {out_path}')

    # 쉬운 유형 요약 프린트
    print()
    print('=== 쉬운 유형(18~24, 26번) 샘플 ===')
    for n in sorted(EASY_TYPES):
        if n not in merged:
            continue
        d = merged[n]
        print(f'\n--- {n}번 (정답: {d.get("answer_number", "?")}) ---')
        print(f'지시문: {d["instruction"]}')
        body_preview = d['body'][:150].replace('\n', ' ')
        print(f'영어 본문 (앞 150자): {body_preview}...')
        kr_preview = d.get('korean_translation', '')[:150].replace('\n', ' ')
        print(f'한국어 해석 (앞 150자): {kr_preview}...')


if __name__ == '__main__':
    main()
