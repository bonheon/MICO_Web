# nAPC — MICO 알고리즘 AI Studio(MLflow) 이관

MICO를 HCP → nAPC로 전환하면서, 핵심 알고리즘을 MLflow 기반 AI Studio에
올리기 위한 검토·예제 폴더.

- `MICO MLflow 작업지시서.md` — 원본 작업지시서
- `simple_example.py` — **여기부터 시작.** 한 파일짜리 최소 예제 (로컬 저장까지)
- `simple_upload.py` — **사내에서 실제로 올려볼 파일.** 한 파일 + 사칙연산만으로
  tracking 서버에 업로드 + 레지스트리 등록까지
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

```bash
cd nAPC
python3 simple_upload.py            # 주소 없이 → 로컬 저장만 (연습)
```

**Jupyter / AI Studio 노트북에서 쓸 때** — 파일 내용을 셀에 그대로 붙여넣고
실행해도 되고, 옆에 두고 아래처럼 불러도 된다.

```python
import simple_upload
simple_upload.run()                                      # 로컬 저장만
simple_upload.run(uri="https://<host>", password="...")  # 업로드
```

> 노트북 셀은 `sys.argv` 에 커널 인자(`-f kernel.json`)를 달고 있다.
> `argparse.parse_args()` 는 그걸 모르는 인자로 보고 `SystemExit` 을 내고,
> IPython 이 그걸 잡아 `To exit: use 'exit', 'quit', or Ctrl-D.` 경고를 띄운다.
> 그래서 이 파일은 `parse_known_args()` 를 써서 모르는 인자를 무시한다.

업로드하려면 주소·계정을 줘야 한다. 셋 중 아무 방법이나 되고,
**우선순위는 명령행 인자 > 환경변수 > 파일 상수**다.

```bash
# (a) 파일 위 TRACKING_URI / TRACKING_USERNAME / TRACKING_PASSWORD 를 채우고 (사내 예제 방식)
python3 simple_upload.py

# (b) 환경변수로
export MLFLOW_TRACKING_USERNAME=aistudio
export MLFLOW_TRACKING_PASSWORD='...'
python3 simple_upload.py --uri https://<host>

# (c) 명령행 인자로
python3 simple_upload.py --uri https://<host> --user aistudio --password '...'
```

어느 방법을 쓰든 `setup_auth()` 가 `MLFLOW_TRACKING_USERNAME` / `PASSWORD` /
`INSECURE_TLS=true` 를 `os.environ` 에 세팅한 뒤 업로드한다.
(a) 를 쓸 때 **비밀번호를 채운 채로 커밋하지 않도록 주의.**
→ `run_id` / `model_uri` / `version` 이 찍히고, 마지막에 되불러서 3줄 출력.

모델 클래스를 파일 안에 두는 것이 핵심이다. MLflow 가 클래스를 cloudpickle 로
**값 자체**로 직렬화하므로 `code_paths` 없이 이 파일 하나로 업로드가 끝난다.
(검증: 이 파일이 없는 별도 프로세스에서 `models:/...` 로 로드해도 동작함)

#### 사내 예제(ElasticNet/iris)와 맞춘 부분

| 항목 | 사내 예제 | `simple_upload.py` |
|---|---|---|
| 인증 | `MLFLOW_TRACKING_USERNAME/PASSWORD` + `INSECURE_TLS=true` | 동일. `--user/--password` 또는 환경변수 |
| 등록 | `log_model(registered_model_name=...)` 한 번에 | 동일 (`ModelInfo.registered_model_version` 로 버전 확인) |
| `artifact_path` | `"ai_studio"` | 동일 |
| `input_example` | `{"input":[{"name","shape","datatype","data"}]}` | 동일이 기본 (`--io-style aistudio`) |
| 래퍼 위치 | `aiu_custom/predict.py` + `code_paths` | 이 파일 안 (code_paths 불필요) |
| `pip_requirements` | `"requirements.txt"` 파일 경로 | 리스트로 버전 고정 (파일 경로도 가능) |

**인증이 제일 중요하다.** 이 세 환경변수가 없으면 업로드가 401 로 떨어진다.
사내 https 가 자체서명 인증서라 `MLFLOW_TRACKING_INSECURE_TLS=true` 도 필요하다.

#### input_example 형식이 서빙 계약을 결정한다 (중요)

사내 예제처럼 엔벨로프 dict 를 `input_example` 로 주면, MLflow 가 거기서
**스키마를 추론해 강제**한다. 즉 그 뒤로는 호출도 반드시 그 모양이어야 한다.
(`setup_json` DataFrame 을 보내면 `Model is missing inputs ['input']` 로 거부됨)

또 MLflow 는 이 엔벨로프를 `input` 컬럼 1개짜리 DataFrame 으로 바꿔서
`predict()` 에 넘긴다 (셀 = 블록 리스트). 그래서 래퍼가 그 모양을 풀 줄 알아야 한다.
`simple_upload.py` 의 `extract_setups()` 가 엔벨로프·표준 DataFrame·리스트를 모두 받는다.

로컬 scoring server 로 확인한 결과 — 아래 셋 다 **HTTP 200**:

| payload | 결과 |
|---|---|
| `{"input": [{...}]}` (사내 예제 그대로) | 200, 응답이 배열 그대로 |
| `{"inputs": {"input": [{...}]}}` | 200, `{"predictions": [...]}` |
| `{"dataframe_split": {"columns":["input"], "data":[[...]]}}` | 200, `{"predictions": [...]}` |

MLflow 표준 계약(`setup_json` 컬럼)으로 올리고 싶으면 `--io-style mlflow` 를 준다.
AI Studio 엔드포인트가 어느 쪽을 요구하는지 확정되면 그쪽으로 고정하면 된다.

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
