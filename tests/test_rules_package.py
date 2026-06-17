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


def _read_rules(filename: str) -> str:
    return (
        importlib.resources.files("naeshin_engine")
        .joinpath("rules", filename)
        .read_text(encoding="utf-8")
    )


# --- 분석(analysis) 규칙 ---------------------------------------------------


def test_analysis_rules_file_loads():
    text = _read_rules("analysis_rules.md")
    assert text.strip(), "analysis_rules.md 가 비어있음 (패키지 포함/경로 확인)"


def test_analysis_rules_has_core_content():
    text = _read_rules("analysis_rules.md")
    assert "분석 철학" in text                         # §0 분석 철학
    assert "blue" in text and "orange" in text         # §3 색상 코드
    assert "주격 관계대명사절" in text                  # §4 라벨링 문법 요소
    assert "서술형 예상 문장 선정" in text              # §6 서술형 선정


def test_analysis_rules_excludes_auto_only():
    text = _read_rules("analysis_rules.md")
    assert "내 드라이브" not in text            # §8 파일 저장(auto 전용) 제외
    assert "출력 PDF 레이아웃" not in text       # §2 PDF 레이아웃(auto 전용) 제외


# --- 단어(vocab) 규칙 -----------------------------------------------------


def test_vocab_rules_file_loads():
    text = _read_rules("vocab_rules.md")
    assert text.strip(), "vocab_rules.md 가 비어있음 (패키지 포함/경로 확인)"


def test_vocab_rules_has_core_content():
    text = _read_rules("vocab_rules.md")
    assert "포함 기준" in text and "제외 기준" in text   # 추출 기준
    assert "give up" in text                            # 구동사 예시
    assert "교육부 기본어휘" in text                     # 제외 하한선 규칙


def test_vocab_rules_excludes_auto_only():
    text = _read_rules("vocab_rules.md")
    assert "VOCAB_META" not in text       # 출력 파일 형식(auto 전용) 제외
    assert "make_vocab_pdf" not in text   # PDF 생성 명령(auto 전용) 제외
    assert "VERIFIER" not in text         # 완료 후 검증 단계(auto 전용) 제외
