# naeshin-engine

naeshin **auto**(실험실)와 **studio**(SaaS)가 함께 쓰는 **공유 엔진 패키지**. 한 곳에서 관리하고 양쪽이 가져다 쓴다.

- GitHub: `kwonpodo1/naeshin-engine` (public, AGPL-3.0)
- 현재 버전: `v1.7.0`

## 무엇이 들어 있나 (단일 소스)

| 구성 | 경로 | 내용 |
|------|------|------|
| 추출 엔진 | `naeshin_engine/extract_*.py` | EBS·모의고사·지문 추출 알고리즘 |
| 자료생성 규칙 | `naeshin_engine/rules/analysis_rules.md` | 내용분석 (색·라벨·노트·서술형 선정) |
| | `naeshin_engine/rules/exam_rules.md` | 실전·변형문제 (유형·가공·오답·해설·서술형) |
| | `naeshin_engine/rules/vocab_rules.md` | 단어시험지 (포함/제외·품질·뜻 표기) |
| 한국어 공백 정리 | `naeshin_engine/ko_spacing.py` · `ko_spacing_core.py` | 조사·어절중간 띄어쓰기 오타 수정 (`apply_safe`) — studio 생성 한국어에도 적용 |
| PDF 빌더 | `naeshin_engine/make_pdf.py` · `make_exam_pdf.py` · `make_vocab_pdf.py` · `font_setup.py` | 분석·실전·단어 PDF 레이아웃 (폰트 윈도우/리눅스 분기 · 분석 로고박스는 `show_logo_box` 파라미터) |

이 파일들이 **유일한 원본**이다. auto·studio 어디에도 사본을 두지 않는다 (auto `scripts/`·studio `_engine/`의 같은 이름 파일은 재수출 shim).

## 누가 어떻게 쓰나

```
        규칙·엔진 원본 (이 패키지)
       /                          \
  auto (editable)            studio (버전 핀)
  즉시 반영                   @vX.Y.Z 로 받음
  태그 불필요                 핀 올리고 재설치해야 받음
```

- **auto**: 이 패키지를 `pip install -e` (editable)로 연결. 원본 파일을 직접 보므로 **고치면 즉시 반영**. 버전 태그가 필요 없다.
- **studio**: `backend/requirements.txt`에서 `naeshin-engine @ ...@vX.Y.Z`로 **특정 버전을 핀**해서 받는다. 새 버전을 받으려면 ① 새 태그를 만들고 ② studio가 그 태그를 보게 핀을 올려야 한다. (검증 안 된 규칙이 실서비스에 갑자기 들어가지 않게 하는 안전장치.)

## 새 버전 릴리스 (auto에서 개선 → studio 적용)

규칙이나 엔진을 고친 뒤 studio에 적용하는 절차. **글로벌 스킬 `/release-engine`이 아래 전 과정을 자동화**한다 (1회 확인 후 자동, 검증 실패 시 studio 핀 롤백).

수동으로 할 경우:

```bash
# 1. 이 패키지에서 규칙/엔진 수정 (auto에서 즉시 테스트 가능)

# 2. pyproject.toml 의 version 을 올리고 커밋·푸시
git add -A && git commit -m "..." && git push

# 3. 새 버전 태그 발행  ← 이게 "정식 버전"
git tag vX.Y.Z && git push origin vX.Y.Z

# 4. studio backend/requirements.txt 핀 한 줄 수정
#    naeshin-engine @ ...@v<이전>  →  @vX.Y.Z

# 5. studio 재설치 + 검증
pip install -r backend/requirements.txt && pytest
```

핵심은 **3번(태그 발행)**과 **4번(핀 올림)**이다. 이 둘이 빠지면 studio는 옛 버전에 머문다.

## 버전 번호 (semver)

| 무엇을 바꿨나 | 올리는 자리 | 예 |
|---|---|---|
| 문구 다듬기·버그픽스 (동작 호환) | patch | 1.2.0 → 1.2.1 |
| 규칙·기능 추가/개선 (하위 호환) | minor | 1.2.0 → 1.3.0 |
| 출력 구조 변경 (studio 어댑터도 수정) | major | 1.x → 2.0.0 |

## 관련 문서

- 쉬운 설명(그림): `release_workflow_guide.html`
- 릴리스 자동화 스킬: `~/.claude/skills/release-engine/SKILL.md`
- 규칙 운영(auto 전용 PDF·저장 등): auto `docs/RULES.md` · `docs/EXAM-RULES.md`
