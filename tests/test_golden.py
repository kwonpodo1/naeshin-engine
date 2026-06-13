"""골든 회귀 테스트 — 이식본 추출이 기대대로 동작하는지 확인.

로컬 샘플(tests/samples/)이 있으면 실행, 없으면 skip.
샘플 PDF는 저작권·용량 때문에 repo 에 포함하지 않는다(.gitignore).
로컬에서 tests/samples/mock_q.pdf (문제지) · mock_a.pdf (해설) 를 두면 실행된다.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from naeshin_engine import extract_mock_exam as me  # noqa: E402

SAMPLES = pathlib.Path(__file__).resolve().parent / "samples"
Q = SAMPLES / "mock_q.pdf"
A = SAMPLES / "mock_a.pdf"


@pytest.mark.skipif(not (Q.exists() and A.exists()), reason="로컬 샘플 PDF 없음")
def test_mock_exam_extracts_passages_and_korean():
    """모의고사 문제지+해설 → 지문 다수 + 한국어 해석이 채워져야 한다."""
    merged = me.merge(me.parse_original(str(Q)), me.parse_answer_sheet(str(A)))
    assert len(merged) >= 20, f"지문 수 부족: {len(merged)}"
    has_ko = sum(1 for d in merged.values() if (d.get("korean_translation") or "").strip())
    assert has_ko >= 20, f"한국어 채워진 지문 부족: {has_ko}/{len(merged)}"
