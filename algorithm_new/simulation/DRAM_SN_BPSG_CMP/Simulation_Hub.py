import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parents[2]))
from Common.Simulation import run

FAMILY    = 'DRAM'
OPER_DESC = 'SN BPSG CMP'

# ── Pre_Thk 산식 control (test 시 여기만 수정) ──────────────────────────────
# PRE_OPER   : moving avg(Pre_Thk 학습값) 사용 여부 (True / False)
# PRE_OPER2~4: None(미사용) | 'raw'(계측값 그대로) | 'reg'(회귀식 val*b1+b0)
#              | (mode, weight) — weight 지정 (예: ('reg', 2), ('raw', 0.5))
# ※ ITM 사전 계측 para (SP 의 EBARA_PRE_THK*)는 web Set-up 의 Pre_Thk_Para_ITM 으로 자동 적용
PRE_THK_FORMULA = {
    'PRE_OPER'  : True,
    'PRE_OPER2' : None,
    'PRE_OPER3' : None,
    'PRE_OPER4' : None,
}

run(FAMILY, OPER_DESC,
    pre_thk_formula=PRE_THK_FORMULA)
