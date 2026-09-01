"""방식 B — 모델을 로컬 폴더에 저장하고 zip 으로 압축한다.

tracking 서버 없이 동작하므로 가장 먼저 실행해볼 수 있다.

    python3 save_model.py
"""

import os
import shutil

import mlflow.pyfunc
import pandas as pd
from mlflow.models.signature import infer_signature

from model_wrapper import MicoAlgorithm

MODEL_DIR = "./mico_model"
ZIP_BASE = "./mico_model"
CONFIG_PATH = "./artifacts/mico_config.json"
CODE_PATH = "./mico_core"

# 서빙 환경에 설치될 의존성. 버전 고정 필수.
PIP_REQUIREMENTS = [
    "mlflow==2.16.2",
    "pandas==2.2.2",
    "numpy==1.26.4",
]

# 저장 후 존재해야 하는 항목들
EXPECTED_ENTRIES = [
    "MLmodel",
    "conda.yaml",
    "requirements.txt",
    "python_model.pkl",
    "code",
    "artifacts",
]


def build_signature():
    """입출력 스키마 추론에 쓸 샘플 입출력을 만든다."""
    sample_in = pd.DataFrame(
        {
            "setup_json": [
                '{"equipment_id":"EQ001","target":1000.0,'
                '"measurements":[1012.0,1008.0,1015.0]}'
            ]
        }
    )
    sample_out = pd.DataFrame({"result_json": ['{"dispersion_gain":0.13}']})
    return sample_in, sample_out, infer_signature(sample_in, sample_out)


def main() -> None:
    """모델을 저장하고 산출물을 검사한 뒤 zip 으로 압축한다."""
    if os.path.exists(MODEL_DIR):
        print(f"[1/4] 기존 폴더 삭제: {MODEL_DIR}")
        shutil.rmtree(MODEL_DIR)

    sample_in, _, signature = build_signature()

    print("[2/4] 모델 저장 중...")
    mlflow.pyfunc.save_model(
        path=MODEL_DIR,
        python_model=MicoAlgorithm(),
        artifacts={"config": CONFIG_PATH},
        code_paths=[CODE_PATH],
        signature=signature,
        input_example=sample_in,
        pip_requirements=PIP_REQUIREMENTS,
    )

    print("[3/4] 산출물 검사")
    missing = []
    for name in EXPECTED_ENTRIES:
        path = os.path.join(MODEL_DIR, name)
        ok = os.path.exists(path)
        print(f"   {'OK  ' if ok else 'MISS'} {name}")
        if not ok:
            missing.append(name)
    if missing:
        raise RuntimeError(f"저장 산출물 누락: {missing}")

    print("[4/4] zip 압축 중...")
    zip_path = shutil.make_archive(ZIP_BASE, "zip", MODEL_DIR)
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"완료: {zip_path} ({size_mb:.2f} MB)")


if __name__ == "__main__":
    main()
