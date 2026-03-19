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
