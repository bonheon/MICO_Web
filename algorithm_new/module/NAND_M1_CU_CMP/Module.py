import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parents[2]))
from Common.Module import run

FAMILY    = 'NAND'
OPER_DESC = 'M1 CU CMP'

run(FAMILY, OPER_DESC)
