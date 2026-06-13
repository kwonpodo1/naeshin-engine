"""
수능특강 Light 영어 PDF에서 본문(영어)과 해석(한글)을 추출하여 정리된 PDF를 생성하는 스크립트.

Usage:
    python scripts/extract_passages.py <input_pdf> [--output <output_pdf>]
"""

import sys
import re
import os
import fitz  # PyMuPDF


# ── 한국어 공백 정리 ─────────────────────────────────────────────────────
# PDF 추출 시 pymupdf 의 단어 분할이 한글 사이 좁은 간격을 단어 경계로 오인해
# "있습니 다", "정보 를", "그 녀는" 같은 인위적 공백이 섞여 들어온다.
# 아래 규칙은 *모호하지 않은* 패턴만 병합한다 — 과/와/만/로/도 처럼 다음 글자와
# 섞일 때 의미가 바뀌는 경우는 추가 제약을 달아 오탐을 피한다.
_KR_PARTICLE_RE = re.compile(
    r'([가-힣]{2,})[ \t]+(을|를|는|의|에서|에게|으로|까지|부터|처럼|마다|조차|마저|보다|에|로|도)'
    r'(?=[\s.,!?;:)\]"\'’”」』]|$)'
)
# "하지 만"·"~지 만" 형태의 역접 접속사만 제한적으로 병합
_KR_MAN_RE = re.compile(r'([가-힣]*지)[ \t]+(만)(?=[\s.,!?]|$)')
# 과/와 — 다음 토큰이 구두점이거나 2글자 이상일 때만 (과학/과목 등 분할 방지)
_KR_AND_RE = re.compile(
    r'([가-힣]{2,})[ \t]+(과|와)(?=[.,!?;:”」』\)\]]|[ \t]+[가-힣]{2}|\s*$)'
)
# 종결어미 "습니 다 / 습니 까"
_KR_END_RE = re.compile(r'([가-힣]*습니)[ \t]+(다|까)(?=[.,!?\s)”』\]]|$)')
# 단일 한글 접두 "그녀/그것/그곳/그들" — PDF 에서 자주 벌어지는 대표 케이스
_KR_GEU_RE = re.compile(r'(?<![가-힣])그[ \t]+(녀|것|곳|들)(?=[가-힣 .,!?]|$)')


def clean_korean_whitespace(text):
    """PDF 추출 시 한글 조사·어미 앞에 끼어든 잘못된 공백을 정리."""
    if not text:
        return text
    prev = None
    while prev != text:
        prev = text
        text = _KR_GEU_RE.sub(r'그\1', text)
        text = _KR_PARTICLE_RE.sub(r'\1\2', text)
        text = _KR_MAN_RE.sub(r'\1\2', text)
        text = _KR_AND_RE.sub(r'\1\2', text)
        text = _KR_END_RE.sub(r'\1\2', text)
    return text


# ── kiwipiepy 기반 한글 wrap-split 병합 ─────────────────────────────────
# clean_korean_whitespace 의 규칙 기반 휴리스틱이 놓치는 일반 wrap-split
# (예: "안타깝 게도", "완벽 한", "집어넣 고") 을 사전 기반 형태소 분석기로 보완.
# pair-only scoring: 두 토큰만 떼어내 붙임/분할 점수를 비교 — 주변 문맥이 들어가면
# `의 생애` 같은 조사 경계에서 FP 가 발생하므로 pair 로 한정해야 한다.
# 임계값 ≥ 5 는 22차 세션 baseline 260건 수작업 검수에서 FP=0 검증된 값.
_KIWI_MERGE_THRESHOLD = 5.0
_KIWI_SPACE_RE = re.compile(r'([가-힣]+)[ \t]+([가-힣]+)')
# 줄바꿈 신호 모드용 — 구분자에 \n 포함. clean_korean_linebreaks 가 \n→공백 전에
# 호출하면, 어절을 음절 단위로 줄바꿈('찾을'→'찾'[줄끝]+'을'[다음줄])해 diff 가 5.0
# 경계 바로 아래(4.9999)인 쌍을, 줄바꿈=어절분리 신호로 보고 낮은 threshold 로 잡는다.
_KIWI_WRAP_RE = re.compile(r'([가-힣]+)[ \t\n]+([가-힣]+)')
_kiwi_instance = None


def _get_kiwi():
    global _kiwi_instance
    if _kiwi_instance is None:
        from kiwipiepy import Kiwi
        _kiwi_instance = Kiwi()
    return _kiwi_instance


def merge_korean_wraps_kiwi(text, audit=None, linebreak_threshold=None):
    """사전 기반 점수 비교로 한글 wrap-split 공백을 제거.

    영문 본문에는 호출하지 않는다 — 호출부에서 한글 필드(translation, topic)에만 적용.

    linebreak_threshold: None 이면 기존 동작(공백 [ \\t] 만 구분자, threshold 5.0).
           float 를 주면 줄바꿈(\\n)도 구분자로 보고, \\n 으로 나뉜 쌍에는 이 낮은
           threshold 를, 같은 줄 공백 쌍에는 5.0 을 적용한다. 모의고사 답지가 어절을
           음절 단위로 줄바꿈('찾을'→'찾'+'을', diff 4.9999)해 5.0 으로 못 잡던 FN 대응.
           clean_korean_linebreaks 처럼 \\n→공백 변환 전에 호출해야 의미가 있다.

    audit: list or None. list 를 넘기면 고려된 모든 pair 에 대해 결정 레코드를 append.
           레코드 키: left, right, merged_score, split_score, diff, merged.
           감사 스크립트(audit_kiwi_merges.py)가 FP/FN 후보 분류에 사용.
    """
    if not text:
        return text
    kiwi = _get_kiwi()
    space_re = _KIWI_WRAP_RE if linebreak_threshold is not None else _KIWI_SPACE_RE
    result = []
    i = 0
    while i < len(text):
        m = space_re.search(text, i)
        if not m:
            result.append(text[i:])
            break
        left, right = m.group(1), m.group(2)
        merged_score = kiwi.analyze(left + right, top_n=1)[0][1]
        split_score = kiwi.analyze(left + ' ' + right, top_n=1)[0][1]
        diff = merged_score - split_score
        # 줄바꿈(\n)으로 나뉜 쌍은 어절 중간 분리 신호가 강함 → 낮은 threshold 적용.
        # m.group(0)(전체 매칭)에 \n 이 있으면 구분자가 줄바꿈이었다는 뜻.
        has_newline = linebreak_threshold is not None and '\n' in m.group(0)
        thr = linebreak_threshold if has_newline else _KIWI_MERGE_THRESHOLD
        merged = diff >= thr
        if audit is not None:
            audit.append({
                'left': left,
                'right': right,
                'merged_score': merged_score,
                'split_score': split_score,
                'diff': diff,
                'merged': merged,
            })
        if merged:
            # left 앞 잔여 emit + 공백 없이 붙인 left+right (병합)
            result.append(text[i:m.start(1)])
            result.append(left + right)
            i = m.end(2)
        else:
            # left + 공백까지만 emit하고 right 시작으로 backtrack — right 가 다음
            # pair 의 left 로 재평가되게 해, 연쇄 공백('A B C')에서 (A,B) 유지 후
            # 가운데 B 를 소비해 (B,C) 를 놓치던 토큰 소비 버그를 막는다.
            result.append(text[i:m.start(2)])
            i = m.start(2)
    return ''.join(result)


# ── 1. PDF에서 텍스트 추출 ──────────────────────────────────────────────

def extract_text_from_pdf(pdf_path):
    """PDF에서 위치 기반으로 텍스트를 추출. 한글+영어+구두점 정확히 재조립.
    Returns (all_lines, para_break_indices) — para_break_indices는 단락 시작 줄 인덱스 set.

    다단 레이아웃 (3모 답지·EBS 정답해설·일부 교과서) 에서 서로 다른 컬럼의
    무관한 텍스트가 같은 Y줄로 병합되는 문제를 피하기 위해 페이지별로
    컬럼 경계를 탐지하여 각 컬럼을 독립 Y그룹핑 후 좌→우 순서로 이어붙인다.
    경계가 감지되지 않으면 (단일 컬럼) 기존 동작과 동일.
    """
    doc = fitz.open(pdf_path)
    all_lines = []
    para_break_indices = set()

    for page in doc:
        words = page.get_text('words')
        if not words:
            continue

        boundaries = _detect_column_boundaries(words, page.rect.width)
        column_groups = _split_words_by_columns(words, boundaries)
        prev_bottom = None

        for col_words in column_groups:
            if not col_words:
                continue
            lines_grouped = _group_into_lines(col_words)
            # 컬럼 전환도 단락 경계로 취급 (컬럼 사이에 가짜 연결 방지)
            if boundaries and all_lines:
                para_break_indices.add(len(all_lines))
            prev_bottom = None  # 컬럼 바뀌면 para-break 기준 리셋

            for line_words in lines_grouped:
                line_top = min(w[1] for w in line_words)
                line_bottom = max(w[3] for w in line_words)
                line_height = line_bottom - line_top

                is_para_break = False
                if prev_bottom is not None:
                    gap = line_top - prev_bottom
                    if line_height > 0 and gap > line_height * 0.8:
                        is_para_break = True

                reconstructed = _reconstruct_line(line_words)
                if reconstructed.strip():
                    if is_para_break:
                        para_break_indices.add(len(all_lines))
                    all_lines.append(reconstructed)
                prev_bottom = line_bottom

    doc.close()
    return all_lines, para_break_indices


def _detect_column_boundaries(words, page_width,
                              min_col_width=120, min_gap=10):
    """x-bitmap 으로 content 가 전혀 없는 수직 띠(백색 gutter) 를 찾아
    컬럼 경계 x좌표 리스트를 반환. 단일 컬럼이면 빈 리스트.

    - min_gap : 경계로 인정할 최소 빈 띠 폭 (px). 단어 사이 정상 공백(~3-5px)
                과 컬럼 gutter 를 구분.
    - min_col_width : 경계 양옆 content 가 이 폭 이상이어야 유효 컬럼으로 인정.
                페이지 가장자리 짧은 헤더 조각이 잘못된 경계를 만드는 것 방지.
    """
    if not words or page_width <= 0:
        return []
    W = int(page_width) + 1
    covered = bytearray(W)
    for w in words:
        x0 = max(0, int(w[0]))
        x1 = min(W - 1, int(w[2]))
        if x1 >= x0:
            for x in range(x0, x1 + 1):
                covered[x] = 1

    gaps = []
    i = 0
    while i < W:
        if covered[i]:
            i += 1
            continue
        j = i
        while j < W and not covered[j]:
            j += 1
        gaps.append((i, j))
        i = j
    if len(gaps) < 2:
        return []

    # 좌/우 margin 식별 (페이지 끝에 붙은 gap)
    left_margin_end = gaps[0][1] if gaps[0][0] == 0 else 0
    right_margin_start = gaps[-1][0] if gaps[-1][1] == W else W

    internal = [
        g for g in gaps
        if g[0] >= left_margin_end and g[1] <= right_margin_start
        and not (g[0] == 0 and g[1] == left_margin_end)
        and not (g[0] == right_margin_start and g[1] == W)
        and (g[1] - g[0]) >= min_gap
    ]
    if not internal:
        return []

    boundaries = [(g[0] + g[1]) / 2 for g in internal]
    edges = [left_margin_end] + boundaries + [right_margin_start]
    filtered = []
    for idx, b in enumerate(boundaries):
        left_w = b - edges[idx]
        right_w = edges[idx + 2] - b
        if left_w >= min_col_width and right_w >= min_col_width:
            filtered.append(b)
    return filtered


def _split_words_by_columns(words, boundaries):
    """각 word 의 x-center 가 어느 컬럼 구간에 속하는지로 분리.
    boundaries 가 비어있으면 단일 컬럼 ([words]) 반환."""
    if not boundaries:
        return [list(words)]
    cols = [[] for _ in range(len(boundaries) + 1)]
    for w in words:
        cx = (w[0] + w[2]) / 2
        col_idx = 0
        for b in boundaries:
            if cx > b:
                col_idx += 1
            else:
                break
        cols[col_idx].append(w)
    return cols


def _group_into_lines(words, y_tolerance=4):
    """단어들을 y좌표 근접도로 그룹화하여 줄 단위로 묶기"""
    if not words:
        return []
    # (x0, y0, x1, y1, text, block_no, line_no, word_no)
    sorted_words = sorted(words, key=lambda w: (w[1], w[0]))

    lines = []
    current_line = [sorted_words[0]]
    current_y = sorted_words[0][1]

    for w in sorted_words[1:]:
        if abs(w[1] - current_y) <= y_tolerance:
            current_line.append(w)
        else:
            lines.append(current_line)
            current_line = [w]
            current_y = w[1]
    if current_line:
        lines.append(current_line)

    return lines


def _is_punct(text):
    return text.strip() in ('.', ',', ';', ':', '!', '?', "'", '"', '…',
                            ')', '(', '[', ']', '{', '}', '-', '—', '·')


def _is_hangul_word(text):
    return any('\uAC00' <= c <= '\uD7A3' for c in text)


# pymupdf 가 숫자+한글단위 ("3" + "년" → "3 년") 같이 한 단어를 두 토큰으로
# 쪼개는 경우를 bbox 기반으로 병합. 정상 단어 경계의 최소 gap 이 약 3.3 px 인
# 반면 intra-word split 은 gap 이 0 이하(대부분 -0.1~-0.05) 로 명확히 분리되어
# 있어 gap <= 1.0 을 보수적 임계값으로 사용. 한글 사이 "없다|고" 같은 ambiguous
# 한글-한글 케이스는 이 범위 밖(gap ~3.33) 이므로 이 규칙으로는 건드리지 않고
# 기존 clean_korean_whitespace 규칙에 맡긴다.
_INTRA_GAP_PX = 1.0

_DIGIT_RE = re.compile(r'^[0-9][0-9,]*$')


def _is_digit_token(text):
    return bool(_DIGIT_RE.match(text))


def _reconstruct_line(line_words):
    """한 줄의 단어들을 x좌표 순서로 정렬하고, 겹치는 구두점을 한글 단어 안에 삽입"""
    if not line_words:
        return ''

    # x0 기준 정렬
    sorted_w = sorted(line_words, key=lambda w: w[0])

    # 1단계: 겹치는 구두점 찾아서 한글 단어에 삽입
    pending = []
    for w in sorted_w:
        x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]
        pending.append((x0, x1, text))

    # 구두점이 다른 단어의 x범위 안에 있는지 확인하고 삽입
    processed = _insert_overlapping_punct(pending)

    # 2단계: 숫자+한글단위 같이 x-gap 이 0 이하인 인접쌍은 공백 없이 병합.
    if not processed:
        return ''
    parts = [processed[0][2]]
    prev_x1 = processed[0][1]
    for x0, x1, text in processed[1:]:
        prev_text = parts[-1]
        gap = x0 - prev_x1
        join_tight = False
        if (gap <= _INTRA_GAP_PX
                and not _is_punct(prev_text) and not _is_punct(text)):
            left_ok = _is_hangul_word(prev_text) or _is_digit_token(prev_text)
            right_ok = _is_hangul_word(text)
            if left_ok and right_ok:
                join_tight = True
        if join_tight:
            parts[-1] = prev_text + text
        else:
            parts.append(text)
        prev_x1 = x1

    return ' '.join(parts)


def _insert_overlapping_punct(words):
    """구두점이 다른 단어의 x범위 안에 겹칠 때, 해당 단어를 동시 분할하여 구두점 삽입.

    예: "방문했습니다사진도구그리고" + ['.', ',', ',']
      → "방문했습니다. 사진, 도구, 그리고"
    """
    long_words = []
    punctuations = []

    for x0, x1, text in words:
        if _is_punct(text) and (x1 - x0) < 10:
            punctuations.append((x0, x1, text))
        else:
            long_words.append([x0, x1, text])

    # 각 긴 단어에 겹치는 구두점들을 한꺼번에 모아서 처리
    punct_assigned = set()
    new_long_words = []

    for lw in long_words:
        wx0, wx1, wtxt = lw
        if not _is_hangul_word(wtxt) or len(wtxt) < 2:
            new_long_words.append(lw)
            continue

        # 이 단어에 겹치는 구두점 수집 (x0 순서)
        overlapping = []
        for pi, (px0, px1, ptxt) in enumerate(punctuations):
            if wx0 < px0 < wx1:
                overlapping.append((pi, px0, ptxt))

        if not overlapping:
            new_long_words.append(lw)
            continue

        overlapping.sort(key=lambda t: t[1])

        # 구두점 위치 → 글자 분할 지점 계산 (경계에 있으므로 +1 보정)
        char_width = (wx1 - wx0) / len(wtxt)
        split_points = []  # (char_idx, punct_text)
        for pi, px0, ptxt in overlapping:
            raw_idx = (px0 - wx0) / char_width
            char_idx = int(raw_idx) + 1  # 구두점은 글자 경계 뒤에 위치
            char_idx = max(1, min(char_idx, len(wtxt)))
            split_points.append((char_idx, ptxt))
            punct_assigned.add(pi)

        # 중복 분할점 제거 (같은 위치면 구두점 합치기)
        merged = {}
        for idx, ptxt in split_points:
            if idx in merged:
                merged[idx] += ptxt
            else:
                merged[idx] = ptxt
        split_points = sorted(merged.items())

        # 텍스트 분할 및 구두점 삽입
        segments = []
        prev = 0
        for idx, ptxt in split_points:
            seg = wtxt[prev:idx]
            if seg:
                segments.append(seg + ptxt)
            prev = idx
        remaining = wtxt[prev:]
        if remaining:
            segments.append(remaining)

        rebuilt = ' '.join(segments)
        new_long_words.append([wx0, wx1, rebuilt])

    result = [(lw[0], lw[1], lw[2]) for lw in new_long_words]

    for pi, p in enumerate(punctuations):
        if pi not in punct_assigned:
            result.append(p)

    result.sort(key=lambda w: w[0])
    return result


# ── 2. 문항 단위로 파싱 ─────────────────────────────────────────────────

def parse_entries(lines, para_break_indices=None):
    """텍스트 라인 목록을 문항 단위로 파싱."""
    if para_break_indices is None:
        para_break_indices = set()

    # 강 이름 매핑: "XX 강 이름" 패턴
    lesson_names = {}
    for line in lines:
        m = re.match(r'^\d{2}\s+강\s+(.+)$', line.strip())
        if m:
            # 이전 줄에서 강 번호 추출
            num_m = re.match(r'^(\d{2})\s+강', line.strip())
            if num_m:
                num = num_m.group(1)
                name = m.group(1).strip()
                if num not in lesson_names and name:
                    lesson_names[num] = name

    # 정규식으로 헤더 라인 매칭: "# 강 01 # 쪽 008 # 번 001 # 문항코드 26662-0001"
    header_re = re.compile(
        r'#\s*강\s+(\d+)\s+#\s*쪽\s+(\d+)\s+#\s*번\s+(\d+)\s+#\s*문항코드\s+(\S+)'
    )

    headers = []  # (line_idx, info_dict)
    for i, line in enumerate(lines):
        m = header_re.search(line)
        if m:
            headers.append((i, {
                '강': m.group(1).zfill(2),
                '쪽': m.group(2),
                '번': m.group(3),
                '코드': m.group(4),
            }))

    entries = []
    for idx, (start, info) in enumerate(headers):
        end = headers[idx + 1][0] if idx + 1 < len(headers) else len(lines)
        local_breaks = {i - start for i in para_break_indices if start <= i < end}
        entries.append({'info': info, 'lines': lines[start:end], 'para_breaks': local_breaks})

    # 장문 세트의 공유 지문 블록을 해당 문항들에 부착.
    # 본문 위치: `# 강 X # 쪽 Y # 번 N1~N2 # 문항코드` (코드 없음) 마커 직후 ~ 다음 코드 헤더 직전.
    # 마커 직후의 N2-N1+1 개 코드 헤더(연속된 같은 강)에만 부착 — 같은 강에 같은 번 범위가
    # 재등장해도 마커별로 대응되는 페어만 매칭된다.
    shared_marker_re = re.compile(
        r'#\s*강\s+(\d+)\s+#\s*쪽\s+\d+\s+#\s*번\s+(\d+)~(\d+)\s+#\s*문항코드\s*$'
    )
    header_starts = [h[0] for h in headers]
    for i, line in enumerate(lines):
        m = shared_marker_re.search(line.strip())
        if not m:
            continue
        lesson = m.group(1).zfill(2)
        n1, n2 = int(m.group(2)), int(m.group(3))
        count = n2 - n1 + 1
        if count < 2:
            continue
        # 다음 코드 헤더까지 블록 범위
        be = len(lines)
        for hs in header_starts:
            if hs > i:
                be = hs
                break
        block_lines = lines[i:be]
        block_breaks = {j - i for j in para_break_indices if i <= j < be}
        # 마커 직후의 `count` 개 연속 헤더 엔트리에만 부착
        start_entry_idx = None
        for ei, (hs, _info) in enumerate(headers):
            if hs >= be:
                start_entry_idx = ei
                break
        if start_entry_idx is None:
            continue
        for k in range(count):
            ei = start_entry_idx + k
            if ei >= len(entries):
                break
            e = entries[ei]
            if e['info']['강'] != lesson:
                break
            try:
                num = int(e['info']['번'])
            except ValueError:
                break
            if not (n1 <= num <= n2):
                break
            e['shared_passage_lines'] = block_lines
            e['shared_para_breaks'] = block_breaks
            e['shared_set_count'] = count

    _precompute_long2_sets(entries)
    return entries, lesson_names


def _precompute_long2_sets(entries):
    """LONG2 세트(공유 지문 1개 + 문항 3개)의 재조립 결과를 한 번 계산해
    세트 내 모든 엔트리에 `long2_precomputed` 로 부착한다.

    REORDER 동반 문항(지시대명사·내용일치)도 같은 재조립 본문/해석을 쓰도록
    하기 위한 전역 공유 단계.
    """
    groups = {}
    for e in entries:
        sl = e.get('shared_passage_lines')
        if sl is None:
            continue
        if e.get('shared_set_count', 0) < 3:
            continue
        groups.setdefault(id(sl), []).append(e)
    for group in groups.values():
        if len(group) < 2:
            continue
        order = None
        for e in group:
            ans = _parse_answer_number(e['lines'])
            if ans is None:
                continue
            choices = _parse_reorder_choices(e['lines'])
            if ans in choices:
                order = choices[ans]
                break
        if order is None:
            continue
        shared_lines = group[0]['shared_passage_lines']
        result = _extract_reorder_long2(group[0], shared_lines, order)
        if result is None:
            continue
        for e in group:
            e['long2_precomputed'] = result


# ── 2.5. 유형 감지 ──────────────────────────────────────────────────────

TYPE_LABELS = (
    'AS_IS', 'REPLACE', 'FILL', 'REMOVE', 'REORDER', 'INSERT',
    'SUMMARY', 'SKIP', 'LONG1', 'LONG2',
)


def _collect_instruction(lines):
    """[ 문제] 마커 뒤에 있는 한글 지시문을 한 덩어리 텍스트로 반환.

    지시문은 보통 1~3줄이며, 선택지(① …)가 시작되면 끝난다.
    지시문 구분이 불확실한 경우에도 최대 5줄까지만 모은다.
    """
    collected = []
    start = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s == '[ 문제]' or s == '[문제]':
            start = i + 1
            break
    if start is None:
        return ''
    for j in range(start, min(start + 6, len(lines))):
        t = lines[j].strip()
        if not t:
            continue
        # 선택지·끝 마커 → 중단
        if t.startswith(('①', '②', '③', '④', '⑤')):
            break
        if t.startswith('[') or t.startswith('{'):
            break
        # 본문이 시작되면 중단 (순수 영문 라인). 단, 한글이 섞인 라인은
        # 안내문/광고 지시문(예: "XXX 에 관한 다음 안내문의 내용과 …")일 수 있으니 포함.
        if is_english_line(t) and not re.search(r'[가-힣]', t):
            break
        collected.append(t)
    return ' '.join(collected)


def _body_slice(lines):
    """지시문과 해설 블록을 제외한 본문 영역 라인들만 반환."""
    body = []
    state = 'header'  # header → instruction → body → answer → translation(skip)
    in_body = False
    for line in lines:
        s = line.strip()
        if s == '[ 문제]' or s == '[문제]':
            state = 'instruction'
            continue
        if s.startswith('[ 정답') or s.startswith('[정답') or s.startswith('[ 해석') or s.startswith('[해석'):
            state = 'after_body'
            in_body = False
            continue
        if state == 'instruction':
            # 지시문이 지나가면 본문이 이어진다.
            # 영어 라인이 처음 나오면 본문 시작으로 본다.
            if is_english_line(s):
                state = 'body'
                in_body = True
            else:
                continue
        if state == 'body' and in_body:
            body.append(s)
    return body


def detect_type(entry):
    """entry dict를 받아 문항 유형 라벨을 반환.

    분류 전용 — 다른 추출 로직에 부수효과를 주지 않는다.
    신호 우선순위: 장문(LONG) → SKIP(도표·실용문) → 지시문 키워드 → 기본 AS_IS.
    """
    lines = entry.get('lines', [])
    if not lines:
        return 'AS_IS'

    instruction = _collect_instruction(lines)
    body_lines = _body_slice(lines)
    body_text = '\n'.join(body_lines)
    full_text = '\n'.join(lines)

    # 본문 내 마커
    has_circled_inline = any(
        any(c in L for c in '①②③④⑤') and len(L.strip()) >= 40
        for L in body_lines
    )
    has_blank = bool(re.search(r'_{3,}', full_text))
    has_down_arrow = '↓' in full_text
    has_abc_blocks = bool(re.search(r'\(\s*A\s*\)', full_text) and re.search(r'\(\s*B\s*\)', full_text) and re.search(r'\(\s*C\s*\)', full_text))
    has_abcd_blocks = has_abc_blocks and bool(re.search(r'\(\s*D\s*\)', full_text))
    has_small_letter_markers = bool(re.search(r'\(\s*a\s*\)', full_text) and re.search(r'\(\s*e\s*\)', full_text))

    ins = instruction

    # 1) 장문 독해
    if '다음 글을 읽고' in ins and '물음에 답하시오' in ins:
        if has_abcd_blocks or '순서로 가장 적절한' in ins or '이어질 내용을 순서' in ins:
            return 'LONG2'
        return 'LONG1'

    # 2) SKIP — 도표·실용문 일반화
    if '도표의 내용' in ins:
        return 'SKIP'
    if '다음 글(안내문)' in ins or '안내문의 내용' in ins or '광고의 내용' in ins:
        return 'SKIP'

    # 3) 지시문 키워드
    # REPLACE
    if '어법상' in ins or ('어법' in ins and ('틀린' in ins or '적절하지 않은' in ins or '적절한' in ins)):
        return 'REPLACE'
    if '낱말의 쓰임' in ins or '문맥에 맞는 낱말' in ins or ('낱말' in ins and '적절' in ins):
        return 'REPLACE'
    if '문맥상 낱말' in ins:
        return 'REPLACE'

    # SUMMARY (FILL보다 먼저 — "빈칸 (A), (B)" 가 겹침)
    if '요약' in ins and ('(A)' in ins or '(B)' in ins or '빈칸' in ins):
        return 'SUMMARY'
    if has_down_arrow and ('빈칸' in ins and ('(A)' in ins or '(B)' in ins)):
        return 'SUMMARY'

    # FILL
    if '빈칸에 들어갈' in ins:
        return 'FILL'

    # REMOVE
    if '전체 흐름과 관계' in ins or '흐름과 무관' in ins or '관계 없는 문장' in ins:
        return 'REMOVE'

    # REORDER
    if '이어질 글의 순서' in ins or '순서에 맞게 배열' in ins or '순서로 가장 적절한' in ins:
        return 'REORDER'

    # INSERT
    if '들어가기에 가장 적절한 곳' in ins or ('주어진 문장' in ins and '적절한' in ins):
        return 'INSERT'

    # AS_IS 키워드
    as_is_patterns = (
        '목적으로 가장 적절한', '목적으로 적절한',
        '심경으로', '심경 변화', '분위기로',
        '요지로', '주장으로',
        '주제로', '제목으로',
        '의미하는 바',
        '내용과 일치하지 않는', '내용과 일치하는',
        '내용으로 일치',
    )
    for kw in as_is_patterns:
        if kw in ins:
            # 실용문·도표 보조 단서: 본문에 번호 선택지 느낌이 없을 때만 AS_IS
            return 'AS_IS'

    # 폴백: 본문 마커로 추정
    if has_circled_inline and ('어법' in full_text or 'grammar' in full_text.lower()):
        return 'REPLACE'
    if has_blank:
        return 'FILL'
    if has_abc_blocks and not has_abcd_blocks:
        return 'REORDER'

    return 'AS_IS'


# ── 3. 본문/해석 추출 ───────────────────────────────────────────────────

def is_english_line(line):
    """라인이 주로 영어인지 판별 (70%이상 ASCII, 4자 이상)"""
    s = line.strip()
    if not s or len(s) < 4:
        return False
    if s in ('.', ',', ';', ':', '—', '-', '...'):
        return False
    return sum(1 for c in s if ord(c) < 128) / len(s) > 0.7


def find_english_passage(lines, para_breaks=None):
    """문항 라인 중 가장 긴 연속 영어 블록(본문)을 찾아 (text, start_idx, end_idx) 반환.
    para_breaks의 줄 인덱스에서만 단락 구분(\n\n)을 삽입한다."""
    if para_breaks is None:
        para_breaks = set()

    blocks = []  # (start_idx, end_idx, [(line_idx, text), ...])
    block_start = None
    block_lines = []

    skip_markers = {'#', 'Page', 'EBS', 'Light', '', '{Structure in Focus}',
                    '{Solution Guide}', 'Structure in Focus', 'Solution Guide'}
    # (A)(B)(C) 순서배열 마커 패턴
    abc_marker_re = re.compile(r'^[\(\[]*[A-C][\)\]]*[\s,]*[\(\[]*[A-C][\)\]]*[\s,]*[\(\[]*[A-C][\)\]]*$')

    for i, line in enumerate(lines):
        s = line.strip()
        if s in skip_markers or abc_marker_re.match(s):
            if block_lines:
                blocks.append((block_start, i, block_lines[:]))
                block_lines = []
                block_start = None
            continue
        if any(c in s for c in '①②③④⑤'):
            # 줄이 짧고 번호로 시작하면 → 선택지 (건너뛰기)
            if len(s) < 40 or re.match(r'^[①②③④⑤]', s):
                if block_lines:
                    blocks.append((block_start, i, block_lines[:]))
                    block_lines = []
                    block_start = None
                continue
            # 긴 영어 문장 안에 마커가 있으면 → 마커 제거 후 포함
            s = re.sub(r'[①②③④⑤]', '', s).strip()
        if s.startswith('*') and ':' in s:
            continue

        if is_english_line(s):
            if block_start is None:
                block_start = i
            block_lines.append((i, s))
        else:
            if block_lines and s in ('.', ',', ';', ':', '—', '-'):
                idx, prev_text = block_lines[-1]
                block_lines[-1] = (idx, prev_text + s)
            elif block_lines:
                blocks.append((block_start, i, block_lines[:]))
                block_lines = []
                block_start = None

    if block_lines:
        blocks.append((block_start, len(lines), block_lines[:]))

    # 2줄 이상 블록 중 가장 긴 것 선택
    long = [b for b in blocks if len(b[2]) >= 2]
    if not long:
        long = blocks
    if not long:
        return '', -1, -1

    best = max(long, key=lambda b: sum(len(t) for _, t in b[2]))

    # 단락 구분이 있는 곳에서만 줄바꿈, 나머지는 공백으로 이어 붙이기
    paragraphs = []
    current_para = []
    for line_idx, text in best[2]:
        if current_para and line_idx in para_breaks:
            paragraphs.append(' '.join(current_para))
            current_para = [text]
        else:
            current_para.append(text)
    if current_para:
        paragraphs.append(' '.join(current_para))

    joined = '\n\n'.join(paragraphs)
    return joined, best[0], best[1]


def clean_passage(text):
    """영어 본문에서 앞에 붙은 서명(이름) 제거"""
    # 패턴: "Name Name To Whom" or "Name Name Dear"
    # 서두 인사말 패턴 찾기
    salutations = [
        r'^[A-Z][a-z]+ [A-Z][a-z]+\s+(To Whom)',
        r'^[A-Z][a-z]+ [A-Z][a-z]+\s+(Dear )',
        r'^[A-Z][a-z]+ [A-Z]\.\s*[A-Z][a-z]+\s+(To Whom)',
        r'^[A-Z][a-z]+ [A-Z]\.\s*[A-Z][a-z]+\s+(Dear )',
    ]
    for pat in salutations:
        m = re.match(pat, text)
        if m:
            text = text[m.start(1):]
            break
    return text


def extract_passage_and_translation(entry):
    """문항 데이터에서 영어 본문과 한글 해석을 추출 (유형별 분기 디스패처).

    `detect_type(entry)` 결과에 따라 유형별 handler 로 라우팅한다.
    장문독해(LONG1) 세트는 공유 지문이 shared_passage_lines 에 부착되므로 별도 분기.
    LONG2 세트(3문항 공유)는 parse_entries 단계에서 재조립 결과를 precompute 하여
    long2_precomputed 에 부착한다 — 해당 경우 모든 동반 문항에 같은 결과를 반환한다.
    """
    if entry.get('long2_precomputed'):
        passage, translation, topic = entry['long2_precomputed']
    elif entry.get('shared_passage_lines') and entry.get('shared_set_count', 2) == 2:
        passage, translation, topic = _extract_long1(entry)
    else:
        entry_type = detect_type(entry)
        handler = _TYPE_HANDLERS.get(entry_type, _extract_as_is)
        passage, translation, topic = handler(entry)
    translation = merge_korean_wraps_kiwi(clean_korean_whitespace(translation))
    topic = merge_korean_wraps_kiwi(clean_korean_whitespace(topic))
    return passage, translation, topic


def _extract_as_is(entry):
    """AS_IS 경로 — 기존 추출 로직. 새 유형 handler 도입 전까지 모든 유형의 pass-through."""
    lines = entry['lines']
    para_breaks = entry.get('para_breaks', set())

    # ── 소재 추출 ──
    topic = ''
    for i, line in enumerate(lines):
        s = line.strip()
        if s in ('소재', '{ 소재}', '{소재}') or '소재}' in s:
            parts = []
            for j in range(i + 1, min(i + 6, len(lines))):
                t = lines[j].strip()
                if not t or '해석' in t:
                    break
                if not is_english_line(t) or len(t) < 30:
                    parts.append(t)
                if sum(len(p) for p in parts) > 50:
                    break
            topic = ' '.join(parts)
            break

    # ── 영어 본문 추출 ──
    passage, eng_start, eng_end = find_english_passage(lines, para_breaks)
    passage = clean_passage(passage)

    # ── 해석 추출 ──
    trans_start = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s in ('해석', '{ 해석}', '{해석}') or '해석}' in s:
            trans_start = i + 1
            break

    translation = ''
    if trans_start is not None:
        trans_end = eng_start if eng_start > trans_start else len(lines)

        for i in range(trans_start, trans_end):
            s = lines[i].strip()
            if s in ('Structure in Focus', 'Solution Guide',
                     '{Structure in Focus}', '{Solution Guide}'):
                trans_end = i
                break

        raw_parts = []
        for i in range(trans_start, trans_end):
            s = lines[i].strip()
            if not s:
                continue
            cleaned = re.sub(r'\s+', ' ', s).strip()
            cleaned = re.sub(r'\s+([.,;:!?)\]])', r'\1', cleaned)
            cleaned = re.sub(r'([(\[])\s+', r'\1', cleaned)
            if cleaned:
                raw_parts.append((i, cleaned))

        # 단락 구분이 있는 곳에서만 줄바꿈
        paragraphs = []
        current_para = []
        for line_idx, text in raw_parts:
            if current_para and line_idx in para_breaks:
                paragraphs.append(' '.join(current_para))
                current_para = [text]
            else:
                current_para.append(text)
        if current_para:
            paragraphs.append(' '.join(current_para))
        translation = '\n\n'.join(paragraphs)

    # 영어 본문 단락 수에 맞춰 해석도 단락 나누기
    translation = _match_paragraph_breaks(passage, translation)

    return passage, translation, topic


# ── REPLACE 유형 handler ───────────────────────────────────────────────
#
# 두 서브타입:
#   1) ①②③④⑤ 밑줄 — 본문 내 단어 앞에 번호 마커. 정답 번호의 단어를 해설
#      {Solution Guide}에 명시된 정답 단어로 교체. 나머지 마커는 제거.
#   2) (A)(B)(C) 네모 — 본문에 `word1 / word2` 슬래시 선택지.
#      선택지 표(예: `③ to digest …… invade …… that`)에서 정답 번호 조합을
#      뽑아 본문에 치환.
# 장문독해 (a)~(e) 서브타입은 지문이 다른 엔트리의 trailing 섹션에 있어
# parse_entries 개편이 필요 — 다음 세션에서 구현. 당분간 AS_IS pass-through.

_SG_VOCAB_RE = re.compile(
    r'\b([A-Za-z][\w\'\-]*)\s*(?:을|를|은|는)\s+([A-Za-z][\w\'\-]*)\s*(?:와|과)?\s*같은\s*낱말로\s*바꾸어야'
)
_SG_GRAM_RE = re.compile(
    r'\b([A-Za-z][\w\'\-]*)\s*(?:을|를|은|는)\s+'
    r'(?:(?:접속사|관계사|관계대명사|관사|대명사|부사|명사|동사|형용사|전치사)\s+)?'
    r'([A-Za-z][\w\'\-]*)\s*(?:으로|로)\s+고쳐야'
)

# Solution Guide가 없거나 파싱 불가한 문항용 수동 override.
# 값: (정답번호 1~5, 틀린단어, 올바른단어)
_REPLACE_OVERRIDE = {
    # 08-001 어법: "make it easier for us ③perceive the imaginary story" — make 구문 목적격 보어
    '26662-0036': (3, 'perceive', 'to perceive'),
    # 09-001 어휘: 지문 전체가 인간의 비합리성을 다룸 → "built-in ⑤rationality" 반대어 필요
    '26662-0041': (5, 'rationality', 'irrationality'),
}


def _parse_answer_number(lines):
    """[ 정답모범답안] 다음 줄의 1~5 정수를 반환. 없으면 None."""
    for i, line in enumerate(lines):
        if '정답모범답안' in line:
            for j in range(i + 1, min(i + 4, len(lines))):
                m = re.match(r'^\s*(\d+)\s*$', lines[j].strip())
                if m:
                    n = int(m.group(1))
                    if 1 <= n <= 5:
                        return n
            break
    return None


def _get_sg_text(lines):
    """{Solution Guide} 블록 본문을 한 덩어리 문자열로 반환."""
    out = []
    in_sg = False
    for line in lines:
        if '{Solution Guide}' in line:
            in_sg = True
            continue
        if in_sg:
            s = line.strip()
            if not s:
                continue
            if s.startswith('{') or s.startswith('['):
                break
            if re.search(r'#\s*강\s+\d+', line):
                break
            out.append(s)
    return ' '.join(out)


def _parse_sg_replacement(sg_text, marker_label):
    """SG에서 (wrong, correct) 추출. 실패 시 None.

    marker_label: 정답 번호의 심볼 ('③' 또는 '(d)').
    marker가 SG에 언급된 위치 이후에 나오는 교체 패턴 중 가장 가까운 것 선택.
    (①②③④⑤ 어법 문항은 정답 번호가 맨 앞에 오고 "X을 Y로 고쳐야"가 바로 뒤에 나옴.
     어휘 문항은 맨 끝 "따라서 ④의 X를 Y와 같은 낱말로..." 패턴.)
    """
    if not sg_text:
        return None

    candidates = []
    for m in _SG_VOCAB_RE.finditer(sg_text):
        candidates.append((m.group(1), m.group(2), m.start()))
    for m in _SG_GRAM_RE.finditer(sg_text):
        candidates.append((m.group(1), m.group(2), m.start()))

    if not candidates:
        return None

    mpos = sg_text.find(marker_label)
    if mpos == -1:
        return candidates[0][:2]

    best = None
    best_dist = 10 ** 9
    for w, c, pos in candidates:
        if pos < mpos:
            continue
        d = pos - mpos
        if d < best_dist and d < 400:
            best = (w, c)
            best_dist = d
    if best:
        return best
    return candidates[0][:2]


def _apply_circled_replacement(lines, answer, wrong, correct):
    """answer번(①②③④⑤) 마커 + wrong 단어를 correct로 교체.

    - 동일 라인에 'target+wrong' 있으면 해당 위치를 correct로 치환.
    - target이 라인 끝에 있고 wrong이 다음 라인 시작에 있으면 분할 케이스 처리.
    - 다른 번호 마커는 그대로 (find_english_passage가 나중에 제거).
    """
    target = '①②③④⑤'[answer - 1]
    out = list(lines)
    pat_same = re.compile(re.escape(target) + r'\s*' + re.escape(wrong) + r'\b')
    pat_end = re.compile(re.escape(target) + r'\s*$')
    pat_word_start = re.compile(r'^\s*' + re.escape(wrong) + r'\b')

    for i, line in enumerate(out):
        m = pat_same.search(line)
        if m:
            out[i] = line[:m.start()] + correct + line[m.end():]
            return out
        if pat_end.search(line) and i + 1 < len(out) and pat_word_start.match(out[i + 1]):
            out[i] = pat_end.sub('', line).rstrip()
            out[i + 1] = re.sub(r'\b' + re.escape(wrong) + r'\b', correct, out[i + 1], count=1)
            return out
    return out


_ABC_OPTION_RE = re.compile(
    r'^([①②③④⑤])\s+(.+?)\s*(?:……|⋯⋯|\.\.\.\.\.\.)\s*(.+?)\s*(?:……|⋯⋯|\.\.\.\.\.\.)\s*(.+?)\s*$'
)


def _parse_abc_table(lines):
    """(A)(B)(C) 선택지 표 파싱 → {번호: (A값, B값, C값)} (전 5개 찾아야 반환)."""
    header_idx = None
    for i, L in enumerate(lines):
        if re.match(r'^\(A\)\s+\(B\)\s+\(C\)\s*$', L.strip()):
            header_idx = i
            break
    if header_idx is None:
        return None
    result = {}
    for j in range(header_idx + 1, min(header_idx + 8, len(lines))):
        m = _ABC_OPTION_RE.match(lines[j].strip())
        if m:
            try:
                num = '①②③④⑤'.index(m.group(1)) + 1
            except ValueError:
                continue
            result[num] = (m.group(2).strip(), m.group(3).strip(), m.group(4).strip())
    return result if len(result) == 5 else None


def _extract_replace_circled(entry):
    lines = entry['lines']
    code = entry['info'].get('코드', '')

    override = _REPLACE_OVERRIDE.get(code)
    if override is not None:
        answer, wrong, correct = override
    else:
        answer = _parse_answer_number(lines)
        if answer is None:
            return _extract_as_is(entry)
        marker = '①②③④⑤'[answer - 1]
        sg_text = _get_sg_text(lines)
        result = _parse_sg_replacement(sg_text, marker)
        if result is None:
            return _extract_as_is(entry)
        wrong, correct = result

    modified_lines = _apply_circled_replacement(lines, answer, wrong, correct)
    modified_entry = dict(entry)
    modified_entry['lines'] = modified_lines
    return _extract_as_is(modified_entry)


def _extract_replace_abc(entry):
    lines = entry['lines']
    answer = _parse_answer_number(lines)
    table = _parse_abc_table(lines)
    if answer is None or table is None or answer not in table:
        return _extract_as_is(entry)

    correct_triplet = table[answer]
    a_opts = {table[n][0] for n in range(1, 6)}
    b_opts = {table[n][1] for n in range(1, 6)}
    c_opts = {table[n][2] for n in range(1, 6)}

    joined = '\u0001'.join(lines)
    for slot, opts, ans_val in (('A', a_opts, correct_triplet[0]),
                                ('B', b_opts, correct_triplet[1]),
                                ('C', c_opts, correct_triplet[2])):
        done = False
        for o1 in opts:
            for o2 in opts:
                if o1 == o2:
                    continue
                pat = re.compile(
                    r'\(\s*' + slot + r'\s*\)[\s\u0001]*'
                    + re.escape(o1) + r'[\s\u0001]*/[\s\u0001]*'
                    + re.escape(o2) + r'(?=[\s\u0001.,;:!?])'
                )
                joined_new, n = pat.subn(ans_val, joined, count=1)
                if n:
                    joined = joined_new
                    done = True
                    break
            if done:
                break

    modified_lines = joined.split('\u0001')
    modified_entry = dict(entry)
    modified_entry['lines'] = modified_lines
    modified_entry['para_breaks'] = set()
    return _extract_as_is(modified_entry)


def _extract_replace(entry):
    """REPLACE dispatcher — 본문 마커 종류로 서브타입 판별.

    - 선두에 `① (a)` 형식 있으면 장문독해 LONG1 (다음 세션). AS_IS 유지.
    - 본문에 `(A)(B)(C) word/word` 슬래시 선택지 있으면 ABC 서브타입.
    - 그 외는 ①②③④⑤ 인라인 밑줄 서브타입.
    """
    lines = entry['lines']
    if any(re.match(r'①\s*\(a\)', L.strip()) for L in lines[:10]):
        return _extract_as_is(entry)
    if _parse_abc_table(lines) is not None:
        joined = '\n'.join(lines)
        if re.search(r'\(\s*A\s*\)[\s\S]{0,40}/[\s\S]{0,40}', joined):
            return _extract_replace_abc(entry)
    return _extract_replace_circled(entry)


# ── LONG1 장문독해 (1지문 2문항) handler ─────────────────────────────
#
# 한 장문 세트는 {제목} + {(a)~(e) 낱말} 2문항이 공유 지문을 쓴다. parse_entries 가
# shared_passage_lines 를 각 entry 에 부착하므로, LONG1 handler 는 그 블록에서
# 본문/해석을 추출한다. (a)~(e) 낱말 문항은 정답 마커 위치의 단어를 correct 로
# 치환 후 모든 (a)~(e) 마커 제거; 해석 내 "지연시킨(→ 완료한)" 같은 힌트 표기도 정리.

# Solution Guide 미제공 문항용 수동 override. 값: (answer_num, wrong, correct)
_LONG1_REPLACE_OVERRIDE = {
    # 15-002 (0078) HANDS: SG 제공 안 됨. 해석의 "배제한다(→ 요구한다)"로 확인.
    '26662-0078': (5, 'excludes', 'requires'),
}


_KOREAN_ARROW_RE = re.compile(r'\S+\s*\(\s*→\s*([^)]+?)\s*\)')
_SMALL_LETTER_MARKER_RE = re.compile(r'\s*\(\s*[a-e]\s*\)\s*')


def _clean_korean_arrows(text):
    """해석 내 `지연시킨(→ 완료한)` 같은 힌트 표기를 정답 단어만 남기도록 치환.
    작은따옴표 `‘ ’` 강조도 제거하고 공백을 정돈한다.
    """
    if not text:
        return text
    text = _KOREAN_ARROW_RE.sub(lambda m: m.group(1).strip(), text)
    text = text.replace('\u2018', '').replace('\u2019', '')
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\s+([.,;:!?)\]])', r'\1', text)
    text = re.sub(r'([(\[])\s+', r'\1', text)
    return text.strip()


def _apply_abe_replacement(lines, answer, wrong, correct):
    """(a)~(e) 밑줄 마커 중 answer번 위치의 wrong 단어를 correct 로 치환.

    같은 라인에 `(x) wrong` 있으면 직접 치환. wrong 이 다음 라인 첫 단어인 분할
    케이스도 처리.
    """
    target = f'({chr(ord("a") + answer - 1)})'
    out = list(lines)
    pat_same = re.compile(re.escape(target) + r'\s+' + re.escape(wrong) + r'\b')
    pat_end = re.compile(re.escape(target) + r'\s*$')
    pat_word_start = re.compile(r'^\s*' + re.escape(wrong) + r'\b')
    for i, line in enumerate(out):
        m = pat_same.search(line)
        if m:
            out[i] = line[:m.start()] + correct + line[m.end():]
            return out
        if pat_end.search(line) and i + 1 < len(out) and pat_word_start.match(out[i + 1]):
            out[i] = pat_end.sub('', line).rstrip()
            out[i + 1] = re.sub(r'\b' + re.escape(wrong) + r'\b', correct, out[i + 1], count=1)
            return out
    return out


def _strip_small_letter_markers(text):
    """본문 내 잔여 (a),(b),(c),(d),(e) 마커 제거."""
    if not text:
        return text
    text = _SMALL_LETTER_MARKER_RE.sub(' ', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)
    return text.strip()


def _extract_long1(entry):
    """LONG1 (장문독해 1지문 2문항) — shared_passage_lines 에서 본문/해석 추출."""
    shared_lines = entry.get('shared_passage_lines') or []
    shared_breaks = entry.get('shared_para_breaks', set())

    instruction = _collect_instruction(entry.get('lines', []))
    is_vocab = ('낱말' in instruction and '쓰임' in instruction)

    working_lines = list(shared_lines)

    if is_vocab:
        code = entry['info'].get('코드', '')
        override = _LONG1_REPLACE_OVERRIDE.get(code)
        if override:
            answer, wrong, correct = override
        else:
            answer = _parse_answer_number(entry.get('lines', []))
            sg_text = _get_sg_text(entry.get('lines', []))
            if answer is not None:
                marker = f'({chr(ord("a") + answer - 1)})'
                repl = _parse_sg_replacement(sg_text, marker)
                if repl is not None:
                    wrong, correct = repl
                else:
                    wrong = correct = None
            else:
                wrong = correct = None
        if wrong and correct:
            working_lines = _apply_abe_replacement(working_lines, answer, wrong, correct)

    pseudo = {
        'info': entry['info'],
        'lines': working_lines,
        'para_breaks': shared_breaks,
    }
    passage, translation, topic = _extract_as_is(pseudo)
    passage = _strip_small_letter_markers(passage)
    translation = _clean_korean_arrows(translation)
    translation = _match_paragraph_breaks(passage, translation)
    return passage, translation, topic


# ── REMOVE 유형 handler ──────────────────────────────────────────────
#
# 본문에 ①②③④⑤ 문장 마커가 인라인으로 박혀 있고, 정답 번호의 문장이
# "전체 흐름과 관계 없는" 문장이다. 해당 문장을 본문에서 제거하고,
# 해석에서는 같은 문장이 `( … .)` 괄호로 표시되어 있으므로 그 괄호 구간을 제거한다.

# `( … )` 중 문장 종결 부호(. ? !)를 포함한 괄호 — 제거 대상 문장.
# 반각 공백 사이 등 여백은 느슨하게 허용. 내부에 중첩 괄호 금지.
_REMOVE_KOR_PAREN_RE = re.compile(r'\(\s*[^()]*?[.?!]\s*\)')


def _remove_circled_sentence(lines, answer):
    """본문에서 answer(1~5)번 ①②③④⑤ 마커로 시작하는 문장 한 덩어리 제거."""
    SEP = '\u0001'
    joined = SEP.join(lines)
    target = '①②③④⑤'[answer - 1]
    mpos = joined.find(target)
    if mpos == -1:
        return lines

    rest = joined[mpos + 1:]
    end_rel = None
    for c in '①②③④⑤':
        p = rest.find(c)
        if p != -1 and (end_rel is None or p < end_rel):
            end_rel = p

    # 줄 시작이 `*` / `[` / `{` 로 시작하면 본문 종료 (각주·해설 블록).
    i = 0
    while i < len(rest):
        if rest[i] == SEP:
            j = i + 1
            while j < len(rest) and rest[j] == ' ':
                j += 1
            if j < len(rest) and rest[j] in '*[{':
                if end_rel is None or i < end_rel:
                    end_rel = i
                break
        i += 1

    if end_rel is None:
        end_rel = len(rest)

    new_joined = joined[:mpos] + joined[mpos + 1 + end_rel:]
    return new_joined.split(SEP)


def _strip_removed_translation(text):
    """해석 내 문장 종결부호를 포함한 `( … .)` 괄호 구간 제거."""
    if not text:
        return text
    text = _REMOVE_KOR_PAREN_RE.sub(' ', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\s+([.,;:!?)\]])', r'\1', text)
    text = re.sub(r'([(\[])\s+', r'\1', text)
    return text.strip()


def _extract_remove(entry):
    answer = _parse_answer_number(entry['lines'])
    if answer is None:
        return _extract_as_is(entry)

    modified_lines = _remove_circled_sentence(entry['lines'], answer)
    modified_entry = dict(entry)
    modified_entry['lines'] = modified_lines
    # 단락 구분 인덱스는 라인 수가 줄어들면 어긋날 수 있으니 재계산 대신 비우고
    # 영어 본문 단락 단위로 _match_paragraph_breaks 가 해석을 다시 나누도록 함.
    modified_entry['para_breaks'] = set()

    passage, translation, topic = _extract_as_is(modified_entry)
    translation = _strip_removed_translation(translation)
    translation = _match_paragraph_breaks(passage, translation)
    return passage, translation, topic


# ── REORDER 유형 handler ───────────────────────────────────────────────
#
# 본문에 `(A)`, `(B)`, `(C)` 블록이 주어진 글 뒤에 이어짐. 선택지 표에서 정답
# 번호의 순서(예: ③=(B)-(C)-(A))를 뽑아 본문 블록을 재배치하고 라벨을 제거.
# 해석은 `{ 해석}`에 이미 정답 순서로 적혀 있어 라벨만 제거하면 됨.
# 장문독해 (A)~(D) 4블록 / shared 본문 형태(16강·22-002·23-026 등)는 별도
# 세션에서 처리 — 현재 handler 는 본문 내 (A)(B)(C)가 모두 있을 때만 동작하고,
# 아니면 AS_IS pass-through 로 baseline 을 보존.

_REORDER_CHOICE_RE = re.compile(
    r'([①②③④⑤])\s*\(\s*([A-D])\s*\)\s*[\u2013\u2014\-]\s*'
    r'\(\s*([A-D])\s*\)\s*[\u2013\u2014\-]\s*\(\s*([A-D])\s*\)'
)


def _parse_reorder_choices(lines):
    """선택지 표에서 {정답번호: (letter1, letter2, letter3)} 반환."""
    result = {}
    for line in lines:
        m = _REORDER_CHOICE_RE.search(line)
        if not m:
            continue
        try:
            num = '①②③④⑤'.index(m.group(1)) + 1
        except ValueError:
            continue
        result[num] = (m.group(2), m.group(3), m.group(4))
    return result


def _reorder_abc_blocks(text, order):
    """text 안의 주어진 글 + (A)(B)(C) 블록을 order 순서로 재배치.

    주어진 글(첫 블록) 다음에 order 에 명시된 순서로 (A)/(B)/(C) 블록을 이어 붙이고
    라벨은 제거. 세 라벨이 모두 발견되지 않으면 None 을 돌려 handler 가 AS_IS 로
    폴백하도록 한다."""
    parts = re.split(r'\s*\(\s*([A-C])\s*\)\s+', text)
    if len(parts) < 7:
        return None
    given = parts[0].strip()
    blocks = {}
    for i in range(1, len(parts) - 1, 2):
        blocks.setdefault(parts[i], parts[i + 1].strip())
    if not all(l in blocks for l in 'ABC'):
        return None
    chunks = [given] + [blocks[l] for l in order]
    return ' '.join(c for c in chunks if c)


def _strip_abc_labels_inline(text):
    """해석·본문에 남은 `(A)`/`(B)`/`(C)` 라벨을 지운다."""
    text = re.sub(r'\(\s*[A-C]\s*\)\s+', '', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r' *\n\n *', '\n\n', text)
    return text.strip()


# ── FILL 유형 handler ─────────────────────────────────────────────────
#
# 본문에 `________` (밑줄 3자 이상) 빈칸 + ①~⑤ 선택지.
# 정답 번호의 선택지 텍스트를 빈칸에 삽입한다. 해석은 이미 정답 단어/구가
# 들어간 상태로 PDF에 인쇄되어 있으므로 손대지 않는다.

_FILL_CHOICE_RE = re.compile(r'^([①②③④⑤])\s*(.+?)\s*$')
_FILL_BLANK_RE = re.compile(r'_{3,}')


def _parse_fill_choices(lines):
    """선택지 라인 `① text` 매칭. 같은 번호가 두 번 이상 나오면 영문(먼저 등장)을 우선."""
    result = {}
    for line in lines:
        s = line.strip()
        m = _FILL_CHOICE_RE.match(s)
        if not m:
            continue
        text = m.group(2).strip()
        if not text:
            continue
        num = '①②③④⑤'.index(m.group(1)) + 1
        if num not in result:
            result[num] = text
    return result


def _extract_fill(entry):
    passage, translation, topic = _extract_as_is(entry)
    answer = _parse_answer_number(entry['lines'])
    if answer is None:
        return passage, translation, topic
    choices = _parse_fill_choices(entry['lines'])
    choice = choices.get(answer)
    if not choice:
        return passage, translation, topic
    new_passage, n = _FILL_BLANK_RE.subn(choice, passage, count=1)
    if n == 0:
        return passage, translation, topic
    return new_passage, translation, topic


_LONG2_ENG_LABEL_RE = re.compile(r'^\(([A-D])\)\s*$')
_LONG2_KOR_LABEL_RE = re.compile(r'^\(([A-D])\)\s+(.*)$')


def _parse_long2_english_blocks(shared_lines):
    """공유 지문에서 `(A)` ~ `(D)` 영어 블록을 라벨별로 분리. 라벨 라인은 standalone.
    `[` 또는 `{` 로 시작하는 라인(해설·Structure 섹션)에서 중단."""
    blocks = {}
    current = None
    buf = []
    for line in shared_lines:
        s = line.strip()
        if not s:
            continue
        m = _LONG2_ENG_LABEL_RE.match(s)
        if m:
            if current is not None:
                blocks.setdefault(current, ' '.join(buf).strip())
            current = m.group(1)
            buf = []
            continue
        if current is None:
            continue
        if s.startswith('[') or s.startswith('{'):
            break
        buf.append(s)
    if current is not None:
        blocks.setdefault(current, ' '.join(buf).strip())
    return blocks


def _parse_long2_korean_blocks(shared_lines):
    """`{ 해석}` 섹션에서 `(A) …` / `(B) …` 등 인라인 라벨 블록 분리."""
    start = None
    for i, line in enumerate(shared_lines):
        s = line.strip()
        if s in ('{ 해석}', '{해석}') or '해석}' in s:
            start = i + 1
            break
    if start is None:
        return {}
    blocks = {}
    current = None
    buf = []
    for i in range(start, len(shared_lines)):
        s = shared_lines[i].strip()
        if not s:
            continue
        # 다음 섹션 (Structure in Focus / Solution Guide / 다음 공유 지문 마커 등) → 중단
        if s in ('{Structure in Focus}', '{Solution Guide}', 'Structure in Focus', 'Solution Guide'):
            break
        if s.startswith('#') and '문항코드' in s:
            break
        m = _LONG2_KOR_LABEL_RE.match(s)
        if m:
            if current is not None:
                blocks.setdefault(current, ' '.join(buf).strip())
            current = m.group(1)
            buf = [m.group(2)]
            continue
        if current is None:
            continue
        buf.append(s)
    if current is not None:
        blocks.setdefault(current, ' '.join(buf).strip())
    return blocks


def _extract_long2_topic(shared_lines):
    for i, line in enumerate(shared_lines):
        s = line.strip()
        if s in ('{ 소재}', '{소재}') or '소재}' in s:
            parts = []
            for j in range(i + 1, min(i + 6, len(shared_lines))):
                t = shared_lines[j].strip()
                if not t or '해석' in t:
                    break
                if not is_english_line(t) or len(t) < 30:
                    parts.append(t)
                if sum(len(p) for p in parts) > 50:
                    break
            return ' '.join(parts)
    return ''


def _extract_reorder_long2(entry, shared_lines, order):
    """LONG2 (공유 지문 기반 순서배열) — 공유 지문의 (A)(B)(C)(D) 블록을 답 순서로 재조립.
    (A) 는 주어진 글로 고정, 뒤에 order(3개 문자) 순서로 나머지를 이어 붙인다.
    (a)~(e) 밑줄 마커(동반 어휘문항용)는 제거한다."""
    topic = _extract_long2_topic(shared_lines)
    eng = _parse_long2_english_blocks(shared_lines)
    kor = _parse_long2_korean_blocks(shared_lines)

    layout = ['A'] + list(order)
    if not all(l in eng for l in layout):
        return None
    eng_parts = [_strip_small_letter_markers(eng[l]) for l in layout]
    passage = '\n\n'.join(p for p in eng_parts if p).strip()

    kor_parts = [kor.get(l, '').strip() for l in layout]
    translation = '\n\n'.join(p for p in kor_parts if p).strip()

    return passage, translation, topic


def _extract_reorder(entry):
    answer = _parse_answer_number(entry['lines'])
    if answer is None:
        return _extract_as_is(entry)
    choices = _parse_reorder_choices(entry['lines'])
    order = choices.get(answer)
    if order is None:
        return _extract_as_is(entry)

    shared_lines = entry.get('shared_passage_lines') or []
    if shared_lines and entry.get('shared_set_count', 0) >= 3:
        result = _extract_reorder_long2(entry, shared_lines, order)
        if result is not None:
            return result
        # 파싱 실패 시 AS_IS 폴백
        return _extract_as_is(entry)

    passage, translation, topic = _extract_as_is(entry)
    reordered = _reorder_abc_blocks(passage, order)
    translation = _strip_abc_labels_inline(translation)
    if reordered is None:
        # 본문에 (A)(B)(C) 가 없는 형태 — AS_IS 로 폴백.
        return passage, translation, topic
    return reordered, translation, topic


# ── INSERT 유형 handler ──────────────────────────────────────────────
#
# 본문 앞에 박스로 주어진 문장이 있고, 본문에 `( ① )` ~ `( ⑤ )` 위치 표시가 있음.
# 정답 번호의 위치에 주어진 문장을 삽입하고 나머지 위치표시는 제거한다.
# 해석은 이미 정답이 반영된 상태로 인쇄되어 있어 AS_IS.

_INSERT_MARKER_RE = re.compile(r'\(\s*([①②③④⑤])\s*\)')
_INSERT_SENT_END_RE = re.compile(r'[.?!][\'")\]]*\s*$')


def _collect_insert_english_lines(lines):
    """`[ 문제]` 이후 첫 연속된 영어 라인 블록 (주어진 문장 + 본문)을 모은다.
    각선 주석(`*`:) 이나 다음 섹션 헤더(`[`) 직전에서 끝난다."""
    result = []
    state = 'header'
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith('*') and ':' in s:
            break
        if state == 'header':
            if '문제' in s and s.startswith('['):
                state = 'instruction'
            continue
        if state == 'instruction':
            if is_english_line(s):
                state = 'body'
                result.append(s)
            # 한글 지시문은 스킵
        elif state == 'body':
            if s.startswith('['):
                break
            if is_english_line(s):
                result.append(s)
            else:
                break
    return result


def _extract_insert(entry):
    passage_asis, translation, topic = _extract_as_is(entry)
    answer = _parse_answer_number(entry['lines'])
    if answer is None:
        return passage_asis, translation, topic

    eng_lines = _collect_insert_english_lines(entry['lines'])
    if len(eng_lines) < 2:
        return passage_asis, translation, topic

    # 주어진 문장: 처음부터 문장 종결(. ? !)이 나올 때까지 누적.
    given_parts = []
    body_start = None
    for i, text in enumerate(eng_lines):
        given_parts.append(text)
        if _INSERT_SENT_END_RE.search(' '.join(given_parts)):
            body_start = i + 1
            break
    if body_start is None or body_start >= len(eng_lines):
        return passage_asis, translation, topic

    given_sentence = ' '.join(given_parts).strip()
    main_body = ' '.join(eng_lines[body_start:])

    target = '①②③④⑤'[answer - 1]

    def _replacer(m):
        return given_sentence if m.group(1) == target else ''

    new_body, n_sub = _INSERT_MARKER_RE.subn(_replacer, main_body)
    if n_sub == 0:
        return passage_asis, translation, topic
    # 빈 자리로 생긴 공백 정돈
    new_body = re.sub(r'\s{2,}', ' ', new_body).strip()
    return new_body, translation, topic


# ── SUMMARY 유형 handler ─────────────────────────────────────────────
#
# 본문 + `↓` 구분자 + 요약문((A)(B) 빈칸 포함) + ①~⑤ `w1 …… w2` 선택지.
# 정답 번호의 (A)(B) 단어쌍을 요약문 빈칸에 채워 본문 뒤에 이어 붙인다.
# 한국어 해석의 `→` 요약문은 이미 정답이 반영되어 있으므로 그대로 두고 `→` 앞에서 단락만 분리.
# 14-004 (0076) 처럼 entry.lines 말미에 다음 15강 LONG1 공유 지문이 딸려 있는 경우가 있어,
# `# 강 ...` 마커 이전까지 잘라낸 뒤 AS_IS 를 돌린다.

_SUMMARY_CHOICE_RE = re.compile(
    r'^([①②③④⑤])\s+(.+?)\s*(?:……|⋯⋯|\.\.\.\.\.\.)\s*(.+?)\s*$'
)
_SUMMARY_AN_RE = re.compile(r'\ba\(n\)\s+(\w)')


def _parse_summary_choices(lines):
    """선택지 `① w1 …… w2` → {번호: (A_word, B_word)}. 영문 줄 우선."""
    result = {}
    for line in lines:
        s = line.strip()
        m = _SUMMARY_CHOICE_RE.match(s)
        if not m:
            continue
        try:
            num = '①②③④⑤'.index(m.group(1)) + 1
        except ValueError:
            continue
        if num not in result:
            result[num] = (m.group(2).strip(), m.group(3).strip())
    return result


def _collect_summary_english_lines(lines):
    """`↓` 다음 요약문 영어 라인 블록을 raw 형태로 모은다.
    (A)(B) 헤더·① 선택지·섹션 시작 라인·비영어 라인에서 종료."""
    start = None
    for i, L in enumerate(lines):
        if L.strip() == '↓':
            start = i + 1
            break
    if start is None:
        return []
    collected = []
    for j in range(start, len(lines)):
        s = lines[j].strip()
        if not s:
            continue
        if re.match(r'^\(\s*A\s*\)\s*\(\s*B\s*\)\s*$', s):
            break
        if s.startswith(('①', '②', '③', '④', '⑤')):
            break
        if s.startswith(('[', '{', '#', '*')):
            break
        if not is_english_line(s):
            break
        collected.append(s)
    return collected


def _fix_an_article(text):
    """`a(n) Word` 표기를 이어지는 단어 첫 글자에 따라 `a Word` / `an Word` 로 정리."""
    def repl(m):
        first = m.group(1)
        article = 'an' if first.lower() in 'aeiou' else 'a'
        return f'{article} {first}'
    return _SUMMARY_AN_RE.sub(repl, text)


def _summary_clip_index(lines):
    """다음 `# 강 ...` 공유 마커 등장 직전 인덱스 반환. 없으면 len(lines)."""
    for i in range(1, len(lines)):
        if re.match(r'#\s*강\s+\d+', lines[i].strip()):
            return i
    return len(lines)


def _extract_summary(entry):
    lines = entry['lines']
    clip = _summary_clip_index(lines)
    clipped = dict(entry)
    clipped['lines'] = lines[:clip]
    clipped['para_breaks'] = {i for i in entry.get('para_breaks', set()) if i < clip}

    passage, translation, topic = _extract_as_is(clipped)

    answer = _parse_answer_number(lines)
    choices = _parse_summary_choices(lines)
    eng_lines = _collect_summary_english_lines(lines)

    if answer is None or answer not in choices or not eng_lines:
        return passage, translation, topic

    a_word, b_word = choices[answer]
    summary = ' '.join(eng_lines)
    summary = re.sub(r'\(\s*A\s*\)', a_word, summary, count=1)
    summary = re.sub(r'\(\s*B\s*\)', b_word, summary, count=1)
    summary = _fix_an_article(summary)
    summary = re.sub(r'\s+([.,;:!?])', r'\1', summary)
    summary = re.sub(r'\s{2,}', ' ', summary).strip()

    new_passage = passage.rstrip() + '\n\n' + summary

    if '→' in translation:
        head, _sep, tail = translation.partition('→')
        head = head.rstrip()
        tail = tail.lstrip()
        if head and tail:
            translation = head + '\n\n→ ' + tail

    return new_passage, translation, topic


# 유형별 handler 라우팅 테이블. 새 유형 전용 handler 가 만들어지면 여기서 교체하기만 하면 된다.
# REPLACE 서브타입(①밑줄·(A)(B)(C) 네모)은 _extract_replace dispatcher 가 분기 처리.
# LONG1 은 extract_passage_and_translation 에서 shared_passage_lines 존재 시 별도 라우팅.
_TYPE_HANDLERS = {label: _extract_as_is for label in TYPE_LABELS}
_TYPE_HANDLERS['REPLACE'] = _extract_replace
_TYPE_HANDLERS['REMOVE'] = _extract_remove
_TYPE_HANDLERS['REORDER'] = _extract_reorder
_TYPE_HANDLERS['FILL'] = _extract_fill
_TYPE_HANDLERS['INSERT'] = _extract_insert
_TYPE_HANDLERS['SUMMARY'] = _extract_summary


def _match_paragraph_breaks(passage, translation):
    """영어 본문의 단락 구조에 맞춰 해석 텍스트도 같은 위치에서 단락 분리.

    1순위: 해석에 이미 추출 단계 bbox(y-gap)에서 온 단락 구분이 있고 그 수가
    영어와 같으면 그대로 신뢰한다 — 레이아웃이 가장 정확한 신호.
    2순위(폴백): 단어 수 비율로 대략적 위치를 잡고, 주변 ±3단어 중
    한국어 조사·어미·구두점 점수가 가장 높은 지점에서 끊는다."""
    eng_paras = [p for p in passage.split('\n\n') if p.strip()]

    if len(eng_paras) <= 1:
        return translation

    kor_paras = [p for p in translation.split('\n\n') if p.strip()]
    if len(kor_paras) == len(eng_paras):
        return translation

    print(f'[para-align] 단락 수 불일치 en={len(eng_paras)} ko={len(kor_paras)} '
          f'→ 단어수 비례 폴백', file=sys.stderr)

    # 기존 단락 구분을 무시하고 영어 구조 기준으로 재분할
    full_text = translation.replace('\n\n', ' ')
    kor_words = full_text.split()
    total_kor = len(kor_words)

    if total_kor < len(eng_paras):
        return translation

    eng_word_counts = [len(p.split()) for p in eng_paras]
    total_eng = sum(eng_word_counts)

    # 각 영어 단락 경계마다 한국어 분할 인덱스 결정
    cumulative = 0
    split_indices = []

    for ewc in eng_word_counts[:-1]:
        cumulative += ewc
        target_idx = cumulative / total_eng * total_kor

        # 목표 ±3단어 범위에서 가장 자연스러운 끊김 찾기
        low = max(0, int(target_idx) - 3)
        high = min(total_kor - 1, int(target_idx) + 3)

        best_idx = round(target_idx)
        best_score = -999

        for c in range(low, high + 1):
            score = _break_score(kor_words[c]) - abs(c - target_idx) * 0.5
            if score > best_score:
                best_score = score
                best_idx = c

        split_indices.append(best_idx + 1)  # 이 단어 '다음'에서 끊기

    # 단락 조립
    new_paras = []
    prev = 0
    for idx in split_indices:
        idx = max(prev + 1, min(idx, total_kor - 1))
        para = ' '.join(kor_words[prev:idx])
        if para.strip():
            new_paras.append(para.strip())
        prev = idx
    remaining = ' '.join(kor_words[prev:])
    if remaining.strip():
        new_paras.append(remaining.strip())

    return '\n\n'.join(new_paras)


def _break_score(word):
    """단어 뒤에서 끊었을 때 자연스러운 정도를 점수로 반환"""
    # 문장 끝 (최우선)
    if re.search(r'[\.\?\!]$', word):
        return 10
    # 인사말·수신자 끝 (편지 형식에서 매우 강력한 끊김)
    if re.search(r'(님께|께|에게)$', word):
        return 8
    # 절 연결 어미+쉼표 (이고, 하고, 되고 등 → 문장 중간이므로 낮은 점수)
    if re.search(r'(이고|하고|되고|하며|되며|인데|으며|면서|라서|해서),?$', word):
        return 1
    # 일반 쉼표
    if word.endswith(','):
        return 5
    # 절 경계 어미·조사 (쉼표 없음)
    if re.search(r'(에서|으로|로서|지만|는데)$', word):
        return 5
    # 주제·주격 조사
    if re.search(r'(는|은|가|이)$', word):
        return 3
    # 목적격 조사
    if re.search(r'(를|을)$', word):
        return 2
    return 0


def reassemble_korean(parts):
    """흩어진 한글+영어+구두점 파트들을 자연스러운 문장으로 재조립"""
    if not parts:
        return ''

    result = parts[0]
    for i in range(1, len(parts)):
        cur = parts[i]

        # 구두점이면 바로 붙이기
        if cur in ('.', ',', ';', ':', '!', '?', ')', ']', '…'):
            result += cur
            continue
        if cur in ('(', '['):
            result += ' ' + cur
            continue

        prev_char = result[-1] if result else ''

        # 이전 끝이 구두점이면 공백 추가
        if prev_char in '.!?':
            result += ' ' + cur
        elif prev_char in ',;:':
            result += ' ' + cur
        # 이전이 한글이고 현재도 한글이면 공백 (문장이 이어지므로)
        elif _is_hangul(prev_char) and cur and _is_hangul(cur[0]):
            result += ' ' + cur
        # 이전이 한글이고 현재가 영어이면 공백
        elif _is_hangul(prev_char) and cur and cur[0].isascii() and cur[0].isalpha():
            result += ' ' + cur
        # 이전이 영어이고 현재가 한글이면 공백
        elif prev_char.isascii() and prev_char.isalpha() and cur and _is_hangul(cur[0]):
            result += ' ' + cur
        # 이전이 영어이고 현재가 영어이면 공백
        elif prev_char.isascii() and cur and cur[0].isascii():
            result += ' ' + cur
        else:
            result += ' ' + cur

    # 최종 정리
    result = re.sub(r'\s+', ' ', result)
    result = re.sub(r'\s+([.,;:!?)\]])', r'\1', result)
    result = re.sub(r'([(\[])\s+', r'\1', result)
    return result.strip()


def _is_hangul(ch):
    return '\uAC00' <= ch <= '\uD7A3' or '\u3131' <= ch <= '\u318E'


# ── 4. PDF 생성 ─────────────────────────────────────────────────────────

def build_extraction_pdf(entries, lesson_names, output_path):
    """추출된 본문과 해석을 PDF로 생성 (1페이지 1지문)"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, PageBreak
    )
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    pdfmetrics.registerFont(TTFont('MalgunGothic', 'C:/Windows/Fonts/malgun.ttf'))
    pdfmetrics.registerFont(TTFont('MalgunGothicBold', 'C:/Windows/Fonts/malgunbd.ttf'))

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'TitleKR', parent=styles['Title'],
        fontName='MalgunGothicBold', fontSize=18, leading=24,
        spaceAfter=6 * mm, textColor=HexColor('#1a237e'),
    )
    header_style = ParagraphStyle(
        'EntryHeader', fontName='MalgunGothicBold', fontSize=13, leading=18,
        spaceBefore=2 * mm, spaceAfter=5 * mm,
        textColor=HexColor('#ffffff'), backColor=HexColor('#1565c0'),
        borderPadding=(6, 12, 6, 12),
    )
    label_eng = ParagraphStyle(
        'LabelEng', fontName='MalgunGothicBold', fontSize=11,
        textColor=HexColor('#1565c0'), spaceBefore=4 * mm, spaceAfter=6 * mm,
    )
    label_kor = ParagraphStyle(
        'LabelKor', fontName='MalgunGothicBold', fontSize=11,
        textColor=HexColor('#2e7d32'), spaceBefore=8 * mm, spaceAfter=6 * mm,
    )
    passage_style = ParagraphStyle(
        'Passage', fontName='MalgunGothic', fontSize=11, leading=19,
        leftIndent=4 * mm, rightIndent=4 * mm, spaceBefore=2 * mm,
        borderWidth=0.5, borderColor=HexColor('#bbdefb'),
        borderPadding=(10, 12, 10, 12), backColor=HexColor('#e3f2fd'),
    )
    trans_style = ParagraphStyle(
        'Translation', fontName='MalgunGothic', fontSize=10.5, leading=18,
        leftIndent=4 * mm, rightIndent=4 * mm, spaceBefore=2 * mm,
        textColor=HexColor('#333333'),
        borderWidth=0.5, borderColor=HexColor('#c8e6c9'),
        borderPadding=(10, 12, 10, 12), backColor=HexColor('#e8f5e9'),
    )

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
    )

    story = []
    story.append(Paragraph('EBS 수능특강 Light 영어 - 본문 및 해석', title_style))
    story.append(Spacer(1, 4 * mm))

    count = 0
    prev_lesson = None

    for entry in entries:
        info = entry['info']
        lesson = info.get('강', '??')

        # SKIP 유형(도표·안내문·광고 등) 제외
        if detect_type(entry) == 'SKIP':
            continue

        passage, translation, topic = extract_passage_and_translation(entry)
        if not passage or len(passage) < 20:
            continue

        count += 1
        번 = info.get('번', '?')
        쪽 = info.get('쪽', '?')
        lesson_name = lesson_names.get(lesson, '')

        # 새 페이지 (첫 번째 제외)
        if count > 1:
            story.append(PageBreak())

        # 헤더
        topic_label = f' - {topic}' if topic else ''
        header = f'{lesson}강 {번}번 (p.{쪽}) {lesson_name}{topic_label}'
        story.append(Paragraph(header, header_style))

        # 본문
        story.append(Paragraph('본문 (English)', label_eng))
        safe = passage.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n\n', '<br/><br/>')
        story.append(Paragraph(safe, passage_style))

        # 해석
        if translation and len(translation) > 10:
            story.append(Paragraph('해석', label_kor))
            safe_t = translation.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n\n', '<br/><br/>')
            story.append(Paragraph(safe_t, trans_style))

    doc.build(story)
    return count


# ── 5. 메인 ─────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_passages.py <input_pdf> [--output <output_pdf>]")
        sys.exit(1)

    input_pdf = sys.argv[1]
    output_pdf = None
    if '--output' in sys.argv:
        idx = sys.argv.index('--output')
        if idx + 1 < len(sys.argv):
            output_pdf = sys.argv[idx + 1]

    if not output_pdf:
        output_pdf = os.path.join('output', '수특라이트영어_본문및해석.pdf')

    os.makedirs(os.path.dirname(output_pdf) or '.', exist_ok=True)

    print(f'[1/3] PDF text extraction... ({input_pdf})')
    lines, para_breaks = extract_text_from_pdf(input_pdf)
    print(f'       -> {len(lines)} lines')

    print(f'[2/3] Parsing entries...')
    entries, lesson_names = parse_entries(lines, para_breaks)
    print(f'       -> {len(entries)} entries, {len(lesson_names)} lessons')

    print(f'[3/3] Building PDF... ({output_pdf})')
    count = build_extraction_pdf(entries, lesson_names, output_pdf)
    print(f'       -> {count} passages included')
    print(f'\n=> Output: {output_pdf}')


if __name__ == '__main__':
    main()
