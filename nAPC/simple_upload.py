"""사칙연산만 든 모델을 '코드만으로' MLflow(AI Studio)에 업로드하는 한 파일 예제.

`simple_example.py` 는 로컬 저장까지만 한다. 이 파일은 거기서 한 걸음 더 나가
tracking 서버에 log + 레지스트리 등록까지 한다. 사내에서 실제로 올려볼 파일.

모델 클래스를 이 파일 안에 두는 것이 핵심이다. 그러면 MLflow 가 클래스를
cloudpickle 로 '값 자체'로 직렬화하므로 code_paths·별도 패키지 없이
이 파일 하나만 있으면 업로드가 끝난다.

    pip install mlflow==2.16.2 pandas

    # 1) 서버 주소를 아직 못 받았을 때 — 로컬 저장까지만 확인
    python3 simple_upload.py

    # 2) 주소를 받은 뒤 — 실제 업로드
    python3 simple_upload.py --uri http://<ai-studio-mlflow-host>:5000

    # 환경변수로 줘도 된다
    export MLFLOW_TRACKING_URI=http://<ai-studio-mlflow-host>:5000
    python3 simple_upload.py
"""

import argparse
import json
import os
import shutil

import mlflow
import mlflow.pyfunc
import pandas as pd
from mlflow.models.signature import infer_signature

EXPERIMENT_NAME = "MICO"
ARTIFACT_PATH = "mico_model"
REGISTERED_MODEL_NAME = "MICO_Algorithm_Simple"
LOCAL_DIR = "./simple_upload_model"

# 서빙 컨테이너에 설치될 의존성. 버전 고정 필수.
PIP_REQUIREMENTS = [
    "mlflow==2.16.2",
    "pandas==2.2.2",
]


# ── 1. 알고리즘 — 전부 사칙연산 ───────────────────────────
# 뒷 단계가 앞 단계 결과를 받아 쓴다. 이 의존 관계만 실제와 같게 두고,
# 안쪽 수식은 나중에 PRE_THK_VM.py / REMOVAL_RATE.py / OFFSET.py 로 교체한다.

def step1_pre_thk_vm(setup: dict) -> float:
    """1단계: 입고 두께 예측. (진짜는 회귀 + moving average)"""
    return setup["a"] + setup["b"]


def step2_removal_rate(setup: dict, pre_thk: float) -> float:
    """2단계: 제거율. 1단계 결과를 받아 쓴다."""
    return (pre_thk - setup["post_thk"]) / setup["pol_time"]


def step3_offset(setup: dict, rr: float) -> float:
    """3단계: 보정값. 2단계 결과를 받아 쓴다."""
    return setup["target"] - rr * setup["pol_time"]


def mico_algorithm(setup: dict) -> dict:
    """set-up 1건을 받아 3단계를 순서대로 실행한다."""
    pre_thk = step1_pre_thk_vm(setup)
    rr = step2_removal_rate(setup, pre_thk)
    offset = step3_offset(setup, rr)
    return {
        "equipment_id": setup["equipment_id"],
        "pre_thk": pre_thk,   # 중간값도 같이 반환해서 흐름을 눈으로 확인
        "rr": rr,
        "offset": offset,
        "status": "success",
    }


# ── 2. MLflow 래퍼 ────────────────────────────────────────
# AI Studio 가 요구하는 껍데기. predict() 하나만 있으면 되고,
# 안에 뭐가 들었는지는 MLflow 가 신경 쓰지 않는다 (ML 모델일 필요 없음).
class MicoModel(mlflow.pyfunc.PythonModel):
    def predict(self, context, model_input: pd.DataFrame) -> pd.DataFrame:
        results = []
        for raw in model_input["setup_json"]:
            try:
                out = mico_algorithm(json.loads(raw))
            except Exception as exc:  # 한 건이 실패해도 나머지는 계속 처리
                out = {"status": "error", "message": f"{type(exc).__name__}: {exc}"}
            results.append(json.dumps(out, ensure_ascii=False))
        return pd.DataFrame({"result_json": results})


# ── 3. 샘플 입출력 (시그니처·검증에 공용) ─────────────────
SAMPLE_SETUPS = [
    {"equipment_id": "EQ001", "a": 1, "b": 2, "post_thk": 0, "pol_time": 1, "target": 10},
    {"equipment_id": "EQ002", "a": 5, "b": 5, "post_thk": 2, "pol_time": 2, "target": 20},
    # 의도적 실패 케이스 — 한 건이 죽어도 batch 는 완주하는지 본다
    {"equipment_id": "EQ003", "a": 1, "b": 2, "post_thk": 0, "pol_time": 0, "target": 10},
]


def build_sample():
    """입출력 스키마 추론에 쓸 샘플 DataFrame 과 signature 를 만든다."""
    sample_in = pd.DataFrame(
        {"setup_json": [json.dumps(s, ensure_ascii=False) for s in SAMPLE_SETUPS]}
    )
    sample_out = MicoModel().predict(None, sample_in)
    return sample_in, infer_signature(sample_in, sample_out)


def show_predictions(model, sample_in: pd.DataFrame) -> None:
    """모델을 실제로 호출해 결과를 출력한다."""
    for row in model.predict(sample_in)["result_json"]:
        print("   ", json.loads(row) if isinstance(row, str) else row)


# ── 4. 업로드 / 로컬 저장 ─────────────────────────────────

def upload(tracking_uri: str) -> None:
    """tracking 서버에 모델을 로깅하고 레지스트리에 등록한 뒤 되불러 검증한다."""
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(EXPERIMENT_NAME)
    print(f"[1/4] tracking = {tracking_uri} / experiment = {EXPERIMENT_NAME}")

    sample_in, signature = build_sample()

    print("[2/4] 업로드 중...")
    with mlflow.start_run() as run:
        mlflow.pyfunc.log_model(
            artifact_path=ARTIFACT_PATH,
            python_model=MicoModel(),   # 이 파일 안의 클래스 → 값으로 직렬화됨
            signature=signature,
            input_example=sample_in,
            pip_requirements=PIP_REQUIREMENTS,
        )
        model_uri = f"runs:/{run.info.run_id}/{ARTIFACT_PATH}"
        print(f"      run_id    = {run.info.run_id}")
        print(f"      model_uri = {model_uri}")

    print(f"[3/4] 레지스트리 등록: {REGISTERED_MODEL_NAME}")
    version = mlflow.register_model(model_uri, REGISTERED_MODEL_NAME)
    print(f"      version   = {version.version}")
    print(f"      models_uri= models:/{REGISTERED_MODEL_NAME}/{version.version}")

    print("[4/4] 되불러서 검증")
    show_predictions(mlflow.pyfunc.load_model(model_uri), sample_in)
    print("\n업로드 완료.")


def save_local() -> None:
    """서버 없이 로컬 폴더에 저장하고 되불러 검증한다."""
    print("tracking 서버 주소가 없어 로컬 저장으로 실행합니다.")
    print("실제 업로드: python3 simple_upload.py --uri http://<host>:5000\n")

    sample_in, signature = build_sample()

    shutil.rmtree(LOCAL_DIR, ignore_errors=True)
    print(f"[1/2] 저장 중: {LOCAL_DIR}")
    mlflow.pyfunc.save_model(
        path=LOCAL_DIR,
        python_model=MicoModel(),
        signature=signature,
        input_example=sample_in,
        pip_requirements=PIP_REQUIREMENTS,
    )

    print("[2/2] 되불러서 검증")
    show_predictions(mlflow.pyfunc.load_model(LOCAL_DIR), sample_in)
    print(f"\n로컬 저장 완료: {LOCAL_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--uri",
        default=os.environ.get("MLFLOW_TRACKING_URI", ""),
        help="MLflow tracking 서버 주소. 없으면 로컬 저장만 한다.",
    )
    args = parser.parse_args()

    if args.uri and "<" not in args.uri:
        upload(args.uri)
    else:
        save_local()


if __name__ == "__main__":
    main()
