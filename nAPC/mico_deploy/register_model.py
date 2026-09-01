"""방식 A — MLflow tracking 서버에 모델을 등록한다.

TRACKING_URI 를 받은 뒤에 실행할 것. 그전까지는 save_model.py 로 검증한다.

    python3 register_model.py
"""

import mlflow
import mlflow.pyfunc
import pandas as pd
from mlflow.models.signature import infer_signature

from model_wrapper import MicoAlgorithm
from save_model import CODE_PATH, CONFIG_PATH, PIP_REQUIREMENTS, build_signature

# TODO: AI Studio 담당자에게 확인 후 실제 주소로 교체
TRACKING_URI = "http://<ai-studio-mlflow-host>:5000"
EXPERIMENT_NAME = "MICO"
ARTIFACT_PATH = "mico_model"
REGISTERED_MODEL_NAME = "MICO_Algorithm"


def main() -> None:
    """pyfunc 모델을 tracking 서버에 로깅하고 모델 레지스트리에 등록한다."""
    if "<" in TRACKING_URI:
        raise RuntimeError(
            "TRACKING_URI 가 아직 설정되지 않았습니다. "
            "AI Studio 담당자에게 MLflow tracking 서버 주소를 확인하세요."
        )

    mlflow.set_tracking_uri(TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT_NAME)

    sample_in, _, signature = build_signature()

    with mlflow.start_run() as run:
        mlflow.pyfunc.log_model(
            artifact_path=ARTIFACT_PATH,
            python_model=MicoAlgorithm(),
            artifacts={"config": CONFIG_PATH},
            code_paths=[CODE_PATH],
            signature=signature,
            input_example=sample_in,
            pip_requirements=PIP_REQUIREMENTS,
            registered_model_name=REGISTERED_MODEL_NAME,
        )
        print(f"run_id = {run.info.run_id}")
        print(f"model_uri = runs:/{run.info.run_id}/{ARTIFACT_PATH}")


if __name__ == "__main__":
    main()
