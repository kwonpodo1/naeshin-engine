<!-- 단일 소스: naeshin_engine/rules/analysis_rules.md — auto·studio 공유 내용분석(구문분석) 규칙. auto 전용 운영(PDF 레이아웃·섹션 데이터 필드·파일 저장)은 auto docs/RULES.md 에 둔다. 여기를 고치면 auto 는 즉시(editable), studio 는 패키지 버전 핀으로 반영. -->

# 내신 자료 자동화 규칙 — 내용분석 편

> 분석 방식의 외부 근거(교육부 고시·교과서·SLA 연구 검증): `docs/research/KB-01-내용분석-구문분석.md`
> 변형문제 규칙은 `naeshin_engine/rules/exam_rules.md` 참고

---

## 0. 분석 철학 (2022 개정 교육과정 정합)

2022 개정 영어과 교육과정은 문법을 독립 평가영역이 아니라 **'언어 지식'**으로 다루고, 평가는 *단편적 문법·어휘 지식의 단순 확인을 지양하고 학습 내용을 새로운 맥락에 적용하는 역량*에 초점을 둔다(교육부 고시 2022-33호).

→ 내용분석 자료의 목적은 **"문법 용어 암기 확인"이 아니라 "구문이 문맥에서 어떻게 작동하는지"**를 한눈에 보여주는 것이다. 태그·노트·한줄해석은 모두 이 목적에 종속된다.

- **청킹 근거**: 긴 문장을 의미 단위로 끊어 표시하면 작업기억 부담이 줄어 독해를 돕는다(특히 중하위권). (`KB-01` A7)
- **신호화 근거**: 구문 요소에 색·태그를 입히는 것은 멀티미디어 학습의 '신호화 원리'로 학습효과가 실증된다(메타분석 파지 g⁺=0.53). 단 **task-relevant 신호일 때만** 유효하고, 색을 과하게 쓰면(over-signaling) 역효과 → **현 색상 수(4색)를 늘리지 않는다.**

---

## 1. 적용 가능한 지문 유형

이 규칙은 **모든 영어 지문**에 동일하게 적용된다.

| 지문 종류 | 예시 |
|---------|------|
| 교과서 본문 | NE능률(오선영), 천재(이재영), 비상(홍민표) 등 |
| 수능 기출 지문 | 2024 수능 23번, 2023 수능 28번 등 |
| 모의고사 지문 | 2025 11월 고2 모의고사 24번 등 |
| EBS 교재 지문 | 수능특강 영어 1강, 수능완성 등 |
| 기타 외부 지문 | 독해 교재, 학원 교재 등 |

---

## 3. 색상 코드

| 코드 | 색상 | 용도 |
|------|------|------|
| `"blue"` | #1a56cc | 주어, 명사구, 보어 |
| `"orange"` | #e06c00 | 핵심 동사, 중요 구문, 관용표현 |
| `"green"` | #1a7a3c | 관계사절, 분사구, 부사절, 동격 |
| `"red"` | #cc0000 | 서술형 강조 (자동 적용, 직접 사용 불필요) |

---

## 4. 반드시 라벨링할 문법 요소

| 요소 | 라벨 텍스트 예시 | 색상 |
|------|----------------|------|
| 주어 | `S`, `S (동명사구)`, `S (명사절)`, `S (to부정사구)` | blue |
| 동사 | `V`, `V (수동태)`, `V (조동사+완료)`, `V (현재완료진행)`, `V (미래진행)`, `V (병렬)`, `V (명령문)`, `V+C` | orange |
| 목적어 | `O`, `IO`, `DO`, `O (명사절)`, `O (동명사)`, `O (to부정사)` | blue |
| 보어 | `C`, `OC`, `C (to부정사)`, `C (분사)` | blue |
| 가주어/진주어 | `가주어`, `진주어`, `가목적어`, `진목적어` | blue |
| 부사구/절 | `부사구`, `연결부사구`, `시간 부사절`, `조건 부사절`, `양보 부사절`, `이유 부사절`, `목적 부사절`, `결과 부사절`, `양보 부사구` | green |
| 관계사절 | `주격 관계대명사절`, `목적격 관계대명사절`, `목적격 관계대명사절 (생략)`, `계속적 용법 관계대명사절`, `관계부사절`, `선행사포함 관계대명사 what` | green |
| 분사구 | `현재분사 후치수식`, `과거분사 후치수식`, `수단의 분사구`, `분사구문`, `being 생략 분사구문`, `접속사 + 분사구문` | green |
| to부정사 | `to부정사(명사적)`, `to부정사(형용사적)`, `to부정사(부사적)`, `to부정사(OC)`, `분리부정사` | green/orange |
| 동명사 | `동명사 주어`, `전치사+동명사`, `동명사(목적어)`, `동명사(보어)` | orange/blue |
| 강조구문 | `강조구문`, `It ~ that 강조구문`, `It's not until ~ that` | orange |
| 도치 | `도치문`, `부정어 도치`, `Only + 부사구 도치`, `가정법 if 생략 도치` | orange |
| 동격 | `동격`, `동격 that절`, `동격 명사구` | green |
| 삽입구 | `삽입구`, `삽입구(양보)`, `호칭` | green |
| by구문/전치사구 | `by구문`, `전치사구` | green |

### 문장 형식(5형식) 표준 체계 (한국 학교문법 표준)

문장 핵심 골격은 아래 5형식 라벨로 통일한다 (출처: 미래엔 「교과서 필수 영문법 A to Z」 등, `KB-01` A1):

| 형식 | 구조 | 동사 유형 |
|------|------|----------|
| 1형식 | `S+V` | 완전자동사 |
| 2형식 | `S+V+SC` | 불완전자동사 (SC = 명사·형용사, 상위 수준에선 to부정사·동명사·명사절·of+추상명사) |
| 3형식 | `S+V+O` | 완전타동사 |
| 4형식 | `S+V+IO+DO` | 수여동사 (IO = ~에게 / DO = ~를) |
| 5형식 | `S+V+O+OC` | 불완전타동사 |

- 기호: `S / V / O / C`, `IO / DO / SC / OC`
- 4→3형식 전환 전치사: **give류 = to** / **buy·make·find = for** / **ask류 = of**
- ※ 5형식 체계는 학술적 비판이 있으나 한국 학교·EBS·내신의 사실상 표준이므로 채택한다.

### 태그 선정 원칙 (참고자료 학습 반영)

- **문장 구성요소를 빠뜨리지 말고 순서대로 표시**: `[호칭] [S] [V] [O]`처럼 문장 맨 앞부터 끝까지 요소를 열거
- **시제/태 명시**: 단순 `[V]`가 아니라 `[V (수동태)]`, `[V (미래진행)]`, `[V (현재완료진행)]` 식으로 명시적으로 표기
- **병렬 동사는 반드시 표시**: `have baggage to handle, have a long wait, and may require information` 같은 경우 `[V (병렬)]`
- **생략 표시**: 관계대명사가 생략되면 `[목적격 관계대명사절 (생략)]`로 명시
- **절 범위는 대괄호로만 표기** (디자인 상 `【 】` 등은 사용하지 않음)
- **동사 어법 정밀화** (`KB-05`): `[V]` 태깅 시 시제(현재완료/과거완료/시제일치)·태(자동사 수동불가·5형식 수동 시 OC to부정사 부활·진행/완료 수동)·준동사(**본동사 자리 vs 준동사 자리** 구분·분사 능동(-ing)/수동(p.p.))를 정확히 반영. 동사 변형이 어법의 ~50%(`KB-02` A4)이므로 핵심 기준선.
- **접미사로 품사 자리 인식** (`KB-07`): -tion/-ment(명사)·-ous/-ful/-able(형용사)·-ize/-ate(동사)·-ly(부사)로 품사 자리 판별 — 어법 형용사/부사·명사/동사 자리 + 어휘 뜻 추론. ⚠️ friendly·costly=형용사·hardly≠hard 예외 주의.

---

## 5. 문법 노트 작성 기준

### 기본 형식

- **구문 풀이**: `표현 = 의미` 형식 (예: `map out = 계획하다`)
- **구문 패턴**: `패턴: 의미` (예: `help + O + V원형: O가 V하도록 돕다`)
- **주의 포인트**: `★ to는 전치사 → 반드시 동명사` 처럼 시험에 자주 나오는 혼동 포인트 강조
- **수동태**: `be p.p. by: ~에 의해 ~되다`
- **조동사**: `may have p.p.: ~했을지도 모른다(과거 추측)`

### 여러 포인트 병기 (청크 기반 — 참고자료 학습 반영)

- 한 문장에 포인트가 2개 이상이면 **슬래시(`/`) 로 나열**
  - 예: `be committed to -ing: ~하는 데 전념하다 / as ... as possible: 가능한 한 ...`
  - 예: `ask + O + to-V: O에게 V해 달라고 요청하다 / located ~: parking lot을 수식`
- **2~4개**까지 병기 가능. 너무 많으면 중요한 것만 취사선택
- 어휘 주석도 포함 가능: `intercity traveler: 도시 간 이동 승객 / through: ~을 통과하여`
- 관용표현/숙어도 가능: `on the other hand: 반면에 / in a hurry: 서둘러`
- **연결사 의미 인식** (`KB-06`): 연결사는 뜻풀이를 넘어 **논리 방향**을 노트에 표시 — 대조·역접(however=앞과 반대)·인과(therefore=앞이 원인)·예시(for example=뒤가 사례)·환언(in other words=앞의 재진술)·통념반박(not A but B=but 뒤가 필자 주장). 주제·요지 포착의 핵심 단서.

### 문장 구조 분석 (분석 깊이 향상)

문장의 핵심 포인트를 잡을 때 다음을 놓치지 말 것:

1. **주어-동사 거리가 먼 경우**: 긴 수식어구가 끼어 있으면 주어를 콕 집어서 표시
2. **병렬구조**: `A, B, and C` 또는 `V1, V2, and V3` 형태 반드시 짚기
3. **생략된 관계대명사**: `the information (that) they need` 같은 경우 `(that) 생략` 노트
4. **분사구문의 의미**: 때·이유·조건·양보·부대상황(동시동작 as / 연속동작 and)의 **5종 중 무엇인지 note에 명시**. 분사구문 = "부사절을 부사구로 바꾼 것"(접속사·중복 주어 삭제 → 동사 -ing), 부정은 분사 앞 `Not/Never` (출처: `KB-01` A3)
5. **수식어의 위치**: 과거분사구/현재분사구가 후치수식하면 반드시 태그

### 끊어읽기(직독직해) 구조 인식 (참고 원칙)

한국 시험영어의 표준 끊어읽기 표기는 **의미 단위(구) 경계 = `/`, 절 경계 = `//`** 2단계다(미래엔 공식 자료, `KB-01` A4). naeshin-auto는 이 경계를 별도 슬래시로 본문에 넣지 않고 **`highlights`의 절·구 단위 태깅으로 구현**한다 — 절(관계사절/부사절/명사절)과 구(전치사구/분사구/to부정사구)를 빠짐없이 묶어 태그하면 끊어읽기 단위가 자동으로 드러난다.

> ⚠️ `note` 안의 슬래시(`/`)는 **"여러 문법 포인트 병기"** 용도이며, 위 끊어읽기 경계 슬래시(`/`·`//`)와는 다른 개념이다. 혼동하지 말 것.

---

## 6. 서술형 예상 문장 선정 기준 (star: True)

### 최고 우선순위

| 구문 | 예시 |
|------|------|
| It ~ that 강조구문 | It was his talent **that** led him to Disney. |
| It's not until ~ that (시간 강조) | It was not until 1950 that **he was awarded** the Nobel Prize. |
| 동명사 주어 | **Mapping out** a plan can be demanding. |
| 가정법 if 생략 도치 | **Had** the Nazis not murdered her, she would have accomplished ... |
| 가주어-진주어 + 의미상주어 | it is common **for people** to answer incorrectly |
| 가목적어-진목적어 | find **it** hard **to accept** the notion |

### 높은 우선순위

| 구문 | 예시 |
|------|------|
| 5형식 (help/enable/allow/encourage/motivate/cause/get/lead/require/force + O + to-V) | **allow us to cultivate** extensive networks |
| 지각/사역동사 + O + 원형부정사/분사 | **saw Mr. Grear talking**; **make us feel** stressed |
| so ~ that / such (a/an) ~ that | was **so strong that** it kept her moving |
| dedicate/commit/devote A **to** -ing (to = 전치사) | dedicated his life **to exploring** |
| succeed/fail **in** -ing | succeeded **in developing** |
| keep/leave/find + O + -ing/-ed (5형식) | kept her **moving** forward |
| not A but B / not only A but (also) B / B as well as A / neither A nor B | **not A but B**, **neither too easy nor too difficult** |
| the 비교급 ~, the 비교급 ~ | **the less** you use it, **the more likely** you are to fail |
| prepare/provide A for/with B / A not in B but in C | **provide** students **with** skill set |
| instead of / because of / despite / in spite of + 동명사 | **instead of staying** focused |

### 중간 우선순위

| 구문 | 예시 |
|------|------|
| 계속적 용법 관계대명사 (which의 선행사=앞 절) | ..., **which** highlights the risks |
| 선행사포함 관계대명사 what | understand **what** he said |
| 관계부사 where/when/how + 완전한 문장 | this is **where** good design is essential |
| 도치구문 (Only/Rarely/Never/Hardly + 조동사 + S + V) | **Rarely does consciousness** come to a standstill |
| 형용사구/분사구 후치수식 | equipment **available** at that time; signals **contained** within them |
| 수동태 + by구문 | was disrupted **when** he was diagnosed |
| 현재완료진행 / 과거완료 | has been **recognized** for years; **had tracked** the fire before |
| 완료부정사 (to have p.p.) | pleased **to have been invited** |
| 분사구문 (특히 being 생략형) | **Shaped** by evolution, hatchlings started ...; **(Being) born** in NY |
| with 분사구문 (부대상황) | **with his legs hanging** over the edge |
| 접속사 + 분사구문 (의미 명확화) | **while trying** to change it |
| spend + 시간/돈 + -ing | **spend much of their time looking for** food |
| 동격 that절 (which ✗) | the fact **that** federal legislation was enacted |

### 판단 원칙 (참고자료 학습 반영)

- **서술형 표시(`#` + 노트의 `★ 서술형 예상: 포인트`)는 한 문항당 2~4개가 이상적** — 너무 많으면 강조 효과 상실
- **문법 포인트가 복합적인 경우 우선**: 가주어-진주어 + 5형식처럼 2개 이상 포인트가 겹치는 문장이 서술형에 가장 잘 나옴
- **어법 혼동 포인트 포함 문장 우선**: to부정사 vs 동명사, 능동 vs 수동, 관계사 선택 등
- **앞뒤 문맥 없이도 의미가 통하는 문장 선호**: 조건 영작/어순 배열 문제로 그대로 쓸 수 있음
- **이론 근거** (`KB-01` A5): 끊어읽기 경계가 생기는 구문(가주어진주어·so~that·관계사절·삽입/동격·분사구문)이 곧 내신·수능 서술형/어법 출제 포인트와 겹친다. 위 우선순위 표가 이 대응 관계를 반영한 것이다.
- **고급 구문 표준 공식** (`KB-04`, 미래엔 1차 출처): 가정법(과거 `If+과거동사 ~, 주어+would+동사원형` / 과거완료 `If+had p.p. ~, 주어+would have p.p.` / 혼합 / **if 생략 도치** `Were I ~`·`Had I ~`)·`It ~ that` 강조구문·도치(부정어 문두 → 조동사+주어)·비교(`the 비교급 ~, the 비교급 ~`)의 정확한 공식과 전환은 KB-04 참조. 서술형은 특히 **가정법 시제 짝**과 **if 생략 도치**가 최빈출.
- **동사 핵심 어법 함정** (`KB-05`, 다출처 1차): 시제(`since`/`ago`·부사절 will 대용)·태(자동사 수동불가·사역지각 수동 시 to부정사 부활)·수일치(`the number of`(단수)/`a number of`(복수)·상관접속사 후항 일치·도치)·준동사(**본동사 vs 준동사 자리**·사역지각 목적보어 동사원형·`be used to -ing` vs `used to V`)는 **어법의 ~50%(`KB-02` A4)인 최빈출** → 이 함정을 포함한 문장은 어법·서술형 출제 1순위(`KB-04`=심화, `KB-05`=핵심).
