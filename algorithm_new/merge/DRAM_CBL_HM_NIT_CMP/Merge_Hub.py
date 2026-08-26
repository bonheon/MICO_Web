import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parents[2]))
from Common.Merge_Data import run

FAMILY    = 'DRAM'
OPER_DESC = 'CBL HM NIT CMP'

PRE_OPER_CONFIG = {
    2: 'MES_HUB',
    3: 'MES_HUB',
}

# 적재 제외할 route(process_id) 목록 — 여기 등록된 route 의 데이터는 merge DB 에 적재되지 않음
# 예) EXCLUDE_PROCESS_IDS = ['ROUTE_ID_1', 'ROUTE_ID_2']
EXCLUDE_PROCESS_IDS = []

run(FAMILY, OPER_DESC, PRE_OPER_CONFIG, exclude_process_ids=EXCLUDE_PROCESS_IDS)
