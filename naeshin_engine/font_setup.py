"""폰트 설정 — 영어: Helvetica(내장), 한국어: Windows 맑은 고딕 / Linux NanumGothic.

auto·studio 공유 단일 원본 (naeshin_engine). Windows(auto 로컬·studio 로컬)와
Linux(studio Render production) 모두에서 한국어 PDF 렌더링이 되도록 platform 분기한다.
빌더(make_pdf·make_exam_pdf·make_vocab_pdf)가 register_fonts + FONT_* 상수를 가져다 쓴다.
"""

import sys

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily


def register_fonts():
    """폰트 등록 — Windows: 맑은 고딕 / Linux: NanumGothic.

    Linux Render 는 fonts-nanum apt 설치 산출(/usr/share/fonts/truetype/nanum/).
    Windows 는 1년 검증된 맑은 고딕(C:/Windows/Fonts/). else 분기가 auto 원본과 동일.
    """
    if sys.platform.startswith("linux"):
        # Render Linux production (fonts-nanum apt)
        regular_path = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
        bold_path = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"
    else:
        # Windows 로컬 (auto·studio 공통 · 1년 검증)
        regular_path = "C:/Windows/Fonts/malgun.ttf"
        bold_path = "C:/Windows/Fonts/malgunbd.ttf"

    pdfmetrics.registerFont(TTFont('Malgun', regular_path))
    pdfmetrics.registerFont(TTFont('MalgunBd', bold_path))
    # 맑은 고딕 폰트 패밀리 등록 → <b> 태그가 MalgunBd로 올바르게 연결됨
    registerFontFamily('Malgun', normal='Malgun', bold='MalgunBd',
                       italic='Malgun', boldItalic='MalgunBd')
    # 영어 폰트: Helvetica는 ReportLab 내장 폰트 (별도 등록 불필요)


# 영문 스타일용
FONT_EN_NORMAL = 'Helvetica'
FONT_EN_BOLD   = 'Helvetica-Bold'

# 한국어 스타일용 (하위 호환성을 위해 FONT_NORMAL/FONT_BOLD도 유지)
FONT_NORMAL = 'Malgun'
FONT_BOLD   = 'MalgunBd'
