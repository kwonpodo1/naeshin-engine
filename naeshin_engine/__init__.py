"""naeshin 추출 엔진 — auto/studio 공유 단일 원본 (AGPL-3.0).

studio wrapper 는 `from naeshin_engine import extract_ebs as _ebs_old` 형태로 모듈을 가져가
`_ebs_old.parse_textbook(...)` 처럼 호출한다. 아래 모듈 export 가 그 계약이다.

공개 계약 (studio wrapper 호환 — 바꾸면 studio wrapper 도 함께 고쳐야 함):
  extract_ebs       : parse_textbook(pdf, target_lessons=None) · parse_solution(pdf, target_lessons=None) · merge(tb, sol)
  extract_mock_exam : parse_original(pdf) · parse_answer_sheet(pdf) · merge(orig, ans) · extract_layout_aware_lines(pdf)
  extract_passages  : extract_text_from_pdf(pdf) · parse_entries(lines, breaks) · detect_type(entry) · extract_passage_and_translation(entry)
"""
from naeshin_engine import extract_ebs, extract_mock_exam, extract_passages

__all__ = ["extract_ebs", "extract_mock_exam", "extract_passages"]
__version__ = "0.0.0"  # 릴리스 시 git 태그와 함께 수동 bump
