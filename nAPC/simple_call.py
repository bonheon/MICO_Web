"""업로드한 모델을 불러서 호출해 보는 예제. `simple_upload.py` 다음에 실행한다.

`simple_upload.py` 와 같은 셀 구조다. Jupyter 셀에 그대로 붙여넣어도 된다.

    python3 simple_call.py

[1] 의 {TODO} 를 채우면 레지스트리(`models:/...`)에서 불러오고,
그대로 두면 `simple_upload.py` 가 만든 로컬 폴더에서 불러온다.
[3] 의 setups 값을 바꿔가며 결과가 어떻게 달라지는지 보면 된다.
"""

# %% [1] 접속 설정 ─────────────────────────────────────────────────────────
import os

import mlflow

mlflow_tracking_uri = "{TODO}"          # simple_upload.py 에 넣은 값과 같게
mlflow_tracking_username = "aistudio"
mlflow_tracking_password = "{TODO}"

mlflow_register_model_name = "MICO_Algorithm_Simple"
model_version = "1"                     # 업로드 때 찍힌 version. "latest" 도 된다
local_dir = "./simple_upload_model"     # 서버 없이 로컬 저장했을 때 쓸 경로

USE_REGISTRY = "{TODO}" not in mlflow_tracking_uri

if USE_REGISTRY:
    os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"
    os.environ["MLFLOW_TRACKING_USERNAME"] = mlflow_tracking_username
    os.environ["MLFLOW_TRACKING_PASSWORD"] = mlflow_tracking_password
    mlflow.set_tracking_uri(mlflow_tracking_uri)
    model_uri = f"models:/{mlflow_register_model_name}/{model_version}"
else:
    model_uri = local_dir

print(f"model_uri = {model_uri}")


# %% [2] 모델 불러오기 ─────────────────────────────────────────────────────
import logging

import mlflow.pyfunc

logging.getLogger("mlflow").setLevel(logging.ERROR)

model = mlflow.pyfunc.load_model(model_uri)
print("로드 완료")

# 이 모델이 어떤 입력을 받는지 (업로드 때 input_example 로 결정된 계약)
print("\n[signature]")
print(model.metadata.signature)


# %% [3] 입력 만들기 ───────────────────────────────────────────────────────
# 값을 바꿔가며 결과가 어떻게 달라지는지 보면 된다.
import json

import pandas as pd

setups = [
    {"equipment_id": "EQ001", "a": 1, "b": 2, "post_thk": 0, "pol_time": 1, "target": 10},
    {"equipment_id": "EQ002", "a": 5, "b": 5, "post_thk": 2, "pol_time": 2, "target": 20},
    {"equipment_id": "EQ003", "a": 7, "b": 3, "post_thk": 2, "pol_time": 4, "target": 30},
    # 실패 케이스도 같이 넣어 batch 가 완주하는지 본다
    {"equipment_id": "EQ004", "a": 1, "b": 2, "post_thk": 0, "pol_time": 0, "target": 10},
]
# 업로드 때 쓴 것과 같은 엔벨로프 형식이어야 한다 (MLflow 가 스키마를 강제한다)
#
# 주의: model.predict() 는 넘긴 dict 를 **제자리에서 고친다**. 스키마를 맞추면서
# shape 의 int 를 numpy.int64 로 바꿔놓기 때문에, 같은 dict 를 나중에
# json 으로 보내려 하면 "Object of type int64 is not JSON serializable" 이 난다.
# 그래서 호출할 때마다 새로 만들어 쓴다.

def build_payload(setup_list: list) -> dict:
    rows = [json.dumps(s, ensure_ascii=False) for s in setup_list]
    return {
        "input": [
            {
                "name": "mico_setup",
                "shape": [len(rows), 1],
                "datatype": "BYTES",
                "data": rows,
            }
        ]
    }


print(pd.DataFrame(setups))


# %% [4] 호출 + 결과 보기 ──────────────────────────────────────────────────
raw = model.predict(build_payload(setups))

print("[원본 반환값]")
print(type(raw))
print(raw)

# result_json 컬럼 안에 JSON 문자열이 들어 있으니 풀어서 본다
results = [json.loads(r) for r in raw["result_json"]]

print("\n[풀어서 본 결과]")
for setup, r in zip(setups, results):
    print(f"  {setup['equipment_id']}: {r}")

print("\n[표로]")
print(pd.DataFrame(results))


# %% [5] 계산이 맞는지 손으로 검산 ─────────────────────────────────────────
# EQ001: a=1, b=2 -> pre_thk = 1+2 = 3
#        rr     = (pre_thk - post_thk) / pol_time = (3-0)/1 = 3.0
#        offset = (target - rr*pol_time) * gain  = (10-3*1)*1.0 = 7.0
ok = results[0]
print(f"EQ001 pre_thk={ok['pre_thk']} (기대 3)")
print(f"EQ001 rr     ={ok['rr']} (기대 3.0)")
print(f"EQ001 offset ={ok['offset']} (기대 7.0)")
print("검산 일치" if (ok["pre_thk"], ok["rr"], ok["offset"]) == (3, 3.0, 7.0) else "검산 불일치")


# %% [6] HTTP 엔드포인트로 호출 ────────────────────────────────────────────
# AI Studio 에서 엔드포인트를 배포하고 주소를 받은 뒤에 쓴다.
# 주소를 안 넣으면 이 셀은 건너뛴다.
endpoint_url = "{TODO}"     # 예: "https://<host>/serving/mico/invocations"

if "{TODO}" not in endpoint_url:
    import requests

    resp = requests.post(
        endpoint_url,
        json=build_payload(setups),         # 매번 새로 만든다 ([3] 주의 참고)
        headers={"Content-Type": "application/json"},
        auth=(mlflow_tracking_username, mlflow_tracking_password),
        verify=False,                       # 사내 자체서명 인증서
        timeout=60,                         # 엔드포인트는 60초 제한
    )
    print(f"HTTP {resp.status_code}")
    print(resp.json())
else:
    print("endpoint_url 이 비어 있어 건너뜁니다.")
    print("로컬에서 서빙해 보려면:")
    print(f"  mlflow models serve -m {model_uri} -p 5001 --env-manager local")


# %% [7] 엔드포인트가 에러를 돌려줄 때 진단 ────────────────────────────────
# 사내 엔드포인트가 HTTP 200 을 주면서 본문에 이런 걸 담아 보내면 에러다.
#   {"error_code": "15001", "error_type": "NotImplementedError",
#    "hcp_error_type": "NOT_IMPLEMENTED", "error_message": "Inference Error"}
#
# 이건 MLflow 표준 서버 응답이 아니라 사내 게이트웨이가 감싼 것이다.
# [4] 의 model.predict() 가 잘 되는데 엔드포인트만 실패한다면,
# 모델 자체는 멀쩡하고 **서빙 런타임이 부르는 메서드가 다른 것**이다.
#
# 사내 예제가 쓰는 aiu_custom.predict.ModelWrapper 를 열어보면 그 계약이 나온다.
# (AI Studio 노트북에서 실행할 것 — 그쪽에만 설치돼 있다)
try:
    import inspect

    import aiu_custom.predict as ac

    print("=== aiu_custom.predict 전체 소스 ===")
    print(inspect.getsource(ac))
    print("\n=== ModelWrapper 가 가진 메서드 ===")
    print([m for m in dir(ac.ModelWrapper) if not m.startswith("__")])
except ImportError as exc:
    print(f"aiu_custom 을 불러올 수 없습니다: {exc}")
    print("AI Studio 노트북에서 실행하면 사내 래퍼의 계약을 확인할 수 있습니다.")

# 지금 올린 모델이 어떤 메서드를 갖고 있는지 (비교용)
print("\n=== 지금 모델의 python_model 메서드 ===")
try:
    python_model = model._model_impl.python_model
    print(type(python_model).__name__,
          [m for m in dir(python_model) if not m.startswith("_")])
except Exception as exc:
    print(f"확인 불가: {exc}")
