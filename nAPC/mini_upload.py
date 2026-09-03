"""사칙연산 모델 최소 업로드. {TODO} 두 개만 채우면 끝.

입력 한 행 = [a, b, post_thk, pol_time, target]   (숫자 5개)
출력      = [offset, offset, ...]                (행마다 숫자 1개, 1차원)

핵심 세 가지:

1. **input_example 을 반드시 넘긴다.** 이걸 넘겨야 MLflow 가 모델 안에
   `serving_input_example.json` 을 만들어 준다. 사내 MLflow 의 다른 모델에는
   전부 있는 파일이고, 서빙 런타임이 이걸로 요청을 해석하는 것으로 보인다.
   빼면 파일이 안 생기고 호출이 안 된다.

2. **input_example 과 실제 호출 payload 를 똑같이 맞춘다.** input_example 에서
   signature 가 추론돼 스키마가 강제되므로, 다르면
   "Failed to enforce schema of data" 가 난다. 예전에 이 에러가 났던 건
   문자열(BYTES) 모델에 숫자 배열을 보냈기 때문이다.

3. **출력은 1차원.** 사내 예제의 ElasticNet 도 1차원 배열을 돌려준다.
   2차원으로 돌려주면 런타임이 "setting an array element with a sequence" 로 죽을 수 있다.

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


def get_rows(model_input):
    """엔벨로프에서 data 2차원 배열을 꺼낸다.

    signature 유무에 따라 도착 모양이 다르다.
      signature 없음 -> dict 그대로:      {"input": [ {..., "data": [[...]]} ]}
      signature 있음 -> DataFrame 으로:   input 컬럼의 셀 = [ {..., "data": [[...]]} ]
    어느 쪽이든 감싼 껍질을 벗겨 블록까지 내려간다.
    """
    x = model_input
    if hasattr(x, "columns"):          # DataFrame
        x = x["input"].iloc[0]
    elif isinstance(x, dict):
        x = x["input"]
    while isinstance(x, (list, tuple)):
        x = x[0]
    return x["data"]


# 사칙연산 3단계. 뒷 단계가 앞 단계 결과를 받아 쓴다.
class ModelWrapper(mlflow.pyfunc.PythonModel):
    def predict(self, context, model_input, params=None):
        out = []
        for a, b, post_thk, pol_time, target in get_rows(model_input):
            pre_thk = a + b                              # 1단계
            rr = (pre_thk - post_thk) / pol_time         # 2단계
            offset = target - rr * pol_time              # 3단계
            out.append(float(offset))                    # 순수 float, 1차원
        return out


#              a     b   post_thk  pol_time  target
sample_data = [
    [ 1.0,  2.0,  0.0,  1.0,  10.0],
    [ 5.0,  5.0,  2.0,  2.0,  20.0],
    [ 7.0,  3.0,  2.0,  4.0,  30.0],
]

# log_model 에 넘기고(-> serving_input_example.json 생성), 호출용으로 파일로도 남긴다.
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
    info = mlflow.pyfunc.log_model(
        python_model=ModelWrapper(),
        artifact_path="ai_studio",
        input_example=input_example,          # <- 이게 있어야 serving_input_example.json 이 생긴다
        registered_model_name="MICO_Mini",
        pip_requirements=["mlflow==2.16.2", "pandas==2.2.2"],
    )
    print("run_id :", run.info.run_id)
    print("version:", info.registered_model_version)
