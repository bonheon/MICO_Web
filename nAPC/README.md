# nAPC — MICO 알고리즘 AI Studio(MLflow) 이관

MICO를 HCP → nAPC로 전환하면서, 핵심 알고리즘을 MLflow 기반 AI Studio에
올리기 위한 검토·예제 폴더.

- `MICO MLflow 작업지시서.md` — 원본 작업지시서
- `simple_example.py` — **여기부터 시작.** 한 파일짜리 최소 예제
- `mico_deploy/` — 작업지시서 구조를 그대로 구현한 전체 예제

---

## 1. 가장 중요한 결론 — ML 모델이 아니어도 된다

MLflow pyfunc는 **안에 뭐가 들었는지 신경 쓰지 않는다.** `predict()` 메서드
하나만 있으면 되고, 그 안에서 뭘 하든 자유다. 학습된 모델일 필요가 없다.

`simple_example.py`가 그 증거다. 머신러닝도, 학습도, 가중치 파일도 없이
사칙연산만 들어 있는데 `save_model()` 로 저장되고 `mlflow models serve` 로
HTTP 서빙까지 된다.

제약은 하나뿐: **입구가 `predict(self, context, model_input)` 모양이어야 한다.**
`Common/Module.py` 의 `run()` 전체를 그 안에서 호출해도 똑같이 동작한다.

> 담당자에게 물을 때는 "ML 모델만 되나요?" 대신
> **"`mlflow.pyfunc.PythonModel` 을 상속한 커스텀 모델 업로드가 되나요?
> 학습된 모델이 아니라 파이썬 코드를 predict() 로 감싼 형태입니다."**
> 라고 물어야 정확한 답이 온다. (용어가 겹쳐서 오해가 생김)

---

## 2. 실행 순서 (하나씩)

### 0단계 — 설치
```bash
pip install mlflow==2.16.2 pandas
python3 -c "import mlflow; print(mlflow.__version__)"
```
→ `2.16.2` 나오면 통과.

### 1단계 — 한 파일짜리로 개념 확인
```bash
cd nAPC
python3 simple_example.py
```
기대 출력:
```
  {'equipment_id': 'EQ001', 'pre_thk': 3, 'rr': 3.0, 'offset': 7.0}
  {'equipment_id': 'EQ002', 'pre_thk': 10, 'rr': 4.0, 'offset': 12.0}
  {'error': 'ZeroDivisionError: division by zero'}
```
- EQ001: `a=1, b=2` → `pre_thk=3` → `rr=3.0` → `offset=7.0`. 3단계가 흐르는 걸 눈으로 확인
- EQ003: `pol_time=0` 을 넣은 의도적 실패 케이스. 한 건이 죽어도 나머지는 완주한다

### 2단계 — 폴더 구조로 저장
```bash
cd mico_deploy
python3 save_model.py
```
→ `MLmodel / conda.yaml / requirements.txt / python_model.pkl / code / artifacts`
전부 `OK`, 끝에 `mico_model.zip` 생성. **이 zip이 AI Studio에 올릴 물건.**

### 3단계 — 저장된 모델 로드
```bash
python3 test_local.py
```
→ 3줄 출력, 마지막 줄이 `{'status': 'error', ...}`

### 4단계 — HTTP 서빙 (터미널 2개, 진짜 관문)
```bash
pip install gunicorn requests        # 로컬 서빙 테스트에만 필요
mlflow models serve -m ./mico_model -p 5001 --env-manager local
```
```bash
python3 test_local.py --serve
```
→ 3단계와 같은 출력이 HTTP로 나오면 통과.

`--env-manager local` 을 빼면 conda 환경을 새로 만들려다 사내망에서 막힌다.
`gunicorn: not found` (return code 127) 가 나오면 gunicorn 이 PATH에 없는 것.

### 5단계 — tracking 서버 등록
주소를 받은 뒤 `register_model.py` 의 `TRACKING_URI` 를 채우고 실행.
받기 전에는 건너뛴다.

---

## 3. 구조 — 매시간 학습을 어떻게 가져갈 것인가

AI Studio가 **스케줄 실행과 엔드포인트를 둘 다 지원**하므로 진입점을 둘로 나눈다.

```
[DataLake] ──Merge_Hub.py──> [Mongo Hub]   (merge data 생성, 기존 유지)
                                  │
                                  │ 컨테이너가 직접 조회 (8.8MB, HTTP 안 탐)
                                  ▼
  ┌─────────────────── AI Studio ───────────────────┐
  │  (A) 스케줄 실행 (매시간)  ← 학습                │
  │      set-up JSON 받음 → 학습 → 학습값 반환       │
  │      pre_thk_vm → removal_rate → offset         │
  │      타임아웃 제약 없음                          │
  │                                                 │
  │  (B) 엔드포인트 (요청 시)  ← 시뮬레이션          │
  │      set-up JSON 받음 → 즉시 계산 → 응답         │
  │      60초 제한                                   │
  └─────────────────────────────────────────────────┘
                    │                    ▲
        학습값 전송  ▼                    │ set-up JSON
                 [ nAPC ] ───────────────┘
```

**60초 타임아웃은 (B)에만 걸린다.** 스케줄 실행은 배치라서 몇 분 걸려도 된다.
그래서 매시간 학습을 통째로 AI Studio에 올릴 수 있다.

(60초 근거: `mlflow models serve` 실행 시 로그에 `gunicorn --timeout=60` 이 찍힌다)

### payload 크기

payload = HTTP 요청 body에 실어 보내는 데이터 본문. `sample_input.json` 이 그 예다.
서버마다 최대 크기 제한이 있고 넘으면 `413 Payload Too Large` 가 난다.

| 보내는 것 | 크기 | HTTP로 보내나 |
|---|---|---|
| set-up JSON | 371 bytes (3건) → 실제 수십 KB | O 문제없음 |
| merge_df | 8.8 MB (2만행 x 52컬럼 JSON 변환) | X 안 보냄 — 컨테이너가 Hub에서 직접 조회 |

### 코드 수정 범위

`Common/Module.py` 에서 바꿀 곳은 **입구와 출구 두 곳뿐**. 계산 로직은 손대지 않는다.

| | 지금 | 바뀐 뒤 |
|---|---|---|
| 입구 | `Get_data.baseinfoGetData()` — web DB 직접 조회 | 넘겨받은 set-up JSON을 DataFrame으로 |
| 데이터 | `fetch_merge_data()` — Mongo 조회 | **그대로** (컨테이너가 붙을 수 있음) |
| 계산 | VM → RR → Offset | **그대로** |
| 출구 | `mongodb_controller.push_df()` — Mongo 누적 | nAPC로 POST |
| 알람 | `Cube_Msg()` | nAPC 쪽으로 이동 검토 |

`baseinfoGetData()` 가 반환하는 `mico_info_table` 형태 그대로 JSON을 설계하면
뒤쪽 코드는 한 줄도 바뀌지 않는다. 이관을 제일 싸게 만드는 지점.

---

## 4. 실제 알고리즘 이관 시 지켜야 할 것

`algorithm_new/Common/Module.py` 는 현재 상태로는 패키징이 안 된다. 두 곳:

- **`Module.py:1-3`** — `sys.path.append` 로 경로 조작. `code_paths` 로 묶으면 깨진다.
- **`Module.py:18-22`** — import 시점에 `Cube_Connector(...)` 생성 + Mongo URL 하드코딩.
  MLflow는 모델을 pickle로 저장하는데 커넥션 객체는 pickle이 안 된다.
  → 커넥션 생성은 `load_context()` 안으로, URL은 artifact config로.

이관 순서는 **offset → removal_rate → pre_thk_vm 역순**을 권장한다.
offset이 입출력이 제일 단순하고, 앞 단계는 더미로 둔 채 하나씩 교체할 수 있다.
pre_thk_vm 이 제일 무거우므로 마지막.

---

## 5. 열려 있는 확인 사항

- [x] AI Studio가 배치 잡(스케줄 실행)을 지원하는가 → **지원. 엔드포인트도 함께**
- [x] 서빙 컨테이너에서 사내 MongoDB / DataLake 접근 가능한가 → **가능**
- [ ] `mlflow.pyfunc.PythonModel` 상속 커스텀 모델 업로드가 허용되는가
- [ ] 스케줄 실행이 "MLflow 모델 호출" 방식인가 "임의 스크립트 실행" 방식인가
      → 스크립트 실행이면 (A) 스케줄 잡에는 pyfunc 래퍼가 필요 없다
- [ ] nAPC 학습값 수신 API 규격 (필드명 / 구조) — 출구 코드를 짜려면 필요
- [ ] 엔드포인트 payload 크기 제한과 타임아웃 실제값
