"""사칙연산 모델 최소 업로드. {TODO} 두 개만 채우면 끝.

사내 예제처럼 숫자 배열 in / 숫자 배열 out. datatype 도 "ndarray" 로 동일.

입력 한 행 = [a, b, post_thk, pol_time, target]   (숫자 5개)
출력 한 행 = [pre_thk, rr, offset]                (숫자 3개)

equipment_id 는 문자열이라 숫자 배열에 못 넣는다. 행 순서로 구분한다.
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


# 사칙연산 3단계. 뒷 단계가 앞 단계 결과를 받아 쓴다.
class ModelWrapper(mlflow.pyfunc.PythonModel):
    def predict(self, context, model_input, params=None):
        rows = model_input["input"][0][0]["data"]
        out = []
        for a, b, post_thk, pol_time, target in rows:
            pre_thk = a + b                              # 1단계
            rr = (pre_thk - post_thk) / pol_time         # 2단계
            offset = target - rr * pol_time              # 3단계
            out.append([pre_thk, rr, offset])
        return out


#              a     b   post_thk  pol_time  target
sample_data = [
    [ 1.0,  2.0,  0.0,  1.0,  10.0],
    [ 5.0,  5.0,  2.0,  2.0,  20.0],
    [ 7.0,  3.0,  2.0,  4.0,  30.0],
]

input_example = {
    "input": [
        {
            "name": "mico",
            "shape": [len(sample_data), len(sample_data[0])],
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
