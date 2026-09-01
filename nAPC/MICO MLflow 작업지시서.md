# MICO 알고리즘 MLflow pyfunc 패키징 작업 지시서

## 배경

MICO 시스템을 HCP에서 nAPC로 전환 중이다.
- **nAPC**: set-up 환경 구축 담당. 여기서 set-up 정보를 batch 형식 API로 전송한다.
- **AI Studio**: MLflow 기반 플랫폼. 원래는 ML 모델을 올려서 x 변수를 API로 받아 y 값을 반환하는 구조.
- **목표**: AI Studio에 MICO 알고리즘 코드를 pyfunc 커스텀 모델로 올려서, nAPC가 보낸 set-up 정보를 받아 알고리즘을 실행하고 결과를 반환한다.

즉, "학습된 모델 서빙"이 아니라 "임의 파이썬 코드를 모델 인터페이스로 감싸서 서빙"하는 구조다.

---

## 만들어야 할 폴더 구조

```
mico_deploy/
├── mico_core/                  # MICO 알고리즘 소스
│   ├── __init__.py
│   ├── engine.py               # MicoEngine 클래스
│   └── utils.py
├── artifacts/
│   └── mico_config.json        # 알고리즘 설정값
├── model_wrapper.py            # pyfunc 래퍼 클래스
├── register_model.py           # 방식 A: tracking 서버 등록
├── save_model.py               # 방식 B: 로컬 저장 후 zip 업로드
├── test_local.py               # 로컬 검증 스크립트
├── sample_input.json           # 호출 예시 JSON
└── requirements.txt
```

---

## 1. mico_core/engine.py

`MicoEngine` 클래스를 만든다.

- `__init__(self, config: dict)` — 설정값 주입
- `run(self, setup: dict) -> dict` — set-up 정보 1건을 받아 알고리즘 실행 후 결과 dict 반환

주의사항:
- DB 커넥션, 파일 핸들, 스레드 등 pickle 불가능한 객체를 `__init__`에서 만들지 말 것
- 내부 import는 `from mico_core.utils import ...` 형태의 절대경로만 사용. 상대경로(`from .utils`)나 `sys.path` 조작 금지

지금은 실제 알고리즘 로직 대신 아래 형태의 stub으로 두고, 나중에 실제 코드를 채워 넣을 수 있게 한다.

```python
def run(self, setup: dict) -> dict:
    # TODO: 실제 MICO 알고리즘 로직
    return {
        "equipment_id": setup.get("equipment_id"),
        "opt_params": {},
        "dispersion_before": 0.0,
        "dispersion_after": 0.0,
        "dispersion_gain": 0.0,
        "status": "success",
    }
```

---

## 2. model_wrapper.py

`mlflow.pyfunc.PythonModel`을 상속한 `MicoAlgorithm` 클래스를 만든다.

**load_context(self, context)**
- `context.artifacts["config"]` 경로에서 설정 JSON 로드
- `MicoEngine` 인스턴스 생성해서 `self.engine`에 저장
- import는 이 메서드 안에서 수행

**predict(self, context, model_input: pd.DataFrame)**
- `model_input["setup_json"]` 컬럼의 각 행은 JSON **문자열**이다
- 행마다 `json.loads` → `self.engine.run()` → `json.dumps(ensure_ascii=False)`
- 반환은 `pd.DataFrame({"result_json": [...]})`
- 개별 행에서 예외가 나도 전체 batch가 죽지 않도록 try/except로 감싸고, 실패한 행은 `{"status": "error", "message": "..."}` 형태의 JSON 문자열을 넣을 것

입력을 `setup_json` 문자열 컬럼 하나로 받는 이유: set-up 정보가 중첩 구조라서 DataFrame 컬럼으로 펼치면 스키마가 깨지기 때문이다. 이 설계는 유지할 것.

---

## 3. register_model.py (방식 A — tracking 서버 사용)

```
mlflow.set_tracking_uri(TRACKING_URI)   # 상수로 빼두고 주석으로 "담당자에게 확인" 표기
mlflow.set_experiment("MICO")
```

`mlflow.start_run()` 안에서 `mlflow.pyfunc.log_model()` 호출. 인자:

- `artifact_path="mico_model"`
- `python_model=MicoAlgorithm()`
- `artifacts={"config": "./artifacts/mico_config.json"}`
- `code_paths=["./mico_core"]`
- `signature=infer_signature(sample_in, sample_out)`
- `input_example=sample_in`
- `pip_requirements=[...]` — **버전 고정 필수**
- `registered_model_name="MICO_Algorithm"`

실행 후 `run_id`를 출력할 것.

sample_in / sample_out 예시:
```python
sample_in = pd.DataFrame({"setup_json": ['{"equipment_id":"EQ001"}']})
sample_out = pd.DataFrame({"result_json": ['{"dispersion_gain":0.13}']})
```

---

## 4. save_model.py (방식 B — zip 업로드)

`mlflow.pyfunc.save_model()` 사용. 인자는 방식 A와 동일하되 `path="./mico_model"`.

- 실행 전 기존 `./mico_model` 폴더가 있으면 삭제 (`shutil.rmtree`)
- 저장 후 `MLmodel`, `conda.yaml`, `requirements.txt`, `python_model.pkl`, `code/`, `artifacts/`가 모두 생성됐는지 검사해서 출력
- 마지막에 `mico_model.zip`으로 압축

---

## 5. sample_input.json

MLflow serving 규격인 `dataframe_split` 형식. batch 3건 예시.

```json
{
  "dataframe_split": {
    "columns": ["setup_json"],
    "data": [
      ["{\"equipment_id\": \"EQ001\", \"params\": {\"temp\": 25.3}}"],
      ["{\"equipment_id\": \"EQ002\", \"params\": {\"temp\": 26.1}}"],
      ["{\"equipment_id\": \"EQ003\", \"params\": {\"temp\": 24.7}}"]
    ]
  }
}
```

---

## 6. test_local.py

두 가지를 순서대로 검증하는 스크립트.

**(1) 로드 테스트**
```python
m = mlflow.pyfunc.load_model("./mico_model")
print(m.predict(pd.DataFrame({"setup_json": [...]})))
```

**(2) 서빙 테스트** — 아래 명령을 주석으로 안내하고, 호출 코드를 작성

```bash
mlflow models serve -m ./mico_model -p 5001 --env-manager local
```

```python
import json, requests
req_url = "http://127.0.0.1:5001/invocations"
with open("sample_input.json", "r", encoding="utf-8") as f:
    data = json.load(f)
resp = requests.post(req_url,
                     headers={"Content-Type": "application/json"},
                     data=json.dumps(data),      # dump 아님, dumps
                     timeout=300)
for row in resp.json()["predictions"]:
    print(json.loads(row["result_json"]))
```

응답 파싱까지 포함할 것. 예상 응답 형태:
```json
{"predictions": [{"result_json": "{\"dispersion_gain\": 0.13}"}]}
```

---

## 코딩 규칙

- 파이썬 3.10 기준
- 타입 힌트 사용
- 주요 함수에 한국어 docstring
- 한자 사용 금지
- 하드코딩 값은 파일 상단 상수로 분리
- 예외 처리 시 무엇이 실패했는지 알 수 있게 메시지 작성

---

## 작업 순서

1. 폴더 구조와 빈 파일 생성
2. `mico_core/engine.py` stub 작성
3. `model_wrapper.py` 작성
4. `save_model.py` 작성 후 실행 → 폴더 생성 확인
5. `test_local.py`로 로드 테스트 통과
6. `mlflow models serve`로 서빙 테스트 통과
7. `register_model.py` 작성 (tracking 서버 주소 확보 후 실행)

각 단계마다 실행 결과를 확인하고 다음으로 넘어갈 것.

---

## 열려 있는 확인 사항 (담당자 문의 필요)

- AI Studio가 pyfunc 커스텀 모델 업로드를 허용하는가
- MLflow tracking 서버 주소를 주는가, zip 업로드 방식인가
- 서빙 API 타임아웃 제한은 몇 초인가 (MICO 시뮬레이션 소요시간과 비교 필요)
