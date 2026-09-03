"""사칙연산 모델 최소 업로드. {TODO} 두 개만 채우면 끝.

사내 예제처럼 숫자 배열 in / 숫자 배열 out. 문자열도 config 도 artifact 도 없다.
"""

import json
import os

import mlflow
import mlflow.pyfunc

mlflow_tracking_uri = "{TODO}"
mlflow_tracking_username = "aistudio"
mlflow_tracking_password = "{TODO}"

os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"
os.environ["MLFLOW_TRACKING_USERNAME"] = mlflow_tracking_username
os.environ["MLFLOW_TRACKING_PASSWORD"] = mlflow_tracking_password
mlflow.set_tracking_uri(mlflow_tracking_uri)
mlflow.set_experiment("MICO")


# 사칙연산만. 한 행이 [a, b] 로 들어오면 a + b 를 돌려준다.
class ModelWrapper(mlflow.pyfunc.PythonModel):
    def predict(self, context, model_input, params=None):
        rows = model_input["input"][0][0]["data"]
        return [r[0] + r[1] for r in rows]


sample_data = [[1.0, 2.0], [3.0, 4.0], [10.0, 5.0]]

input_example = {
    "input": [
        {
            "name": "mico",
            "shape": [len(sample_data), 2],
            "datatype": "ndarray",
            "data": sample_data,
        }
    ]
}

with open("input_example.json", "w") as f:
    json.dump(input_example, f, indent=2)

with mlflow.start_run() as run:
    mlflow.pyfunc.log_model(
        python_model=ModelWrapper(),
        artifact_path="ai_studio",
        input_example=input_example,
        registered_model_name="MICO_Mini",
        pip_requirements=["mlflow==2.16.2", "pandas==2.2.2"],
    )
    print("run_id:", run.info.run_id)
