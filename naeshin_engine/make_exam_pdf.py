"""
make_exam_pdf.py — 변형문제 PDF 자동 생성 스크립트 (섹션별 발췌 방식)

사용법:
    python scripts/make_exam_pdf.py data/exam_data_{식별자}.py
    python scripts/make_exam_pdf.py data/exam_data_{식별자}.py --output-dir G:\\경로

exam_data 파일이 제공해야 할 것:
    EXAM_INFO = {
        "source_label": "...",
        "subject":      "...",
        "grade":        "...",
        "round":        "1",          # 회차
        "total_questions": 30,
        # 선택:
        # "output_filename": "...pdf",  # 없으면 파일 stem + 회차로 자동 생성
        # "output_dir":      "output",  # 없으면 기본 output/
    }
    SECTIONS = [ {label, passage, questions:[...]}, ... ]
"""

import sys
import os
import argparse


from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, NextPageTemplate, Table, TableStyle,
    Paragraph, Spacer, HRFlowable, PageBreak, KeepTogether, FrameBreak
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT

from naeshin_engine.font_setup import register_fonts, FONT_NORMAL, FONT_BOLD

# ── 색상 ───────────────────────────────────────────────
C_HEADER    = colors.HexColor('#1a3a6b')
C_PASSAGE   = colors.HexColor('#f8f8f8')
C_PASSAGE_BD= colors.HexColor('#cccccc')
C_STAR      = colors.HexColor('#cc0000')
C_ANS_BG    = colors.HexColor('#eef2fa')
C_ANS_BD    = colors.HexColor('#1a3a6b')
C_KEY       = colors.HexColor('#e06c00')
C_GRAY      = colors.HexColor('#555555')
C_LIGHT     = colors.HexColor('#dddddd')
C_GREEN     = colors.HexColor('#1a7a3c')


W, H = A4

MARGIN_LR = 15 * mm
MARGIN_TOP = 10 * mm
MARGIN_BOT = 12 * mm
COL_GAP = 8 * mm
COL_WIDTH = (W - 2 * MARGIN_LR - COL_GAP) / 2.0
TITLE_BAND_H = 22 * mm   # 1페이지 상단 제목 배너 높이

class ExamDocTemplate(BaseDocTemplate):
    def __init__(self, filename, exam_info, **kw):
        super().__init__(filename, **kw)
        self.exam_info = exam_info

    def handle_pageBegin(self):
        super().handle_pageBegin()
        canvas = self.canv
        canvas.saveState()
        
        # Draw center line for 2-column templates (first page reserves a title band)
        _tid = self.pageTemplate.id if getattr(self, 'pageTemplate', None) else ''
        if _tid in ('2Col', '2ColFirst'):
            canvas.setStrokeColor(C_GRAY)
            canvas.setLineWidth(0.5)
            line_top = H - MARGIN_TOP - 5*mm
            if _tid == '2ColFirst':
                line_top = H - MARGIN_TOP - TITLE_BAND_H - 2*mm
            line_bot = MARGIN_BOT + 5*mm
            canvas.line(W/2, line_top, W/2, line_bot)

        # Page Number
        canvas.setFont(FONT_NORMAL, 8)
        canvas.setFillColor(C_GRAY)
        canvas.drawCentredString(W/2, 7*mm, f'- {self.page} -')
        
        # Suneung Style Header text
        source = self.exam_info.get('source_label', '')
        if source:
            canvas.setFont(FONT_BOLD, 7.5)
            canvas.setFillColor(C_HEADER)
            canvas.drawRightString(W - MARGIN_LR, 7*mm, source)
            
        canvas.restoreState()



# ── 데이터 로드 ─────────────────────────────────────────
def load_exam_data(data_file):
    import importlib.util
    spec = importlib.util.spec_from_file_location("exam_data", data_file)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # EXAM_INFO 필수 키 검증 (make_exam_pdf.py 본체가 실제로 읽는 키만)
    exam_info = getattr(mod, 'EXAM_INFO', None)
    if exam_info is None:
        raise AttributeError(
            f"EXAM_INFO not found in data file: {data_file}"
        )
    required_keys = ['source_label']  # round / output_filename / output_dir 은 .get() 기본값 처리됨
    missing = [k for k in required_keys if k not in exam_info]
    if missing:
        raise KeyError(
            f"Missing EXAM_INFO keys in {data_file}: {', '.join(missing)}"
        )
    # 새 SECTIONS 형식 우선, 구형 PASSAGE+QUESTIONS 형식 fallback
    if hasattr(mod, 'SECTIONS'):
        sections = mod.SECTIONS
        if not isinstance(sections, list) or not sections:
            raise ValueError(
                f"SECTIONS must be a non-empty list in {data_file}"
            )
        for i, sec in enumerate(sections):
            for key in ('label', 'passage', 'questions'):
                if key not in sec:
                    raise KeyError(
                        f"SECTIONS[{i}] missing key '{key}' in {data_file}"
                    )
        return exam_info, sections
    # 구형 fallback
    if not hasattr(mod, 'PASSAGE') or not hasattr(mod, 'QUESTIONS'):
        raise AttributeError(
            f"{data_file}: either SECTIONS or (PASSAGE + QUESTIONS) required"
        )
    return exam_info, [{
        "label": "다음 글을 읽고 물음에 답하시오.",
        "passage": mod.PASSAGE,
        "questions": mod.QUESTIONS,
    }]


# ── 스타일 ─────────────────────────────────────────────
def make_styles():
    return {
        'h1': ParagraphStyle('h1', fontName=FONT_BOLD, fontSize=13, leading=18,
                             textColor=C_HEADER),
        'sub': ParagraphStyle('sub', fontName=FONT_NORMAL, fontSize=8.5, leading=12,
                              textColor=C_GRAY),
        'q_text': ParagraphStyle('q_text', fontName=FONT_NORMAL, fontSize=9.5, leading=14),
        'choice': ParagraphStyle('choice', fontName=FONT_NORMAL, fontSize=9, leading=13,
                                 leftIndent=5),
        'cond': ParagraphStyle('cond', fontName=FONT_NORMAL, fontSize=8.5, leading=12,
                               textColor=colors.HexColor('#333333')),
        'insert': ParagraphStyle('insert', fontName=FONT_BOLD, fontSize=9, leading=13,
                                 textColor=C_HEADER,
                                 backColor=colors.HexColor('#eef2fa'),
                                 borderColor=C_ANS_BD, borderWidth=0.6,
                                 borderPadding=(4, 6, 4, 6)),
        'ans_table_head': ParagraphStyle('ath', fontName=FONT_BOLD, fontSize=9, leading=12,
                                         alignment=TA_CENTER, textColor=C_HEADER),
        'ans_table_val': ParagraphStyle('atv', fontName=FONT_BOLD, fontSize=10, leading=13,
                                        alignment=TA_CENTER, textColor=C_STAR),
        'exp_head': ParagraphStyle('exph', fontName=FONT_BOLD, fontSize=10, leading=14,
                                   textColor=C_HEADER),
        'exp_body': ParagraphStyle('expb', fontName=FONT_NORMAL, fontSize=9, leading=13,
                                   textColor=colors.black),
        'key': ParagraphStyle('key', fontName=FONT_BOLD, fontSize=9, leading=13,
                              textColor=C_KEY),
        'ans_label': ParagraphStyle('ansl', fontName=FONT_BOLD, fontSize=9, leading=12,
                                    textColor=C_GREEN),
    }


# ── 헤더 빌드 ──────────────────────────────────────────
def build_header(exam_info, styles):
    return Spacer(1, 1*mm)


def build_title_banner(exam_info):
    """1페이지 상단 전체 폭 제목 배너 — 자료 제목 + 강 + 예상문제 회차."""
    src   = exam_info.get('source_label', '') or '예상문제'
    rnd   = str(exam_info.get('round', '1'))
    subj  = exam_info.get('subject', '')
    grade = exam_info.get('grade', '')
    sub_bits = ' · '.join([b for b in (subj, grade) if b])

    title_st = ParagraphStyle('exam_title', fontName=FONT_BOLD, fontSize=15, leading=19,
                              textColor=C_HEADER)
    subtl_st = ParagraphStyle('exam_subtitle', fontName=FONT_NORMAL, fontSize=8.5, leading=12,
                              textColor=C_GRAY)
    round_st = ParagraphStyle('exam_round', fontName=FONT_BOLD, fontSize=10.5, leading=14,
                              textColor=colors.white, alignment=TA_CENTER)

    left = [Paragraph(src, title_st)]
    if sub_bits:
        left.append(Paragraph(sub_bits, subtl_st))

    badge = Table([[Paragraph(f'예상문제 {rnd}회', round_st)]], colWidths=[34*mm])
    badge.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), C_HEADER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ]))

    full_w = W - 2*MARGIN_LR
    t = Table([[left, badge]], colWidths=[full_w - 38*mm, 38*mm])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    return [t, HRFlowable(width='100%', thickness=1.2, color=C_HEADER), Spacer(1, 3*mm)]


# ── 선택지 블록 빌드 ─────────────────────────────────────
def build_choices_block(q, styles):
    items = []
    qtype = q.get('type', '')

    if qtype == '어법_ABC' and q.get('choices'):
        rows = [['', '(A)', '(B)', '(C)']]
        for i, choice in enumerate(q['choices']):
            text = choice
            for sym in ['①','②','③','④','⑤']:
                text = text.replace(sym, '')
            parts = [p.strip() for p in text.split('—')]
            label = ['①','②','③','④','⑤'][i]
            rows.append([label] + parts[:3])

        tw = COL_WIDTH
        t = Table(rows, colWidths=[tw*0.1, tw*0.3, tw*0.3, tw*0.3])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), C_ANS_BG),
            ('FONTNAME',   (0,0), (-1,0), FONT_BOLD),
            ('ALIGN',      (0,0), (-1,-1), 'CENTER'),
            ('FONTSIZE',   (0,0), (-1,-1), 9),
            ('LEADING',    (0,0), (-1,-1), 12),
            ('GRID',       (0,0), (-1,-1), 0.3, C_LIGHT),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ]))
        items.append(t)

    elif qtype == '조건_영작':
        items.append(Paragraph(
            f'<font color="#1a3a6b"><b>▶</b></font> {q.get("korean", "")}',
            styles['q_text']
        ))
        items.append(Spacer(1, 1*mm))
        cond_lines = '<br/>'.join(f'  • {c}' for c in q.get('conditions', []))
        cond_para = Paragraph('＜조건＞<br/>' + cond_lines, styles['cond'])
        cond_t = Table([[cond_para]], colWidths=[COL_WIDTH])
        cond_t.setStyle(TableStyle([
            ('BOX',  (0,0), (-1,-1), 0.8, C_ANS_BD),
            ('LEFTPADDING',  (0,0), (-1,-1), 8),
            ('TOPPADDING',   (0,0), (-1,-1), 5),
            ('BOTTOMPADDING',(0,0), (-1,-1), 5),
        ]))
        items.append(cond_t)
        items.append(Spacer(1, 1*mm))
        items.append(Paragraph('_' * 60, styles['q_text']))

    elif q.get('choices'):
        for choice in q['choices']:
            items.append(Paragraph(choice, styles['choice']))

    return items


# ── 정답 가드 (#5) ─────────────────────────────────────
CIRCLED_ANS = '①②③④⑤⑥⑦'


def _answer_char(q):
    """객관식 answer(1-base) → 원형 숫자. 잘못된 값은 조용히 틀린 정답표를 찍는 대신 즉시 실패.

    기존 결함: answer=0 → 조용히 ⑤ 출력 / None → TypeError / 6+ → IndexError."""
    num = q.get('num', '?')
    ans = q.get('answer')
    choices = q.get('choices') or []
    try:
        ans_i = int(ans)
    except (TypeError, ValueError):
        raise ValueError(
            f"문항 {num}: answer 가 정수가 아님: {ans!r} — 객관식은 1~{len(choices) or 5} 필수")
    hi = min(len(choices) if choices else 5, len(CIRCLED_ANS))
    if not (1 <= ans_i <= hi):
        raise ValueError(
            f"문항 {num}: answer={ans_i} 가 1~{hi} 범위 밖 (0은 1번이 아니라 데이터 오류)")
    return CIRCLED_ANS[ans_i - 1]


def validate_answers(sections):
    """객관식 정답 전수 검증 — 빌드 전에 호출되어 오류를 한 번에 보고."""
    problems = []
    for sec in sections:
        for q in sec.get('questions', []):
            if q.get('answer_display') == '서술형':
                continue
            if q.get('choices') is None:
                continue
            try:
                _answer_char(q)
            except ValueError as e:
                problems.append(str(e))
    if problems:
        raise ValueError(
            "정답 데이터 오류 — PDF 생성 중단(틀린 정답표 출력 방지):\n  - "
            + "\n  - ".join(problems))


# ── 정답 일람표 ────────────────────────────────────────
def build_answer_table(all_questions, styles):
    obj_qs = [q for q in all_questions
              if q.get('choices') is not None and q.get('answer_display') != '서술형']

    if not obj_qs:
        return [Spacer(1, 1*mm)]

    tw = W - 2*MARGIN_LR
    # 줄당 최대 10문항씩 나눠서 표 생성 (넓은 간격으로 세로 래핑 방지)
    chunk = 10
    tables = []
    for start in range(0, len(obj_qs), chunk):
        group = obj_qs[start:start+chunk]
        header_row = [Paragraph(str(q['num']), styles['ans_table_head']) for q in group]
        answer_row = [Paragraph(
            _answer_char(q), styles['ans_table_val']
        ) for q in group]
        col_w = tw / len(group)
        t = Table([header_row, answer_row], colWidths=[col_w]*len(group))
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), C_ANS_BG),
            ('BOX',   (0,0), (-1,-1), 1,   C_ANS_BD),
            ('GRID',  (0,0), (-1,-1), 0.3, C_LIGHT),
            ('TOPPADDING',    (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ]))
        tables.append(t)
        tables.append(Spacer(1, 2*mm))
    return tables


# ── 해설 블록 ──────────────────────────────────────────
def build_explanation_block(q, styles):
    items = []
    num = q['num']

    if q.get('answer_display') == '서술형':
        ans_para = Paragraph(
            f'<b>{num}번</b>  <font color="#cc0000"><b>[서술형]</b></font>',
            styles['exp_head']
        )
    else:
        ans_char = _answer_char(q)
        ans_para = Paragraph(
            f'<b>{num}번</b>  <font color="#cc0000"><b>{ans_char}</b></font>',
            styles['exp_head']
        )
    items.append(ans_para)

    if q.get('answer_display') == '서술형' and q.get('answer'):
        items.append(Paragraph(
            f'<font color="#1a7a3c"><b>모범 답안:</b></font> {q["answer"]}',
            styles['ans_label']
        ))

    if q.get('key_phrases'):
        key_str = ' / '.join(f'<b>{kp}</b>' for kp in q['key_phrases'])
        items.append(Paragraph(
            f'<font color="#e06c00">• 핵심: {key_str}</font>',
            styles['key']
        ))

    explanation = q.get('explanation', '')
    if explanation:
        for line in explanation.split('\n'):
            line = line.strip()
            if line:
                items.append(Paragraph(line, styles['exp_body']))

    items.append(Spacer(1, 2*mm))
    items.append(HRFlowable(width='100%', thickness=0.4, color=C_LIGHT))
    items.append(Spacer(1, 1*mm))
    return KeepTogether(items)


# ── 메인 ──────────────────────────────────────────────
def build_exam_pdf(exam_info, sections, output_path, mode='teacher'):
    """
    mode='teacher' — 문제지 + 정답·해설 (기본, 선생님용)
    mode='student' — 문제지만 (학생 배포용, 정답·해설 제거)
    """
    validate_answers(sections)  # #5 가드 — 양 모드 공통, 빌드 전 전수 검증
    register_fonts()

    doc = ExamDocTemplate(
        output_path,
        exam_info,
        pagesize=A4,
        leftMargin=MARGIN_LR, rightMargin=MARGIN_LR,
        topMargin=MARGIN_TOP, bottomMargin=MARGIN_BOT,
    )
    
    body_h = H - MARGIN_TOP - MARGIN_BOT
    col_h_first = body_h - TITLE_BAND_H
    # 1페이지 전용: 전체 폭 제목 배너 프레임 + 그 아래 2단 본문 프레임
    pt_first = PageTemplate(id='2ColFirst', frames=[
        Frame(MARGIN_LR, H - MARGIN_TOP - TITLE_BAND_H, W - 2*MARGIN_LR, TITLE_BAND_H, id='title', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
        Frame(MARGIN_LR, MARGIN_BOT, COL_WIDTH, col_h_first, id='c1', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
        Frame(MARGIN_LR + COL_WIDTH + COL_GAP, MARGIN_BOT, COL_WIDTH, col_h_first, id='c2', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
    ])
    pt_2col = PageTemplate(id='2Col', frames=[
        Frame(MARGIN_LR, MARGIN_BOT, COL_WIDTH, body_h, id='c1', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
        Frame(MARGIN_LR + COL_WIDTH + COL_GAP, MARGIN_BOT, COL_WIDTH, body_h, id='c2', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    ])
    pt_1col = PageTemplate(id='1Col', frames=[
        Frame(MARGIN_LR, MARGIN_BOT, W - 2*MARGIN_LR, body_h, id='c1', leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    ])
    doc.addPageTemplates([pt_first, pt_2col, pt_1col])


    styles = make_styles()
    story  = []

    # ── 1페이지 상단 제목 배너 (자료 제목 + 강 + 예상문제 회차) ──
    story.append(NextPageTemplate('2Col'))     # 2페이지부터는 일반 2단 레이아웃
    story.extend(build_title_banner(exam_info))
    story.append(FrameBreak())                 # 제목 프레임 종료 → 본문 컬럼으로 이동


    all_questions = []
    for section in sections:
        passage = section.get('passage', '')
        qs = section.get('questions', [])

        if not qs:
            continue

        # 지문은 섹션당 한 번만 렌더링한다. 여러 문제가 한 지문을 공유.
        passage_style = ParagraphStyle(
            'passage',
            fontName=FONT_NORMAL, fontSize=9.5, leading=15,
            textColor=colors.black,
            firstLineIndent=12,
        )
        passage_flowables = []
        for para_text in passage.split('\n'):
            if para_text.strip():
                passage_flowables.append(Paragraph(para_text.strip(), passage_style))
        passage_flowables.append(Spacer(1, 4*mm))

        for idx, q in enumerate(qs):
            section_items = []

            num = q['num']
            qtext = q['question']
            qtype = q.get('type', '')

            # ── 1. 문제 번호 및 질문 (모의고사 폼) ──
            q_para = Paragraph(f'<b>{num}.</b> {qtext}', styles['q_text'])
            section_items.append(q_para)
            section_items.append(Spacer(1, 2.5*mm))

            # ── 2. 문장 삽입 박스 (있을 경우) ──
            if qtype == '문장_삽입' and q.get('insert_sentence'):
                ins_para = Paragraph(q['insert_sentence'], styles['insert'])
                section_items.append(ins_para)
                section_items.append(Spacer(1, 3*mm))

            # ── 3. 지문 (첫 문제에만 부착; 후속 문제는 같은 지문을 공유) ──
            if idx == 0:
                section_items.extend(passage_flowables)

            # ── 4. 선택지 및 조건 박스 ──
            for choice_item in build_choices_block(q, styles):
                section_items.append(choice_item)

            all_questions.append(q)

            # 문제 간격 (한 컬럼에 2문제가 밸런스 있게 들어가도록 넉넉한 여백)
            section_items.append(Spacer(1, 15*mm))

            story.append(KeepTogether(section_items))

    # ── 정답지 (새 페이지) — teacher 모드만 ────────────────────────────
    if mode == 'teacher':
        story.append(NextPageTemplate('1Col'))
        story.append(PageBreak())
        story.append(build_header(exam_info, styles))
        story.append(Spacer(1, 3*mm))

        story.append(Paragraph('<b>정 답</b>', ParagraphStyle(
            'ath2', fontName=FONT_BOLD, fontSize=12, leading=16, textColor=C_HEADER
        )))
        story.append(Spacer(1, 2*mm))
        for item in build_answer_table(all_questions, styles):
            story.append(item)
        story.append(Spacer(1, 5*mm))

        story.append(Paragraph('<b>해 설</b>', ParagraphStyle(
            'exth', fontName=FONT_BOLD, fontSize=12, leading=16, textColor=C_HEADER
        )))
        story.append(HRFlowable(width='100%', thickness=1, color=C_HEADER))
        story.append(Spacer(1, 2*mm))

        for q in all_questions:
            story.append(build_explanation_block(q, styles))

    # ── 페이지 번호 ───────────────────────────────────
    doc.build(story)
    mode_label = '학생용' if mode == 'student' else '선생님용'
    print(f"[완료] 변형문제 PDF({mode_label}) 생성 완료: {output_path}")


def resolve_output(data_file, exam_info, cli_output_dir, mode='teacher'):
    """출력 파일명 / 디렉토리 결정.

    파일명:  EXAM_INFO['output_filename'] (있으면 사용, 단 mode='student'면 _학생용 suffix 자동 부여)
             > 데이터 파일 stem에서 파생 (exam_data_{ID}.py → {ID}_예상문제_{round}회.pdf)
    디렉토리: --output-dir > EXAM_INFO['output_dir'] > 기본 output/
    """
    filename = exam_info.get('output_filename')
    if not filename:
        stem = os.path.splitext(os.path.basename(data_file))[0]
        ident = stem[len('exam_data_'):] if stem.startswith('exam_data_') else stem
        round_str = str(exam_info.get('round', '1'))
        filename = f"{ident}_예상문제_{round_str}회.pdf"

    if mode == 'student':
        base, ext = os.path.splitext(filename)
        if not base.endswith('_학생용'):
            filename = f"{base}_학생용{ext}"

    out_dir = cli_output_dir or exam_info.get('output_dir') or \
        os.path.join(os.path.dirname(__file__), '..', 'output')
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, filename)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n', 1)[0])
    parser.add_argument('data_file', help='exam_data_{식별자}.py 파일 경로')
    parser.add_argument('--output-dir', default=None, help='PDF 저장 디렉토리 (선택)')
    parser.add_argument('--mode', choices=['teacher', 'student', 'both'], default='teacher',
                        help="teacher=문제+정답해설(기본), student=문제만, both=두 버전 모두 생성")
    args = parser.parse_args()

    exam_info, sections = load_exam_data(args.data_file)

    modes = ['teacher', 'student'] if args.mode == 'both' else [args.mode]
    for mode in modes:
        output_path = resolve_output(args.data_file, exam_info, args.output_dir, mode=mode)
        build_exam_pdf(exam_info, sections, output_path, mode=mode)
