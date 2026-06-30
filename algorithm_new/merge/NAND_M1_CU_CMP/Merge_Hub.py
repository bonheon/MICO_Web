import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parents[2]))
from Common.Merge_Data import run

FAMILY    = 'NAND'
OPER_DESC = 'M1 CU CMP'

PRE_OPER_CONFIG = {
    2: 'SRC_HUB',
    3: 'SRC_HUB',
    4: 'SRC_HUB',
}

run(FAMILY, OPER_DESC, PRE_OPER_CONFIG, eqp_ch_mode='AMAT')
