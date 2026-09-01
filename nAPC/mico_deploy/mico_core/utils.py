"""MICO 알고리즘 보조 함수 모음."""

from typing import Sequence

import numpy as np


def rmse_to_target(values: Sequence[float], target: float) -> float:
    """측정값들이 target에서 얼마나 벗어나 있는지 RMSE로 계산한다."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return 0.0
    return float(np.sqrt(np.mean((arr - target) ** 2)))


def clip(value: float, low: float, high: float) -> float:
    """value를 [low, high] 범위로 자른다."""
    return float(min(max(value, low), high))
