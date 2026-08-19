"""APC 산식 엔진 — Simul_APC / Simul_THK 산출 (단일 소스).

Simulation 결과(MICO_Simulation_*)에 들어있는 '학습값 + 실측값' 을 재료로
실제로 장비에 내려갈 APC 값(Simul_APC)과 그 값으로 연마했을 때 나올 두께
(Simul_THK)를 계산한다.

이 모듈 하나만 산식을 정의하고, 두 곳에서 같은 함수를 호출한다.

    · algorithm_new/Common/Simulation.py  — 배치 실행 시 기본 설정으로 계산해 DB 적재
    · setup_mico/views.py                 — web 에서 파라미터를 바꿔가며 즉시 재계산

즉 web 에서 weight 를 바꿔 본 결과와 실제 배치가 내는 값이 어긋날 수 없다.


■ 두 가지 모드 (FB_Type)

  TIME (13P)      : APC = 연마시간. 두께 자체를 Target 에 맞춘다.
  PRESSURE (zone) : APC = 압력. 두께를 직접 맞추는 게 아니라 13P(중심) 대비
                    **편차(BIAS)** 를 0 으로 맞춘다.
                    → zone 두께 = TIME 이 결정한 13P 두께 + 편차
                    → 시간 보정량인 Idle OFFSET 은 산식에서 제외한다.


■ TIME 계산 흐름

    (1) Ref lot 별 FB 값        FB_1 ~ FB_4
    (2) Ref 개수별 weight 결합   Simul_APC        (Ref 없음 → Linear 산식)
    (3) upper/lower limit 적용   Simul_APC_Limit
    (4) 실제 RR 산출            Simul_RR
    (5) 제거량                  Removal_Amount
    (6) 시뮬레이션 두께          Simul_THK

    FB_i    = Ref_APC + (Ref_Post - Target + (Pre_Thk - Ref_Pre_VM) * pre_weight)
                        / RR_DB * rr_weight + Simul_OFFSET - Ref_OFFSET
    Linear  = (Pre_Target + Pre_Thk - Target) / RR_DB + Simul_OFFSET - Pol_Time_1

    Simul_RR       = sign * (Pre_Target + Pre_Thk - THK) / Pol_Time
    Removal_Amount = Simul_RR * (Simul_APC_Limit + Pol_Time_1)
    Simul_THK      = Pre_Target + Pre_Thk - sign * Removal_Amount

  · sign : Thk_Para 가 REV 계열이면 -1 (두께가 반대 방향으로 움직이는 계측)
  · Pol_Time_1 : APC 가 제어하지 않는 '앞단 고정 연마 step'.
      Pol_Time 을 2개 쓰는 공정에서만 존재하므로 Simul_APC 에서는 빼고
      (APC 는 뒷 step 만 결정), 두께 계산에서는 다시 더해 총 연마시간으로 되돌린다.
      1개만 쓰는 공정은 Pol_Time_1 == Pol_Time 이라 항이 0 이어야 한다
      → pol_time_1='auto' 는 Pol_Time_2 컬럼이 있을 때만 항을 살린다.


■ PRESSURE 계산 흐름

  기준이 되는 편차 정의는 학습측(Module.py / REMOVAL_RATE.py)의 BIAS 와 동일하다.

    Bias_Actual = (THK - THK_13P) - (Target - Target_13P)      … 0 이 목표

  이 정의를 뒤집으면 zone 두께는 13P 두께에 편차를 더한 값이 된다.

    THK = THK_13P + (Target - Target_13P) + Bias

  그래서 PRESSURE 시뮬레이션은 **TIME 이 산출한 Simul_THK_13P 위에 편차를 얹는다.**

    (1) 압력 → 편차 민감도 학습   Bias_Slope / Bias_Intercept
        (eqp_id · recipe_id 별로 Bias_Actual 을 APC_Value(압력)에 회귀)
    (2) Ref lot 별 FB 값          FB_1 ~ FB_4      (Idle OFFSET 항 없음)
    (3) weight 결합 → limit       Simul_APC_Limit
    (4) 그 압력에서 나올 편차      Simul_Bias
    (5) 13P 시뮬 두께 + 편차       Simul_THK

    Ref_Bias = (Ref_Post - Ref_13P) - (Target - Target_13P)
    FB_i     = Ref_APC - (Ref_Bias + (Pre_Thk - Ref_Pre_VM) * pre_weight)
                         / Bias_Slope * rr_weight
    Linear   = -(Bias_Intercept + Pre_Thk * pre_weight) / Bias_Slope

    Simul_Bias = Bias_Slope * Simul_APC_Limit + Bias_Intercept
    Simul_THK  = Simul_THK_13P + (Target - Target_13P) + Simul_Bias

  · FB 의 부호가 TIME 과 반대(-)인 이유: TIME 의 RR_DB 는 '제거율'(시간이 늘면
    두께가 준다)이라 부호가 이미 뒤집혀 있고, Bias_Slope 는 d(편차)/d(압력) 그대로라
    Newton 보정 -오차/기울기 를 그대로 쓴다. 기울기 부호는 데이터가 정한다.
  · Bias_Slope 주의: 압력은 편차에 반응해 움직인 제어 출력이라 closed-loop 회귀가
    된다 → 기울기가 실제보다 작게(또는 부호가 뒤집혀) 나올 수 있다.
    신뢰할 수 있는 값을 알고 있으면 bias_slope 에 직접 넣어 고정할 것.


■ Linear 로 빠지는 조건 (두 모드 공통)
    · 쓸 수 있는 Ref 가 하나도 없음
    · Ref_YN 이 'N'
    · Ref_Count 가 ref_skip_count(기본 11)
"""

import ast

import numpy as np
import pandas as pd

MAX_REF = 4

MODE_TIME     = 'TIME'
MODE_PRESSURE = 'PRESSURE'
MODES         = (MODE_TIME, MODE_PRESSURE)


# ── 기본 산식 ──────────────────────────────────────────────────────────────

# TIME
DEFAULT_FB_EXPR = (
    'Ref_APC + (Ref_Post - Target + (Pre_Thk - Ref_Pre_VM) * pre_weight)'
    ' / RR_DB * rr_weight + Simul_OFFSET - Ref_OFFSET'
)
DEFAULT_LINEAR_EXPR  = '(Pre_Target + Pre_Thk - Target) / RR_DB + Simul_OFFSET - Pol_Time_1'
DEFAULT_RR_EXPR      = 'sign * (Pre_Target + Pre_Thk - THK) / Pol_Time'
DEFAULT_REMOVAL_EXPR = 'Simul_RR * (Simul_APC_Limit + Pol_Time_1)'
DEFAULT_THK_EXPR     = 'Pre_Target + Pre_Thk - sign * Removal_Amount'

# PRESSURE — Idle OFFSET(시간 보정) 항 없음
DEFAULT_P_FB_EXPR = (
    'Ref_APC - (Ref_Bias + (Pre_Thk - Ref_Pre_VM) * pre_weight) / Bias_Slope * rr_weight'
)
DEFAULT_P_LINEAR_EXPR = '-(Bias_Intercept + Pre_Thk * pre_weight) / Bias_Slope'
DEFAULT_P_BIAS_EXPR   = 'Bias_Slope * Simul_APC_Limit + Bias_Intercept'
DEFAULT_P_THK_EXPR    = 'Simul_THK_13P + (Target - Target_13P) + Simul_Bias'

# Ref 개수(1~4)별 FB 결합 weight. 기본은 균등 배분.
DEFAULT_WEIGHTS = {
    '1': [1.0],
    '2': [0.5, 0.5],
    '3': [1 / 3, 1 / 3, 1 / 3],
    '4': [0.25, 0.25, 0.25, 0.25],
}

_COMMON_DEFAULTS = {
    'pre_weight'    : 1.0,
    'rr_weight'     : 1.0,
    'weights'       : DEFAULT_WEIGHTS,
    'upper_limit'   : None,          # None = 상한 없음
    'lower_limit'   : None,          # None = 하한 없음
    'ref_skip_count': 11,            # Ref_Count 가 이 값이면 Linear
}

_MODE_DEFAULTS = {
    MODE_TIME: {
        'pol_time_1'  : 'auto',      # 'auto' | 'use' | 'ignore'
        'fb_expr'     : DEFAULT_FB_EXPR,
        'linear_expr' : DEFAULT_LINEAR_EXPR,
        'rr_expr'     : DEFAULT_RR_EXPR,
        'removal_expr': DEFAULT_REMOVAL_EXPR,
        'thk_expr'    : DEFAULT_THK_EXPR,
    },
    MODE_PRESSURE: {
        # None → eqp/recipe 별로 데이터에서 회귀. 숫자를 넣으면 그 기울기로 고정.
        'bias_slope'    : None,
        'bias_min_count': 30,        # 회귀에 필요한 최소 건수
        # 설명력이 이보다 낮은 회귀는 버린다. 기울기가 0 에 가까우면 그것으로 나눈
        # Simul_APC 가 터무니없이 커지므로, 엉터리 값을 내기보다 '민감도 없음'(NaN)이 낫다.
        'bias_min_r2'   : 0.1,
        'fb_expr'       : DEFAULT_P_FB_EXPR,
        'linear_expr'   : DEFAULT_P_LINEAR_EXPR,
        'bias_expr'     : DEFAULT_P_BIAS_EXPR,
        'thk_expr'      : DEFAULT_P_THK_EXPR,
    },
}

EXPR_KEYS = {
    MODE_TIME    : ('fb_expr', 'linear_expr', 'rr_expr', 'removal_expr', 'thk_expr'),
    MODE_PRESSURE: ('fb_expr', 'linear_expr', 'bias_expr', 'thk_expr'),
}

# 계산으로 새로 붙는 컬럼 (DB 적재 / web 조회 대상)
_FB_COLUMNS  = ['FB_1', 'FB_2', 'FB_3', 'FB_4']
_APC_COLUMNS = ['Simul_APC', 'Simul_APC_Limit', 'Simul_APC_Mode',
                'Simul_Ref_Used', 'Simul_APC_Clipped']

OUTPUT_COLUMNS = {
    MODE_TIME    : _FB_COLUMNS + _APC_COLUMNS + ['Simul_RR', 'Removal_Amount', 'Simul_THK'],
    MODE_PRESSURE: _FB_COLUMNS + _APC_COLUMNS + ['Bias_Actual', 'Bias_Slope', 'Bias_Intercept',
                                                 'Bias_R2', 'Simul_Bias', 'Simul_THK'],
}
ALL_OUTPUT_COLUMNS = list(dict.fromkeys(OUTPUT_COLUMNS[MODE_TIME] + OUTPUT_COLUMNS[MODE_PRESSURE]))

# web 수식 편집 도움말 — 단계별로 쓸 수 있는 변수
_TIME_COMMON = [
    'Target', 'Pre_Target', 'Pre_Thk', 'RR_DB', 'Simul_OFFSET',
    'Pol_Time', 'Pol_Time_1', 'Pol_Time_2', 'THK', 'APC_Value', 'Consumable',
    'pre_weight', 'rr_weight', 'sign',
]
_PRESSURE_COMMON = [
    'Target', 'Target_13P', 'Pre_Target', 'Pre_Thk', 'THK', 'THK_13P',
    'Bias_Actual', 'Bias_Slope', 'Bias_Intercept', 'Bias_R2', 'Simul_THK_13P',
    'RR_DB', 'APC_Value', 'Consumable', 'pre_weight', 'rr_weight', 'sign',
]

EXPR_VARIABLES = {
    MODE_TIME: {
        'fb_expr'     : ['Ref_APC', 'Ref_Post', 'Ref_Pre_VM', 'Ref_OFFSET', 'Ref_Pre_ITM'] + _TIME_COMMON,
        'linear_expr' : list(_TIME_COMMON),
        'rr_expr'     : ['Target', 'Pre_Target', 'Pre_Thk', 'THK', 'Pol_Time', 'Pol_Time_1',
                         'Pol_Time_2', 'RR_DB', 'APC_Value', 'Consumable', 'sign'],
        'removal_expr': ['Simul_RR', 'Simul_APC', 'Simul_APC_Limit', 'Pol_Time', 'Pol_Time_1',
                         'Pol_Time_2', 'RR_DB', 'sign'],
        'thk_expr'    : ['Removal_Amount', 'Simul_RR', 'Simul_APC_Limit', 'Target', 'Pre_Target',
                         'Pre_Thk', 'THK', 'Pol_Time', 'Pol_Time_1', 'sign'],
    },
    MODE_PRESSURE: {
        'fb_expr'    : ['Ref_APC', 'Ref_Post', 'Ref_13P', 'Ref_Bias', 'Ref_Pre_VM',
                        'Ref_Pre_ITM'] + _PRESSURE_COMMON,
        'linear_expr': list(_PRESSURE_COMMON),
        'bias_expr'  : ['Simul_APC', 'Simul_APC_Limit'] + _PRESSURE_COMMON,
        'thk_expr'   : ['Simul_Bias', 'Simul_APC_Limit'] + _PRESSURE_COMMON,
    },
}

# 산식 단계별 한글 라벨 (web 패널 표시용)
EXPR_LABELS = {
    'fb_expr'     : 'FB 산식 (Ref lot 1건당)',
    'linear_expr' : 'Linear 산식 (Ref 없음 / Ref_YN=N)',
    'rr_expr'     : 'Removal Rate',
    'removal_expr': '제거량 (Removal Amount)',
    'bias_expr'   : '편차 (Simul Bias)',
    'thk_expr'    : 'Simulation 두께',
}


class FormulaError(ValueError):
    """수식 문법 오류 / 허용되지 않은 이름·구문."""


# ── 안전한 수식 평가 ───────────────────────────────────────────────────────
# 공정별로 산식을 바꿔가며 시뮬레이션해야 하므로 수식을 텍스트로 받는다.
# 임의 코드 실행이 되지 않도록 AST 를 화이트리스트로 검사한 뒤에만 평가한다.

_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Name, ast.Load, ast.Constant,
    ast.Call, ast.Compare, ast.BoolOp, ast.IfExp, ast.Tuple,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod,
    ast.USub, ast.UAdd, ast.Not, ast.Invert,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.And, ast.Or, ast.BitAnd, ast.BitOr,
)


def _nan_to_num_safe(x):
    return np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)


_FUNCS = {
    'abs'     : np.abs,
    'sqrt'    : np.sqrt,
    'log'     : np.log,
    'exp'     : np.exp,
    'where'   : np.where,
    'clip'    : np.clip,
    'minimum' : np.minimum,
    'maximum' : np.maximum,
    'isnan'   : lambda x: ~np.isfinite(np.asarray(x, dtype=float)),
    'fillna'  : lambda x, v=0.0: np.where(np.isfinite(np.asarray(x, dtype=float)),
                                          np.asarray(x, dtype=float), v),
    'nan_to_num': _nan_to_num_safe,
}


def check_expr(expr, allowed_names):
    """수식을 검증하고 컴파일된 코드 객체를 반환. 문제가 있으면 FormulaError."""
    expr = (expr or '').strip()
    if not expr:
        raise FormulaError('수식이 비어 있습니다')

    try:
        tree = ast.parse(expr, mode='eval')
    except SyntaxError as e:
        raise FormulaError(f'문법 오류: {e.msg}') from None

    allowed = set(allowed_names) | set(_FUNCS)
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise FormulaError(f'허용되지 않은 구문입니다: {type(node).__name__}')
        if isinstance(node, ast.Name) and node.id not in allowed:
            raise FormulaError(
                f"알 수 없는 변수: '{node.id}'\n사용 가능: {', '.join(sorted(allowed_names))}"
            )
        if isinstance(node, ast.Call) and (
            not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS
        ):
            raise FormulaError(f'허용되지 않은 함수 호출입니다 (사용 가능: {", ".join(sorted(_FUNCS))})')

    return compile(tree, '<apc_formula>', 'eval')


def eval_expr(expr, ctx):
    """검증 후 평가. ctx 는 {변수명: Series|scalar}."""
    code = check_expr(expr, ctx.keys())
    with np.errstate(divide='ignore', invalid='ignore'):
        return eval(code, {'__builtins__': {}}, {**_FUNCS, **ctx})   # noqa: S307


def validate_config(cfg, mode=MODE_TIME):
    """해당 모드의 수식을 모두 검증. 오류 메시지 dict 반환 (비어 있으면 정상)."""
    errors = {}
    for key in EXPR_KEYS[mode]:
        try:
            check_expr(cfg.get(key) or _MODE_DEFAULTS[mode][key], EXPR_VARIABLES[mode][key])
        except FormulaError as e:
            errors[key] = str(e)
    return errors


# ── 설정 정규화 ────────────────────────────────────────────────────────────

def _f(value, default=None):
    if value is None or value == '':
        return default
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return default if not np.isfinite(v) else v


def detect_mode(df):
    """FB_Type 컬럼으로 TIME / PRESSURE 판별 (없으면 TIME)."""
    if df is None or 'FB_Type' not in getattr(df, 'columns', []):
        return MODE_TIME
    values = df['FB_Type'].dropna().astype(str).str.upper()
    if len(values) and (values == MODE_PRESSURE).mean() >= 0.5:
        return MODE_PRESSURE
    return MODE_TIME


def resolve_config(config=None, mode=MODE_TIME):
    """부분 지정된 설정 dict 를 해당 모드의 기본값으로 채워 정규화한다."""
    if mode not in MODES:
        mode = MODE_TIME

    cfg = dict(_COMMON_DEFAULTS)
    cfg.update(_MODE_DEFAULTS[mode])
    cfg['weights'] = {k: list(v) for k, v in DEFAULT_WEIGHTS.items()}
    cfg['mode']    = mode

    for key, value in (config or {}).items():
        if key in cfg and key != 'mode':
            cfg[key] = value

    cfg['pre_weight']     = _f(cfg['pre_weight'], 1.0)
    cfg['rr_weight']      = _f(cfg['rr_weight'], 1.0)
    cfg['upper_limit']    = _f(cfg['upper_limit'], None)
    cfg['lower_limit']    = _f(cfg['lower_limit'], None)
    cfg['ref_skip_count'] = int(_f(cfg['ref_skip_count'], 11))

    if mode == MODE_TIME:
        if cfg['pol_time_1'] not in ('auto', 'use', 'ignore'):
            cfg['pol_time_1'] = 'auto'
    else:
        cfg['bias_slope']     = _f(cfg['bias_slope'], None)
        cfg['bias_min_count'] = max(2, int(_f(cfg['bias_min_count'], 30)))
        cfg['bias_min_r2']    = min(1.0, max(0.0, _f(cfg['bias_min_r2'], 0.1)))

    # weights: {'1': [...], ...} — 길이가 n 이 되도록 보정, 전부 0 이면 균등 배분
    weights = {}
    given = cfg.get('weights') or {}
    for n in range(1, MAX_REF + 1):
        raw = given.get(str(n), given.get(n)) or DEFAULT_WEIGHTS[str(n)]
        vals = [_f(v, 0.0) for v in list(raw)[:n]]
        vals += [0.0] * (n - len(vals))
        if not any(vals):
            vals = list(DEFAULT_WEIGHTS[str(n)])
        weights[str(n)] = vals
    cfg['weights'] = weights

    for key in EXPR_KEYS[mode]:
        cfg[key] = (cfg.get(key) or '').strip() or _MODE_DEFAULTS[mode][key]

    return cfg


# ── 입력 컬럼 → 계산 context ───────────────────────────────────────────────

def _series(df, name, default=np.nan):
    """컬럼이 있으면 float Series, 없으면 default 로 채운 Series."""
    if name in df.columns:
        return pd.to_numeric(df[name], errors='coerce')
    return pd.Series(default, index=df.index, dtype=float)


def _first_series(df, names, default=np.nan):
    for name in names:
        if name in df.columns:
            return pd.to_numeric(df[name], errors='coerce')
    return pd.Series(default, index=df.index, dtype=float)


def _sign_series(df):
    """REV 계열 계측 파라미터는 두께 증감 방향이 반대 → -1."""
    if 'Thk_Para' not in df.columns:
        return pd.Series(1.0, index=df.index, dtype=float)
    is_rev = df['Thk_Para'].astype(str).str.contains('REV', case=False, na=False)
    return pd.Series(np.where(is_rev, -1.0, 1.0), index=df.index, dtype=float)


def _pol_time_1(df, cfg):
    """APC 가 제어하지 않는 앞단 고정 step 시간.

    'auto' : Pol_Time_2 가 있는 (= 연마 step 2개 이상) 공정만 항을 살린다.
             step 1개 공정은 Pol_Time_1 == Pol_Time 이라 빼면 안 되므로 0.
    """
    if cfg['pol_time_1'] == 'ignore':
        return pd.Series(0.0, index=df.index, dtype=float)
    if cfg['pol_time_1'] == 'auto' and 'Pol_Time_2' not in df.columns:
        return pd.Series(0.0, index=df.index, dtype=float)
    return _series(df, 'Pol_Time_1', 0.0).fillna(0.0)


def _shared_context(df, cfg):
    """두 모드가 공통으로 쓰는 변수."""
    # 0 으로 나누면 inf 가 되어 이후 계산이 전부 오염되므로 NaN 으로 돌린다
    return {
        'Target'     : _series(df, 'Target'),
        'Pre_Target' : _series(df, 'Pre_Target'),
        'Pre_Thk'    : _first_series(df, ['Pre_Thk_VM', 'Pre_Thk'], 0.0).fillna(0.0),
        'RR_DB'      : _series(df, 'RR_DB').replace(0, np.nan),
        'THK'        : _series(df, 'THK'),
        'APC_Value'  : _series(df, 'APC_Value'),
        'Consumable' : _series(df, 'Consumable'),
        'sign'       : _sign_series(df),
        'pre_weight' : cfg['pre_weight'],
        'rr_weight'  : cfg['rr_weight'],
    }


def _time_context(df, cfg):
    ctx = _shared_context(df, cfg)
    ctx.update({
        'Simul_OFFSET': _first_series(df, ['Simul_OFFSET', 'OFFSET_Learn'], 0.0).fillna(0.0),
        'Pol_Time'    : _series(df, 'Pol_Time').replace(0, np.nan),
        'Pol_Time_1'  : _pol_time_1(df, cfg),
        'Pol_Time_2'  : _series(df, 'Pol_Time_2', 0.0).fillna(0.0),
    })
    return ctx


# ── PRESSURE: 편차(BIAS) 와 압력 민감도 ────────────────────────────────────

def bias_actual(df):
    """학습측(Module.py)과 동일한 BIAS 정의.

        Bias = (THK - THK_13P) - (Target - Target_13P)

    13P 계측/Target 이 없으면 NaN (PRESSURE 시뮬레이션 불가).
    """
    thk    = _series(df, 'THK')
    thk13  = _series(df, 'THK_13P')
    tgt    = _series(df, 'Target')
    tgt13  = _series(df, 'Target_13P')
    return (thk - thk13) - (tgt - tgt13)


def _group_key(df):
    """압력 민감도를 따로 학습할 단위 (장비 + 레시피)."""
    if 'eqp_id' in df.columns and 'recipe_id' in df.columns:
        return df['eqp_id'].astype(str) + '//' + df['recipe_id'].astype(str)
    if 'eqp_id' in df.columns:
        return df['eqp_id'].astype(str)
    return pd.Series('_ALL_', index=df.index)


def _fit_line(x, y, min_count, min_r2=0.0):
    """1차 회귀 → (slope, intercept, r2).

    데이터가 모자라거나 기울기가 0 이거나 설명력이 min_r2 미만이면 (nan, nan, r2).
    기울기가 0 에 가까우면 그것으로 나누는 순간 Simul_APC 가 발산하므로,
    믿을 수 없는 회귀는 값을 내지 않는 편이 안전하다.
    """
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if len(x) < min_count or np.ptp(x) == 0:
        return np.nan, np.nan, np.nan

    slope, intercept = np.polyfit(x, y, 1)
    if not np.isfinite(slope) or slope == 0:
        return np.nan, np.nan, np.nan

    ss_tot = float(((y - y.mean()) ** 2).sum())
    ss_res = float(((y - (slope * x + intercept)) ** 2).sum())
    r2     = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    if r2 < min_r2:
        return np.nan, np.nan, r2
    return float(slope), float(intercept), r2


def bias_model(df, cfg, bias=None):
    """압력 → 편차 민감도(Bias_Slope) / 절편(Bias_Intercept) / 설명력(Bias_R2) 산출.

    bias_slope 설정이 있으면 그 기울기로 고정하고 절편만 그룹 평균으로 맞춘다.
    (압력은 편차에 반응해 움직인 제어 출력이라 회귀가 closed-loop 이 된다 —
     신뢰할 수 있는 민감도를 알고 있으면 고정하는 쪽이 안전하다.)
    """
    bias = bias_actual(df) if bias is None else bias
    apc  = _series(df, 'APC_Value')
    key  = _group_key(df)

    slope     = pd.Series(np.nan, index=df.index, dtype=float)
    intercept = pd.Series(np.nan, index=df.index, dtype=float)
    r2_out    = pd.Series(np.nan, index=df.index, dtype=float)

    fixed     = cfg.get('bias_slope')
    min_count = cfg.get('bias_min_count', 30)
    min_r2    = cfg.get('bias_min_r2', 0.0)

    # 그룹에서 못 구하면 전체 데이터로 대체
    all_slope, all_intercept, all_r2 = (
        (fixed, np.nan, np.nan) if fixed is not None
        else _fit_line(apc.to_numpy(float), bias.to_numpy(float), min_count, min_r2)
    )

    for _, idx in key.groupby(key).groups.items():
        x = apc.loc[idx].to_numpy(float)
        y = bias.loc[idx].to_numpy(float)

        if fixed is not None:
            # 기울기 고정 — 절편만 데이터 평균에 맞춘다
            s, r2 = fixed, np.nan
            mask  = np.isfinite(x) & np.isfinite(y)
            b     = float(np.mean(y[mask] - s * x[mask])) if mask.sum() else np.nan
        else:
            s, b, r2 = _fit_line(x, y, min_count, min_r2)
            if not np.isfinite(s):
                s, b = all_slope, all_intercept
                r2   = all_r2 if np.isfinite(all_slope) else r2

        slope.loc[idx]     = s
        intercept.loc[idx] = b
        r2_out.loc[idx]    = r2

    return slope, intercept, r2_out


def _pressure_context(df, cfg):
    ctx   = _shared_context(df, cfg)
    bias  = bias_actual(df)
    slope, intercept, r2 = bias_model(df, cfg, bias)

    ctx.update({
        'Target_13P'    : _series(df, 'Target_13P'),
        'THK_13P'       : _series(df, 'THK_13P'),
        'Bias_Actual'   : bias,
        'Bias_Slope'    : slope.replace(0, np.nan),
        'Bias_Intercept': intercept,
        'Bias_R2'       : r2,
        # TIME(13P) 시뮬레이션이 결정한 중심 두께 — PRESSURE 는 여기에 편차를 얹는다
        'Simul_THK_13P' : _series(df, 'Simul_THK_13P'),
    })
    return ctx


def has_ref_columns(df):
    """Ref lot 재료 컬럼이 하나라도 있는지 (없으면 Linear 만 계산된다)."""
    return any(f'Ref_{i}_APC' in df.columns for i in range(1, MAX_REF + 1))


# ── 단계별 계산 ────────────────────────────────────────────────────────────

def _ref_context(df, base, i, mode):
    """Ref_i 재료를 산식 변수명(Ref_*)으로 노출."""
    ctx = dict(base)
    ctx.update({
        'Ref_APC'    : _series(df, f'Ref_{i}_APC'),
        'Ref_Post'   : _series(df, f'Ref_{i}_Post'),
        'Ref_Pre_VM' : _series(df, f'Ref_{i}_Pre_VM'),
        'Ref_Pre_ITM': _series(df, f'Ref_{i}_Pre_ITM'),
    })
    if mode == MODE_PRESSURE:
        ref_13p = _series(df, f'Ref_{i}_13P')
        ctx['Ref_13P'] = ref_13p
        # ref wafer 의 편차 — Bias_Actual 과 같은 정의
        ctx['Ref_Bias'] = ((ctx['Ref_Post'] - ref_13p)
                           - (base['Target'] - base['Target_13P']))
    else:
        ctx['Ref_OFFSET'] = _series(df, f'Ref_{i}_OFFSET', 0.0).fillna(0.0)
    return ctx


def compute_fb(df, cfg, base, mode):
    """Ref lot 별 FB 값 (FB_1 ~ FB_4) DataFrame 반환."""
    out = pd.DataFrame(index=df.index)
    for i in range(1, MAX_REF + 1):
        value = eval_expr(cfg['fb_expr'], _ref_context(df, base, i, mode))
        out[f'FB_{i}'] = pd.Series(np.asarray(value, dtype=float), index=df.index)
    return out


def combine_fb(fb_df, cfg):
    """유효한 FB 값을 앞에서부터 모아 개수별 weight 로 결합.

    Ref_2 만 비어 있는 것처럼 중간이 빈 경우에도 남은 값들을 순서대로 당겨
    (개수 n 의) weight_n1..weight_nn 을 적용한다.

    Returns: (결합값 Series, 사용된 Ref 개수 Series)
    """
    fb    = fb_df.to_numpy(dtype=float)
    valid = np.isfinite(fb)
    n_ref = valid.sum(axis=1)

    # 유효한 값을 원래 순서를 유지한 채 왼쪽으로 당긴다 (stable argsort)
    order  = np.argsort(~valid, axis=1, kind='stable')
    packed = np.take_along_axis(np.nan_to_num(fb, nan=0.0), order, axis=1)

    # 행별 Ref 개수에 맞는 weight 행렬 (개수보다 뒤쪽 열은 0)
    wmat = np.zeros((MAX_REF + 1, MAX_REF), dtype=float)
    for n in range(1, MAX_REF + 1):
        wmat[n, :n] = cfg['weights'][str(n)]

    weights  = wmat[n_ref]
    combined = (packed * weights).sum(axis=1)
    combined = np.where(n_ref > 0, combined, np.nan)

    return (pd.Series(combined, index=fb_df.index),
            pd.Series(n_ref, index=fb_df.index))


def _linear_mask(df, cfg, n_ref, fb_value):
    """Linear 산식으로 빠지는 행 마스크."""
    mask = (n_ref == 0) | ~np.isfinite(fb_value)

    if 'Ref_YN' in df.columns:
        yn = df['Ref_YN'].astype(str).str.strip().str.upper()
        mask = mask | yn.isin(['N', 'NO'])

    if 'Ref_Count' in df.columns:
        count = pd.to_numeric(df['Ref_Count'], errors='coerce')
        mask = mask | (count == cfg['ref_skip_count'])

    return mask


def _eval_series(expr, ctx, index):
    return pd.Series(np.asarray(eval_expr(expr, ctx), dtype=float), index=index)


def _compute_apc(df, cfg, base, mode):
    """FB 결합 → Linear 분기 → limit 적용. 공통 단계."""
    fb_df = compute_fb(df, cfg, base, mode)
    fb_value, n_ref = combine_fb(fb_df, cfg)

    linear     = _eval_series(cfg['linear_expr'], base, df.index)
    use_linear = _linear_mask(df, cfg, n_ref, fb_value)
    simul_apc  = fb_value.where(~use_linear, linear)

    lower, upper = cfg['lower_limit'], cfg['upper_limit']
    limited = simul_apc
    if lower is not None:
        limited = limited.clip(lower=lower)
    if upper is not None:
        limited = limited.clip(upper=upper)

    result = {col: fb_df[col] for col in fb_df.columns}
    result.update({
        'Simul_APC'        : simul_apc,
        'Simul_APC_Mode'   : np.where(use_linear, 'LINEAR', 'FB'),
        'Simul_Ref_Used'   : n_ref.where(~use_linear, 0),
        'Simul_APC_Limit'  : limited,
        'Simul_APC_Clipped': (np.isfinite(simul_apc) & (limited != simul_apc)).astype(int),
    })
    return result, simul_apc, limited


def apply_formula(df, config=None, mode=None):
    """Simulation 결과 DataFrame 에 Simul_APC / Simul_THK 계열 컬럼을 추가.

    입력에 필요한 컬럼이 없으면 해당 항은 NaN 이 되고 계산은 계속 진행된다.

    Args:
        df     : Simulation 결과 (또는 web 조회 결과)
        config : 부분 설정 dict — resolve_config 로 기본값이 채워진다
        mode   : 'TIME' | 'PRESSURE' (None 이면 FB_Type 컬럼으로 판별)
    Returns:
        컬럼이 추가된 DataFrame (원본은 수정하지 않음)
    """
    if df is None or len(df) == 0:
        return df

    mode = mode or detect_mode(df)
    cfg  = resolve_config(config, mode)
    out  = df.copy()

    base = _pressure_context(out, cfg) if mode == MODE_PRESSURE else _time_context(out, cfg)
    result, simul_apc, limited = _compute_apc(out, cfg, base, mode)

    if mode == MODE_PRESSURE:
        # 압력 → 편차 → (13P 시뮬 두께 + 편차)
        result['Bias_Actual']    = base['Bias_Actual']
        result['Bias_Slope']     = base['Bias_Slope']
        result['Bias_Intercept'] = base['Bias_Intercept']
        result['Bias_R2']        = base['Bias_R2']

        ctx = dict(base)
        ctx.update({'Simul_APC': simul_apc, 'Simul_APC_Limit': limited})
        simul_bias = _eval_series(cfg['bias_expr'], ctx, out.index)
        result['Simul_Bias'] = simul_bias

        ctx['Simul_Bias'] = simul_bias
        result['Simul_THK'] = _eval_series(cfg['thk_expr'], ctx, out.index)
    else:
        # 실제 RR → 제거량 → 두께
        ctx = dict(base)
        simul_rr = _eval_series(cfg['rr_expr'], ctx, out.index)
        result['Simul_RR'] = simul_rr

        ctx.update({'Simul_RR': simul_rr, 'Simul_APC': simul_apc, 'Simul_APC_Limit': limited})
        removal = _eval_series(cfg['removal_expr'], ctx, out.index)
        result['Removal_Amount'] = removal

        ctx['Removal_Amount'] = removal
        result['Simul_THK'] = _eval_series(cfg['thk_expr'], ctx, out.index)

    for col, value in result.items():
        out[col] = value
    return out


def summarize(df, mode=None):
    """web 상단 배지에 쓸 요약 (FB/Linear 건수, limit 걸린 건수, 두께 산포)."""
    if df is None or len(df) == 0:
        return {}

    mode = mode or detect_mode(df)
    mode_col = df.get('Simul_APC_Mode')

    def _stat(series):
        s = pd.to_numeric(series, errors='coerce').dropna() if series is not None else pd.Series(dtype=float)
        if s.empty:
            return None
        return {'n': int(s.size), 'avg': float(s.mean()), 'std': float(s.std(ddof=0))}

    out = {
        'mode'        : mode,
        'rows'        : int(len(df)),
        'fb_count'    : int((mode_col == 'FB').sum()) if mode_col is not None else 0,
        'linear_count': int((mode_col == 'LINEAR').sum()) if mode_col is not None else 0,
        'clipped'     : int(pd.to_numeric(df.get('Simul_APC_Clipped'), errors='coerce').fillna(0).sum())
                        if 'Simul_APC_Clipped' in df else 0,
        'apc'         : _stat(df.get('Simul_APC_Limit')),
        'simul_thk'   : _stat(df.get('Simul_THK')),
        'actual_thk'  : _stat(df.get('THK')),
    }

    if mode == MODE_PRESSURE:
        slope = pd.to_numeric(df.get('Bias_Slope'), errors='coerce') if 'Bias_Slope' in df else pd.Series(dtype=float)
        out.update({
            'bias_actual': _stat(df.get('Bias_Actual')),
            'simul_bias' : _stat(df.get('Simul_Bias')),
            'slope_avg'  : float(slope.dropna().mean()) if slope.notna().any() else None,
            'r2_avg'     : (float(pd.to_numeric(df['Bias_R2'], errors='coerce').dropna().mean())
                            if 'Bias_R2' in df and pd.to_numeric(df['Bias_R2'], errors='coerce').notna().any()
                            else None),
            'slope_missing': int(slope.isna().sum()) if len(slope) else int(len(df)),
        })
    return out
