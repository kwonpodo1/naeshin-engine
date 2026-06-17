<!-- 단일 소스: naeshin_engine/rules/vocab_rules.md — auto·studio 공유 단어시험지(어휘 선별) 규칙. auto 전용 운영(vocab_data 파일 형식·PDF 생성 명령·생성 PDF 3섹션 구성·검증 단계)은 auto agents/08_VOCAB-MAKER-extracts-words.md 에 둔다. 여기를 고치면 auto 는 즉시(editable), studio 는 패키지 버전 핀으로 반영. -->

# 내신 자료 자동화 규칙 — 단어시험지(어휘) 편

> 어휘 선별·시험 설계의 외부 근거(교육부 고시·KICE Word Lister·SLA 연구 검증): `docs/research/KB-03-단어시험지-어휘.md`
> 변형문제 어휘 오답 설계는 `naeshin_engine/rules/exam_rules.md` 10번 참고

## 역할

영어 본문에서 **고등학생 내신 시험 수준**의 중요 어휘를 빠짐없이 추출한다. 학생이 외워야 할 단어·숙어를 중요도 순서로 뽑아 단어시험지의 원천 데이터로 쓴다.

---

## 단어 추출 기준

### ✅ 포함 기준
- 고등학교 1~3학년 수준의 어휘 (중학교 수준 이상, 전문용어 이하)
- 본문의 핵심 주제·논지와 직결된 단어
- 수능 빈출 어휘, 교과서 필수 어휘
- 동사구·연어(collocation) 중 시험 출제 가능성이 높은 것 (예: `rely on`, `be responsible for`)
- 파생어 중 형태 변화가 시험에 나올 법한 것 (예: `reliable`, `reliability`)
- **다의어**: 본문 문맥에서의 의미가 중학 수준 기본 뜻과 다르면 반드시 포함 (예: `condition`, `feature`, `match`)

### ❌ 제외 기준
- 중학교 수준 이하 기초 어휘 (go, come, big, good 등) — **교육부 기본어휘 3,000 단어군 중 별표(초등 800)·별별표(중·고 공통 1,200) 부류가 하한선** (`KB-03` A2). 단, 기본어휘는 하한 기준선일 뿐 **EBS·수능 빈출 비기본어는 포함**한다(무조건 배제 금지). (auto 는 `data/basic_vocab_2022.py` 대조 테이블로 굴절·파생형까지 자동 점검)
- 관사·전치사·접속사 등 기능어
- 고유명사 (인명, 지명, 제품명 등)
- **호칭·감탄사·단위명·약어·화학식·알파벳·기수/서수** — 교육과정상 '학습 어휘'로 간주하지 않음 (`KB-03` A3, KICE Word Lister 기준)
- **같은 단어군(word family)의 굴절형 중복** — `develop/developed/developing`은 대표형 하나로 통합, 별개 단어로 중복 출제 금지 (`KB-03` A4)
- 본문에서 1회 등장하며 주제와 무관한 주변 어휘

### 📦 분량
- 외워야 할 것 같은 단어는 **전부 추출** (빠짐없이)
- 단, **최대 80개**를 넘기지 않는다
- 짧은 지문은 적게, 긴 지문은 많이 (지문 길이에 비례). 80개를 억지로 채우려 쉬운 단어를 넣지 말 것. (40개 단위로 페이지가 자동 분리됨)

### 🎯 어휘 선별 품질 향상 (참고자료 학습 반영)

단지 자료 Part 3 스타일에서 학습한 선별 원칙:

1. **어휘 변형문제 출제 예상 단어 우선**: `naeshin_engine/rules/exam_rules.md` 10번에서 설명한 오답 설계용 단어 풀을 의식하며 추출
2. **동의어 묶음으로 존재하는 단어 우선**: 예를 들어 `rescue`는 `save/recover/retrieve`와 묶이므로 변형문제 어휘 오답으로 자주 쓰임 → 포함
3. **반의어 대응이 명확한 단어 우선**: `beneficial ↔ harmful`, `increase ↔ decrease` 등
4. **교과서/EBS 빈출 동사구 우선**: `play a role in`, `turn out that`, `remind A of B`, `provide A with B` 등
5. **다의어는 본문 문맥 의미를 뜻에 반영**: 기본 뜻이 아닌 본문에 쓰인 의미를 기록 (예: `condition` 본문 의미가 "환경"이면 `"환경"`으로)
6. **범용성 가중(용례지수)**: 본문 빈도만이 아니라 여러 지문에 두루 쓰이는 단어를 우선한다 (`KB-03` A8). 한 본문에만 몰린 주변어보다 범용 핵심어.
7. **파생어 병기**: 빈도 높고 출제 가능성 큰 파생형만 대표형 옆 ( )에 표기 (예: `rely (reliable, reliability)`) — 표준 36개 파생접사 범위 내 (`KB-03` A5)
8. **어원·접사로 뜻·품사 인식** (`KB-07`): 접두사(부정 un-/in-/dis-·방향 re-/pre-/trans-/sub-·정도 over-/under-)·어근(spect 보다·port·fer 나르다·ject 던지다·mit 보내다·tain 잡다·pos 놓다·duc 이끌다 등)으로 모르는 단어 뜻 추론. 접미사로 품사 인식(-tion/-ment 명사·-ous/-ful 형용사·-ize/-ate 동사·-ly 부사, ⚠️ friendly/costly=형용사·hardly≠hard 예외).
9. **혼동어 쌍 세트 병기** (`KB-07`): rise/raise(자·타)·affect/effect·principal/principle·economic/economical·considerate/considerable·imaginary/imaginative/imaginable·adapt/adopt 같은 혼동쌍은 **세트로 묶어 뜻 대조 병기**(예: `considerate 사려 깊은(↔considerable 상당한)`), 자·타동사는 3단변화 함께.
10. **다의어는 본문 의미 우선** (`KB-07`): address(다루다)·figure·subject(be subject to)·matter·observe(준수하다)·bear·found(설립)·content(만족한)·last·term 등 다의어는 **본문에 쓰인 의미를 대표 뜻으로 앞세움**.
11. **구동사 idiomatic 우선** (`KB-07`): give up·carry out(=수행)·come up with(=고안)·turn out(=판명)·break out(=발생)·put off(=연기)처럼 글자뜻≠실제뜻인 구동사를 우선 추출.

---

## 한국어 뜻 작성 기준
- 본문 **문맥에 맞는** 대표 뜻 1~2개
- 품사 포함: 동사 → `~하다`, 명사 → `~것, ~함`, 형용사 → `~한`
- 최대 20~30자 이내로 간결하게
- 동사구는 전체를 하나의 항목으로 작성 (`rely on`, `make sure` 등)

## 영어 단어(원형) 작성 기준
- 원형 (동사 ran/running → run · 명사 books → book · 비교급 better → good)
- 숙어·구동사는 띄어쓰기 유지 (give up, in terms of, figure out)
- 고유명사 아닌 이상 소문자로 통일
- 원문 직접 복사 권장 (단, 활용형은 원형으로 보정)
