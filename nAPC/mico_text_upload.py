"""문자 in / 문자 out 최소 예제. {TODO} 두 개만 채우면 끝.

`mico_upload.py` 는 숫자 배열만 주고받는다. 이 파일은 그 반대로
**문자열만** 주고받는 가장 단순한 형태다. "문자로도 학습값을 받아올 수 있나"
를 확인하는 용도.

    입력 한 행 = "E2"                       (문자열 하나)
    출력 한 행 = "E2 | period=3 | OK"       (문자열 하나)

핵심 제약은 하나뿐이다 — **한 배열 안의 값은 전부 같은 타입**.
전부 문자열이면 문제없다. signature 는 Array(Array(string)) 로 잡힌다.
숫자를 같이 보내고 싶으면 배열이 아니라 **행을 dict 로** 보낸다
(`mico_train_upload.py` 참고).

**돌려줄 때 문자+숫자를 섞고 싶으면 행을 dict 로 반환한다** (로컬 서빙 200 확인):

    return [{"lot_code": "E2", "period": 3, "status": "OK"}, ...]
    -> outputs: [{"type":"string","name":"lot_code"},
                 {"type":"long","name":"period"},
                 {"type":"string","name":"status"}]

아래 기본 구현은 가장 단순한 1차원 문자열 배열이고, 숫자를 문자열 안에 넣는다.

**최상위 키는 반드시 `input`.** MLflow 는 최상위가 `input` 이면 본문을 그대로
predict 에 넘기는 경로를 탄다. 평평한 dict 는 400 이다.

주의: 이 파일은 **스크립트로 실행**할 것 (`python3 mico_text_upload.py`).
import 해서 log_model 하면 cloudpickle 이 TextWrapper 를 참조로만 저장해
서빙에서 ModuleNotFoundError 로 워커가 못 뜬다.

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
mlflow_register_model_name = "MICO_Text"


def connect():
    os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"
    os.environ["MLFLOW_TRACKING_USERNAME"] = mlflow_tracking_username
    os.environ["MLFLOW_TRACKING_PASSWORD"] = mlflow_tracking_password
    mlflow.set_tracking_uri(mlflow_tracking_uri)
    mlflow.set_experiment(mlflow_experiment_name)


# ── 2. 입력 = 문자열 리스트 (Lot_Code) ────────────────────
sample_data = ["E2", "NA", "AG"]


# ── 3. "학습" 자리 — 문자열을 받아 문자열을 돌려준다 ──────
# 실제로는 여기서 lot_code 로 Mongo Hub 의 merge_df 를 읽어
# PRE_THK_VM / REMOVAL_RATE / OFFSET 을 돌린다. 지금은 표 하나로 대신한다.
LEARNED = {
    "E2": {"period": 3, "rr": 98.5},
    "NA": {"period": 5, "rr": 102.1},
}


def learn(lot_code):
    """문자열 하나 -> 문자열 하나. 입력 문자에 따라 결과가 갈린다."""
    lot_code = str(lot_code).strip().upper()
    hit = LEARNED.get(lot_code)
    if hit is None:
        return f"{lot_code} | NO_DATA"
    return f"{lot_code} | period={hit['period']} | rr={hit['rr']} | OK"


# ── 4. input_example (사내 예제와 같은 엔벨로프) ──────────
input_example = {
    "input": [
        {
            "name": "mico_text",
            "shape": [len(sample_data)],
            "datatype": "ndarray",
            "data": sample_data,        # 전부 문자열
        }
    ]
}

with open("text_input_example.json", "w") as f:
    json.dump(input_example, f, indent=2, ensure_ascii=False)


# ── 5. 래퍼 ───────────────────────────────────────────────
class TextWrapper(mlflow.pyfunc.PythonModel):
    def predict(self, context, model_input, params=None):
        return self._run(model_input)

    # 구현 안 하면 MLflow 기본 구현이 NotImplementedError
    # -> 게이트웨이가 NOT_IMPLEMENTED 로 감싼다
    def predict_stream(self, context, model_input, params=None):
        for v in self._run(model_input)["aiu_output"]:
            yield v

    def _run(self, model_input):
    # 반환은 **{"aiu_output": [...]} dict** 다. 게이트웨이가 이걸 한 번 더 감싸
    # {"output": {"aiu_output": [...]}} 로 돌려준다. 모델이 배열을 그대로 주면
    # 게이트웨이가 꺼낼 키가 없다 -> aiu_output 키는 모델이 만들어야 한다.
        # 리스트는 1차원 순수 str. 2차원 배열이면 배열 변환에서 깨진다
        return {"aiu_output": [str(learn(x)) for x in _get_rows(model_input)]}

        # 문자+숫자를 같이 돌려주려면 리스트 원소를 dict 로 바꾼다
        # return {"aiu_output": [
        #     {"lot_code": str(x), "period": 3, "rr": 98.5, "status": "OK"}
        #     for x in _get_rows(model_input)]}


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


# ── 6. 올리기 전 자가 점검 ────────────────────────────────
def preflight(cls):
    """올리기 전에 서빙에서 깨질 조건을 여기서 먼저 잡는다.

    특히 predict_stream: 사내 게이트웨이는 이걸 직접 부르는데,
    없으면 MLflow 기본 구현이 NotImplementedError 를 내고 게이트웨이가
        {"error_type":"NotImplementedError","hcp_error_type":"NOT_IMPLEMENTED",
         "error_message":"Inference Error"}
    로 감싸서 돌려준다. 로컬 `mlflow models serve` 에는 스트리밍 경로가 없어서
    predict_stream 을 아예 부르지 않는다 -> **로컬 200 으로는 절대 안 걸린다.**
    그래서 업로드 직전에 확인한다.
    """
    base = mlflow.pyfunc.PythonModel
    if cls.predict_stream is base.predict_stream:
        raise RuntimeError(
            f"{cls.__name__} 에 predict_stream 이 없다. 이대로 올리면 엔드포인트에서 "
            "NOT_IMPLEMENTED 가 난다 (로컬 서빙으로는 안 걸린다)"
        )
    if cls.predict is base.predict:
        raise RuntimeError(f"{cls.__name__} 에 predict 가 없다")
    print("preflight OK — predict / predict_stream 둘 다 있음")


# ── 7. 로깅 + 등록 ────────────────────────────────────────
if __name__ == "__main__":
    preflight(TextWrapper)
    connect()
    with mlflow.start_run() as run:
        mlflow.log_metrics({"sample_rows": len(sample_data)})

        info = mlflow.pyfunc.log_model(
            python_model=TextWrapper(),
            artifact_path="ai_studio",
            input_example=input_example,
            registered_model_name=mlflow_register_model_name,
            pip_requirements=["mlflow==2.16.2", "pandas==2.2.2"],
        )
        print(f"run_id  = {run.info.run_id}")
        print(f"version = {info.registered_model_version}")
        print()
        print("올라간 모델이 맞는지 확인하려면:")
        print(f"  python3 mico_check_model.py --model runs:/{run.info.run_id}/ai_studio")
