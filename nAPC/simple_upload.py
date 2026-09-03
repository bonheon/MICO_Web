"""사칙연산만 든 모델을 MLflow(AI Studio)에 업로드하는 예제.

사내 MLflow 로깅 예제(ElasticNet/iris)와 **같은 순서·구조**로 맞췄다.
위에서 아래로 한 번 훑으면 끝이고, Jupyter 셀에 그대로 붙여넣어도 된다.
(`# %%` 는 셀 구분자. Jupyter / VS Code 가 셀로 인식한다)

    pip install mlflow==2.16.2 pandas

바꿀 곳은 [1] 의 {TODO} 두 개뿐이다. 그대로 두면 서버 없이 로컬 저장만 한다.

사내 예제와 다른 점은 하나 — 래퍼 클래스를 별도 모듈(`aiu_custom/predict.py`)이
아니라 이 파일 안에 뒀다. MLflow 가 클래스를 cloudpickle 로 값 자체로
직렬화하므로 `code_paths` 없이 이 파일 하나로 업로드가 끝난다.
"""

# %% [1] 접속 설정 ─────────────────────────────────────────────────────────
import os

import mlflow

mlflow_tracking_uri = "{TODO}"          # 예: "https://<ai-studio-mlflow-host>"
mlflow_tracking_username = "aistudio"
mlflow_tracking_password = "{TODO}"     # 주의: 채운 채로 커밋하지 말 것

mlflow_experiment_name = "MICO"
mlflow_register_model_name = "MICO_Algorithm_Simple"
mlflow_artifact_path = "ai_studio"      # 사내 예제와 동일

# 주소를 안 넣으면 서버 없이 로컬 저장만 한다 (연습용)
UPLOAD = "{TODO}" not in mlflow_tracking_uri

if UPLOAD:
    # 이 세 개가 없으면 업로드가 401 로 떨어진다. INSECURE_TLS 는 자체서명 인증서 대응.
    os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"
    os.environ["MLFLOW_TRACKING_USERNAME"] = mlflow_tracking_username
    os.environ["MLFLOW_TRACKING_PASSWORD"] = mlflow_tracking_password
    mlflow.set_tracking_uri(mlflow_tracking_uri)
    mlflow.set_experiment(mlflow_experiment_name)
    print(f"tracking   = {mlflow_tracking_uri}")
    print(f"experiment = {mlflow_experiment_name}")
else:
    print("mlflow_tracking_uri 가 비어 있어 로컬 저장만 합니다.")
    print("업로드하려면 [1] 의 {TODO} 두 곳을 채우세요.")


# %% [2] 데이터 준비 ───────────────────────────────────────────────────────
# 사내 예제의 load_iris + train_test_split 자리.
# 여기서 다루는 건 학습 데이터가 아니라 set-up 정보 몇 건이다.
import json

import pandas as pd

setups = [
    {"equipment_id": "EQ001", "a": 1, "b": 2, "post_thk": 0, "pol_time": 1, "target": 10},
    {"equipment_id": "EQ002", "a": 5, "b": 5, "post_thk": 2, "pol_time": 2, "target": 20},
    # 의도적 실패 케이스 — 한 건이 죽어도 batch 는 완주하는지 본다
    {"equipment_id": "EQ003", "a": 1, "b": 2, "post_thk": 0, "pol_time": 0, "target": 10},
]
setup_json = [json.dumps(s, ensure_ascii=False) for s in setups]

print(pd.DataFrame(setups))
print(f"\nset-up {len(setups)} 건")


# %% [3] 알고리즘 정의 ─────────────────────────────────────────────────────
# 사내 예제의 ElasticNet 자리. 학습도 가중치 파일도 없이 사칙연산 3단계뿐이다.
# 뒷 단계가 앞 단계 결과를 받아 쓴다. 이 의존 관계만 실제와 같게 두고,
# 안쪽 수식은 나중에 PRE_THK_VM.py / REMOVAL_RATE.py / OFFSET.py 로 교체한다.

def step1_pre_thk_vm(setup: dict) -> float:
    """1단계: 입고 두께 예측. (진짜는 회귀 + moving average)"""
    return setup["a"] + setup["b"]


def step2_removal_rate(setup: dict, pre_thk: float) -> float:
    """2단계: 제거율. 1단계 결과를 받아 쓴다."""
    return (pre_thk - setup["post_thk"]) / setup["pol_time"]


def step3_offset(setup: dict, rr: float, gain: float) -> float:
    """3단계: 보정값. 2단계 결과와 config 의 gain 을 받아 쓴다."""
    return (setup["target"] - rr * setup["pol_time"]) * gain


def mico_algorithm(setup: dict, gain: float = 1.0) -> dict:
    """set-up 1건을 받아 3단계를 순서대로 실행한다."""
    pre_thk = step1_pre_thk_vm(setup)
    rr = step2_removal_rate(setup, pre_thk)
    offset = step3_offset(setup, rr, gain)
    return {
        "equipment_id": setup["equipment_id"],
        "pre_thk": pre_thk,   # 중간값도 같이 반환해서 흐름을 눈으로 확인
        "rr": rr,
        "offset": offset,
        "status": "success",
    }


def compute_metrics(results: list) -> tuple:
    """사내 예제의 compute_metrics 자리. 여기선 성공 건수를 센다."""
    total = len(results)
    success = sum(r.get("status") == "success" for r in results)
    return total, success


# %% [4] input_example 만들기 ──────────────────────────────────────────────
# 사내 예제와 같은 엔벨로프 형식.
#
# 중요: 이 형식이 곧 서빙 계약이 된다. MLflow 가 여기서 스키마를 추론해 **강제**하므로,
# 업로드 뒤 호출도 반드시 {"input": [...]} 모양이어야 한다.
batch_size = len(setup_json)
input_example = {
    "input": [
        {
            "name": "mico_setup",
            "shape": [batch_size, 1],
            "datatype": "BYTES",   # 문자열 배열. 사내 예제는 numpy 라 숫자형이었다
            "data": setup_json,
        }
    ]
}

with open("input_example.json", "w") as f:
    json.dump(input_example, f, indent=2, ensure_ascii=False)

print("Check Input Example")
print(type(input_example))


# %% [5] 래퍼 정의 ─────────────────────────────────────────────────────────
# 사내 예제의 aiu_custom/predict.py ModelWrapper 자리.
# 이 파일 안에 두므로 code_paths 가 필요 없다.
#
# MLflow 가 요구하는 건 predict() 하나뿐이다. 안에 뭐가 들었는지는 신경 쓰지 않는다.
# 그래서 ML 모델이 아니어도 (학습된 게 없어도) 서빙된다.
import logging

import mlflow.pyfunc

logging.getLogger("mlflow").setLevel(logging.ERROR)


def extract_setups(model_input) -> list:
    """서빙 쪽이 어떤 모양으로 보내든 set-up dict 리스트로 통일한다.

    [4] 의 엔벨로프로 올리면 MLflow 가 그걸 input 컬럼 1개짜리 DataFrame 으로
    바꿔서 predict 에 넘긴다(셀 = 블록 리스트). 그래서 두 경우를 같이 받는다.
    """
    def to_setup(item):
        return json.loads(item) if isinstance(item, str) else item

    def from_blocks(cells):
        rows = []
        for cell in cells:
            for block in ([cell] if isinstance(cell, dict) else list(cell)):
                rows.extend(block.get("data", []))
        return [to_setup(r) for r in rows]

    if isinstance(model_input, dict) and "input" in model_input:
        return from_blocks([model_input["input"]])

    if isinstance(model_input, pd.DataFrame):
        if "input" in model_input.columns:
            return from_blocks(model_input["input"])
        if "setup_json" in model_input.columns:
            return [to_setup(v) for v in model_input["setup_json"]]
        return model_input.to_dict("records")

    if isinstance(model_input, list):
        return [to_setup(r) for r in model_input]

    raise TypeError(f"지원하지 않는 입력 형식: {type(model_input).__name__}")


class ModelWrapper(mlflow.pyfunc.PythonModel):
    config = {}   # load_context 전에 쓰일 기본값

    def load_context(self, context):
        """artifact 로 넘긴 config 를 읽는다.

        DB 커넥션·파일 핸들 같은 pickle 불가 리소스는 __init__ 이 아니라
        여기서 만들어야 한다. 실제 알고리즘 이관 시 지켜야 할 지점.
        """
        with open(context.artifacts["config"], encoding="utf-8") as f:
            self.config = json.load(f)

    def predict(self, context, model_input) -> pd.DataFrame:
        gain = float(self.config.get("gain", 1.0))
        results = []
        for setup in extract_setups(model_input):
            try:
                out = mico_algorithm(setup, gain)
            except Exception as exc:  # 한 건이 실패해도 나머지는 계속 처리
                out = {"status": "error", "message": f"{type(exc).__name__}: {exc}"}
            results.append(json.dumps(out, ensure_ascii=False))
        return pd.DataFrame({"result_json": results})


# %% [6] config 저장 ───────────────────────────────────────────────────────
# 사내 예제의 config/config.json 자리. artifact 로 같이 올라간다.
config_dir = "config"
config_path = os.path.join(config_dir, "config.json")
os.makedirs(config_dir, exist_ok=True)

params = {
    "gain": 1.0,
    "algorithm": "arithmetic_3step",
}

with open(config_path, "w", encoding="utf-8") as f:
    json.dump(params, f, indent=4)

print(f"config 저장: {config_path} -> {params}")


# %% [7] 로깅 + 등록 ───────────────────────────────────────────────────────
# 사내 예제의 with mlflow.start_run() 블록 자리.
# 사칙연산이라 fit() 이 없다. 대신 샘플로 한 번 돌려 결과를 metric 으로 남긴다.
import shutil

pip_requirements = [
    "mlflow==2.16.2",
    "pandas==2.2.2",
]
local_dir = "./simple_upload_model"

if UPLOAD:
    with mlflow.start_run() as run:
        mlflow.log_params(params)

        # 사내 예제의 model.fit -> predict -> compute_metrics -> log_metrics 자리
        results = [mico_algorithm(s, params["gain"]) if s["pol_time"] else {"status": "error"}
                   for s in setups]
        total, success = compute_metrics(results)
        mlflow.log_metrics({"sample_rows": total, "sample_success": success})

        info = mlflow.pyfunc.log_model(
            artifact_path=mlflow_artifact_path,
            python_model=ModelWrapper(),
            artifacts={"config": config_path},
            input_example=input_example,
            pip_requirements=pip_requirements,
            registered_model_name=mlflow_register_model_name,   # 로깅+등록 한 번에
        )

        model_uri = f"runs:/{run.info.run_id}/{mlflow_artifact_path}"
        version = info.registered_model_version
        print(f"run_id     = {run.info.run_id}")
        print(f"model_uri  = {model_uri}")
        print(f"version    = {version}")
        print(f"models_uri = models:/{mlflow_register_model_name}/{version}")
else:
    shutil.rmtree(local_dir, ignore_errors=True)
    mlflow.pyfunc.save_model(
        path=local_dir,
        python_model=ModelWrapper(),
        artifacts={"config": config_path},
        input_example=input_example,
        pip_requirements=pip_requirements,
    )
    model_uri = local_dir
    print(f"로컬 저장: {local_dir}")


# %% [8] 되불러서 검증 ─────────────────────────────────────────────────────
# 저장/업로드된 모델을 다시 읽어 [4] 의 input_example 그대로 호출한다.
model = mlflow.pyfunc.load_model(model_uri)
results = [json.loads(r) for r in model.predict(input_example)["result_json"]]

for r in results:
    print(" ", r)

total, success = compute_metrics(results)
print(f"\n{success}/{total} 성공 (3번째는 pol_time=0 인 의도적 실패 케이스)")
print("업로드 완료." if UPLOAD else "로컬 저장 완료.")
