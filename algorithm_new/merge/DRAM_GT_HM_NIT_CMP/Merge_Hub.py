import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parents[2]))
from Common.Merge_Data import run

FAMILY    = 'DRAM'
OPER_DESC = 'GT HM NIT CMP'

PRE_OPER_CONFIG = {}  # 사전공정 없음

run(FAMILY, OPER_DESC, PRE_OPER_CONFIG, eqp_ch_mode='AMAT')
