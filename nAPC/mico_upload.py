"""MICO 사칙연산 모델을 MLflow(AI Studio)에 올린다. {TODO} 두 개만 채우면 끝.

사내 예제(ElasticNet + iris)와 **구조를 최대한 같게** 맞췄다.
다른 건 계산 내용뿐이고, 서빙에 관계되는 것은 전부 동일하게 둔다.

  - 입력: 숫자 2차원 배열만. datatype "ndarray"
  - 출력: 숫자 1차원 배열만
  - artifacts (model.pkl + config.json) 를 함께 올려 artifacts 폴더가 생기게 한다
  - input_example 을 넘겨 serving_input_example.json 이 생기게 한다

    pip install mlflow==2.16.2 pandas

입력 한 행 = [a, b, post_thk, pol_time, target]
출력      = [offset, offset, ...]

equipment_id 는 문자열이라 숫자 배열에 넣지 않는다. 행 순서로 구분한다.
"""

import json
import os

import joblib
import mlflow
import mlflow.pyfunc
import numpy as np

# ── 1. 접속 설정 ──────────────────────────────────────────
mlflow_tracking_uri = "{TODO}"
mlflow_tracking_username = "aistudio"
mlflow_tracking_password = "{TODO}"

mlflow_experiment_name = "MICO"
mlflow_register_model_name = "MICO_Arith"

os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"
os.environ["MLFLOW_TRACKING_USERNAME"] = mlflow_tracking_username
os.environ["MLFLOW_TRACKING_PASSWORD"] = mlflow_tracking_password
mlflow.set_tracking_uri(mlflow_tracking_uri)
mlflow.set_experiment(mlflow_experiment_name)


# ── 2. 데이터 (사내 예제의 iris 자리) ─────────────────────
#              a     b   post_thk  pol_time  target
sample_data = np.array([
    [ 1.0,  2.0,  0.0,  1.0,  10.0],
    [ 5.0,  5.0,  2.0,  2.0,  20.0],
    [ 7.0,  3.0,  2.0,  4.0,  30.0],
])


# ── 3. 계산 (사내 예제의 ElasticNet 자리) ─────────────────
# 학습이 없다. 사칙연산 3단계뿐이다.
#
# 주의: 이 계산을 클래스로 만들어 joblib 으로 artifact 에 넣으면 안 된다.
# joblib(=pickle)은 클래스를 **이름으로만** 저장하므로(__main__.XXX),
# 서빙 컨테이너에서 __main__ 이 gunicorn 이라 클래스를 못 찾고 워커가 죽는다.
#   AttributeError: Can't get attribute 'XXX' on <module '__main__' ... gunicorn>
# 사내 예제가 joblib 을 써도 괜찮은 건 ElasticNet 이 설치된 sklearn 모듈의
# 클래스이기 때문이다. 우리가 직접 만든 클래스는 그렇지 않다.
#
# 그래서 계산은 아래 함수로 두고 ModelWrapper 안에서 부른다.
# ModelWrapper 는 MLflow 가 cloudpickle 로 '값 자체'를 저장하므로 안전하다.

def compute_offset(X, gain=1.0):
    """X: (n, 5) 숫자 배열 -> (n,) 숫자 배열"""
    X = np.asarray(X, dtype=float)
    a, b, post_thk, pol_time, target = X[:, 0], X[:, 1], X[:, 2], X[:, 3], X[:, 4]
    pre_thk = a + b                           # 1단계
    rr = (pre_thk - post_thk) / pol_time      # 2단계
    offset = (target - rr * pol_time) * gain  # 3단계
    return offset


# ── 4. input_example (사내 예제와 같은 형식) ──────────────
input_example = {
    "input": [
        {
            "name": "mico_example",
            "shape": list(sample_data.shape),
            "datatype": type(sample_data).__name__,   # -> "ndarray"
            "data": sample_data.tolist(),
        }
    ]
}

with open("input_example.json", "w") as f:
    json.dump(input_example, f, indent=2)

print("Check Input Example")
print(type(input_example))


# ── 5. 래퍼 (사내 예제의 aiu_custom ModelWrapper 자리) ────
# artifacts 로 올린 model.pkl / config.json 을 load_context 에서 읽는다.
class ModelWrapper(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        # artifact 는 순수 데이터(dict/json)만 담는다. 커스텀 클래스는 넣지 않는다.
        self.params = joblib.load(context.artifacts["model"])
        with open(context.artifacts["config"], encoding="utf-8") as f:
            self.config = json.load(f)

    def predict(self, context, model_input, params=None):
        gain = float(getattr(self, "params", {}).get("gain", 1.0))
        rows = _get_rows(model_input)
        return [float(v) for v in compute_offset(rows, gain)]   # 1차원 순수 float


def _get_rows(model_input):
    """엔벨로프에서 data 2차원 배열을 꺼낸다.

    signature 가 있으면 DataFrame(input 컬럼, 셀 = 블록 리스트)으로,
    없으면 dict 원본으로 도착한다. 어느 쪽이든 껍질을 벗겨 블록까지 내려간다.
    """
    x = model_input
    if hasattr(x, "columns"):          # DataFrame
        x = x["input"].iloc[0]
    elif isinstance(x, dict):
        x = x["input"]
    while isinstance(x, (list, tuple)):
        x = x[0]
    return x["data"]


# ── 6. 로깅 + 등록 (사내 예제와 같은 순서) ────────────────
config_dir = "config"
config_path = os.path.join(config_dir, "config.json")
os.makedirs(config_dir, exist_ok=True)

with mlflow.start_run() as run:
    params = {"gain": 1.0}
    mlflow.log_params(params)

    with open(config_path, "w") as f:
        json.dump(params, f, indent=4)

    predictions = compute_offset(sample_data, params["gain"])
    mlflow.log_metrics({"sample_rows": len(sample_data), "offset_mean": float(predictions.mean())})

    model_dir = "saved_model"
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, "model.pkl")
    joblib.dump(params, model_path)   # 순수 dict 만 저장 (커스텀 클래스 금지)

    info = mlflow.pyfunc.log_model(
        python_model=ModelWrapper(),
        artifact_path="ai_studio",
        artifacts={"model": model_path, "config": config_path},
        input_example=input_example,
        registered_model_name=mlflow_register_model_name,
        pip_requirements=["mlflow==2.16.2", "pandas==2.2.2"],   # numpy 는 고정하지 않는다 (환경과 어긋나면 경고/설치 충돌)
    )
    print(f"run_id  = {run.info.run_id}")
    print(f"version = {info.registered_model_version}")
