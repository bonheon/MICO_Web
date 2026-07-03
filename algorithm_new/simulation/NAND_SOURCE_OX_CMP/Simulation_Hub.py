import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parents[2]))
from Common.Simulation import run

FAMILY    = 'NAND'
OPER_DESC = 'SOURCE OX CMP'

# ── Pre_Thk 산식 control (test 시 여기만 수정) ──────────────────────────────
# PRE_OPER   : moving avg(Pre_Thk 학습값) 사용 여부 (True / False)
# PRE_OPER2~4: None(미사용) | 'raw'(계측값 그대로) | 'reg'(회귀식 val*b1+b0)
#              | (mode, weight) — weight 지정 (예: ('reg', 2), ('raw', 0.5))
PRE_THK_FORMULA = {
    'PRE_OPER'  : True,
    'PRE_OPER2' : ('reg', 2),    # source: SOURCE OX CMP 는 OPER2 weight 2
    'PRE_OPER3' : None,
    'PRE_OPER4' : None,
}

run(FAMILY, OPER_DESC,
    pre_thk_formula=PRE_THK_FORMULA)
