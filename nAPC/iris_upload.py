"""대조 실험 — 사내 예제(ElasticNet + iris)를 그대로 재현한다.

없는 `aiu_custom.predict.ModelWrapper` 만 같은 파일 안의 최소 래퍼로 대체했다.
나머지(데이터·모델·input_example 형식·log_model 인자)는 사내 예제와 동일하다.

목적: 사칙연산 모델이 아니라 **진짜 sklearn 모델**로도 엔드포인트가 실패하는지 본다.

  - 이것도 실패하면  -> 우리 코드 문제가 아니다. 플랫폼/배포 설정 문제이고,
                       aiu_custom 을 받거나 담당자 확인이 필요하다.
  - 이건 성공하면    -> 차이가 우리 모델 쪽에 있다. 둘을 비교해 좁힌다.

    pip install mlflow==2.16.2 pandas scikit-learn
"""

import json
import os

import mlflow

mlflow_tracking_uri = "{TODO}"
mlflow_tracking_username = "aistudio"
mlflow_tracking_password = "{TODO}"

mlflow_experiment_name = "MICO"
mlflow_register_model_name = "IRIS_Control"

os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"
os.environ["MLFLOW_TRACKING_USERNAME"] = mlflow_tracking_username
os.environ["MLFLOW_TRACKING_PASSWORD"] = mlflow_tracking_password
mlflow.set_tracking_uri(mlflow_tracking_uri)
mlflow.set_experiment(mlflow_experiment_name)


# ── 데이터 (사내 예제와 동일) ─────────────────────────────
from sklearn.datasets import load_iris
from sklearn.model_selection import train_test_split

iris_df = load_iris(as_frame=True).frame
train_df, test_df = train_test_split(iris_df, test_size=0.2, random_state=42)

train_dataset = mlflow.data.from_pandas(train_df, name="train")
train_x = train_dataset.df.drop(["target"], axis=1)
train_y = train_dataset.df[["target"]]

test_dataset = mlflow.data.from_pandas(test_df, name="test")
test_x = test_dataset.df.drop(["target"], axis=1)
test_y = test_dataset.df[["target"]]

print(f"Train: {train_x.shape}, Test: {test_x.shape}")


# ── 모델 (사내 예제와 동일) ───────────────────────────────
from sklearn.linear_model import ElasticNet
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

model = ElasticNet(alpha=0.5, l1_ratio=0.5, random_state=42)


def compute_metrics(actual, predicted):
    rmse = mean_squared_error(actual, predicted)
    mae = mean_absolute_error(actual, predicted)   # 원본 오타(mean_absoluted_error) 수정
    r2 = r2_score(actual, predicted)
    return rmse, mae, r2


# ── input_example (사내 예제와 동일) ──────────────────────
batch_size = 10
sample_data = test_x.head(batch_size).to_numpy()   # 원본 오타(haed) 수정

input_example = {
    "input": [
        {
            "name": "sklearn_example",
            "shape": list(sample_data.shape),
            "datatype": type(sample_data).__name__,   # -> "ndarray"
            "data": sample_data.tolist(),
        }
    ]
}

with open("input_example.json", "w") as f:
    json.dump(input_example, f, indent=2)           # 원본 오타(indect) 수정

print("Check Input Example")
print(type(input_example))


# ── 래퍼 (aiu_custom.predict.ModelWrapper 대체) ───────────
# 사내 패키지가 없으므로 같은 역할을 하는 최소 구현을 파일 안에 둔다.
# artifacts 로 받은 model.pkl 을 로드해 predict 하고, 1차원 배열로 돌려준다.
import logging

import joblib
import mlflow.pyfunc
import numpy as np

logging.getLogger("mlflow").setLevel(logging.ERROR)


class ModelWrapper(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        self.model = joblib.load(context.artifacts["model"])

    def predict(self, context, model_input, params=None):
        data = model_input["input"][0][0]["data"]
        return self.model.predict(np.array(data)).tolist()


# ── 학습 + 로깅 (사내 예제와 동일) ────────────────────────
config_dir = "config"
config_path = os.path.join(config_dir, "config.json")
os.makedirs(config_dir, exist_ok=True)

with mlflow.start_run() as run:
    params = {"alpha": 0.5, "l1_ratio": 0.5}
    mlflow.log_params(params)

    with open(config_path, "w") as f:
        json.dump(params, f, indent=4)

    model.fit(train_x, train_y)

    predictions = model.predict(test_x)
    (rmse, mae, r2) = compute_metrics(test_y, predictions)
    mlflow.log_metrics({"rmse": rmse, "r2": r2, "mae": mae})

    model_dir = "saved_model"
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, "model.pkl")
    joblib.dump(model, model_path)

    info = mlflow.pyfunc.log_model(
        python_model=ModelWrapper(),
        artifact_path="ai_studio",
        artifacts={"model": model_path, "config": config_path},
        input_example=input_example,
        registered_model_name=mlflow_register_model_name,
        pip_requirements=["mlflow==2.16.2", "pandas==2.2.2", "scikit-learn==1.5.1"],
    )
    print(f"run_id  = {run.info.run_id}")
    print(f"version = {info.registered_model_version}")
