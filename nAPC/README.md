# nAPC — MICO 알고리즘 AI Studio(MLflow) 이관

MICO를 HCP → nAPC로 전환하면서, 핵심 알고리즘을 MLflow 기반 AI Studio에
올리기 위한 검토·예제 폴더.

- `MICO MLflow 작업지시서.md` — 원본 작업지시서
- `mini_upload.py` / `mini_call.py` — **가장 단순한 최소 재현.** 숫자 배열 in/out,
  각각 50줄·15줄. 엔드포인트가 안 될 때 여기부터 좁힌다
- `simple_example.py` — 한 파일짜리 최소 예제 (로컬 저장까지)
- `simple_upload.py` — **사내에서 실제로 올려볼 파일.** 한 파일 + 사칙연산만으로
  tracking 서버에 업로드 + 레지스트리 등록까지
- `simple_call.py` — 올린 모델을 **불러서 호출하고 반환값 확인**. `simple_upload.py` 다음
- `simple_probe.py` — 엔드포인트가 **어떤 payload 를 받는지** 후보를 던져 알아내는 탐침
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

### 5단계 — tracking 서버 업로드
주소를 받은 뒤 실행한다. 받기 전에는 건너뛴다. 두 가지 경로가 있다.

**(a) 가장 간단한 경로 — `simple_upload.py` 파일 하나.** 사칙연산만 든 모델을
코드만으로 올린다. 폴더 구조도, zip 도, 별도 패키지도 필요 없다.

**사내 예제(ElasticNet/iris)와 같은 순서·구조**로 써 뒀다. 위에서 아래로 한 번
훑으면 되고, Jupyter 셀에 그대로 붙여넣어도 된다 (`# %%` 가 셀 구분자).

| 셀 | 하는 일 | 사내 예제의 대응 |
|---|---|---|
| [1] | 접속 설정 (`{TODO}` 두 개) | tracking uri / 계정 / experiment |
| [2] | 데이터 준비 (set-up 3건) | `load_iris` + `train_test_split` |
| [3] | 알고리즘 정의 (사칙연산 3단계) | `ElasticNet` + `compute_metrics` |
| [4] | `input_example` 엔벨로프 + json 저장 | 동일 |
| [5] | 래퍼 `ModelWrapper` | `aiu_custom/predict.py` |
| [6] | `config/config.json` 저장 | 동일 |
| [7] | `with mlflow.start_run():` 로깅 + 등록 | 동일 |
| [8] | 되불러서 검증 | (추가) |

```bash
pip install mlflow==2.16.2 pandas
cd nAPC
python3 simple_upload.py        # {TODO} 그대로면 로컬 저장만 (연습)
```

업로드하려면 [1] 의 `{TODO}` 두 곳만 채우고 다시 실행한다.

```python
mlflow_tracking_uri = "https://<ai-studio-mlflow-host>"
mlflow_tracking_password = "..."      # 채운 채로 커밋하지 말 것
```

노트북에서는 파일 내용을 셀에 붙여넣어도 되고 `%run simple_upload.py` 도 된다.

`version = 1` 과 `models_uri` 가 찍히면 **사칙연산만으로 업로드 + 레지스트리
등록이 된다**는 게 확인된 것이다.

사내 예제와 다른 점은 하나 — 래퍼를 별도 모듈이 아니라 파일 안에 뒀다.
MLflow 가 클래스를 cloudpickle 로 **값 자체**로 직렬화하므로 `code_paths` 없이
이 파일 하나로 업로드가 끝난다.
(검증: 이 파일이 없는 별도 프로세스에서 `models:/...` 로 로드해도 동작함)

#### 올린 모델 호출해서 반환값 보기 — `simple_call.py`

```bash
python3 simple_call.py
```

[1] 의 `{TODO}` 를 채우면 레지스트리(`models:/<name>/<version>`)에서,
그대로 두면 `simple_upload.py` 가 만든 로컬 폴더에서 불러온다.

| 셀 | 하는 일 |
|---|---|
| [1] | 접속 설정 + 어디서 불러올지 (`models:/...` vs 로컬 폴더) |
| [2] | 모델 로드 + signature 출력 (이 모델이 받는 입력 계약) |
| [3] | 입력 만들기 — `setups` 값을 바꿔가며 실험 |
| [4] | 호출 + 반환값 (원본 DataFrame / 풀어서 / 표로) |
| [5] | 손 검산 (`pre_thk=3, rr=3.0, offset=7.0`) |
| [6] | HTTP 엔드포인트 호출 (주소 받은 뒤) |

반환은 `result_json` 컬럼 하나짜리 DataFrame이고, 셀 안에 JSON 문자열이 들어 있다.
`json.loads()` 로 풀면 `{equipment_id, pre_thk, rr, offset, status}` 가 나온다.

> **주의:** `model.predict(payload)` 는 넘긴 dict 를 **제자리에서 고친다.**
> 스키마를 맞추며 `shape` 의 int 를 `numpy.int64` 로 바꿔놓기 때문에, 같은 dict 를
> 나중에 HTTP 로 보내면 `Object of type int64 is not JSON serializable` 이 난다.
> 그래서 `build_payload()` 로 호출할 때마다 새로 만든다.

#### 엔드포인트가 `NOT_IMPLEMENTED` 를 돌려줄 때

**먼저 `mini_upload.py` / `mini_call.py` 로 좁힌다.** 우리 모델이 문자열(JSON)을
주고받는 게 사내 런타임과 안 맞을 수 있다. 사내 예제(ElasticNet/iris)는
**숫자 배열 in / 숫자 배열 out** 이었으므로, 그 모양으로 최소 재현을 만들었다.

```bash
python3 mini_upload.py     # {TODO} 2개 채우고 실행 -> MICO_Mini 등록
python3 mini_call.py       # req_url 채우고 실행
```

`mini_upload.py` 는 config·artifact·load_context·predict_stream 없이
`predict()` 하나뿐이고, `[a, b]` 를 받아 `a + b` 를 돌려준다.

- **이게 되면** 문제는 우리 모델의 입출력 형식(문자열 JSON)이다. 그 모양을
  숫자 배열로 바꾸면 된다.
- **이것도 안 되면** 모델 복잡도 문제가 아니다. 사내 서빙 런타임이 pyfunc 를
  그대로 부르지 않는 것이므로 담당자 확인이 필요하다 (아래 참고).

로컬 MLflow 서버로 검증한 결과: `HTTP 200`, 본문 `[3.0, 7.0, 15.0]`.


```json
{"error_code": "15001", "error_type": "NotImplementedError",
 "hcp_error_type": "NOT_IMPLEMENTED", "error_message": "Inference Error"}
```

HTTP 200 이어도 이건 **에러**다. `hcp_error_type` 은 MLflow 가 쓰는 필드가 아니라
사내 게이트웨이가 붙인 것이므로, MLflow 표준 서버가 아니라 사내 서빙 런타임이
낸 오류다. 아래 순서로 좁힌다.

1. `simple_call.py` [4] 의 `model.predict()` 가 되는지 본다.
   **되면 모델 자체는 멀쩡하고 서빙 런타임 문제다** (레지스트리 로드까지 성공한 것).
2. `simple_call.py` [7] 진단 셀을 AI Studio 노트북에서 돌려
   `aiu_custom.predict.ModelWrapper` 소스를 확인한다. 사내 런타임이 부르는
   메서드가 거기 있다. 그게 `predict` 가 아니면 그 이름으로 맞춰줘야 한다.

미리 맞춰둔 것 두 가지 (`simple_upload.py` 의 `ModelWrapper`):

- `predict(self, context, model_input, params=None)` — MLflow 정식 시그니처.
  런타임이 3인자로 부르면 `params` 를 안 받는 쪽은 `TypeError` 가 난다.
- `predict_stream()` 구현 — 스트리밍으로 부르는 런타임 대비.
  구현이 없으면 MLflow 기본 구현이 `NotImplementedError` 를 낸다.

그래도 안 되면 `simple_probe.py` 로 payload 형식을 좁힌다.

```bash
python3 simple_probe.py     # endpoint_url 만 채우고 실행
```

후보 8종(사내 엔벨로프 / `inputs` / `dataframe_split` / `dataframe_records` /
`instances` / KServe v2 형 등)을 순서대로 POST 하고, 어느 게 통하는지 요약해 준다.
`/ping` `/health` `/version` 도 찔러 서버 정체를 확인한다.

MLflow 표준 서버로 검증했을 때는 아래 4종이 통했다.

| payload | 결과 |
|---|---|
| `{"input": [{...}]}` (사내 예제 그대로) | 200 |
| `{"inputs": {"input": [{...}]}}` | 200 |
| `{"dataframe_split": {"columns":["input"], ...}}` | 200 |
| `{"dataframe_records": [{"input": [{...}]}]}` | 200 |

전부 실패하면 payload 문제가 아니라 서빙 런타임이 모델을 부르는 방식이 다른 것이다.
그때 담당자에게 확인할 것:

- **`aiu_custom` 패키지를 어디서 받는지.** 사내 예제가 `code_paths=["aiu_custom"]`
  으로 올리는 로컬 폴더인데, 노트북에 없으면 그 예제도 그대로는 안 돈다.
- 서빙 런타임이 pyfunc 의 `predict()` 를 부르는지, 다른 메서드를 부르는지
- 엔드포인트가 기대하는 요청 본문 예시

**(b) 폴더 구조 경로 — `mico_deploy/register_model.py`.** 실제 알고리즘처럼
코드가 여러 모듈로 나뉘고 artifact(설정 파일)가 붙는 경우.
`TRACKING_URI` 를 채우고 실행한다.

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
