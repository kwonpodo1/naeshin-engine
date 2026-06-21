"""
make_vocab_pdf.py — 단어 시험지 PDF 자동 생성 스크립트

PDF 구성 (한 파일):
    1. 영어 → 한국어  (영어 단어 보고 한국어 뜻 쓰기)
    2. 한국어 → 영어  (한국어 뜻 보고 영어 단어 쓰기)
    3. 단어장 / 정답  (영어 + 한국어 모두 표시)

사용법:
    python scripts/make_vocab_pdf.py data/vocab_data_{식별자}.py
    python scripts/make_vocab_pdf.py data/vocab_data_{식별자}.py --output-dir G:\\경로
"""

import sys
import os
import argparse
import html
import importlib.util


from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame,
    Paragraph, Spacer, HRFlowable, PageBreak,
    Table, TableStyle,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER

from naeshin_engine.font_setup import register_fonts, FONT_NORMAL, FONT_BOLD, FONT_EN_BOLD, FONT_EN_NORMAL

# ── 색상 ────────────────────────────────────────────────────────────────────
C_HEADER = colors.HexColor('#1a3a6b')
C_GRAY   = colors.HexColor('#777777')
C_GRID   = colors.HexColor('#d0d0d0')

# ── 치수 ────────────────────────────────────────────────────────────────────
W, H = A4
MARGIN_LR  = 15 * mm
MARGIN_TOP = 10 * mm
MARGIN_BOT = 14 * mm

CONTENT_W = W - 2 * MARGIN_LR      # ≈180 mm
INNER_GAP = 6 * mm                  # 좌·우 테이블 사이 간격
TABLE_W   = (CONTENT_W - INNER_GAP) / 2  # 한 쪽 테이블 폭 ≈87 mm

# 테이블 열 폭 (No. | 단어 | 뜻)
NUM_W  = 8 * mm
WORD_W = (TABLE_W - NUM_W) / 2
MEAN_W = (TABLE_W - NUM_W) / 2

WORDS_PER_PAGE_DEFAULT = 40
WORDS_PER_COL_DEFAULT  = 20

# 행 높이 상수
HEADER_AREA_H = 16 * mm
AVAIL_H  = H - MARGIN_TOP - MARGIN_BOT - HEADER_AREA_H
TH_ROW_H = 8 * mm


def calc_td_row_h(words_per_col):
    return (AVAIL_H - TH_ROW_H) / words_per_col


# ── 문서 템플릿 ──────────────────────────────────────────────────────────────
class VocabDocTemplate(BaseDocTemplate):
    def __init__(self, filename, vocab_meta, **kw):
        super().__init__(filename, **kw)
        self.vocab_meta = vocab_meta

    def handle_pageBegin(self):
        super().handle_pageBegin()
        c = self.canv
        c.saveState()
        # 페이지 번호 (하단 중앙)
        c.setFont(FONT_NORMAL, 8)
        c.setFillColor(C_GRAY)
        c.drawCentredString(W / 2, 7 * mm, f'- {self.page} -')
        c.restoreState()


# ── 데이터 로드 ──────────────────────────────────────────────────────────────
def load_vocab_data(data_file):
    spec = importlib.util.spec_from_file_location("vocab_data", data_file)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # VOCAB_META 필수 키 검증 (make_vocab_pdf.py 본체가 실제로 읽는 키만)
    meta = getattr(mod, 'VOCAB_META', None)
    if meta is None:
        raise AttributeError(
            f"VOCAB_META not found in data file: {data_file}"
        )
    required_keys = ['source_label', 'lesson_title', 'output_filename']
    missing = [k for k in required_keys if k not in meta]
    if missing:
        raise KeyError(
            f"Missing VOCAB_META keys in {data_file}: {', '.join(missing)}"
        )
    # WORDS: 비어있지 않은 리스트, 각 항목에 num/en/ko 필요 (vocab_data_template.py 스키마)
    words = getattr(mod, 'WORDS', None)
    if not isinstance(words, list) or not words:
        raise ValueError(
            f"WORDS must be a non-empty list in {data_file}"
        )
    for i, w in enumerate(words):
        if not isinstance(w, dict) or not all(k in w for k in ('num', 'en', 'ko')):
            raise KeyError(
                f"WORDS[{i}] must have 'num', 'en', 'ko' keys in {data_file}"
            )
    return meta, words


# ── 스타일 ──────────────────────────────────────────────────────────────────
def make_styles():
    return {
        # 페이지 제목 (출처 | 단원명)
        'title': ParagraphStyle(
            'title', fontName=FONT_BOLD, fontSize=11, leading=15,
            textColor=C_HEADER, alignment=TA_CENTER,
        ),
        # 섹션 라벨 (영어→한국어 등)
        'section': ParagraphStyle(
            'section', fontName=FONT_NORMAL, fontSize=8.5, leading=12,
            textColor=C_GRAY, alignment=TA_CENTER,
        ),
        # 테이블 헤더 셀 (흰 글씨)
        'th': ParagraphStyle(
            'th', fontName=FONT_BOLD, fontSize=8.5, leading=11,
            textColor=colors.white, alignment=TA_CENTER,
        ),
        # No. 셀
        'td_num': ParagraphStyle(
            'td_num', fontName=FONT_NORMAL, fontSize=9, leading=12,
            textColor=C_HEADER, alignment=TA_CENTER,
        ),
        # 영어 단어 셀
        'td_en': ParagraphStyle(
            'td_en', fontName=FONT_EN_BOLD, fontSize=9.5, leading=12,
            textColor=colors.black,
        ),
        # 한국어 뜻 셀
        'td_ko': ParagraphStyle(
            'td_ko', fontName=FONT_NORMAL, fontSize=9, leading=12,
            textColor=colors.black,
        ),
    }


# ── 단일 테이블 빌드 (15단어) ────────────────────────────────────────────────
def build_single_table(words, mode, styles, td_row_h):
    """No.|단어|뜻 형태 테이블"""
    col_widths = [NUM_W, WORD_W, MEAN_W]

    header = [
        Paragraph('No.', styles['th']),
        Paragraph('단어', styles['th']),
        Paragraph('뜻',   styles['th']),
    ]
    rows = [header]

    for w in words:
        num_p = Paragraph(str(w['num']), styles['td_num'])

        en_txt = html.escape(w['en'])
        ko_txt = html.escape(w['ko'])

        if mode == 'en_to_ko':
            en_p = Paragraph(en_txt, styles['td_en'])
            ko_p = Paragraph('',     styles['td_ko'])   # 빈칸
        elif mode == 'ko_to_en':
            en_p = Paragraph('',     styles['td_en'])   # 빈칸
            ko_p = Paragraph(ko_txt, styles['td_ko'])
        else:  # vocab_list
            en_p = Paragraph(en_txt, styles['td_en'])
            ko_p = Paragraph(ko_txt, styles['td_ko'])

        rows.append([num_p, en_p, ko_p])

    row_heights = [TH_ROW_H] + [td_row_h] * len(words)

    t = Table(rows, colWidths=col_widths, rowHeights=row_heights)
    t.setStyle(TableStyle([
        # 헤더 행
        ('BACKGROUND', (0, 0), (-1, 0), C_HEADER),
        ('TEXTCOLOR',  (0, 0), (-1, 0), colors.white),
        # 그리드
        ('GRID', (0, 0), (-1, -1), 0.4, C_GRID),
        ('BOX',  (0, 0), (-1, -1), 0.7, C_HEADER),
        # 정렬
        ('ALIGN',  (0, 0), (0, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        # 패딩
        ('LEFTPADDING',   (0, 0), (-1, -1), 5),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 5),
    ]))
    return t


# ── 2열 테이블 레이아웃 (한 페이지 40단어) ────────────────────────────────────
def build_page_tables(chunk, mode, styles, words_per_col, td_row_h):
    """좌/우 2열 배치"""
    left_words  = list(chunk[:words_per_col])
    right_words = list(chunk[words_per_col:words_per_col * 2])

    left_t = build_single_table(left_words, mode, styles, td_row_h)

    if right_words:
        right_t = build_single_table(right_words, mode, styles, td_row_h)
        outer = Table(
            [[left_t, '', right_t]],
            colWidths=[TABLE_W, INNER_GAP, TABLE_W],
        )
    else:
        outer = Table(
            [[left_t, '', '']],
            colWidths=[TABLE_W, INNER_GAP, TABLE_W],
        )

    outer.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    return outer


# ── 메인 빌드 ────────────────────────────────────────────────────────────────
def build_vocab_pdf(meta, words, output_path):
    register_fonts()

    doc = VocabDocTemplate(
        output_path, meta,
        pagesize=A4,
        leftMargin=MARGIN_LR, rightMargin=MARGIN_LR,
        topMargin=MARGIN_TOP, bottomMargin=MARGIN_BOT,
    )

    body_h = H - MARGIN_TOP - MARGIN_BOT
    pt = PageTemplate(
        id='Main',
        frames=[Frame(
            MARGIN_LR, MARGIN_BOT, CONTENT_W, body_h,
            leftPadding=0, rightPadding=0,
            topPadding=0, bottomPadding=0,
        )],
    )
    doc.addPageTemplates([pt])

    styles = make_styles()
    story  = []

    source_label = meta.get('source_label', '')
    lesson_title = meta.get('lesson_title', '')
    title_text = f"{source_label}  |  {lesson_title}" if lesson_title else source_label

    words_per_col  = meta.get('words_per_col', WORDS_PER_COL_DEFAULT)
    words_per_page = words_per_col * 2
    td_row_h       = calc_td_row_h(words_per_col)

    chunks = [words[i:i + words_per_page] for i in range(0, len(words), words_per_page)]

    SECTIONS = [
        ('en_to_ko',   '영어 → 한국어'),
        ('ko_to_en',   '한국어 → 영어'),
        ('vocab_list', '단어장 / 정답'),
    ]

    first_section = True
    for mode, label in SECTIONS:
        if not first_section:
            story.append(PageBreak())
        first_section = False

        for j, chunk in enumerate(chunks):
            if j > 0:
                story.append(PageBreak())

            # ── 페이지 헤더 ──
            story.append(Paragraph(title_text, styles['title']))
            story.append(Spacer(1, 1.5 * mm))
            sect_display = f"{label}  (계속)" if j > 0 else label
            story.append(Paragraph(sect_display, styles['section']))
            story.append(Spacer(1, 1 * mm))
            story.append(HRFlowable(
                width='100%', thickness=0.7, color=C_HEADER,
                spaceAfter=3 * mm,
            ))

            # ── 단어 테이블 ──
            story.append(build_page_tables(chunk, mode, styles, words_per_col, td_row_h))

    doc.build(story)
    print(f"[완료] 단어 시험지 PDF 생성 완료: {output_path}")


# ── CLI 진입점 ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='단어 시험지 PDF 생성기')
    parser.add_argument('data_file', help='vocab_data 파일 경로')
    parser.add_argument('--output-dir', default=None,
                        help='출력 폴더 override (기본: VOCAB_META의 output_dir)')
    args = parser.parse_args()

    data_file = os.path.abspath(args.data_file)
    if not os.path.isfile(data_file):
        print(f"[오류] 파일을 찾을 수 없습니다: {data_file}")
        sys.exit(1)

    meta, words = load_vocab_data(data_file)

    output_dir = args.output_dir or meta.get('output_dir', 'output')
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(os.path.dirname(__file__), '..', output_dir)

    os.makedirs(output_dir, exist_ok=True)

    output_filename = meta.get('output_filename', 'vocab_test.pdf')
    output_path = os.path.join(output_dir, output_filename)

    build_vocab_pdf(meta, words, output_path)


if __name__ == '__main__':
    main()
