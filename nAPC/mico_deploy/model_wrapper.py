"""MICO 알고리즘을 MLflow pyfunc 모델 인터페이스로 감싸는 래퍼.

입출력을 JSON 문자열 컬럼 하나로 고정한다.
set-up 정보가 중첩 구조라서 DataFrame 컬럼으로 펼치면 스키마가 깨지기 때문이다.

    입력:  DataFrame({"setup_json":  ["<json 문자열>", ...]})
    출력:  DataFrame({"result_json": ["<json 문자열>", ...]})
"""

import json
from typing import Any, Dict

import mlflow.pyfunc
import pandas as pd

INPUT_COLUMN = "setup_json"
OUTPUT_COLUMN = "result_json"


class MicoAlgorithm(mlflow.pyfunc.PythonModel):
    """nAPC 가 보낸 set-up batch 를 받아 MICO 알고리즘을 실행한다."""

    def load_context(self, context) -> None:
        """모델 로드 시 1회 호출된다. 설정 파일을 읽고 엔진을 만든다."""
        # import 는 이 메서드 안에서 수행한다 (pickle 시점 의존성 회피)
        from mico_core.engine import MicoEngine

        config_path = context.artifacts["config"]
        with open(config_path, "r", encoding="utf-8") as f:
            config: Dict[str, Any] = json.load(f)

        self.engine = MicoEngine(config)

    def predict(self, context, model_input: pd.DataFrame) -> pd.DataFrame:
        """batch 를 행 단위로 실행한다. 한 행이 실패해도 전체는 계속 진행한다."""
        if INPUT_COLUMN not in model_input.columns:
            raise ValueError(
                f"입력 DataFrame 에 '{INPUT_COLUMN}' 컬럼이 없습니다. "
                f"실제 컬럼: {list(model_input.columns)}"
            )

        results = []
        for raw in model_input[INPUT_COLUMN]:
            try:
                setup = json.loads(raw)
                result = self.engine.run(setup)
            except Exception as exc:  # noqa: BLE001 - 행 단위 격리가 목적
                result = {
                    "status": "error",
                    "message": f"{type(exc).__name__}: {exc}",
                }
            results.append(json.dumps(result, ensure_ascii=False))

        return pd.DataFrame({OUTPUT_COLUMN: results})
