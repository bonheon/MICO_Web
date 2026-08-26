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

## 예정 작업
- 사내 DB 연동 (학습값, History, APC 수정건수, 산포 개선 전 항목)
- Skynet API 실제 연동 (`_mock_skynet_api()` 함수 교체)
- APC 산식(Pre Thickness / Removal Rate / Offset) 기반 Simulation 결과값 표시
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
