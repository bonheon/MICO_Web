import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parents[2]))
from Common.Merge_Data import run

FAMILY    = 'DRAM'
OPER_DESC = 'M1 CU CMP'

PRE_OPER_CONFIG = {
    2: 'SRC_HUB',  # 13P·ED·Z5 다존 → pivot 모드 자동 적용
}

run(FAMILY, OPER_DESC, PRE_OPER_CONFIG)
