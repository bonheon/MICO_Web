"""MICO 3단계 체인을 MLflow 모델로 감싸는 최소 예제 — 이 파일 하나가 전부다.

수식은 전부 사칙연산이다. 파이프라인 "모양"만 실제와 같게 두고,
나중에 각 단계 안쪽만 진짜 알고리즘으로 갈아끼운다.

    pip install mlflow pandas
    python3 simple_example.py
"""

import json

import mlflow.pyfunc
import pandas as pd


# ── 1. 알고리즘 3단계 ─────────────────────────────────────
# 뒷 단계가 앞 단계 결과를 받아 쓴다. 이 의존 관계가 핵심이고,
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
    }


# ── 2. MLflow 래퍼 ────────────────────────────────────────
# 여기가 AI Studio 가 요구하는 껍데기. predict() 하나만 있으면 된다.
# 안에 뭐가 들었는지는 MLflow 가 신경 쓰지 않는다 (ML 모델일 필요 없음).
class MicoModel(mlflow.pyfunc.PythonModel):
    def predict(self, context, model_input: pd.DataFrame) -> pd.DataFrame:
        results = []
        for raw in model_input["setup_json"]:
            try:
                out = mico_algorithm(json.loads(raw))
            except Exception as exc:  # 한 건이 실패해도 나머지는 계속 처리
                out = {"error": f"{type(exc).__name__}: {exc}"}
            results.append(json.dumps(out, ensure_ascii=False))
        return pd.DataFrame({"result_json": results})


# ── 3. 저장하고 바로 불러서 실행 ──────────────────────────
if __name__ == "__main__":
    import shutil

    shutil.rmtree("./simple_model", ignore_errors=True)
    mlflow.pyfunc.save_model(path="./simple_model", python_model=MicoModel())
    print("저장 완료: ./simple_model\n")

    model = mlflow.pyfunc.load_model("./simple_model")
    sample = pd.DataFrame({"setup_json": [
        '{"equipment_id":"EQ001","a":1,"b":2,"post_thk":0,"pol_time":1,"target":10}',
        '{"equipment_id":"EQ002","a":5,"b":5,"post_thk":2,"pol_time":2,"target":20}',
        '{"equipment_id":"EQ003","a":1,"b":2,"post_thk":0,"pol_time":0,"target":10}',
    ]})
    for row in model.predict(sample)["result_json"]:
        print(" ", json.loads(row))
