import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parents[2]))
from Common.Merge_Data import run

FAMILY    = 'NAND'
OPER_DESC = 'M0C FILL OX CMP'

PRE_OPER_CONFIG = {
    2: 'SRC_HUB',  # para 여러 개(13P·ED·EX) → pivot 모드 자동 적용
    3: 'SRC_HUB',
}

run(FAMILY, OPER_DESC, PRE_OPER_CONFIG)
