# MICO Web 프로젝트 컨텍스트

Django 기반 MICO (Model Integrated Process Control Optimization) 웹 애플리케이션.
반도체 CMP 공정의 APC(Advanced Process Control) 파라미터 관리 및 학습값 모니터링을 위한 내부 웹툴.

---

## 기본 정보

- **경로:** `/Users/bonheonkoo/MICO_Web`
- **스택:** Django 4.1.13, SQLite, Python 3.10
- **프론트:** Bootstrap 5.3.2, Bootstrap Icons 1.11.3, Chart.js 4.4.2
- **메인 앱:** `setup_mico` (`mico` 앱은 미사용)
- **superuser:** 2057197 / Qhsjsl@341
- **DEBUG:** False (커스텀 에러 페이지 적용)

### 서버 실행
```bash
python3 manage.py runserver 0.0.0.0:8000
```
- 로컬: http://127.0.0.1:8000
- LAN: http://192.168.0.23:8000

---

## 데이터 모델 (`setup_mico/models.py`)

| 모델 | 관계 | 주요 필드 |
|------|------|-----------|
| Category | - | product, oper_id, oper_desc (CharField max_length=100) |
| SimulFormulaConfig | → Category (FK) | zone(''=공통), params (JSONField, APC 산식 설정) |
| SubCategory | → Category (FK) | fab, device, recipe_id, maker |
| Detail | → SubCategory (FK) | apc_para, thk_para, target, pre_target, pre_thk_period, rr_para, offset_group, rr_max, rr_period, if_rr |
| RecipeGroup | → Category (FK), SubCategory (M2M) | name, subcategories |
| Voc | → User (FK x2) | title, content, reply, replied_by, replied_at |
| SetupHistory | → User (FK) | action, model_type, object_id, object_repr, changes (JSONField) |
| AccessLog | → User (FK) | path, ip_address, accessed_at |

- **Category.__str__:** `product / oper_id / oper_desc` (oper_desc 없으면 `product / oper_id`)
- **migration 순서:** 0001~0006(기존) → 0007(Voc) → 0008(RecipeGroup) → 0009(AccessLog) → 0010(SetupHistory) → 0011(oper_desc CharField)

---

## 사이드바 메뉴 구조

```
MAIN
  └ Dashboard

CONFIGURATION
  ├ Set-up 현황
  └ Set-up (콜랩스 서브메뉴)
      ├ Category
      ├ SubCategory
      ├ Detail
      └ Recipe Grouping
  └ 변경 이력

LEARNING
  ├ 학습값
  ├ Trend
  ├ Simulation 결과 (web 조회)
  ├ Simulation (Spotfire)
  └ History 조회

IMPROVEMENT
  ├ 산포 개선 현황
  └ APC 수정건수

SUPPORT
  └ VOC 게시판

ADMIN (superuser만 노출)
  └ 접속 현황
```

---

## 전체 URL / View 목록

| URL | view name | 설명 |
|-----|-----------|------|
| `/` | dashboard | Dashboard (샘플 데이터) |
| `/login/` | login | 로그인 (Skynet 버튼 메인 + 아이디/비밀번호 접힘) |
| `/login/skynet/` | skynet_login | Skynet SSO 로그인 (현재 Mock) |
| `/register/` | register | 회원가입 (staff 전용) |
| `/logout/` | logout | 로그아웃 |
| `/setup/status/` | setup_status | Set-up 현황 트리뷰 |
| `/setup/history/` | setup_history | Set-up 변경 이력 |
| `/setup/category/` | category_list | Category CRUD |
| `/setup/subcategory/` | subcategory_list | SubCategory CRUD |
| `/setup/detail/` | detail_list | Detail CRUD |
| `/setup/recipe-group/` | recipe_group_list | Recipe Grouping |
| `/learning/` | learning_values | 학습값 Trend (샘플) |
| `/learning/history/` | learning_history | History 조회 (DB 미연결) |
| `/simulation/` | simulation | Simulation (Spotfire 링크) |
| `/simulation/result/` | simulation_result | Simulation 결과 web 조회 (Simul APC/THK, THK/RR/Pre Thk/Offset) |
| `/simulation/result/data/` | simulation_result_data | 위 화면의 JSON API (APC 산식 재계산 포함) |
| `/simulation/result/formula/` | simulation_formula | APC 산식 설정 저장/삭제 (POST) |
| `/apc/history/` | apc_history | APC 수정건수 (DB 미연결) |
| `/improvement/dispersion/` | dispersion | 산포 개선 현황 (DB 미연결) |
| `/voc/` | voc_list | VOC 게시판 |
| `/admin-stats/` | access_stats | 접속 현황 (superuser only) |

---

## 완료된 기능 상세

### 인증
- Skynet SSO 로그인: `_mock_skynet_api()` Mock 구현, 실제 API 연동 시 해당 함수만 교체
- Skynet 유저: `set_unusable_password()` 적용, Django 비밀번호 없음
- 회원가입: staff만 접근 가능

### 커스텀 에러 페이지
- `DEBUG=False`, `config/urls.py`에 handler400/403/404/500 등록
- `templates/errors/` 에 400/403/404/500.html

### Set-up (Category / SubCategory / Detail)
- 추가 / 수정 / 삭제 / 복사
- **컬럼별 검색:** thead 아래 검색 row → 실시간 JS 필터링 (AND 조건)

### Set-up 변경 이력 (`/setup/history/`)
- `_sub_repr()`, `_det_repr()` 헬퍼로 object_repr에 전체 계층 경로 저장
  - 형식: `product/oper_id/oper_desc > fab/device/recipe_id > apc_para/thk_para`
- 필터 1행: CATEGORY (Product / Oper ID / Oper Desc)
  - product/oper_id 검색 → object_repr__icontains (전 계층 포함)
  - oper_desc 검색 → 해당 Category의 모든 하위 이력 포함
- 필터 2행: 구분 / 작업 / 작업자 / 날짜

### 학습값
- Category 선택 시 드롭다운에 `product / oper_id — oper_desc` 표시
- 선택 후 카드 하단에 oper_desc 설명 표시

### Simulation 결과 → MongoDB 적재 → web 조회
Spotfire 연동용 CSV 대신 **다른 학습값과 같은 MongoDB** 에 적재하고 web 에서 바로 조회.

**컬렉션명 (다른 학습 테이블과 동일 규칙 — 공정명 포함)**
```
MICO_PRE_THK_{Lot_Code}_{Oper_Desc}_{Fab}_Period   (Pre Thk 학습, MongoDB)
MICO_Removal_Rate_{Lot_Code}_{Oper_Desc}_{Fab}     (RR 학습,      MongoDB)
MICO_OFFSET_{Lot_Code}_{Oper_Desc}_{Fab}           (Offset 학습,  MongoDB)
MICO_Simulation_{Lot_Code}_{Oper_Desc}_{Fab}       (Simulation 결과, MongoDB)
```
- zone(13P / EDGE / EXED / Z5 …) 은 컬렉션 분리 대신 `ZONE` 필드로 구분
- Lot_Code = Category.product / Oper_Desc = Category.oper_desc / Fab = SubCategory.fab
- 매 실행이 전체 재계산이라 적재 전 해당 컬렉션을 비운다 (`_clear_collection`)

**접속 주소 (한 곳에서만 관리)**
| 환경 | 위치 |
|------|------|
| 배치 (`algorithm_new`) | `Common/Simulation.py` 의 `_MICO_URL` / `_MICO_DB` |
| web (`setup_mico`) | `config/settings.py` 의 `MICO_MONGO_URL` / `MICO_MONGO_DB` (환경변수로 덮어쓰기 가능) |

두 환경이 **같은 MongoDB** 를 가리켜야 한다. web 은 `pymongo` 필요.
APC 산식 설정(`SimulFormulaConfig`)만 Set-up 정보라 Django DB 에 남는다.

**구성 파일**
| 파일 | 역할 |
|------|------|
| `setup_mico/apc_formula.py` | **APC 산식 단일 소스** (Simul_APC / Simul_THK, 안전한 수식 평가) — web 전용 |
| `setup_mico/simulation_db.py` | 컬렉션 명명 규칙 + MongoDB 조회 helper + 산식 설정 load/save |
| `algorithm_new/Common/Simulation.py` | `_add_view_columns()` 로 web 표준 컬럼 생성 → `_save_results_db()` (MongoDB 적재) |
| `setup_mico/views.py` | `simulation_result`, `simulation_result_data` |
| `algorithm_new/test_dram_m1cu_simul.py` | **[TEST 삭제]** 로컬 검증 러너 (학습 테이블 샘플 생성 + 적재) |

**환경 분리 (중요)**
사내에서 `algorithm_new`(배치)와 `setup_mico`(web)는 **별개 환경에 배포**된다.
→ `algorithm_new` 는 `setup_mico` 를 import 하면 안 된다.
아래 짝은 import 로 공유하지 않고 각자 정의하므로 **함께 수정**할 것:
- `Simulation.SAVE_COLUMNS` ↔ `simulation_db.VIEW_COLUMNS`
- `Simulation.table_name()` ↔ `simulation_db.table_name()` (`TABLE_PREFIX` / `KEEP_SPACE_IN_TABLE_NAME`)

**web 표준 컬럼** (공정/zone 무관하게 이름 고정 — 차트 코드 공통화용)
`ZONE / APC_Para / Thk_Para / Formula / Target / Pre_Target / Pad_Seperation / THK / APC_Value /
Consumable(_Para) / RR_Actual / RR_DB / RR_Normal / RR_Weighted / RR_Current / RR_IF /
Pre_Thk_VM / Pre_Thk_MA / Pre_Thk_ITM / Pre_Thk_Actual / Pre_Thk_Implied / OFFSET_Learn / OFFSET_Actual`

APC 산식 **재료** 컬럼만 적재 (`simulation_db.FORMULA_INPUT_COLUMNS`)
`Pol_Time_1 / Pol_Time_2 / Ref_Count / Ref_YN / THK_13P / Target_13P /
 Ref_{1..4}_{APC,Post,13P,Pre_VM,OFFSET,Pre_ITM}`

산식 **결과** 컬럼(`FB_1~4 / Simul_APC / Simul_APC_Limit / Simul_RR / Removal_Amount /
Bias_* / Simul_Bias / Simul_THK`)은 **적재하지 않는다.**
web 화면에서 key-in 한 파라미터로 값이 달라지므로 조회 시점에 `apc_formula` 가 계산한다.
- `Simul_THK_13P`(PRESSURE 재료)도 TIME 산식의 결과라 저장하지 않는다.
  web 이 같은 기간의 13P 행을 함께 읽어 계산 후 `substrate_id` 로 붙인다
  (`views._attach_simul_thk_13p`, 샘플링 누락 방지를 위해 `fetch(max_rows=None)`)

**로컬 → 사내 전환**
- MongoDB 주소만 교체 (위 '접속 주소' 표 참조) — 코드 수정 없음
- 로컬 검증은 `test_dram_m1cu_simul.py`, 사내는 `simulation/{공정}/Simulation_Hub.py` 를 그대로 실행
- CSV 출력은 `run(export_csv=...)` — 기본값은 `export_dir` 존재 시에만 출력(로컬 자동 skip)

### APC 산식 (Simul_APC / Simul_THK)
학습값으로 실제 내려갈 APC 값을 산출하고, 그 값으로 연마했을 때의 두께를 시뮬레이션.

**단일 소스: `setup_mico/apc_formula.py`** — 배치(`Simulation.py`)와 web(`views.py`)이 같은 함수를 호출하므로
화면에서 파라미터를 바꿔 본 값과 배치가 적재하는 값이 어긋날 수 없다.
zone 의 `FB_Type` 으로 **TIME / PRESSURE 두 모드**를 자동 판별한다 (`detect_mode`).

#### TIME (13P) — 두께를 Target 에 맞춤
```
FB_i   = Ref_APC + (Ref_Post - Target + (Pre_Thk - Ref_Pre_VM) * pre_weight) / RR_DB * rr_weight
                 + Simul_OFFSET - Ref_OFFSET              (Ref_1~4 각각)
Simul_APC       = Σ weight_n1..nn × FB   (n = 쓸 수 있는 Ref 개수, 중간이 비면 앞으로 당겨 결합)
Linear          = (Pre_Target + Pre_Thk - Target) / RR_DB + Simul_OFFSET - Pol_Time_1
Simul_APC_Limit = clip(Simul_APC, lower_limit, upper_limit)
Simul_RR        = sign × (Pre_Target + Pre_Thk - THK) / Pol_Time
Removal_Amount  = Simul_RR × (Simul_APC_Limit + Pol_Time_1)
Simul_THK       = Pre_Target + Pre_Thk - sign × Removal_Amount
```
- **`sign`:** Thk_Para 가 REV 계열이면 -1
- **`Pol_Time_1`:** APC 가 제어하지 않는 앞단 고정 step.
  `pol_time_1='auto'` 는 `Pol_Time_2` 컬럼이 있을 때(= step 2개 공정)만 항을 살린다
  (step 1개 공정은 `Pol_Time_1 == Pol_Time` 이라 빼면 안 됨)

#### PRESSURE (EDGE / EXED / Z5 …) — 13P 대비 편차를 0 에 맞춤
두께를 직접 맞추지 않고 **TIME 이 산출한 13P 시뮬 두께에 편차를 더한다.**
편차 정의는 학습측(`Module.py`, `REMOVAL_RATE.py`)의 `BIAS` 와 동일.
**시간 보정값인 Idle OFFSET 은 산식에서 제외** (압력은 시간이 아니므로).
```
Bias_Actual  = (THK - THK_13P) - (Target - Target_13P)        ← 0 이 목표
Bias_Slope   = d(편차)/d(압력)   … eqp_id·recipe_id 별 회귀 (bias_slope 로 고정 가능)
Ref_Bias     = (Ref_Post - Ref_13P) - (Target - Target_13P)
FB_i         = Ref_APC - (Ref_Bias + (Pre_Thk - Ref_Pre_VM) * pre_weight) / Bias_Slope * rr_weight
Linear       = -(Bias_Intercept + Pre_Thk * pre_weight) / Bias_Slope
Simul_Bias   = Bias_Slope × Simul_APC_Limit + Bias_Intercept
Simul_THK    = Simul_THK_13P + (Target - Target_13P) + Simul_Bias
```
- **13P 결과 연결:** `_run_key` 가 TIME 루프 후 `_simul_thk_13p()` 로 substrate_id → Simul_THK
  맵을 만들어 PRESSURE 프레임에 `Simul_THK_13P` 로 붙인다 (`_attach_simul_thk_13p`)
- **FB 부호(-):** TIME 의 RR_DB 는 '제거율'이라 부호가 이미 뒤집혀 있고, Bias_Slope 는
  d(편차)/d(압력) 그대로 → Newton 보정 `-오차/기울기` 를 그대로 사용
- **`bias_min_r2`(기본 0.1) 가드:** 압력은 편차에 반응해 움직인 제어 출력이라 회귀가
  closed-loop 이 된다. 기울기가 0 에 가까우면 나눗셈이 발산하므로, 설명력이 낮은 회귀는
  버리고 NaN('민감도 없음')을 낸다. 신뢰할 값이 있으면 `bias_slope` 에 넣어 고정할 것.

#### 공통
- **Linear 분기 조건:** 쓸 수 있는 Ref 없음 / `Ref_YN='N'` / `Ref_Count == ref_skip_count`(기본 11)
- 모드별로 쓸 수 있는 수식 변수가 다르다 (`EXPR_VARIABLES`) — PRESSURE 에서 `Simul_OFFSET`,
  TIME 에서 `Bias_Slope` 를 쓰면 검증 단계에서 거부된다

**web 에서 key-in (`/simulation/result/` 상단 "APC 산식" 패널)**
- pre_weight / rr_weight / upper·lower limit / Ref 제외 Count
- TIME 전용: Pol_Time_1 처리 / PRESSURE 전용: Bias Slope · 회귀 최소 건수 · 최소 R²
  (zone 을 바꾸면 입력칸과 수식 항목이 그 모드에 맞게 다시 구성됨)
- Ref 개수별 weight (weight_11 / 21·22 / 31·32·33 / 41~44) — 행별 합계 표시
- 수식을 텍스트로 직접 편집 (공정별 산식 수정) — AST 화이트리스트로 검증,
  허용 함수: abs/sqrt/log/exp/where/clip/minimum/maximum/isnan/fillna/nan_to_num
  · TIME 5종: fb / linear / rr / removal / thk
  · PRESSURE 4종: fb / linear / bias / thk
- [재계산] 은 서버에서 다시 계산해 차트 갱신, [기본값으로 저장] 은 `SimulFormulaConfig` 에 보관
  (Category 단위, '이 Zone 에만 적용' 체크 시 zone 별 — 조회 시 공통 위에 zone 설정을 덮어씀)
- 배치 실행도 저장된 설정을 읽어 같은 값으로 적재

**화면 구성 (`/simulation/result/`)**
1. **THK Trend** (메인, 7:3) — 실측 THK vs Simulation THK + Target 기준선 / 우측 Boxplot·산포 비교(산포 변화 %)
2. **APC · RR · Pre Thk · Offset** — 2×2 4분할, 각 셀은 `chartCell()` 로 차트 + 요약표를 한 박스에
   - APC Para: 실제 적용값(회색) vs Simul APC (FB 파랑 / Linear 주황) + limit 밴드, Bias/MAE/RMSE
   - 2번 셀은 모드에 따라 교체 — TIME: Removal Rate(실제 RR vs if>current>weighted>normal) /
     PRESSURE: 편차(BIAS) 실측 vs Simulation + 목표선 0 + Bias Slope·R²·민감도 실패 건수
     (X축 날짜/압력·소모품 토글 공통)
   - Pre Thk VM: pre 챔버별 학습값 / Idle Offset: IDLE 구간별 학습값
   - 표가 길어지면 `.cell-stats` 가 스크롤 (셀 높이 고정)

### Jupyter 노트북
- `notebooks/mico_setup_query.ipynb`: SQLite 직접 연결, Set-up 전체 계층 DataFrame 조회

---

## DB 연동 대기 중인 기능 (수정 포인트)

| 기능 | views.py 함수 | 수정할 변수 |
|------|--------------|------------|
| History 조회 | `learning_history` | `rows = []` → 실제 쿼리 결과 리스트 |
| APC 수정건수 드롭다운 | `apc_history` | `product_list`, `device_list`, `process_list` |
| APC 수정건수 차트 | `apc_history` | `chart_data = None` → 실제 데이터 dict |
| 산포 개선 드롭다운 | `dispersion` | `product_list`, `device_list`, `process_list` |
| 산포 개선 차트 | `dispersion` | `chart_data = None` |
| 학습값 실제 데이터 | `learning_values` | tree 구성 시 실제 학습값 포함 |
| Dashboard 통계 | `dashboard` | context의 count 및 차트 데이터 |

---

## 예정 작업
- 사내 DB 연동 (학습값, History, APC 수정건수, 산포 개선 전 항목)
- Skynet API 실제 연동 (`_mock_skynet_api()` 함수 교체)
- Simulation 결과 web 조회 확장 (PRESSURE zone 실데이터 검증, Ref lot / Online Simulation 항목 표시)
- Dashboard 실제 데이터 연결
- **알람 발생 현황** (신규)
  - 알람 누적 관리 (발생 일시, 장비, 공정, 알람 종류 등 이력 저장)
  - 알람 원인 분석 화면 (발생 패턴, 빈도, 원인 분류 등)

---

## 논의 중 (미구현) — CBL HM NIT CMP Pre_Thk VM 학습 소스 문제

> 2026-08-19 검토 완료, 구현 보류 상태. 별도 브랜치에서 진행 예정.

### 문제
- `Module.compute_pre_thk_vm`(algorithm_new/Common/Module.py:122~)은 **Pre_Thk_Para_ITM 존재 여부** 하나로 학습 경로를 결정
  - ITM 있음 → `BIAS = ITM값 − mean` → moving avg + Pre_Oper2~4 회귀 y축 = BIAS
  - ITM 없음 → post thk 기반 `compute_detrend` → y축 = Detrend_Thk
- CBL HM NIT CMP는 Pre_Thk를 ITM에서 실측하지만, 사전공정 zone 차이가 **입고 두께가 아닌 removal rate에 영향**을 주는 공정
- 따라서 ITM BIAS를 y로 회귀하면 pre_oper2/3 zone 파라미터와 상관이 안 나옴 (zone 효과는 post thk에만 나타남)
- 근본 원인: "어떤 계측값이 존재하는가"와 "VM 회귀 y를 무엇으로 학습할 것인가"가 별개 결정인데 한 필드가 두 역할을 겸함
- 참고: Pre_Thk_Para_ITM은 VM 학습 외에 Simulation.py(178, 644행) 시뮬레이션 베이스, REMOVAL_RATE.py(140, 360~381행) RR 학습에도 사용됨

### 검토한 방안
1. ~~ITM Set-up 삭제~~ → 비추천: Simulation 베이스·RR 학습의 ITM 경로까지 잃음, 재입력 시 동작이 소리 없이 바뀌는 운영 리스크
2. ~~CBL 공정명 하드코딩~~ → 비추천: 공통 코드에 공정 특수 케이스 침투, 동일 유형 공정 재발 시 하드코딩 누적
3. **[채택 방향] Set-up(Detail 모델)에 학습 소스 플래그 추가** — 예: `pre_thk_vm_source` = `AUTO`(기본, 기존 동작 그대로) / `POST`(ITM 있어도 detrend 경로로 학습)
   - Pre_Thk_Para_ITM은 유지 → Simulation·RR 학습은 계속 ITM 사용, VM 학습 경로만 웹에서 공정별 선택
   - 수정 범위: models.py + migration, Detail CRUD 화면, Get_Data.py mico_info_key, Module.py 분기 조건

### 추가 개선 (방안 3에 얹기)
- `POST` 모드에서 detrend 계산 시 `RR = (Pre_Target − post) / Pol_Time` 대신 **ITM 실측값 사용**: `RR = (ITM 실측 pre − post) / Pol_Time`
- 이유: Pre_Target 고정이면 입고 두께 산포가 Detrend_Thk에 섞여 zone 회귀계수에 흡수되고, 시뮬레이션에서 ITM으로 입고 두께를 또 보정하므로 **이중 보정** 발생
- ITM 실측 기반이면 역할 분리 명확: ITM = 입고 두께 담당, zone 회귀 = RR 변동 담당

### 구현 전 확인 사항
- CBL 데이터로 Detrend_Thk(가능하면 ITM 실측 기반) vs pre_oper2/3 zone 파라미터 상관 확인
- 상관이 안 나오면 zone 효과가 pad cycle rolling MA(window=10)에 씻겨나갈 가능성(zone 분포가 시간적으로 뭉치는 경우) 등 detrend 파라미터부터 점검
