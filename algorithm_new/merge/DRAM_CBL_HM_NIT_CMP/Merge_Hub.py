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

run(FAMILY, OPER_DESC, PRE_OPER_CONFIG)
