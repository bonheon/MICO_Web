"""올라간 모델이 실제로 어떻게 생겼는지 확인한다. 배포 전/후 자가 진단용.

`NOT_IMPLEMENTED` / `Inference Error` 가 떴을 때 **추측하지 말고 이걸 먼저 돌린다.**

    {"error_code":"15001","error_type":"NotImplementedError",
     "hcp_error_type":"NOT_IMPLEMENTED","error_message":"Inference Error"}

이 에러는 MLflow 안에서 딱 한 곳에서만 나온다 — `PythonModel.predict_stream`
기본 구현(`mlflow/pyfunc/model.py`). 즉 **배포된 클래스에 predict_stream
오버라이드가 없다**는 뜻이다. 내 소스에 있어도 소용없다. 올라간 것이 기준이다.

참고: MLflow 자체 서빙(`mlflow models serve` 의 `/invocations`)에는 스트리밍
경로가 없어서 predict_stream 을 아예 부르지 않는다. 그래서 로컬에서는 200 이
나오는데 사내 엔드포인트에서만 이 에러가 난다. 게이트웨이가 predict_stream 을
직접 부르기 때문이다. **로컬 200 은 이 에러가 없다는 증거가 못 된다.**

## 쓰는 법

    # 레지스트리의 특정 버전
    python3 mico_check_model.py --model "models:/MICO_Text/3"

    # 방금 만든 run
    python3 mico_check_model.py --model "runs:/<run_id>/ai_studio"

    # 노트북에서
    from mico_check_model import check
    check("models:/MICO_Text/3")

tracking 서버에 붙어야 하면 mico_text_upload.py 의 {TODO} 와 같은 값을 넣는다.
"""

import argparse
import json
import os
import sys

import mlflow
import mlflow.pyfunc

# ── 접속 설정 (레지스트리 모델을 볼 때만 필요) ────────────
mlflow_tracking_uri = "{TODO}"
mlflow_tracking_username = "aistudio"
mlflow_tracking_password = "{TODO}"


def connect():
    if mlflow_tracking_uri == "{TODO}":
        return                      # 로컬 경로만 볼 때는 붙지 않는다
    os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"
    os.environ["MLFLOW_TRACKING_USERNAME"] = mlflow_tracking_username
    os.environ["MLFLOW_TRACKING_PASSWORD"] = mlflow_tracking_password
    mlflow.set_tracking_uri(mlflow_tracking_uri)


def check(model_uri, payload=None):
    """모델을 받아 열어 보고 문제가 될 지점을 짚어 준다."""
    connect()
    print(f"모델: {model_uri}")
    model = mlflow.pyfunc.load_model(model_uri)

    flavor = model.metadata.flavors.get("python_function", {})
    streamable = flavor.get("streamable")

    print("\n[1] MLmodel 기록")
    print(f"    streamable     : {streamable}")
    print(f"    loader_module  : {flavor.get('loader_module')}")

    # 실제 클래스에 predict_stream 오버라이드가 있는지 — 이게 핵심이다
    print("\n[2] 배포된 클래스 (NOT_IMPLEMENTED 의 원인이 여기 있다)")
    impl = getattr(model, "_model_impl", None)
    pm = getattr(impl, "python_model", None)
    if pm is None:
        print("    PythonModel 이 아니다 — 이 검사는 건너뛴다")
    else:
        base = mlflow.pyfunc.PythonModel
        has_stream = type(pm).predict_stream is not base.predict_stream
        print(f"    클래스          : {type(pm).__module__}.{type(pm).__name__}")
        print(f"    predict_stream  : {'재정의됨 (정상)' if has_stream else '없음 (이게 원인)'}")
        if not has_stream:
            print("    -> 업로드한 클래스에 predict_stream 을 넣고 다시 올릴 것")
        if type(pm).__module__ != "__main__":
            print(f"    !! 클래스가 __main__ 이 아니다 ({type(pm).__module__}).")
            print("       업로드 스크립트를 import 하지 말고 직접 실행할 것")

    # signature
    print("\n[3] signature")
    sig = model.metadata.signature
    print(f"    inputs : {sig.inputs if sig else '(없음)'}")
    print(f"    outputs: {sig.outputs if sig else '(없음)'}")

    # 실제 호출
    if payload is None:
        payload = _load_serving_example(model_uri)
    if payload is None:
        print("\n[4] 호출 검사 건너뜀 (serving_input_example.json 을 못 찾음)")
        return

    print("\n[4] 실제 호출")
    try:
        print(f"    predict()       -> {model.predict(payload)}")
    except Exception as e:
        print(f"    predict() 실패   -> {type(e).__name__}: {e}")
    try:
        print(f"    predict_stream()-> {list(model.predict_stream(payload))}")
    except Exception as e:
        print(f"    predict_stream() 실패 -> {type(e).__name__}: {e}")
        print("    -> 엔드포인트에서 NOT_IMPLEMENTED 가 나는 이유가 이것이다")


def _load_serving_example(model_uri):
    """모델에 같이 올라간 serving_input_example.json 을 꺼낸다."""
    try:
        local = mlflow.artifacts.download_artifacts(model_uri)
    except Exception:
        return None
    path = os.path.join(local, "serving_input_example.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help='예: models:/MICO_Text/3')
    if "ipykernel" in sys.modules:
        return ap.parse_args([])
    args, _unknown = ap.parse_known_args()
    return args


if __name__ == "__main__":
    check(_parse_args().model)
