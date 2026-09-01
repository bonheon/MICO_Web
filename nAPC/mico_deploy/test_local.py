"""로컬 검증 스크립트.

(1) 저장된 모델을 로드해서 predict 가 되는지 확인
(2) mlflow models serve 로 띄운 서버에 HTTP 호출

    # (1) 만 실행
    python3 test_local.py

    # (2) 까지 실행하려면 다른 터미널에서 먼저 서버를 띄운다
    mlflow models serve -m ./mico_model -p 5001 --env-manager local
    python3 test_local.py --serve
"""

import json
import sys

import mlflow.pyfunc
import pandas as pd

MODEL_DIR = "./mico_model"
SAMPLE_INPUT = "sample_input.json"
REQ_URL = "http://127.0.0.1:5001/invocations"
TIMEOUT_SEC = 300


def load_sample_rows() -> list:
    """sample_input.json 의 setup_json 문자열 목록을 읽는다."""
    with open(SAMPLE_INPUT, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [row[0] for row in data["dataframe_split"]["data"]]


def test_load() -> None:
    """저장된 모델을 직접 로드해서 예측한다."""
    print("=== (1) 로드 테스트 ===")
    model = mlflow.pyfunc.load_model(MODEL_DIR)
    frame = pd.DataFrame({"setup_json": load_sample_rows()})
    out = model.predict(frame)
    for row in out["result_json"]:
        print("   ", json.loads(row))
    print("로드 테스트 통과\n")


def test_serve() -> None:
    """서빙 중인 엔드포인트에 sample_input.json 을 그대로 POST 한다."""
    import requests

    print("=== (2) 서빙 테스트 ===")
    with open(SAMPLE_INPUT, "r", encoding="utf-8") as f:
        data = json.load(f)

    resp = requests.post(
        REQ_URL,
        headers={"Content-Type": "application/json"},
        data=json.dumps(data),  # dump 아님, dumps
        timeout=TIMEOUT_SEC,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"서빙 호출 실패 {resp.status_code}: {resp.text[:500]}")

    for row in resp.json()["predictions"]:
        print("   ", json.loads(row["result_json"]))
    print("서빙 테스트 통과")


if __name__ == "__main__":
    test_load()
    if "--serve" in sys.argv:
        test_serve()
    else:
        print("서빙 테스트는 --serve 옵션으로 실행하세요.")
        print("  mlflow models serve -m ./mico_model -p 5001 --env-manager local")
