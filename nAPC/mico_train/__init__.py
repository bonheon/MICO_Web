"""nAPC 학습 패키지.

web Set-up 을 payload 로 받아, merge_df 를 DataLake+DataHub 에서 직접 만들어 학습한다.
Django 도 MongoDB 도 쓰지 않는다 (컨테이너에 둘 다 없다).
"""

from .setup_payload import build_payload, to_info_table, INFO_COLUMNS, SCHEMA_VERSION
from .data_source import fetch_merge_df, set_provider
from .entry import run_training, set_trainer
from .result_collector import ResultCollector

__all__ = [
    'build_payload', 'to_info_table', 'INFO_COLUMNS', 'SCHEMA_VERSION',
    'fetch_merge_df', 'set_provider',
    'run_training', 'set_trainer', 'ResultCollector',
]
