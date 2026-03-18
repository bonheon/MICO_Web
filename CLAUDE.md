# MICO Web 프로젝트 컨텍스트

Django 기반 MICO (Manufacturing Intelligence Control) 웹 애플리케이션.
반도체 CMP 공정의 APC(Advanced Process Control) 파라미터 관리 및 학습값 모니터링을 위한 내부 웹툴.

---

## 기본 정보

- **경로:** `/Users/bonheonkoo/MICO_Web`
- **스택:** Django 4.1.13, SQLite, Python 3.10
- **프론트:** Bootstrap 5.3.2, Bootstrap Icons 1.11.3, Chart.js 4.4.2
- **메인 앱:** `setup_mico` (`mico` 앱은 미사용)
- **superuser:** 2057197 / Qhsjsl@341

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
| Category | - | product, oper_id, oper_desc |
| SubCategory | → Category (FK) | fab, device, recipe_id, maker |
| Detail | → SubCategory (FK) | apc_para, thk_para, target, pre_target, pre_thk_period, rr_para, offset_group, rr_max, rr_period, if_rr |
| RecipeGroup | → Category (FK), SubCategory (M2M) | name, subcategories |
| Voc | → User (FK x2) | title, content, reply, replied_by, replied_at |

- **migration 순서:** 0001~0006(기존) → 0007(Voc) → 0008(RecipeGroup)

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

LEARNING
  ├ 학습값
  ├ History 조회
  └ Simulation

IMPROVEMENT
  ├ APC 수정건수
  └ 산포 개선 현황

SUPPORT
  └ VOC 게시판
```

---

## 전체 URL / View 목록

| URL | view name | 설명 |
|-----|-----------|------|
| `/` | dashboard | Dashboard (샘플 데이터) |
| `/login/` | login | 로그인 |
| `/register/` | register | 회원가입 |
| `/logout/` | logout | 로그아웃 |
| `/setup/status/` | setup_status | Set-up 현황 트리뷰 |
| `/setup/category/` | category_list | Category CRUD |
| `/setup/category/create/` | category_create | |
| `/setup/category/<pk>/update/` | category_update | |
| `/setup/category/<pk>/delete/` | category_delete | |
| `/setup/category/<pk>/copy/` | category_copy | |
| `/setup/subcategory/` | subcategory_list | SubCategory CRUD |
| `/setup/subcategory/create/` | subcategory_create | |
| `/setup/subcategory/<pk>/update/` | subcategory_update | |
| `/setup/subcategory/<pk>/delete/` | subcategory_delete | |
| `/setup/subcategory/<pk>/copy/` | subcategory_copy | Detail 포함 여부 선택 |
| `/setup/detail/` | detail_list | Detail CRUD |
| `/setup/detail/create/` | detail_create | |
| `/setup/detail/<pk>/update/` | detail_update | |
| `/setup/detail/<pk>/delete/` | detail_delete | |
| `/setup/detail/<pk>/copy/` | detail_copy | |
| `/setup/recipe-group/` | recipe_group_list | Recipe Grouping |
| `/setup/recipe-group/create/` | recipe_group_create | |
| `/setup/recipe-group/<pk>/update/` | recipe_group_update | |
| `/setup/recipe-group/<pk>/delete/` | recipe_group_delete | |
| `/learning/` | learning_values | 학습값 Trend (샘플) |
| `/learning/history/` | learning_history | History 조회 (DB 미연결) |
| `/simulation/` | simulation | Simulation |
| `/apc/history/` | apc_history | APC 수정건수 (DB 미연결) |
| `/improvement/dispersion/` | dispersion | 산포 개선 현황 (DB 미연결) |
| `/voc/` | voc_list | VOC 게시판 |
| `/voc/create/` | voc_create | |
| `/voc/<pk>/` | voc_detail | 상세 + 답변 |
| `/voc/<pk>/reply/` | voc_reply | 답변 등록/수정 (staff only) |
| `/voc/<pk>/delete/` | voc_delete | 본인 또는 staff |

---

## 완료된 기능 상세

### Set-up (Category / SubCategory / Detail)
- 추가 / 수정 / 삭제 / 복사
  - Category, Detail 복사: 모달에 데이터 채워서 오픈
  - SubCategory 복사: Detail 포함 여부 선택 모달
- **컬럼별 검색:** thead 아래 검색 row → 실시간 JS 필터링 (AND 조건)
- `#`, 등록일, 관리 컬럼은 검색창 없음

### Set-up 현황
- Category → SubCategory → Detail 계층 아코디언 트리뷰
- Category 행에 SubCategory 수 + Detail 수 배지 표시
  - Detail 수는 `Count('subcategories__details')` annotate로 정확히 집계

### Recipe Grouping
- 동일 Category 내 SubCategory(recipe_id)들을 그룹으로 묶어 학습 데이터 함께 관리
- 모달에서 Category 선택 시 JS로 해당 SubCategory 체크박스 동적 렌더
- 수정 시 Category 변경 불가 (같은 Category 내에서만 recipe 변경)
- 카테고리별 그룹 카드, 카드 내 recipe_id 초록 배지 표시

### 학습값
- Category → SubCategory → Detail 순차 선택
- 3탭: Pre Thickness / Removal Rate / Offset Trend 차트 (샘플 데이터)

### History 조회
- Lot ID / Wafer ID / 공정(Oper ID) 텍스트 입력 후 조회
- DB 미연결 시 JS 샘플 12건 표시
- 컬럼: 조회일시, Lot ID, Wafer ID, Oper ID, Recipe ID, APC Para, THK Para, Pre THK, Target, APC Input, APC Result, 수정여부

### Simulation
- Category → SubCategory → Detail → 장비명(key-in) 4단계 선택
- 4개 모두 입력 시 실행 버튼 활성화
- 실행 후: Set-up 등록 학습값(필수/선택 파라미터) 카드 표시
- DB 연동 및 APC 산식 결과는 향후 구현 (플레이스홀더 존재)

### APC 수정건수
- Product / Device / 공정 드롭다운 (DB 연동 전 disabled)
- 조회 시 샘플 차트: 월별 Bar + 공정별 가로 Bar

### 산포 개선 현황
- Product / Device / 공정 드롭다운 (DB 연동 전 disabled)
- 조회 시 샘플 차트:
  - 공정별 MICO 전/후 Sigma 비교 grouped Bar
  - 공정별 개선율 가로 Bar
  - 월별 Sigma Trend Line

### VOC 게시판
- 모든 로그인 사용자 글 작성
- 답변대기 / 답변완료 배지
- 답변 작성/수정: staff(is_staff=True)만 가능
- 삭제: 본인 또는 staff

---

## DB 연동 대기 중인 기능 (수정 포인트)

| 기능 | views.py 함수 | 수정할 변수 |
|------|--------------|------------|
| History 조회 | `learning_history` | `rows = []` → 실제 쿼리 결과 리스트 |
| APC 수정건수 드롭다운 | `apc_history` | `product_list`, `device_list`, `process_list` |
| APC 수정건수 차트 | `apc_history` | `chart_data = None` → 실제 데이터 dict |
| 산포 개선 드롭다운 | `dispersion` | `product_list`, `device_list`, `process_list` |
| 산포 개선 차트 | `dispersion` | `chart_data = None` → `{"labels":[], "before":[], "after":[]}` |
| 학습값 실제 데이터 | `learning_values` | tree 구성 시 실제 학습값 포함 |
| Dashboard 통계 | `dashboard` | context의 count 및 차트 데이터 |

---

## 예정 작업
- 사내 DB 연동 (학습값, History, APC 수정건수, 산포 개선 전 항목)
- APC 산식(Pre Thickness / Removal Rate / Offset) 기반 Simulation 결과값 표시
- Dashboard 실제 데이터 연결
- Recipe Grouping 기반 학습 데이터 묶음 관리 로직
