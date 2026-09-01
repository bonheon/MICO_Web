# mico_deploy — MICO 알고리즘 MLflow pyfunc 최소 예제

algorithm_new 이관 전에 "임의 파이썬 코드를 MLflow 모델로 감싸 서빙"하는
구조가 실제로 도는지 확인하기 위한 최소 예제.

## 실행

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt gunicorn requests   # gunicorn/requests 는 로컬 서빙 테스트용

python3 save_model.py          # ./mico_model 저장 + mico_model.zip 생성
python3 test_local.py          # (1) 로드 테스트

# 서빙 테스트는 터미널 2개
mlflow models serve -m ./mico_model -p 5001 --env-manager local
python3 test_local.py --serve  # (2) HTTP 호출 테스트
```

tracking 서버 주소를 받으면 `register_model.py` 의 `TRACKING_URI` 를 채우고 실행.

## 인터페이스

nAPC → AI Studio 로 오가는 형식은 JSON 문자열 컬럼 하나로 고정한다.
set-up 이 중첩 구조라 DataFrame 컬럼으로 펼치면 스키마가 깨지기 때문.

```
요청  {"dataframe_split": {"columns": ["setup_json"], "data": [["{...}"], ...]}}
응답  {"predictions": [{"result_json": "{...}"}, ...]}
```

행 단위 try/except 로 감싸므로 한 건이 실패해도 batch 전체는 완주한다.
실패 행은 `{"status": "error", "message": "..."}` 로 채워진다.

## 이관 시 지켜야 할 것

- `MicoEngine.__init__` 에서 pickle 불가 객체(DB 커넥션, 파일 핸들, 스레드)를 만들지 말 것.
  MLflow 가 python_model 을 pickle 로 저장한다. 리소스는 `load_context` 에서 만든다.
- import 는 `from mico_core.xxx import ...` 절대경로만. 상대 import·`sys.path` 조작 금지.
  (algorithm_new/Common/Module.py 는 현재 `sys.path.append` + import 시점 Cube_Connector
   생성을 하고 있어 그대로는 패키징 불가 — 이관 시 분리 필요)
- `pip_requirements` 버전 고정 필수.

## 파일

| 파일 | 역할 |
|------|------|
| `mico_core/engine.py` | `MicoEngine.run(setup) -> dict`. 실제 알고리즘이 들어갈 자리 |
| `mico_core/utils.py` | 보조 함수 |
| `model_wrapper.py` | `mlflow.pyfunc.PythonModel` 상속 래퍼 |
| `save_model.py` | 방식 B — 로컬 저장 + zip |
| `register_model.py` | 방식 A — tracking 서버 등록 |
| `test_local.py` | 로드/서빙 검증 |
| `sample_input.json` | 호출 예시 (3번째 행은 의도적 에러 케이스) |
| `artifacts/mico_config.json` | 알고리즘 설정값 |
