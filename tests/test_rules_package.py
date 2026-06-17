# -*- coding: utf-8 -*-
"""공유 규칙 파일(rules/exam_rules.md) 패키지 포함 + 로드 검증 — 자동반영 단일 소스."""
import importlib.resources


def _read_exam_rules() -> str:
    return (
        importlib.resources.files("naeshin_engine")
        .joinpath("rules", "exam_rules.md")
        .read_text(encoding="utf-8")
    )


def test_exam_rules_file_loads():
    text = _read_exam_rules()
    assert text.strip(), "exam_rules.md 가 비어있음 (패키지 포함/경로 확인)"


def test_exam_rules_has_core_content():
    text = _read_exam_rules()
    assert "오답 제1원칙" in text                       # §0 출제 대원칙
    assert "주제_파악" in text and "조건_영작" in text   # §3 17유형
    assert "서술형" in text                             # §11 루브릭


def test_exam_rules_excludes_auto_only():
    text = _read_exam_rules()
    assert "내 드라이브" not in text          # §7 파일 저장(auto 전용) 제외
    assert "## 1. 출력 PDF" not in text       # §1 PDF 구성(auto 전용) 제외
