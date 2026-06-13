"""
EBS 수능특강 영어 PDF 파서 (Phase C — 1차 버전, 1강 검증 스코프)

기능:
  - 본책 PDF → 목차 기반 강별 페이지 범위 → Gateway + Exercises 01~04
    × {instruction, body, choices, vocab, footnote}
  - 해설집 PDF → layout-aware 라인 → 강번호/섹션 라벨 기반 블록 분리
    → {answer, sozae, korean_translation, solution_guide, structure_in_focus}
  - 강번호 매칭 → 강 단위 구조화 JSON

현재 범위 (세션 52):
  - 유형편 20개 강(01~20) 중 1강(글의 목적 파악) 매칭 통과 목표
  - 2~20강은 동일 패턴으로 자동 동작 예상 — 다음 세션에서 일반화·검증

재사용:
  - scripts/extract_mock_exam.py 의 layout-aware 엔진 (extract_layout_aware_lines)

Usage:
    python -X utf8 scripts/extract_ebs.py <textbook_pdf> <solution_pdf> [--lesson 1]
"""

import sys
import os
import re
import json
import argparse

import fitz

# extract_mock_exam 의 layout-aware 엔진 재사용 (패키지 내부 import)
from naeshin_engine.extract_mock_exam import extract_layout_aware_lines


# ── 1. 본책 파서 ──────────────────────────────────────────────────────

# 목차 한 줄 패턴
TOC_LESSON_NUM = re.compile(r'^(\d{2})$')
TOC_PAGE_NUM = re.compile(r'^(\d{1,3})$')

# 본책 문항 ID (예: 26005-0001)
EBS_QID_LINE = re.compile(r'^\s*(26005-\d{4})\s*$')

# 블록 분할 전에 통째로 건너뛸 섹션들
# - Solving Strategies: Gateway 다음 페이지 (유형편 전용 해설)
# - Academic Vocabulary by Topic: 주제·소재편 Gateway 다음 페이지 (단어 학습)
SKIPPABLE_SECTION_STARTS = [
    re.compile(r'^\s*Solving\s+Strategies\s*$'),
    re.compile(r'^\s*Academic\s+Vocabulary\s+by\s+Topic\s*$'),
]

# Exercises 섹션 시작 마커 (skip 종료 조건)
XERCISES_MARKER = re.compile(r'^\s*xercises\s*$')


def strip_skippable_sections(lines):
    """Solving Strategies / Academic Vocabulary by Topic 섹션을
    xercises 라인 또는 qid 마커 직전까지 제거.

    두 섹션 모두 qid 마커가 없는 해설·단어학습 페이지로, Exercise 01 블록 앞에
    누수되어 지시문 탐색을 방해한다. 블록 분할 전에 통째로 걷어낸다.
    """
    out = []
    skipping = False
    for ln in lines:
        s = ln.strip()
        if any(p.match(s) for p in SKIPPABLE_SECTION_STARTS):
            skipping = True
            continue
        if skipping:
            if XERCISES_MARKER.match(s) or EBS_QID_LINE.match(ln):
                skipping = False
                out.append(ln)
                continue
            continue
        out.append(ln)
    return out


# 지시문 시작 키워드 (문제 지시문만 인식, Solving Strategies 결론문 배제)
INSTRUCTION_START = re.compile(
    r'^\s*(다음\s+글|다음은|다음\s+빈칸|밑줄\s+친|윗글|주어진\s+글'
    r'|다음\s+문장|다음\s+도표|다음\s+표|다음\s+안내문|다음에)'
)

# 결론문 접두사 (지시문 fallback 에서 배제)
CONCLUSION_PREFIX = re.compile(r'^\s*(따라서|그러므로|즉|그래서|결론적으로)')

# 장문독해 그룹 지시문: "01~02 다음 글을 읽고, 물음에 답하시오."
GROUP_INSTRUCTION = re.compile(r'^\s*\d{2}\s*[~～〜]\s*\d{2}\s+(다음\s+글.+)')

# 장문독해 문제별 지시문: "41. 윗글의 제목으로 가장 적절한 것은?"
# (장문독해 Gateway/Ex 블록에서 본문 끝을 잡는 anchor)
PROBLEM_QUESTION = re.compile(
    r'^\d{1,2}\.\s*(윗글|밑줄|빈칸|문맥상|다음\s+글|다음\s+빈칸)'
)


# 본책 노이즈 — 페이지 꼬리말 / 로고 / 헤더
TB_NOISE = [
    re.compile(r'^\s*$'),
    re.compile(r'^\s*\d+\s+20\d+학년도\s+EBS\s+수능특강\s+영어\s*$'),   # "10 2027학년도 EBS 수능특강 영어"
    re.compile(r'^\s*\d{1,3}\s*$'),                                  # 페이지번호 단독
    re.compile(r'^\s*(ateway|xercises|Solving\s+Strategies|Words\s*&\s*Phrases\s+in\s+Use|Solution\s+Guide|Structure\s+in\s+Focus|Academic\s+Vocabulary\s+by\s+Topic)\s*$'),
    re.compile(r'^\s*[GE]\s*$'),                                     # 깨진 G/E 로고
    re.compile(r'^\s*(유형편|주제ㆍ소재편|주제·소재편)\s*$'),
    re.compile(r'^\s*I{1,3}\s*$'),                                   # I, II, III
    re.compile(r'^\s*%?\d+%?\s*$'),                                  # %68 등
    re.compile(r'^\s*\[20\d+학년도[^\]]+\]\s*$'),                     # [2026학년도 수능 18번]
    re.compile(r'^\s*20\d+학년도\s+.+번\s*$'),                        # "2026학년도 6월 모의평가 34번" (주제·소재편은 대괄호 없음)
    re.compile(r'^\s*정답과\s*해설\s*\d+쪽?\s*$'),                    # "정답과 해설 2쪽"
    re.compile(r'^\s*C\s*o\s*n\s*t\s*e\s*n\s*t\s*s\s*$'),
    re.compile(r'^\s*\d+\s*[•·ㆍ]\s*.+\s+\d+\s*$'),                  # "01•글의 목적 파악 11" 페이지 헤더
]


def parse_toc(doc, toc_pages=(3, 4, 5)):
    """본책 p.4~6 목차에서 {lesson_num: (start_page, title)} 추출.

    유형편(01~20강)은 p.4~5, 주제·소재편(21~30강)은 p.6에 목차.
    줄 단위로 (강번호 2자리 / 제목 / 시작페이지) 3줄 패턴.
    """
    toc_text_parts = []
    for p in toc_pages:
        if p < len(doc):
            toc_text_parts.append(doc[p].get_text())
    toc_text = '\n'.join(toc_text_parts)
    lines = [ln.strip() for ln in toc_text.split('\n') if ln.strip()]

    result = {}
    i = 0
    while i + 2 < len(lines):
        lesson_m = TOC_LESSON_NUM.match(lines[i])
        if lesson_m:
            lesson_num = int(lesson_m.group(1))
            title = lines[i + 1]
            page_m = TOC_PAGE_NUM.match(lines[i + 2])
            if (1 <= lesson_num <= 30
                    and page_m
                    and not re.match(r'^\d', title)):
                start_page = int(page_m.group(1))
                if 5 <= start_page <= 250:
                    result[lesson_num] = (start_page, title)
                    i += 3
                    continue
        i += 1

    return result


def compute_lesson_page_ranges(toc, total_pages):
    """각 강의 (start_page, end_page) 계산. end_page = 다음 강 시작 - 1.

    마지막 강의 end_page는 문서 끝 또는 주제·소재편 시작 전 — MVP는 다음 강 기준만.
    """
    sorted_nums = sorted(toc.keys())
    ranges = {}
    for i, num in enumerate(sorted_nums):
        start = toc[num][0]
        if i + 1 < len(sorted_nums):
            end = toc[sorted_nums[i + 1]][0] - 1
        elif 21 <= num <= 30:
            # 주제·소재편 마지막 강(30강) — 강당 4p 고정 (130, 134, 138, ...)
            # 테스트편(III) 이 뒤에 이어지므로 total_pages 로 잡으면 누수됨.
            end = min(start + 3, total_pages)
        else:
            end = total_pages
        ranges[num] = (start, end)
    return ranges


def split_by_qid(lines):
    """lines 를 26005-XXXX 마커로 문제 블록 분할.

    각 qid 줄은 문제 블록의 끝에 위치. 블록 = (이전 qid 줄 +1) ~ (현재 qid 줄 -1).
    qid 줄 자체는 블록에서 제외.
    """
    qid_positions = []
    for i, ln in enumerate(lines):
        m = EBS_QID_LINE.match(ln)
        if m:
            qid_positions.append((i, m.group(1)))

    blocks = []
    last = 0
    for idx, qid in qid_positions:
        blocks.append({'qid': qid, 'lines': lines[last:idx]})
        last = idx + 1
    return blocks


def parse_textbook_problem(lines, lesson_title):
    """한 문제 블록 lines 에서 {instruction, body, choices, vocab, footnote} 분리."""
    title_noise = re.compile(r'^\s*' + re.escape(lesson_title) + r'\s*$')

    cleaned = []
    for ln in lines:
        if any(p.match(ln) for p in TB_NOISE):
            continue
        if title_noise.match(ln):
            continue
        s = ln.strip()
        if s:
            cleaned.append(s)

    # 1) 지시문 검출 (3단계)
    #    1-a) 장문독해 그룹 지시문: "01~02 다음 글을 읽고, 물음에 답하시오."
    #         → body = 그룹 지시문 다음 ~ 첫 문제별 지시문("41. 윗글의 ...") 직전
    #    1-b) 일반 엄격 매치: INSTRUCTION_START 키워드로 시작하는 첫 줄
    #    1-c) fallback: 한국어 + `?` 로 끝나는 첫 줄 (결론문 배제)
    instruction = ''
    body_start = 0
    body_end_override = None
    found = False

    # 1-a) 장문독해 그룹 지시문
    for i, ln in enumerate(cleaned):
        gm = GROUP_INSTRUCTION.match(ln)
        if gm:
            instruction = gm.group(1).strip()
            body_start = i + 1
            for j in range(body_start, len(cleaned)):
                if PROBLEM_QUESTION.match(cleaned[j]):
                    body_end_override = j
                    break
            found = True
            break

    # 1-b) 일반 지시문
    if not found:
        for i, ln in enumerate(cleaned):
            if not INSTRUCTION_START.match(ln):
                continue
            if (not ln.rstrip().endswith('?')
                    and i + 1 < len(cleaned)
                    and '적절한' in cleaned[i + 1]):
                instruction = ln + ' ' + cleaned[i + 1]
                body_start = i + 2
            else:
                instruction = ln
                body_start = i + 1
            found = True
            break

    # 1-c) fallback
    if not found:
        for i, ln in enumerate(cleaned):
            if (re.search(r'[가-힣]', ln)
                    and ln.rstrip().endswith('?')
                    and not CONCLUSION_PREFIX.match(ln)):
                instruction = ln
                body_start = i + 1
                break

    # 2) 본문 이후 마커 위치 찾기
    choice_start = body_end_override
    vocab_start = None
    footnote_start = None
    for i in range(body_start, len(cleaned)):
        ln = cleaned[i]
        if choice_start is None and re.match(r'^[①②③④⑤]', ln):
            choice_start = i
        if vocab_start is None and ln.startswith('□'):
            vocab_start = i
        # 각주: "* word: 설명" — 단 별표가 영문자 뒤에 바로 붙는 형태
        if footnote_start is None and re.match(r'^\*\s*[A-Za-z]', ln) and ':' in ln:
            footnote_start = i

    # 3) 본문 끝 = choice / vocab / footnote 중 가장 이른 것
    ends = [x for x in [choice_start, vocab_start, footnote_start] if x is not None]
    body_end = min(ends) if ends else len(cleaned)
    body = '\n'.join(cleaned[body_start:body_end]).strip()

    # 4) 선택지 = choice_start ~ vocab_start (혹은 끝)
    choices = ''
    if choice_start is not None:
        c_end = len(cleaned)
        if vocab_start is not None and vocab_start > choice_start:
            c_end = min(c_end, vocab_start)
        choices = '\n'.join(cleaned[choice_start:c_end]).strip()

    # 5) 단어풀이
    vocab = '\n'.join(cleaned[vocab_start:]).strip() if vocab_start is not None else ''

    # 6) 각주
    footnote = ''
    if footnote_start is not None:
        f_end = len(cleaned)
        if choice_start is not None and choice_start > footnote_start:
            f_end = min(f_end, choice_start)
        footnote = '\n'.join(cleaned[footnote_start:f_end]).strip()

    return {
        'instruction': instruction,
        'body': body,
        'choices': choices,
        'vocab': vocab,
        'footnote': footnote,
    }


def parse_textbook(pdf_path, target_lessons=None):
    """본책 PDF → {lesson_num: {title, page_range, gateway, exercises}}."""
    doc = fitz.open(pdf_path)
    toc = parse_toc(doc)
    ranges = compute_lesson_page_ranges(toc, len(doc))

    if target_lessons is None:
        target_lessons = sorted(toc.keys())

    result = {}
    for n in target_lessons:
        if n not in toc:
            continue
        start_p, end_p = ranges[n]
        title = toc[n][1]

        # 해당 강의 모든 페이지 텍스트 수집 (페이지별 단순 get_text)
        all_lines = []
        for p in range(start_p - 1, end_p):  # 0-indexed
            page_text = doc[p].get_text()
            all_lines.extend(page_text.split('\n'))

        # Solving Strategies / Academic Vocabulary 섹션 통째 제거
        # (Exercise 01 블록 앞에 누수되어 지시문 탐색을 방해하는 것 방지)
        all_lines = strip_skippable_sections(all_lines)

        # qid 마커로 블록 분할
        blocks = split_by_qid(all_lines)

        # 각 블록 파싱
        problems = []
        for b in blocks:
            parsed = parse_textbook_problem(b['lines'], title)
            parsed['qid'] = b['qid']
            problems.append(parsed)

        result[n] = {
            'title': title,
            'page_range': [start_p, end_p],
            'gateway': problems[0] if problems else None,
            'exercises': problems[1:],
        }

    doc.close()
    return result


# ── 2. 해설집 파서 ────────────────────────────────────────────────────

# 강 표지 헤더: "01 글의 목적 파악" — title 은 한글로 시작 + ASCII space 1개만 허용
# Unicode em-space(\u2003/\u2004)는 배제 — 해설 본문의 "02\u2004드레스…" 같은
# solution guide 문제번호 라벨이 LESSON_HEADER 로 오매칭되는 것 방지.
LESSON_HEADER = re.compile(r'^(\d{2}) ([가-힣].*)$')

# LESSON_HEADER 에 매치되지만 실제로는 파트 표지 (노이즈). title 로 나오면 reject.
LESSON_TITLE_BLACKLIST = {'유형편', '주제·소재편', '주제ㆍ소재편', '테스트편'}

# Gateway 정답 요약 (단일): "G ateway ②" — layout 얽힘(앞뒤 토큰 누수) 허용
#   예: "두 번 G ateway ②"  / "G ateway ② 유형편"
#   `.match()` 호출이라 prefix `.*?` 로 시작 위치 임의 매치 시뮬레이션
GATEWAY_ANSWER_SUMMARY = re.compile(r'.*?G\s*ateway\s+([①②③④⑤])(?:\s|$)')

# Gateway 정답 요약 (멀티, 장문독해): "G ateway 01 ② 02 ⑤"
GATEWAY_ANSWER_MULTI = re.compile(r'.*?G\s*ateway\s+(\d{2}\s*[①②③④⑤].+)$')

# Exercises 정답 요약: "E xercises 01 ③ 02 ⑤ 03 ① 04 ②"
EX_ANSWER_SUMMARY = re.compile(r'^E\s*xercises\s+\d{2}\s*[①②③④⑤]')

# 정답표 이어지는 줄 (EX_ANSWER_SUMMARY 또는 GATEWAY_ANSWER_MULTI 다음 줄):
# "06 ② 07 ② 08 ⑤" 또는 "11 ⑤ 12 ⑤"
ANS_CONTINUATION = re.compile(r'^\d{2}\s*[①②③④⑤]')

# Gateway 본문 위치: "ateway 본문 10쪽"
GATEWAY_BODY_START = re.compile(r'^ateway\s+본문\s+(\d+)쪽\s*$')

# Exercises 본문 위치: "E 본문 12~15쪽"
EXERCISES_BODY_START = re.compile(r'^E\s+본문\s+(\d+)\s*[~～〜]\s*(\d+)쪽\s*$')

# 섹션 라벨 — 뒤에 페이지 헤더 꼬리("유형편"/"주제·소재편") 붙는 경우 허용
#   예: "정답 ② 유형편"
ANS_LABEL = re.compile(r'^정답\s*([①②③④⑤])(?:\s+.+)?\s*$')
# 장문독해 멀티답: "정답 01 ② 02 ⑤" 또는 "정답 01 ② 02 ⑤ 03 ⑤"
ANS_LABEL_MULTI = re.compile(r'^정답\s+(\d{2}\s*[①②③④⑤].+)$')
SOZAE_LABEL = re.compile(r'^소재\s+(.+)$')
HAESEOK_LABEL = re.compile(r'^해석\s+(.+)$')
SOL_GUIDE_LABEL = re.compile(r'^Solution\s+Guide\s*$')
STRUCT_LABEL = re.compile(r'^Structure\s+in\s+Focus\s*$')

# Exercise 번호 (단독 또는 뒤꼬리 포함).
# layout-aware 파싱이 페이지 헤더나 다른 컬럼 텍스트를 같은 줄에 붙일 수 있으므로
# `\d{2}` 뒤 뭐든 허용. 단 is_known_ex_number 로 번호 유효성 검증하므로 안전.
# 예: "03" / "03 유형편" / "03 deliberately situated"
EX_NUM_LINE = re.compile(r'^(\d{2})(?:\s+.+)?\s*$')

# 테스트편 진입 마커 "TEST 본문 172~193쪽" — 이후는 강 귀속 해제
TEST_SECTION_MARKER = re.compile(r'^TEST\s+본문\s+\d+')

# 해설집 노이즈
SOL_NOISE = [
    re.compile(r'^\s*$'),
    re.compile(r'^\s*Part\s*$'),
    re.compile(r'^\s*Part\s+I+\s+.+\s*$'),              # "Part I 유형편"
    re.compile(r'^\s*I{1,2}\s*$'),
    re.compile(r'^\s*[GE]\s*$'),                        # G, E 단독 로고
    re.compile(r'^\s*유형편\s*$'),
    re.compile(r'^\s*주제·소재편\s*$'),
    re.compile(r'^\s*주제ㆍ소재편\s*$'),
    re.compile(r'^\s*정답과\s*해설\s*\d*\s*$'),           # "정답과 해설 3"
    re.compile(r'^\s*\d+\s+20\d+학년도\s+EBS\s+수능특강\s+영어\s*$'),
    re.compile(r'^\s*영\s*어\s*$'),                      # 해설집 표지 상단
    re.compile(r'^\s*영어영역\s*$'),
]

# 본문 줄 끝/중간에 끼어든 페이지 머리말 토큰 (단독 줄은 위 SOL_NOISE 가 처리).
# 레이아웃 그룹핑이 우측 상단 머리말을 본문 줄과 같은 Y로 묶어 "…직원과 고 유형편"
# 처럼 트레일링되거나 "Solution Guide 유형편" 처럼 라벨 뒤에 붙어 라벨 매칭을 깨뜨림.
_PAGE_HEADER_INLINE = re.compile(r'\s*(?:유형편|주제[ㆍ·]소재편)\s*')

# Culture Note 박스(페이지 하단 문화 각주) 시작 — 본문 해석이 아니므로 누적 중단 신호.
_CULTURE_NOTE = re.compile(r'^Culture\s*Note\b')


def parse_answer_pairs(text):
    """텍스트에서 (번호, 원형숫자) 페어 추출. 정답표 파싱 공용."""
    pairs = re.findall(r'(\d{2})\s*([①②③④⑤])', text)
    return {k: v for k, v in pairs}


def _make_problem(kind, **extra):
    """빈 Exercise / Gateway 객체 기본 템플릿."""
    p = {
        'kind': kind,
        'answer': '',
        'sozae': '',
        'korean_translation': '',
        'solution_guide': '',
        'structure_in_focus': '',
    }
    p.update(extra)
    return p


def parse_solution(pdf_path, target_lessons=None):
    """해설집 PDF → {lesson_num: {title, gateway_answer, exercises_answers, gateway, exercises}}

    상태 머신 주요 변수:
      current_lesson / current_section ('gw'|'ex') / current_problem
      current_shared : 여러 Exercise 가 같은 본문·해설을 공유할 때 쓰는 리스트
                       (장문독해 "정답 01 ⑤ 02 ④" 같은 멀티답 라인 처리용)
      current_field  : 'korean_translation' / 'solution_guide' / 'structure_in_focus'
    """
    raw_lines = extract_layout_aware_lines(pdf_path)

    # 노이즈 필터
    lines = []
    for ln in raw_lines:
        if any(p.match(ln) for p in SOL_NOISE):
            continue
        lines.append(ln)

    result = {}
    current_lesson = None
    current_section = None
    current_problem = None
    current_shared = []      # 본문/해석을 공유하는 Exercise 리스트 (단일이면 [current_problem])
    current_field = None
    field_buffer = []

    def flush():
        """field_buffer 를 current_shared 의 모든 Exercise 에 복사."""
        nonlocal field_buffer
        if not field_buffer or current_field is None:
            field_buffer = []
            return
        targets = current_shared if current_shared else (
            [current_problem] if current_problem else []
        )
        joined = '\n'.join(field_buffer)
        # 본문 줄에 끼어든 페이지 머리말(유형편/주제·소재편) 제거 — 필드 텍스트에만
        # 적용하므로 라인스트림의 강·문항 경계 탐지에는 영향이 없다.
        joined = _PAGE_HEADER_INLINE.sub(' ', joined)
        joined = re.sub(r'[ \t]{2,}', ' ', joined).strip()
        for tgt in targets:
            existing = tgt.get(current_field, '')
            if existing:
                tgt[current_field] = (existing + '\n' + joined).strip()
            else:
                tgt[current_field] = joined
        field_buffer = []

    def is_known_ex_number(lesson_num, ex_no):
        """exercises_answers 에 있는 번호인지 — EX_NUM 오매칭 방지."""
        answers = result.get(lesson_num, {}).get('exercises_answers', {})
        return ex_no in answers

    i = 0
    while i < len(lines):
        ln = lines[i].strip()

        # 테스트편 진입 — 30강 이후 테스트편 해설이 마지막 강에 누수되는 것 차단
        if TEST_SECTION_MARKER.match(ln):
            flush()
            current_field = None
            current_problem = None
            current_shared = []
            current_section = None
            current_lesson = None
            i += 1
            continue

        # 강 표지 헤더 — "01 글의 목적 파악" (title 한글 시작 + 블랙리스트 제외)
        m = LESSON_HEADER.match(ln)
        if m and 1 <= int(m.group(1)) <= 30:
            title_raw = m.group(2).strip()
            is_real_header = (
                title_raw not in LESSON_TITLE_BLACKLIST
                and not ANS_LABEL.match(ln)
                and not SOZAE_LABEL.match(ln)
                and not HAESEOK_LABEL.match(ln)
            )
            if is_real_header:
                flush()
                current_field = None
                lesson_num = int(m.group(1))
                current_lesson = lesson_num
                if lesson_num not in result:
                    result[lesson_num] = {
                        'title': title_raw,
                        'gateway_answer': '',
                        'gateway_answer_map': {},
                        'exercises_answers': {},
                        'gateway': None,
                        'exercises': {},
                    }
                current_section = None
                current_problem = None
                current_shared = []
                i += 1
                continue
            # 블랙리스트 title (예: "03 유형편") → LESSON_HEADER 아님 →
            # 아래 EX_NUM_LINE 분기로 fallthrough

        # Gateway 정답 요약 멀티 "G ateway 01 ② 02 ⑤" (장문독해)
        m = GATEWAY_ANSWER_MULTI.match(ln)
        if m and current_lesson is not None:
            pairs = parse_answer_pairs(m.group(1))
            if pairs:
                flush()
                current_field = None
                result[current_lesson]['gateway_answer_map'] = pairs
                # summary 는 "②,⑤" 형태로 요약
                result[current_lesson]['gateway_answer'] = ','.join(pairs[k] for k in sorted(pairs))
                i += 1
                continue

        # Gateway 정답 요약 단일 "G ateway ②"
        m = GATEWAY_ANSWER_SUMMARY.match(ln)
        if m and current_lesson is not None:
            flush()
            current_field = None
            result[current_lesson]['gateway_answer'] = m.group(1)
            i += 1
            continue

        # Exercises 정답 요약 "E xercises 01 ③ 02 ⑤ 03 ① 04 ②"
        # — 바로 아래 ANS_CONTINUATION 줄 ("06 ② 07 ② 08 ⑤") 이 이어지면 합쳐 파싱
        if EX_ANSWER_SUMMARY.match(ln) and current_lesson is not None:
            flush()
            current_field = None
            combined = ln
            j = i + 1
            while j < len(lines) and ANS_CONTINUATION.match(lines[j].strip()):
                combined += ' ' + lines[j].strip()
                j += 1
            result[current_lesson]['exercises_answers'] = parse_answer_pairs(combined)
            i = j
            continue

        # Gateway 블록 시작 "ateway 본문 10쪽"
        m = GATEWAY_BODY_START.match(ln)
        if m and current_lesson is not None:
            flush()
            current_field = None
            current_section = 'gw'
            problem = _make_problem('gateway', body_ref_page=int(m.group(1)))
            result[current_lesson]['gateway'] = problem
            current_problem = problem
            current_shared = [problem]
            i += 1
            continue

        # Exercises 블록 시작 "E 본문 12~15쪽"
        m = EXERCISES_BODY_START.match(ln)
        if m and current_lesson is not None:
            flush()
            current_field = None
            current_section = 'ex'
            current_problem = None
            current_shared = []
            # 다음 줄 'xercises' 단독이면 skip
            j = i + 1
            if j < len(lines) and lines[j].strip() == 'xercises':
                j += 1
            i = j
            continue

        # Exercise 번호 단독 줄 "01" / "02" ...
        # (정답표에 있는 번호만 인정 → 본문 중 우연한 2자리 숫자 "33" 오매칭 방지)
        m = EX_NUM_LINE.match(ln)
        if (m and current_section == 'ex' and current_lesson is not None
                and is_known_ex_number(current_lesson, m.group(1))):
            flush()
            current_field = None
            ex_no = m.group(1)
            problem = _make_problem(f'exercise_{ex_no}', ex_number=ex_no)
            # 이미 같은 번호가 있으면 덮어쓰지 않음 (멀티답 라인이 먼저 만들었을 수 있음)
            if ex_no not in result[current_lesson]['exercises']:
                result[current_lesson]['exercises'][ex_no] = problem
                current_problem = problem
                current_shared = [problem]
            else:
                current_problem = result[current_lesson]['exercises'][ex_no]
                current_shared = [current_problem]
            i += 1
            continue

        # 섹션 라벨 처리 — current_problem 또는 current_shared 필요
        have_target = current_problem is not None or current_shared

        if have_target or current_section in ('gw', 'ex'):
            # 멀티답 정답 라인 "정답 01 ② 02 ⑤" (장문독해 특수)
            mm = ANS_LABEL_MULTI.match(ln)
            if mm and current_section in ('gw', 'ex'):
                pairs = parse_answer_pairs(mm.group(1))
                if pairs:
                    flush()
                    current_field = None
                    if current_section == 'ex' and current_lesson is not None:
                        # 여러 Exercise 객체 생성 (없으면) + current_shared 로 묶음
                        created = []
                        for ex_no, ans in sorted(pairs.items()):
                            if ex_no not in result[current_lesson]['exercises']:
                                problem = _make_problem(f'exercise_{ex_no}',
                                                        ex_number=ex_no, answer=ans)
                                result[current_lesson]['exercises'][ex_no] = problem
                            else:
                                problem = result[current_lesson]['exercises'][ex_no]
                                problem['answer'] = ans
                            created.append(problem)
                        current_shared = created
                        current_problem = created[0] if created else None
                    elif current_section == 'gw' and current_problem is not None:
                        # Gateway 내부 정답 라인 — answer 는 요약만 저장
                        current_problem['answer'] = ','.join(pairs[k] for k in sorted(pairs))
                        current_problem['answer_map'] = pairs
                    i += 1
                    continue

        if current_problem is not None or current_shared:
            # 라벨 줄 끝에 페이지 머리말이 붙어("정답 ① 유형편", "Solution Guide 유형편")
            # 매칭이 깨지거나 소재·해석 캡처 그룹에 머리말이 빨려드는 것을 막으려고,
            # **섹션 라벨 판정에만** 머리말 제거본(ln_lbl)을 쓴다. 강·문항 경계 패턴
            # (LESSON_HEADER/EX_NUM_LINE/ANS_LABEL_MULTI)은 위에서 원본 줄로 판정 —
            # 그래야 강 경계가 흔들리지 않는다(b8a396a 회귀 가드로 확인됨).
            ln_lbl = re.sub(r'[ \t]{2,}', ' ', _PAGE_HEADER_INLINE.sub(' ', ln)).strip()
            m = ANS_LABEL.match(ln_lbl)
            if m:
                flush()
                current_field = None
                ans = m.group(1)
                # 단일 정답은 current_shared 전부에 동일하게
                for tgt in (current_shared or [current_problem]):
                    tgt['answer'] = ans
                i += 1
                continue
            m = SOZAE_LABEL.match(ln_lbl)
            if m:
                flush()
                current_field = None
                sozae = m.group(1).strip()
                for tgt in (current_shared or [current_problem]):
                    tgt['sozae'] = sozae
                i += 1
                continue
            m = HAESEOK_LABEL.match(ln_lbl)
            if m:
                flush()
                current_field = 'korean_translation'
                field_buffer = [m.group(1).strip()]
                i += 1
                continue
            if SOL_GUIDE_LABEL.match(ln_lbl):
                flush()
                current_field = 'solution_guide'
                field_buffer = []
                i += 1
                continue
            if STRUCT_LABEL.match(ln_lbl):
                flush()
                current_field = 'structure_in_focus'
                field_buffer = []
                i += 1
                continue

        # Culture Note 박스는 본문 해석/해설이 아니라 페이지 하단 문화 각주 →
        # 누적 중단. 이후 ■ 설명 줄들은 current_field=None 이라 자동으로 무시되고,
        # 다음 문항 번호/라벨이 나오면 상태가 정상 복귀한다.
        if _CULTURE_NOTE.match(ln):
            flush()
            current_field = None
            i += 1
            continue

        # 일반 본문 라인 — current_field 에 누적
        if (current_problem is not None or current_shared) and current_field is not None:
            field_buffer.append(ln)
        i += 1

    flush()

    if target_lessons is not None:
        result = {k: v for k, v in result.items() if k in target_lessons}

    return result


# ── 3. 매칭 & 저장 ────────────────────────────────────────────────────

def merge(textbook_data, solution_data):
    """강번호 기준 merge. Gateway + Exercises 01~04 병합."""
    merged = {}
    all_nums = set(textbook_data.keys()) | set(solution_data.keys())
    for n in sorted(all_nums):
        tb = textbook_data.get(n, {})
        sol = solution_data.get(n, {})

        gw_tb = tb.get('gateway') or {}
        gw_sol = sol.get('gateway') or {}
        gw_answer = sol.get('gateway_answer', '')

        gateway_merged = {**gw_tb, **gw_sol, 'answer_number': gw_answer}

        ex_list_tb = tb.get('exercises') or []
        ex_map_sol = sol.get('exercises') or {}
        ex_answers = sol.get('exercises_answers') or {}

        exercises_merged = []
        for idx, ex_tb in enumerate(ex_list_tb):
            ex_no = f'{idx + 1:02d}'
            ex_sol = ex_map_sol.get(ex_no, {})
            merged_ex = {
                **ex_tb,
                **ex_sol,
                'ex_number': ex_no,
                'answer_number': ex_answers.get(ex_no, ''),
            }
            exercises_merged.append(merged_ex)

        title_str = tb.get('title') or sol.get('title', '')

        # 장문독해 본책 qid 쌍(2문제 per 본문) 보정: body 가 비어 있으면
        # Gateway 또는 이전 형제 Ex 의 body 를 공유 (해설 ko 는 이미 공유됨)
        if '장문 독해' in title_str and exercises_merged:
            # Ex01 body=0 → Gateway body 공유 (쌍의 첫 문제가 Gateway 범위에 걸침)
            if not exercises_merged[0].get('body') and gateway_merged.get('body'):
                exercises_merged[0]['body'] = gateway_merged['body']
            # Ex02~ body=0 → 이전 형제 body 공유
            for i_ex in range(1, len(exercises_merged)):
                cur = exercises_merged[i_ex]
                prev = exercises_merged[i_ex - 1]
                if not cur.get('body') and prev.get('body'):
                    cur['body'] = prev['body']

        merged[n] = {
            'title': title_str,
            'page_range': tb.get('page_range'),
            'gateway': gateway_merged,
            'exercises': exercises_merged,
        }

    return merged


# ── 4. 메인 ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='EBS 수능특강 영어 PDF 파서')
    parser.add_argument('textbook_pdf', help='수능특강 본책 PDF 경로')
    parser.add_argument('solution_pdf', help='수능특강 해설집 PDF 경로')
    parser.add_argument('--lesson', type=int, default=None,
                        help='특정 강만 처리 (1~20). 생략 시 전체.')
    parser.add_argument('--output', default='output/ebs_extracted.json',
                        help='출력 JSON 경로')
    args = parser.parse_args()

    target_lessons = [args.lesson] if args.lesson else None

    print(f'[1/3] 본책 파싱... ({args.textbook_pdf})')
    tb_data = parse_textbook(args.textbook_pdf, target_lessons)
    print(f'       -> {len(tb_data)}개 강')
    for n in sorted(tb_data.keys()):
        d = tb_data[n]
        gw_qid = (d["gateway"] or {}).get('qid', '?')
        ex_count = len(d["exercises"])
        print(f'          {n}강 "{d["title"]}" — Gateway {gw_qid} + Exercises {ex_count}')

    print(f'[2/3] 해설집 파싱... ({args.solution_pdf})')
    sol_data = parse_solution(args.solution_pdf, target_lessons)
    print(f'       -> {len(sol_data)}개 강')
    for n in sorted(sol_data.keys()):
        d = sol_data[n]
        ex_count = len(d.get('exercises', {}))
        gw_ok = '✓' if d.get('gateway') else '✗'
        print(f'          {n}강 "{d.get("title")}" — Gateway {gw_ok} + Exercises {ex_count}')

    print('[3/3] 매칭 & 저장...')
    merged = merge(tb_data, sol_data)

    os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f'       -> {args.output}')

    # 1강 검증 샘플 프린트
    if target_lessons and 1 in target_lessons and 1 in merged:
        d = merged[1]
        print()
        print('=== 1강 매칭 검증 ===')
        print(f'제목: {d["title"]}  (본책 {d["page_range"]})')
        gw = d['gateway']
        print(f'\n--- Gateway (정답 {gw.get("answer_number", "?")}) ---')
        print(f'지시문       : {gw.get("instruction", "")}')
        body_preview = (gw.get('body') or '')[:120].replace('\n', ' ')
        ko_preview = (gw.get('korean_translation') or '')[:120].replace('\n', ' ')
        print(f'영어 본문[:120]: {body_preview}...')
        print(f'한글 해석[:120]: {ko_preview}...')
        print(f'choices      : {(gw.get("choices") or "")[:80]!r}')

        for ex in d['exercises']:
            print(f'\n--- Exercise {ex.get("ex_number", "?")} '
                  f'(정답 {ex.get("answer_number", "?")}) ---')
            print(f'지시문       : {ex.get("instruction", "")}')
            body_preview = (ex.get('body') or '')[:120].replace('\n', ' ')
            ko_preview = (ex.get('korean_translation') or '')[:120].replace('\n', ' ')
            print(f'영어 본문[:120]: {body_preview}...')
            print(f'한글 해석[:120]: {ko_preview}...')


if __name__ == '__main__':
    main()
