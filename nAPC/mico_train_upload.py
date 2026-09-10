"""MICO 학습 트리거 모델을 MLflow(AI Studio)에 올린다. {TODO} 두 개만 채우면 끝.

`mico_upload.py` 와 같은 구조인데, **입력이 숫자가 아니라 문자열**이다.
학습은 "어떤 공정을 학습할지"를 키로 받아야 하므로 숫자 배열로는 표현이 안 된다.

  입력 한 행 = [Lot_Code(device), Oper_Code, Fab]     예: ["E2", "V5077000E", "M10"]
  출력       = ["E2_V5077000E_M10:OK", ...]           (문자열 1차원 배열)

문자열은 MLflow signature 에서 정상 지원된다(`Array(Array(string))`).
로컬 `mlflow models serve` 로 POST -> 200 + 결과 배열까지 실제로 확인했다.

지킬 것은 하나뿐: **한 배열 안에 문자열과 숫자를 섞지 말 것.**
섞으면 `infer_signature` 가 `Expected all values in list to be of same type` 로 죽는다.
숫자가 같이 필요하면 (1) 전부 문자열로 보내고 안에서 float() 하거나,
(2) 엔벨로프에 스칼라 필드를 따로 두거나(`"lot_code": "E2"`), (3) 숫자는
Mongo Hub 에서 직접 읽는다. 자세한 건 nAPC/README.md 참고.

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


# ── 2. 학습 대상 키 (for_key_list = Lot_Code + Oper_Code + Fab) ──
sample_keys = [
    ["E2", "V5077000E", "M10"],
    ["NA", "V5077000E", "M10"],
]


# ── 3. 실제 학습이 들어갈 자리 ────────────────────────────
def run_training(lot_code, oper_code, fab):
    """이 키 하나에 대한 학습. 지금은 자리만 잡아 둔 더미다.

    실제로는 여기서 Mongo Hub 의 merge_df 를 직접 읽어(HTTP 로 안 보낸다)
    PRE_THK_VM / REMOVAL_RATE / OFFSET 을 돌리고 결과 컬렉션에 쓴다.
    """
    return f"{lot_code}_{oper_code}_{fab}:OK"


# ── 4. input_example (mico_upload.py 와 같은 엔벨로프) ────
input_example = {
    "input": [
        {
            "name": "mico_train_key",
            "shape": [len(sample_keys), len(sample_keys[0])],
            "datatype": "ndarray",
            "data": sample_keys,      # 문자열 2차원 배열
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
        out = []
        for row in _get_rows(model_input):
            lot_code, oper_code, fab = (str(v) for v in row)
            out.append(str(run_training(lot_code, oper_code, fab)))
        return out                                  # 1차원 순수 str


def _get_rows(model_input):
    """엔벨로프에서 data 2차원 배열을 꺼낸다 (mico_upload.py 와 동일)."""
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
        mlflow.log_metrics({"sample_keys": len(sample_keys)})

        info = mlflow.pyfunc.log_model(
            python_model=TrainWrapper(),
            artifact_path="ai_studio",
            input_example=input_example,
            registered_model_name=mlflow_register_model_name,
            pip_requirements=["mlflow==2.16.2", "pandas==2.2.2"],
        )
        print(f"run_id  = {run.info.run_id}")
        print(f"version = {info.registered_model_version}")
