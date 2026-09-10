"""MICO 학습 트리거 모델을 MLflow(AI Studio)에 올린다. {TODO} 두 개만 채우면 끝.

`mico_upload.py` 는 숫자 배열만 받는다. 학습·시뮬레이션 호출은 **문자와 숫자가 섞여서**
들어오므로(`Lot_Code` 같은 키 + `target` 같은 값) 그 형태를 그대로 받는 예제다.

핵심: **한 행을 배열이 아니라 dict 로 보낸다.**
MLflow 제약은 "한 배열 안의 값은 전부 같은 타입"이지, 타입 혼합 자체가 아니다.
dict 로 보내면 필드마다 타입이 달라도 되고, signature 가 필드별로 잡힌다.

    data: Array({fab: string, lot_code: string, oper_code: string,
                 pol_time: double, post_thk: double, target: double})

  입력 한 행 = {"lot_code","oper_code","fab", "post_thk","pol_time","target"}
  출력      = ["E2_V5077000E_M10:OK", ...]   (1차원 순수 str)

문자열 키만 필요하면 숫자 필드를 빼면 된다. 형식은 그대로다.

지킬 것 두 가지:
  - **숫자는 실수로** 보낼 것. signature 가 double 이라 `2` 는 400, `2.0` 은 통과
  - **모든 행에 같은 필드**가 있을 것. 없어도 되는 필드는 input_example 의
    한 행에서 빼두면 signature 에 optional 로 잡힌다

주의: 이 파일은 **스크립트로 실행**할 것(`python3 mico_train_upload.py`).
다른 모듈에서 import 해서 log_model 하면 cloudpickle 이 TrainWrapper 를 '참조'로만
저장해(`mico_train_upload.TrainWrapper`) 서빙 컨테이너에서
`ModuleNotFoundError: No module named 'mico_train_upload'` 로 워커가 못 뜬다.
__main__ 에서 정의된 클래스라야 값 자체가 저장된다.

    pip install mlflow==2.16.2 pandas
"""

import json
import os

import mlflow
import mlflow.pyfunc

# ── 1. 접속 설정 ──────────────────────────────────────────
mlflow_tracking_uri = "{TODO}"
mlflow_tracking_username = "aistudio"
mlflow_tracking_password = "{TODO}"

mlflow_experiment_name = "MICO"
mlflow_register_model_name = "MICO_Train"


def connect():
    """tracking 서버 접속. import 만 할 때는 붙지 않도록 함수로 둔다."""
    os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"
    os.environ["MLFLOW_TRACKING_USERNAME"] = mlflow_tracking_username
    os.environ["MLFLOW_TRACKING_PASSWORD"] = mlflow_tracking_password
    mlflow.set_tracking_uri(mlflow_tracking_uri)
    mlflow.set_experiment(mlflow_experiment_name)


# ── 2. 학습 대상 한 행 (for_key_list = Lot_Code + Oper_Code + Fab) ──
# 문자와 숫자를 한 dict 안에 같이 담는다. 배열로 담으면 안 된다.
sample_rows = [
    {"lot_code": "E2", "oper_code": "V5077000E", "fab": "M10",
     "post_thk": 1.0, "pol_time": 2.0, "target": 10.0},
    {"lot_code": "NA", "oper_code": "V5077000E", "fab": "M10",
     "post_thk": 3.0, "pol_time": 4.0, "target": 20.0},
]


# ── 3. 실제 학습이 들어갈 자리 ────────────────────────────
def run_training(row):
    """이 키 하나에 대한 학습. 지금은 자리만 잡아 둔 더미다.

    실제로는 여기서 Mongo Hub 의 merge_df 를 직접 읽어(HTTP 로 안 보낸다)
    PRE_THK_VM / REMOVAL_RATE / OFFSET 을 돌리고 결과 컬렉션에 쓴다.
    """
    key = f"{row['lot_code']}_{row['oper_code']}_{row['fab']}"
    return f"{key}:OK"


# ── 4. input_example (mico_upload.py 와 같은 엔벨로프) ────
input_example = {
    "input": [
        {
            "name": "mico_train_key",
            "shape": [len(sample_rows)],    # dict 행이라 행 수만
            "datatype": "ndarray",
            "data": sample_rows,
        }
    ]
}

with open("train_input_example.json", "w") as f:
    json.dump(input_example, f, indent=2)


# ── 5. 래퍼 ───────────────────────────────────────────────
class TrainWrapper(mlflow.pyfunc.PythonModel):
    def predict(self, context, model_input, params=None):
        return self._run(model_input)

    # 구현 안 하면 MLflow 기본 구현이 NotImplementedError -> 게이트웨이 NOT_IMPLEMENTED
    def predict_stream(self, context, model_input, params=None):
        for v in self._run(model_input):
            yield v

    def _run(self, model_input):
        return [str(run_training(row)) for row in _get_rows(model_input)]


def _get_rows(model_input):
    """엔벨로프에서 data 리스트를 꺼낸다 (mico_upload.py 와 동일)."""
    x = model_input
    if hasattr(x, "columns"):          # DataFrame
        x = x["input"].iloc[0]
    elif isinstance(x, dict):
        x = x["input"]
    while isinstance(x, (list, tuple)):
        x = x[0]
    return x["data"]


# ── 6. 로깅 + 등록 ────────────────────────────────────────
if __name__ == "__main__":
    connect()
    with mlflow.start_run() as run:
        mlflow.log_metrics({"sample_rows": len(sample_rows)})

        info = mlflow.pyfunc.log_model(
            python_model=TrainWrapper(),
            artifact_path="ai_studio",
            input_example=input_example,
            registered_model_name=mlflow_register_model_name,
            pip_requirements=["mlflow==2.16.2", "pandas==2.2.2"],
        )
        print(f"run_id  = {run.info.run_id}")
        print(f"version = {info.registered_model_version}")
