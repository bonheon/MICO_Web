"""MICO 알고리즘 실행 엔진.

지금은 offset 보정 한 단계만 계산하는 최소 예제다.
실제 알고리즘(algorithm_new)을 이관할 때 run() 내부만 교체하면 된다.

주의: DB 커넥션, 파일 핸들, 스레드 등 pickle 불가능한 객체를
__init__ 에서 만들지 말 것. MLflow 가 이 객체를 pickle 로 저장한다.
"""

from typing import Any, Dict

from mico_core.utils import clip, rmse_to_target

# 설정값 기본치 (mico_config.json 이 없을 때 사용)
DEFAULT_OFFSET_LIMIT = 50.0
DEFAULT_GAIN = 1.0


class MicoEngine:
    """set-up 정보 1건을 받아 APC 파라미터를 계산하는 엔진."""

    def __init__(self, config: Dict[str, Any]) -> None:
        """설정값을 주입받는다. 무거운 리소스는 여기서 만들지 않는다."""
        self.config = config or {}
        self.offset_limit: float = float(
            self.config.get("offset_limit", DEFAULT_OFFSET_LIMIT)
        )
        self.gain: float = float(self.config.get("gain", DEFAULT_GAIN))

    def run(self, setup: Dict[str, Any]) -> Dict[str, Any]:
        """set-up 1건을 받아 알고리즘을 실행하고 결과 dict 를 반환한다.

        입력 예시:
            {"equipment_id": "EQ001", "target": 1000.0,
             "measurements": [1012.0, 1008.0, 1015.0]}
        """
        equipment_id = setup.get("equipment_id")
        target = float(setup.get("target", 0.0))
        measurements = setup.get("measurements") or []

        if not measurements:
            raise ValueError(
                f"measurements 가 비어 있습니다 (equipment_id={equipment_id})"
            )

        mean_value = sum(float(v) for v in measurements) / len(measurements)

        # offset = target 과 실측 평균의 차이. gain 을 곱하고 리미트로 자른다.
        raw_offset = (target - mean_value) * self.gain
        offset = clip(raw_offset, -self.offset_limit, self.offset_limit)

        # offset 적용 전후 산포(target 기준 RMSE) 비교
        before = rmse_to_target(measurements, target)
        after = rmse_to_target([float(v) + offset for v in measurements], target)

        return {
            "equipment_id": equipment_id,
            "opt_params": {"offset": round(offset, 4)},
            "dispersion_before": round(before, 4),
            "dispersion_after": round(after, 4),
            "dispersion_gain": round(before - after, 4),
            "status": "success",
        }
