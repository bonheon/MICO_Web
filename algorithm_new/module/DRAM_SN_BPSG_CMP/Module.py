import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parents[2]))
from Common.Module import run

FAMILY    = 'DRAM'
OPER_DESC = 'SN BPSG CMP'

run(FAMILY, OPER_DESC)
