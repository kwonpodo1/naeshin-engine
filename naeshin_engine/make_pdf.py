"""내용분석 PDF 렌더링 — auto·studio 공유 단일 원본 (naeshin_engine).

삽화분석본 + 한줄해석 레이아웃. 지원 지문: 교과서·모의고사·EBS·외부 지문 등.
이 모듈은 순수 렌더링(sentences + output_path → PDF)만 담당한다.
auto 전용 CLI(SOURCE_ID 설정·OUTPUT_DIR·build_pdf_from_data_file·__main__)는
auto scripts/make_pdf.py(shim)에 남는다. 폰트는 naeshin_engine.font_setup(플랫폼 분기).

출력 차이 보존:
  - show_logo_box: auto 는 헤더 우측 주황 로고 박스를 그린다(기본 True).
    studio 는 그 박스를 빼고 쓰므로 build_pdf(..., show_logo_box=False) 로 호출한다.
    → 한 코드로 양쪽 출력 외형을 그대로 유지.
"""

import re
import sys
import importlib.util
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, PageBreak
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus.flowables import Flowable

from naeshin_engine.font_setup import register_fonts


# ── 색상 ───────────────────────────────────────────────────
C_BLUE       = colors.HexColor('#1a56cc')   # 주어/명사구
C_ORANGE     = colors.HexColor('#e06c00')   # 동사/핵심구문
C_GREEN      = colors.HexColor('#1a7a3c')   # 관계사절/분사구
C_RED        = colors.HexColor('#cc0000')   # 서술형 강조
C_STAR_BG    = colors.HexColor('#fff0f0')   # 서술형 배경
C_HEADER_BG  = colors.HexColor('#1a3a6b')   # 헤더 배경 (진남색)
C_SECTION_BG = colors.HexColor('#e8f0fb')   # 섹션 헤더 배경
C_NOTE_BG    = colors.HexColor('#f5f5f5')   # 문법 노트 배경
C_NUM_BG     = colors.HexColor('#1a3a6b')   # 번호 셀 배경
C_GRAY       = colors.HexColor('#666666')
C_LIGHT_GRAY = colors.HexColor('#dddddd')

COLOR_MAP = {
    'blue':   C_BLUE,
    'orange': C_ORANGE,
    'green':  C_GREEN,
    'red':    C_RED,
}

W, H = A4

# 컬럼 너비: 번호(12mm) | 영어(110mm) | 한국어(58mm)
NUM_W = 12 * mm
EN_W  = 110 * mm
KO_W  = 58 * mm


def c2h(c):
    """ReportLab Color 객체 → '#rrggbb' 문자열"""
    return '#{:02x}{:02x}{:02x}'.format(
        int(c.red * 255), int(c.green * 255), int(c.blue * 255))


# ── 스타일 ────────────────────────────────────────────────
def make_styles():
    s = {}
    s['en'] = ParagraphStyle('en',
        fontName='Helvetica', fontSize=9.5, leading=14,
        textColor=colors.black, spaceAfter=0)
    s['ko'] = ParagraphStyle('ko',
        fontName='Malgun', fontSize=8.5, leading=13,
        textColor=colors.HexColor('#222222'), spaceAfter=0)
    s['note'] = ParagraphStyle('note',
        fontName='Malgun', fontSize=7.8, leading=12,
        textColor=colors.HexColor('#444444'))
    s['num'] = ParagraphStyle('num',
        fontName='Helvetica-Bold', fontSize=9, leading=11,
        textColor=colors.white, alignment=TA_CENTER)
    s['labels'] = ParagraphStyle('labels',
        fontName='Malgun', fontSize=6.5, leading=9,
        textColor=C_GRAY, spaceAfter=1)
    return s


# ── 데이터 로드 ───────────────────────────────────────────
def load_analysis_module(data_file):
    spec = importlib.util.spec_from_file_location("sentence_data", data_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_sentences(data_file):
    mod = load_analysis_module(data_file)
    return mod.SENTENCES


def load_pdf_meta(data_file):
    mod = load_analysis_module(data_file)
    meta = getattr(mod, "PDF_META", None)
    if meta is None:
        raise AttributeError(
            f"PDF_META not found in data file: {data_file}"
        )

    required_keys = ["lesson_title", "source_label", "badge_label", "logo_text"]
    missing_keys = [key for key in required_keys if key not in meta]
    if missing_keys:
        raise KeyError(
            f"Missing PDF_META keys in {data_file}: {', '.join(missing_keys)}"
        )

    return meta


# ── 라벨 행 (문법 태그 — Malgun으로 렌더링하여 한글 지원) ──
def build_label_row(sentence, styles):
    """하이라이트 항목의 라벨을 컬러 소형 텍스트로 표현 (한글 포함 라벨 안전)"""
    highlights = sentence.get('highlights', [])
    if not highlights:
        return None
    parts = []
    for phrase, color_key, label in highlights:
        col   = COLOR_MAP.get(color_key, colors.black)
        hex_c = c2h(col)
        parts.append(f'<font color="{hex_c}" size="6.5"><b>[{label}]</b></font>')
    return Paragraph('  '.join(parts), styles['labels'])


# ── 영어 문장 (색상 강조만 적용, 라벨 inline 없음) ───────
def _xml_escape(text):
    """reportlab Paragraph 마크업용 이스케이프 — en 본문/구절 공통 적용."""
    return (text.replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;'))


# 닫는 인용부호 — near-miss(따옴표 안에 문장부호) relaxed 매치용.
_CLOSE_QUOTES = '"\'’”'


def _span_candidates(esc_en, esc_phrase):
    """esc_phrase 의 (start,end) 후보 + relaxed 여부.
    word-boundary → plain → relaxed-quote(닫는따옴표 앞 문장부호 optional) 순."""
    pat = re.escape(esc_phrase)
    if esc_phrase[:1].isalnum():
        pat = r'(?<![A-Za-z0-9])' + pat
    if esc_phrase[-1:].isalnum():
        pat = pat + r'(?![A-Za-z0-9])'
    ms = [(m.start(), m.end()) for m in re.finditer(pat, esc_en)]
    if ms:
        return ms, False
    i = esc_en.find(esc_phrase)
    if i >= 0:
        return [(i, i + len(esc_phrase))], False
    if esc_phrase and esc_phrase[-1] in _CLOSE_QUOTES:
        rpat = re.escape(esc_phrase[:-1]) + r'[.,;:!?]?' + re.escape(esc_phrase[-1])
        rms = [(m.start(), m.end()) for m in re.finditer(rpat, esc_en)]
        if rms:
            return rms, True
    return [], False


def _locate_spans(esc_en, highlights):
    """각 하이라이트 구절의 위치를 비소비로 탐색.
    반환: spans[(s,e,hex,idx)], needs_interval(겹침 or relaxed), missed[(idx,phrase)]."""
    spans, claimed, missed = [], [], []
    occupied = [False] * len(esc_en)
    needs = False
    for idx, hl in enumerate(highlights):
        phrase, color_key = hl[0], hl[1]
        esc_phrase = _xml_escape(str(phrase))
        cands, relaxed = _span_candidates(esc_en, esc_phrase)
        pick = next(((s, e) for (s, e) in cands if (s, e) not in claimed), None)
        if pick is None:
            missed.append((idx, phrase))
            continue
        s, e = pick
        claimed.append((s, e))
        if relaxed or any(occupied[s:e]):
            needs = True
        for k in range(s, e):
            occupied[k] = True
        spans.append((s, e, c2h(COLOR_MAP.get(color_key, colors.black)), idx))
    return spans, needs, missed


def _render_intervals(esc_en, spans):
    """문자별 '가장 짧은(=안쪽) span 색 우선'(동률 시 뒤 idx)으로 nested 색칠."""
    n = len(esc_en)
    win_len = [None] * n
    win_hex = [None] * n
    win_idx = [-1] * n
    for (s, e, hex_c, idx) in spans:
        L = e - s
        for k in range(s, e):
            if win_len[k] is None or L < win_len[k] or (L == win_len[k] and idx > win_idx[k]):
                win_len[k], win_hex[k], win_idx[k] = L, hex_c, idx
    out, i = [], 0
    while i < n:
        h = win_hex[i]
        j = i
        while j < n and win_hex[j] == h:
            j += 1
        seg = esc_en[i:j]
        out.append(f'<font color="{h}"><b>{seg}</b></font>' if h else seg)
        i = j
    return ''.join(out)


def _render_flat(sentence, esc_en, highlights):
    """기존 placeholder 기반 평면 색칠 — 겹침/near-miss 없는 문장 전용(출력 불변)."""
    result = esc_en
    pending = []  # (placeholder, 최종 마크업)
    for idx, hl in enumerate(highlights):
        phrase, color_key = hl[0], hl[1]
        hex_c = c2h(COLOR_MAP.get(color_key, colors.black))
        esc_phrase = _xml_escape(phrase)
        pat = re.escape(esc_phrase)
        if esc_phrase[:1].isalnum():
            pat = r'(?<![A-Za-z0-9])' + pat
        if esc_phrase[-1:].isalnum():
            pat = pat + r'(?![A-Za-z0-9])'
        placeholder = f'\x00H{idx}\x00'
        result, n = re.subn(pat, placeholder, result, count=1)
        if n == 0 and esc_phrase in result:
            # 경계 조건 탓에 못 찾은 경우(하이픈 연접 등) — 평문 치환 폴백
            result = result.replace(esc_phrase, placeholder, 1)
            n = 1
        if n == 0:
            num = sentence.get('num', '?')
            print(f"[highlight-miss] 문장{num}: 구절 '{phrase}' 이(가) en에 없음 — 색 누락",
                  file=sys.stderr)
            continue
        pending.append((placeholder, f'<font color="{hex_c}"><b>{esc_phrase}</b></font>'))
    for placeholder, markup in pending:
        result = result.replace(placeholder, markup, 1)
    return result


def _render_en_markup(sentence):
    """en 색칠 마크업 문자열. 겹침/near-miss 있으면 구간 렌더, 아니면 평면(출력 불변)."""
    highlights = sentence.get('highlights', [])
    esc_en = _xml_escape(sentence['en'])
    spans, needs_interval, missed = _locate_spans(esc_en, highlights)
    if needs_interval:
        result = _render_intervals(esc_en, spans)
        for idx, phrase in missed:
            num = sentence.get('num', '?')
            print(f"[highlight-miss] 문장{num}: 구절 '{phrase}' 이(가) en에 없음 — 색 누락",
                  file=sys.stderr)
    else:
        result = _render_flat(sentence, esc_en, highlights)
    if sentence.get('star', False):
        result = '<font color="#cc0000">★ </font>' + result
    return result


def build_en_paragraph(sentence, styles):
    """highlights 구절을 색상+볼드로 표시. 라벨은 build_label_row()에서 별도 처리.

    가드(#4): ① en 전체 이스케이프 ② 영단어 경계 존중 ③ 구절이 en 에 없으면 stderr 경고.
    겹쳐 칠한 하이라이트(단어/구/절 레이어)는 구간 렌더러로 안쪽색 우선 nested 색칠하고,
    겹침이 없는 문장은 기존 평면 경로를 그대로 타 출력이 불변이다."""
    return Paragraph(_render_en_markup(sentence), styles['en'])


# ── 문장 블록 ─────────────────────────────────────────────
def build_sentence_block(s, styles):
    """한 문장 블록: 메인 행(번호|영어+라벨|한국어) + 노트 행 → KeepTogether"""
    is_star = s.get('star', False)
    row_bg  = C_STAR_BG if is_star else colors.white
    num_bg  = colors.HexColor('#8b0000') if is_star else C_NUM_BG

    label_para = build_label_row(s, styles)
    en_para    = build_en_paragraph(s, styles)
    ko_para    = Paragraph(s['ko'], styles['ko'])

    # 서술형 이유 표시
    star_para = None
    if is_star:
        star_reason = s.get('star_reason', '★ 서술형 예상')
        star_para = Paragraph(
            f'<font color="#cc0000"><b>{star_reason}</b></font>',
            ParagraphStyle('sp', fontName='MalgunBd', fontSize=7, leading=9)
        )

    # 영어 컬럼: [라벨] + 영어문장 + [서술형이유]
    en_content = []
    if label_para:
        en_content.append(label_para)
    en_content.append(en_para)
    if star_para:
        en_content.append(star_para)

    # ── 메인 행 ──────────────────────────────────────────
    num_para  = Paragraph(f'<b>{s["num"]}</b>', styles['num'])
    main_data = [[num_para, en_content, ko_para]]
    main_table = Table(main_data, colWidths=[NUM_W, EN_W, KO_W])
    main_table.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (0, 0), num_bg),
        ('BACKGROUND',    (1, 0), (1, 0), row_bg),
        ('BACKGROUND',    (2, 0), (2, 0),
            colors.HexColor('#f0f4ff') if not is_star else C_STAR_BG),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('ALIGN',         (0, 0), (0, 0),  'CENTER'),
        ('VALIGN',        (0, 0), (0, 0),  'MIDDLE'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LINEBELOW',     (0, 0), (-1, -1), 0.3, C_LIGHT_GRAY),
    ]))

    # ── 노트 행 (문법 설명) ───────────────────────────────
    note_text = s.get('note', '')
    note_para = Paragraph(
        f'<font color="#444444">▶ {note_text}</font>' if note_text else '',
        ParagraphStyle('np', fontName='Malgun', fontSize=7.8, leading=11,
                       textColor=colors.HexColor('#444444'))
    )
    empty = Paragraph('', styles['note'])
    note_data  = [[empty, note_para, empty]]
    note_table = Table(note_data, colWidths=[NUM_W, EN_W, KO_W])
    note_table.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), C_NOTE_BG),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LINEBELOW',     (0, 0), (-1, -1), 0.8, C_LIGHT_GRAY),
    ]))

    return KeepTogether([main_table, note_table, Spacer(1, 1.5 * mm)])


# ── 헤더 Flowable ──────────────────────────────────────────
class HeaderFlowable(Flowable):
    """진남색 배경 + 오렌지 원형 뱃지 + 중앙 제목 (+ show_logo_box 시 우측 로고 박스).

    show_logo_box: auto 는 True(우측 주황 로고 박스 표시), studio 는 False(박스 생략).
    """

    def __init__(self, width, badge_label, lesson_title, source_label, logo_text,
                 show_logo_box=True):
        Flowable.__init__(self)
        self.width        = width
        self.height       = 22 * mm
        self.badge_label  = badge_label
        self.lesson_title = lesson_title
        self.source_label = source_label
        self.logo_text    = logo_text
        self.show_logo_box = show_logo_box

    def draw(self):
        c = self.canv
        w, h = self.width, self.height

        # 배경
        c.setFillColor(C_HEADER_BG)
        c.rect(0, 0, w, h, fill=1, stroke=0)

        # 원형 뱃지 (오렌지)
        c.setFillColor(C_ORANGE)
        c.circle(15 * mm, h / 2, 10 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont('MalgunBd', 10)
        c.drawCentredString(15 * mm, h / 2 - 3.5, self.badge_label)

        # 중앙 제목
        c.setFillColor(colors.white)
        c.setFont('MalgunBd', 13)
        c.drawCentredString(w / 2, h / 2 + 3, self.lesson_title)

        # 부제 (출처)
        c.setFont('Malgun', 8)
        c.setFillColor(colors.HexColor('#aaccff'))
        c.drawCentredString(w / 2, h / 2 - 9, self.source_label)

        # 우측 로고 박스 (주황) — auto 만 (studio 는 show_logo_box=False 로 생략)
        if self.show_logo_box:
            BOX_W = 22 * mm
            BOX_H = 14 * mm
            box_x = w - BOX_W - 4 * mm
            box_y = h / 2 - BOX_H / 2
            c.setFillColor(C_ORANGE)
            c.roundRect(box_x, box_y, BOX_W, BOX_H, 3 * mm, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont('MalgunBd', 9)
            c.drawCentredString(box_x + BOX_W / 2, h / 2 - 3.5, self.logo_text)


# ── 범례 ──────────────────────────────────────────────────
def make_legend():
    items = [
        '<font color="#1a56cc"><b>■</b></font> 주어/명사구',
        '<font color="#e06c00"><b>■</b></font> 동사/핵심구문',
        '<font color="#1a7a3c"><b>■</b></font> 관계사절/분사구',
        '<font color="#cc0000"><b>■</b></font> ★ 서술형 예상',
    ]
    style = ParagraphStyle('leg', fontName='Malgun', fontSize=7.5,
                           leading=10, textColor=colors.black)
    cells = [[Paragraph(txt, style) for txt in items]]
    t = Table(cells, colWidths=[45 * mm] * 4)
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#f0f4ff')),
        ('BOX',           (0, 0), (-1, -1), 0.5, C_LIGHT_GRAY),
        ('LEFTPADDING',   (0, 0), (-1, -1), 5),
        ('TOPPADDING',    (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    return t


# ── 섹션 헤더 ─────────────────────────────────────────────
def make_section_header(name):
    data = [[
        Paragraph(
            f'<b>◆  {name}</b>',
            ParagraphStyle('sh', fontName='MalgunBd', fontSize=10.5, leading=14,
                           textColor=colors.HexColor('#1a3a6b'))
        ),
    ]]
    t = Table(data, colWidths=[NUM_W + EN_W + KO_W])
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), C_SECTION_BG),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW',     (0, 0), (-1, -1), 1.5, colors.HexColor('#1a3a6b')),
    ]))
    return t


# ── 강 구분 배너 (통합 파일 전용 — 단일 파일은 사용 안 함) ──
def make_kang_divider(kang_label):
    """강 전환 구분 배너 (진남색 배경 + 큰 흰 글씨)"""
    data = [[
        Paragraph(
            f'<b>{kang_label}</b>',
            ParagraphStyle('kd', fontName='MalgunBd', fontSize=22, leading=30,
                           textColor=colors.white, alignment=TA_CENTER)
        ),
    ]]
    t = Table(data, colWidths=[NUM_W + EN_W + KO_W])
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), C_HEADER_BG),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('TOPPADDING',    (0, 0), (-1, -1), 18),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 18),
    ]))
    return t


# ── 메인 빌드 ─────────────────────────────────────────────
def build_pdf(sentences, output_path,
              badge_label, lesson_title, source_label, logo_text,
              show_logo_box=True):
    register_fonts()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=10 * mm,
        bottomMargin=12 * mm,
    )

    styles = make_styles()
    story  = []

    # 헤더
    story.append(HeaderFlowable(
        W - 30 * mm, badge_label, lesson_title, source_label, logo_text,
        show_logo_box=show_logo_box))
    story.append(Spacer(1, 3 * mm))

    # 범례
    story.append(make_legend())
    story.append(Spacer(1, 3 * mm))

    # 본문
    current_section = None
    section_num = 0
    for s in sentences:
        # 강 구분 marker: 새 페이지 + 강 배너, current_section 리셋
        if s.get('_kang_divider'):
            story.append(PageBreak())
            story.append(HeaderFlowable(
                W - 30 * mm, badge_label, lesson_title, source_label, logo_text,
                show_logo_box=show_logo_box))
            story.append(Spacer(1, 3 * mm))
            story.append(make_legend())
            story.append(Spacer(1, 6 * mm))
            story.append(make_kang_divider(s.get('kang_label', '')))
            story.append(Spacer(1, 6 * mm))
            current_section = None
            section_num = 0
            continue

        section = s.get('section')
        if section and section != current_section:
            if current_section is not None:
                # 문항 번호가 바뀌면 새 페이지로 넘김
                story.append(PageBreak())
                # 새 페이지에 헤더 + 범례 다시 표시
                story.append(HeaderFlowable(
                    W - 30 * mm, badge_label, lesson_title, source_label, logo_text,
                    show_logo_box=show_logo_box))
                story.append(Spacer(1, 3 * mm))
                story.append(make_legend())
                story.append(Spacer(1, 3 * mm))
            current_section = section
            section_num = 0  # 새 문항이면 번호 리셋
            story.append(Spacer(1, 3 * mm))
            story.append(make_section_header(section))
            story.append(Spacer(1, 2 * mm))

        # 문단 경계: spacer 행은 번호 카운트에서 제외하고 얇은 공백만 추가
        if s.get('_spacer'):
            story.append(Spacer(1, 4 * mm))
            continue

        # 문항별 번호를 1부터 시작
        section_num += 1
        s_copy = dict(s)
        s_copy['num'] = f'{section_num:02d}'
        story.append(build_sentence_block(s_copy, styles))

    # 페이지 번호 / 푸터
    def add_page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont('Malgun', 8)
        canvas.setFillColor(C_GRAY)
        canvas.drawCentredString(W / 2, 7 * mm, f'- {doc.page} -')
        canvas.setFont('MalgunBd', 7.5)
        canvas.setFillColor(C_HEADER_BG)
        canvas.drawRightString(W - 15 * mm, 7 * mm, source_label)
        canvas.restoreState()

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    print(f'[완료] PDF 생성 완료: {output_path}')
