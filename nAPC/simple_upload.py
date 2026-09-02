"""사칙연산만 든 모델을 '코드만으로' MLflow(AI Studio)에 업로드하는 한 파일 예제.

`simple_example.py` 는 로컬 저장까지만 한다. 이 파일은 거기서 한 걸음 더 나가
tracking 서버에 log + 레지스트리 등록까지 한다. 사내에서 실제로 올려볼 파일.

모델 클래스를 이 파일 안에 두는 것이 핵심이다. 그러면 MLflow 가 클래스를
cloudpickle 로 '값 자체'로 직렬화하므로 code_paths·별도 패키지 없이
이 파일 하나만 있으면 업로드가 끝난다.
(사내 예제의 `code_paths=["aiu_custom"]` 은 래퍼가 별도 모듈일 때 필요한 것)

    pip install mlflow==2.16.2 pandas

    # 1) 서버 주소를 아직 못 받았을 때 — 로컬 저장까지만 확인
    python3 simple_upload.py

    # 2) 주소를 받은 뒤 — 실제 업로드 (계정은 환경변수로)
    export MLFLOW_TRACKING_USERNAME=aistudio
    export MLFLOW_TRACKING_PASSWORD='...'          # 사내 AI Studio 계정
    python3 simple_upload.py --uri https://<ai-studio-mlflow-host>

    # 환경변수 대신 인자로 줘도 된다
    python3 simple_upload.py --uri https://<host> --user aistudio --password '...'
"""

import argparse
import json
import logging
import os
import shutil

import mlflow
import mlflow.pyfunc
import pandas as pd
from mlflow.models.signature import infer_signature

logging.getLogger("mlflow").setLevel(logging.ERROR)   # 업로드 로그 노이즈 억제

EXPERIMENT_NAME = "MICO"
ARTIFACT_PATH = "ai_studio"        # 사내 예제와 동일하게 맞춤
REGISTERED_MODEL_NAME = "MICO_Algorithm_Simple"
LOCAL_DIR = "./simple_upload_model"
DEFAULT_USERNAME = "aistudio"

# 서빙 컨테이너에 설치될 의존성. 버전 고정 필수.
# 사내 예제처럼 requirements.txt 파일 경로를 줘도 된다 (pip_requirements="requirements.txt").
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

def _to_setup(item) -> dict:
    """입력 원소 1개를 set-up dict 로 만든다. JSON 문자열도 dict 도 받는다."""
    if isinstance(item, str):
        return json.loads(item)
    if isinstance(item, dict):
        return item
    raise TypeError(f"해석할 수 없는 입력 원소: {type(item).__name__}")


def _blocks_to_setups(cells) -> list:
    """AI Studio 엔벨로프의 input 블록들에서 data 를 모아 set-up 리스트로 만든다."""
    rows = []
    for cell in cells:
        blocks = [cell] if isinstance(cell, dict) else list(cell)
        for block in blocks:
            rows.extend(block.get("data", []))
    return [_to_setup(r) for r in rows]


def extract_setups(model_input) -> list:
    """서빙 쪽이 어떤 모양으로 보내든 set-up dict 리스트로 통일한다.

    어느 쪽이 실제로 오는지 아직 확정 전이라 둘 다 받아둔다.
      (1) AI Studio 형  {"input": [{"name":..., "shape":..., "data": [...]}]}
          MLflow 가 스키마를 강제하면서 이걸 input 컬럼 1개짜리 DataFrame 으로
          바꿔서 넘겨준다 (셀 = 블록 리스트). 그래서 두 경우를 같이 받는다.
      (2) MLflow 표준   DataFrame({"setup_json": ['{...}', ...]})
      (3) 그냥 리스트   ['{...}', ...] 또는 [{...}, ...]
    """
    if isinstance(model_input, dict) and "input" in model_input:
        return _blocks_to_setups([model_input["input"]])

    if isinstance(model_input, pd.DataFrame):
        if "input" in model_input.columns:
            return _blocks_to_setups(model_input["input"])
        if "setup_json" in model_input.columns:
            return [_to_setup(v) for v in model_input["setup_json"]]
        return model_input.to_dict("records")   # 컬럼이 그대로 set-up 필드인 경우

    if isinstance(model_input, list):
        return [_to_setup(r) for r in model_input]

    raise TypeError(f"지원하지 않는 입력 형식: {type(model_input).__name__}")


class MicoModel(mlflow.pyfunc.PythonModel):
    def predict(self, context, model_input) -> pd.DataFrame:
        results = []
        for setup in extract_setups(model_input):
            try:
                out = mico_algorithm(setup)
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

SAMPLE_JSON = [json.dumps(s, ensure_ascii=False) for s in SAMPLE_SETUPS]


def build_io(io_style: str):
    """(검증 호출용 입력, log_model 에 넘길 input_example, signature) 를 만든다.

    io_style="aistudio" — 사내 예제와 같은 엔벨로프. signature 는 MLflow 가 추론하게 둔다.
      주의: 이렇게 하면 MLflow 가 엔벨로프 스키마를 **강제**한다. 즉 서빙 호출도
      반드시 {"input":[...]} 모양이어야 하고, setup_json DataFrame 을 보내면 거부된다.
    io_style="mlflow"   — MLflow 표준 DataFrame + 명시적 signature.
    """
    if io_style == "aistudio":
        envelope = {
            "input": [
                {
                    "name": "mico_setup",
                    "shape": [len(SAMPLE_JSON), 1],
                    "datatype": "BYTES",   # 문자열 배열. 사내 예제는 numpy 라 숫자형이었다
                    "data": SAMPLE_JSON,
                }
            ]
        }
        return envelope, envelope, None

    sample_df = pd.DataFrame({"setup_json": SAMPLE_JSON})
    return sample_df, sample_df, infer_signature(sample_df, MicoModel().predict(None, sample_df))


def show_predictions(model, verify_input) -> int:
    """모델을 실제로 호출해 결과를 출력하고 성공 건수를 반환한다."""
    success = 0
    for row in model.predict(verify_input)["result_json"]:
        out = json.loads(row) if isinstance(row, str) else row
        success += int(out.get("status") == "success")
        print("   ", out)
    return success


# ── 4. 업로드 / 로컬 저장 ─────────────────────────────────

def setup_auth(username: str, password: str) -> None:
    """사내 AI Studio 접속용 환경변수를 세팅한다. 이게 없으면 401 이 난다."""
    # 사내 https 가 자체서명 인증서라 검증을 끈다. 이미 지정돼 있으면 그 값을 존중.
    os.environ.setdefault("MLFLOW_TRACKING_INSECURE_TLS", "true")
    if username:
        os.environ["MLFLOW_TRACKING_USERNAME"] = username
    if password:
        os.environ["MLFLOW_TRACKING_PASSWORD"] = password
    elif not os.environ.get("MLFLOW_TRACKING_PASSWORD"):
        print("주의: 비밀번호가 비어 있습니다. 인증이 걸린 서버면 401 이 납니다.")
        print("      export MLFLOW_TRACKING_PASSWORD='...' 또는 --password 로 지정하세요.\n")


def upload(tracking_uri: str, io_style: str) -> None:
    """tracking 서버에 모델을 로깅하고 레지스트리에 등록한 뒤 되불러 검증한다."""
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(EXPERIMENT_NAME)
    print(f"[1/3] tracking = {tracking_uri}")
    print(f"      experiment = {EXPERIMENT_NAME} / io_style = {io_style}")

    verify_input, input_example, signature = build_io(io_style)

    print("[2/3] 업로드 중...")
    with mlflow.start_run() as run:
        # 사칙연산이라 학습 파라미터는 없지만, run 에 무엇으로 올렸는지는 남겨둔다
        mlflow.log_params({"algorithm": "arithmetic_3step", "io_style": io_style})

        info = mlflow.pyfunc.log_model(
            artifact_path=ARTIFACT_PATH,
            python_model=MicoModel(),   # 이 파일 안의 클래스 → 값으로 직렬화됨
            signature=signature,
            input_example=input_example,
            pip_requirements=PIP_REQUIREMENTS,
            registered_model_name=REGISTERED_MODEL_NAME,   # 로깅과 등록을 한 번에
        )
        model_uri = f"runs:/{run.info.run_id}/{ARTIFACT_PATH}"
        print(f"      run_id     = {run.info.run_id}")
        print(f"      model_uri  = {model_uri}")
        print(f"      version    = {info.registered_model_version}")
        print(f"      models_uri = models:/{REGISTERED_MODEL_NAME}/{info.registered_model_version}")

        print("[3/3] 되불러서 검증")
        success = show_predictions(mlflow.pyfunc.load_model(model_uri), verify_input)
        mlflow.log_metrics({"sample_rows": len(SAMPLE_SETUPS), "sample_success": success})

    print("\n업로드 완료.")


def save_local(io_style: str) -> None:
    """서버 없이 로컬 폴더에 저장하고 되불러 검증한다."""
    print("tracking 서버 주소가 없어 로컬 저장으로 실행합니다.")
    print("실제 업로드: python3 simple_upload.py --uri https://<host>\n")

    verify_input, input_example, signature = build_io(io_style)

    shutil.rmtree(LOCAL_DIR, ignore_errors=True)
    print(f"[1/2] 저장 중: {LOCAL_DIR} (io_style = {io_style})")
    mlflow.pyfunc.save_model(
        path=LOCAL_DIR,
        python_model=MicoModel(),
        signature=signature,
        input_example=input_example,
        pip_requirements=PIP_REQUIREMENTS,
    )

    print("[2/2] 되불러서 검증")
    show_predictions(mlflow.pyfunc.load_model(LOCAL_DIR), verify_input)
    print(f"\n로컬 저장 완료: {LOCAL_DIR}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--uri",
        default=os.environ.get("MLFLOW_TRACKING_URI", ""),
        help="MLflow tracking 서버 주소. 없으면 로컬 저장만 한다.",
    )
    parser.add_argument(
        "--user",
        default=os.environ.get("MLFLOW_TRACKING_USERNAME", DEFAULT_USERNAME),
        help=f"tracking 서버 계정 (기본 {DEFAULT_USERNAME})",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("MLFLOW_TRACKING_PASSWORD", ""),
        help="tracking 서버 비밀번호. MLFLOW_TRACKING_PASSWORD 환경변수 권장.",
    )
    parser.add_argument(
        "--io-style",
        choices=["aistudio", "mlflow"],
        default="aistudio",
        help="input_example 형식. aistudio=사내 예제 엔벨로프(기본), mlflow=표준 DataFrame",
    )
    args = parser.parse_args()

    if args.uri and "<" not in args.uri:
        setup_auth(args.user, args.password)
        upload(args.uri, args.io_style)
    else:
        save_local(args.io_style)


if __name__ == "__main__":
    main()
