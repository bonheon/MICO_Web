# nAPC — MICO 알고리즘 AI Studio(MLflow) 이관

MICO를 HCP → nAPC로 전환하면서, 핵심 알고리즘을 MLflow 기반 AI Studio에
올리기 위한 검토·예제 폴더.

- `MICO MLflow 작업지시서.md` — 원본 작업지시서
- `mico_upload.py` / `mico_call.py` — **여기부터 시작.** 숫자 배열만 주고받는 업로드/호출 한 쌍
- `simple_example.py` — MLflow pyfunc 개념 확인용 (로컬 저장까지)
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

### 5단계 — tracking 서버 업로드 + 호출

```bash
cd nAPC
python3 mico_upload.py     # 상단 {TODO} 2개(uri, password) 채우고 실행
python3 mico_call.py       # url 채우고 실행
```

사내 예제(ElasticNet + iris)와 **서빙에 관계되는 부분을 전부 같게** 맞췄다.
다른 건 계산 내용뿐이다.

| 항목 | 값 |
|---|---|
| 입력 | 숫자 2차원 배열만, `datatype: "ndarray"` |
| 출력 | 숫자 1차원 배열만 (순수 `float`) |
| `input_example` | `log_model` 에 넘긴다 -> `serving_input_example.json` 생성 |
| `artifacts` | `model.pkl` + `config.json` -> `artifacts` 폴더 생성 |
| 입력 한 행 | `[a, b, post_thk, pol_time, target]` |
| 출력 | `[offset, ...]` |

`equipment_id` 는 문자열이라 숫자 배열에 넣지 않는다. 행 순서로 구분하고,
`mico_call.py` 가 `equipment_ids` 리스트와 zip 해서 보여준다.

#### 반드시 지킬 것 (전부 실제로 깨졌던 것들)

**1. `artifact` 에 직접 만든 클래스를 넣지 말 것.**
`joblib.dump` 는 클래스를 **이름으로만** 저장한다(`__main__.XXX`). 서빙
컨테이너에서는 `__main__` 이 gunicorn 이라 그 클래스를 못 찾고 워커가 아예
못 뜬다.

```
AttributeError: Can't get attribute 'ArithModel' on <module '__main__' ... gunicorn>
```

사내 예제가 `joblib.dump(model, ...)` 를 써도 되는 건 `ElasticNet` 이 설치된
sklearn 모듈의 클래스이기 때문이다. 우리가 만든 클래스는 그렇지 않다.
artifact 에는 **순수 데이터(dict/json)만** 넣고, 계산은 함수로 두고
`ModelWrapper` 안에서 부른다. `ModelWrapper` 는 MLflow 가 cloudpickle 로
'값 자체'를 저장하므로 안전하다.

**2. `input_example` 을 `log_model` 에 반드시 넘길 것.**
안 넘기면 `serving_input_example.json` 이 안 생긴다. 사내 MLflow 의 다른
모델에는 전부 있는 파일이다.

**3. `input_example` 과 호출 payload 를 똑같이 맞출 것.**
`input_example` 에서 signature 가 추론돼 강제된다. 다르면
`Failed to enforce schema of data` 가 난다.
`mico_call.py` 는 `input_example.json` 을 그대로 읽어 보내므로 어긋날 일이 없다.

**4. `predict` 와 `predict_stream` 을 둘 다 구현할 것.**
`predict_stream` 을 안 만들면 MLflow 기본 구현이 `NotImplementedError` 를 내고,
사내 게이트웨이가 그걸 이렇게 감싸서 돌려준다.

```json
{"error_code": "15001", "error_type": "NotImplementedError",
 "hcp_error_type": "NOT_IMPLEMENTED", "error_message": "Inference Error"}
```

pyfunc 안에서 `NotImplementedError` 를 **직접 던지는 곳은
`PythonModel.predict_stream` 기본 구현 하나뿐**이다(`predict` 는 본문이 비어 있다).
실제로 `predict()` 는 되는데 `predict_stream()` 만 이 예외를 내는 것을 확인했다.

**5. 출력은 1차원 순수 `float`.**
2차원이면 런타임이 결과를 배열에 담다가
`setting an array element with a sequence` 로 죽을 수 있다.

#### 올린 뒤 확인할 것

MLflow UI 에서 그 모델 artifact 에 아래 두 가지가 보여야 한다.

- `serving_input_example.json` — 이게 곧 POST 할 본문이다. 그대로 복사해 보내도 된다
- `artifacts/` 폴더 (`model.pkl`, `config.json`)

#### 에러 메시지로 어디까지 갔는지 읽기

| 메시지 | 뜻 |
|---|---|
| `NOT_IMPLEMENTED` | 입력조차 처리 못 함 |
| `Failed to enforce schema of data` | payload 가 모델 signature 와 불일치 |
| `Inference Error` | 입력은 통과. `predict` 안 또는 결과 처리에서 실패 |

로컬 검증 결과: 서버 기동 `ping 200`, `serving_input_example.json` 을 그대로
POST -> `[7.0, 12.0, 22.0]`, `mico_call.py` 로도 동일.


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
