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
| SubCategory | → Category (FK) | fab, device, recipe_id, maker |
| Detail | → SubCategory (FK) | apc_para, thk_para, target, pre_target, pre_thk_period, rr_para, offset_group, rr_max, rr_period, if_rr, pre_thk_vm_source(AUTO/POST) |
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
  ├ History 조회
  └ Simulation

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
| `/simulation/` | simulation | Simulation |
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

### Merge Hub route(process_id) 적재 제외
- `Merge_Data.run(..., exclude_process_ids=[...])`: 목록의 process_id 행은 적재에서 제외
- merge DB: DataLake 초기 로드·HUB 업데이트 공통 적용 (`_prepare_merge_df`에서 필터)
- PRE_THK_INFO: 사전공정 초기 로드(SRC/MES)·HUB upsert, simple·pivot 경로 모두 적용 (`_drop_excluded_routes`)
  - 단, PRE_THK 데이터 소스 쿼리 결과에 process_id 컬럼(대소문자 무관)이 있어야 동작 — 없으면 해당 소스는 필터 없이 기존 동작
- 각 `algorithm_new/merge/*/Merge_Hub.py`의 `EXCLUDE_PROCESS_IDS` 리스트에 route ID를 등록해서 사용 (기본 `[]` = 제외 없음)
- 이미 적재된 과거 데이터는 지우지 않음 — 필요 시 MongoDB에서 해당 process_id 문서 수동 삭제

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

## nAPC 이관 (MLflow / AI Studio) — 검토·예제 단계

MICO를 HCP → nAPC로 전환하면서 핵심 알고리즘을 MLflow 기반 AI Studio에 올리는 작업.
상세 내용·실행 순서·미해결 항목은 **`nAPC/README.md`** 참고.

- `nAPC/simple_example.py` — 한 파일 최소 예제. pre_thk_vm → removal_rate → offset 3단계 체인을 사칙연산으로 구현 (로컬 저장까지)
- `nAPC/simple_upload.py` — 위 예제 + tracking 서버 업로드/레지스트리 등록. 사내에서 실제로 올려볼 파일
  - 사내 MLflow 예제(ElasticNet/iris)와 같은 순서·구조. `# %%` 셀 8개 선형 흐름, 노트북에 붙여넣기 가능
  - 상단 `{TODO}` 2개(uri, password)만 채우면 업로드. 그대로 두면 로컬 저장만
  - 인증 필수: `MLFLOW_TRACKING_USERNAME/PASSWORD` + `MLFLOW_TRACKING_INSECURE_TLS=true` (없으면 401)
  - input_example 형식이 서빙 계약을 결정함 — 엔벨로프를 주면 MLflow가 그 스키마를 강제하고,
    predict에는 `input` 컬럼 1개짜리 DataFrame(셀=블록 리스트)으로 넘어옴
  - 래퍼를 파일 안에 두면 cloudpickle이 값으로 직렬화 → `code_paths` 불필요
- `nAPC/simple_call.py` — 올린 모델을 불러서 호출하고 반환값 확인 (레지스트리/로컬/HTTP 3경로)
  - `model.predict(payload)` 는 payload를 제자리에서 변형(int→np.int64)하므로 호출마다 새로 만들 것
  - [7] 진단 셀: 엔드포인트가 `NOT_IMPLEMENTED`/`Inference Error`를 주면 `aiu_custom.predict.ModelWrapper` 소스로 사내 서빙 계약 확인
- ModelWrapper는 `predict(context, model_input, params=None)` + `predict_stream()` 둘 다 구현 — 서빙 런타임 호출 방식 차이 대비
- `nAPC/mini_upload.py` / `mini_call.py` — 가장 단순한 최소 재현 (숫자 배열 in/out, 50줄·15줄)
  - config·artifact·load_context·predict_stream 없이 predict() 하나
  - 계산은 simple_upload.py 와 같은 3단계. 입력 `[a,b,post_thk,pol_time,target]` → 출력 `[offset,...]` 1차원
  - 출력 1차원이 중요 — 2차원이면 사내 런타임이 `setting an array element with a sequence`로 죽음
    (MLflow 표준 서버는 2차원도 200. 이 제약은 사내 런타임 쪽)
  - equipment_id는 문자열이라 숫자 배열에서 제외 — 행 순서로 구분
  - 이게 되면 문제는 문자열 JSON 입출력 형식, 이것도 안 되면 서빙 런타임 자체 문제
  - `datatype`은 사내 예제와 같은 `"ndarray"` 사용. MLflow는 이 값을 안 따지므로(ndarray/FP64/BYTES 모두 200)
    이 필드를 읽는 건 사내 런타임 — `NOT_IMPLEMENTED`가 모르는 datatype에서 났을 수 있음
- `nAPC/iris_upload.py` / `iris_call.py` — 대조 실험. 사내 예제(ElasticNet+iris) 그대로 재현, `aiu_custom`만 최소 래퍼로 대체
  - 이것도 엔드포인트에서 실패하면 우리 코드 문제가 아님 → 플랫폼/배포 설정 또는 `aiu_custom` 필요
- `nAPC/simple_probe.py` — 엔드포인트가 받는 payload 형식을 후보 8종 던져 좁히는 탐침
  - MLflow 표준 서버 기준 `{'input':...}` / `{'inputs':{'input':...}}` / dataframe_split / dataframe_records 4종 통과
  - 전부 실패하면 payload가 아니라 서빙 런타임 호출 방식 문제 → `aiu_custom` 패키지 출처를 담당자에게 확인
- `nAPC/mico_deploy/` — 작업지시서 구조 전체 예제 (save/register/test)
- 핵심: MLflow pyfunc는 ML 모델이 아니어도 됨. `predict()` 메서드만 있으면 임의 파이썬 코드 서빙 가능
- 구조: 매시간 학습 = 스케줄 실행(타임아웃 없음) / 시뮬레이션 = 엔드포인트(60초 제한) 로 분리
- merge_df(8.8MB)는 HTTP로 보내지 않고 컨테이너가 Mongo Hub에서 직접 조회
- 이관 순서: offset → removal_rate → pre_thk_vm (역순, pre_thk_vm이 제일 무거움)

---

## 예정 작업
- 사내 DB 연동 (학습값, History, APC 수정건수, 산포 개선 전 항목)
- Skynet API 실제 연동 (`_mock_skynet_api()` 함수 교체)
- APC 산식(Pre Thickness / Removal Rate / Offset) 기반 Simulation 결과값 표시
- Dashboard 실제 데이터 연결
- **알람 발생 현황** (신규)
  - 알람 누적 관리 (발생 일시, 장비, 공정, 알람 종류 등 이력 저장)
  - 알람 원인 분석 화면 (발생 패턴, 빈도, 원인 분류 등)

---

## 구현 완료 — CBL HM NIT CMP Pre_Thk VM 학습 소스 문제

> 2026-08-19 검토 완료 → 2026-08-25 방안 3 구현 완료 (브랜치 claude/cbl-hm-nit-cmp-post-thk-u4a9zw).
> 단, "추가 개선" 항목(POST 모드 detrend RR 계산에 ITM 실측값 사용)은 **적용하지 않음** — detrend는 기존 `RR = (Pre_Target − post) / Pol_Time` 그대로 사용.
>
> 구현 내역: Detail 모델에 `pre_thk_vm_source` 필드(AUTO/POST, 기본 AUTO) 추가 (migration 0022),
> Detail CRUD 화면(detail_list.html)·Set-up 현황 수정 모달(setup_status.html)에 선택 UI 추가,
> Get_Data.py mico_info_key에 `Pre_Thk_VM_Source` 컬럼 추가,
> Module.py `compute_pre_thk_vm`에서 `POST`면 ITM이 있어도 detrend 경로로 분기 (`use_itm = ITM존재 and not force_post`).
> 컬럼이 없는 구버전 mico_info_key는 기존 AUTO 동작 유지. Simulation·RR 학습의 ITM 사용은 변경 없음.

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
