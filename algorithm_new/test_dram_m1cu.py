# ════════════════════════════════════════════════════════════════════
# [TEST 삭제] 이 파일 전체 삭제 대상
# 로컬 환경 전용 테스트 러너. 회사 실서버에서는 불필요.
# ════════════════════════════════════════════════════════════════════

"""
DRAM M1 CU CMP 알고리즘 파이프라인 테스트 러너
==============================================
실행 위치: algorithm_new/
  python3 test_dram_m1cu.py

외부 의존성 Mock:
  - MongoClient      : 빈 컬렉션 반환 (check_alarm 용)
  - load_pre_thk_data: CSV merge_df 기반 VM=0 처리 (MongoDB 우회)
  - load_rr_data     : 가상 B1/B0 컬럼 추가 (MongoDB RR 테이블 우회)
"""

import sys
import os
from pathlib import Path
from unittest.mock import MagicMock

# ── sys.path: algorithm_new/ 를 최상위로 ─────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

# ────────────────────────────────────────────────────────────────────────
# 1. MongoClient 전역 Mock (pymongo 임포트 전에 교체)
# ────────────────────────────────────────────────────────────────────────
import pymongo as _pymongo

_mock_collection = MagicMock()
_mock_collection.find.return_value = iter([])
_mock_collection.list_collection_names.return_value = []

_mock_db = MagicMock()
_mock_db.__getitem__.return_value = _mock_collection
_mock_db.list_collection_names.return_value = []

_mock_mongo_client = MagicMock()
_mock_mongo_client.__getitem__.return_value = _mock_db
_mock_mongo_client.close.return_value = None

_pymongo.MongoClient = MagicMock(return_value=_mock_mongo_client)

# ────────────────────────────────────────────────────────────────────────
# 2. Common 모듈 임포트 (day 패키지 및 Get_Data / MongoDB_Control 포함)
# ────────────────────────────────────────────────────────────────────────
import Common.REMOVAL_RATE as _rr_mod
import Common.OFFSET as _offset_mod

# ────────────────────────────────────────────────────────────────────────
# 3. load_pre_thk_data Mock
#    MongoDB에서 Pre_Thk_VM을 불러오는 대신 VM=0으로 처리
# ────────────────────────────────────────────────────────────────────────
def _mock_load_pre_thk_data(merge_df, mico_info_key, mongo_url, mongo_db):
    merge_df_rr = merge_df.copy()
    for thk_key in mico_info_key['Thk_Para'].unique():
        merge_df_rr[f'{thk_key}_VM'] = 0.0
    print(f'    [mock] load_pre_thk_data: VM=0.0 for {list(mico_info_key["Thk_Para"].unique())}')
    return merge_df_rr

_rr_mod.Removal_Rate_Get.load_pre_thk_data = staticmethod(_mock_load_pre_thk_data)

# ────────────────────────────────────────────────────────────────────────
# 4. load_rr_data Mock
#    MongoDB에서 RR B1/B0를 불러오는 대신 가상값 삽입
#    → compute_offset 가 정상 경로로 실행됨
# ────────────────────────────────────────────────────────────────────────
def _mock_load_rr_data(merge_df, Fab, Lot_Code, Oper_Desc, APC_Para_List, mongo_url, mongo_db):
    merge_df_out = merge_df.copy()
    # 대표 RR 기울기/절편 (테스트 전용 임의값)
    for para in APC_Para_List:
        merge_df_out[f'{para}_B1'] = 0.80   # Å/sec per km
        merge_df_out[f'{para}_B0'] = 5.00   # Å/sec
    print(f'    [mock] load_rr_data: 가상 B1=0.80 / B0=5.00 삽입 for {list(APC_Para_List)}')
    return merge_df_out

_offset_mod.OFFSET_Get.load_rr_data = staticmethod(_mock_load_rr_data)

# ────────────────────────────────────────────────────────────────────────
# 5. 파이프라인 실행
# ────────────────────────────────────────────────────────────────────────
from Common.Module import run

FAMILY    = 'DRAM'
OPER_DESC = 'M1 CU CMP'
POL_TYPE  = 3

if __name__ == '__main__':
    run(FAMILY, OPER_DESC, POL_TYPE)
