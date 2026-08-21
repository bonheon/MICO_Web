"""Simulation 결과 컬렉션 (MICO_Simulation_*) 명명 규칙 및 조회 helper.

Simulation 결과는 다른 학습값(Pre Thk / RR / OFFSET)과 동일하게 MongoDB 에 적재한다.
쓰기(적재)는 algorithm_new/Common/Simulation.py, 읽기(web 조회)는 이 모듈이 담당한다.

    MICO_Simulation_{Lot_Code}_{Oper_Desc}_{Fab}

  · Lot_Code  : web Set-up 의 Category.product
  · Oper_Desc : Category.oper_desc  (예: 'M1 CU CMP')
  · Fab       : SubCategory.fab
  · zone(13P / EDGE / EXED / Z5 ...) 은 ZONE 필드로 구분

접속 주소는 config/settings.py 의 MICO_MONGO_URL / MICO_MONGO_DB
(환경변수로 덮어쓰기 가능) 한 곳에서만 관리한다.

※ APC 산식 설정(SimulFormulaConfig)은 Set-up 정보라 Django DB 에 그대로 둔다.
"""

from django.conf import settings

TABLE_PREFIX = 'MICO_Simulation'

# 컬렉션명에 Oper_Desc 의 공백을 그대로 둘지 여부.
# (algorithm_new/Common/Simulation.KEEP_SPACE_IN_TABLE_NAME 과 반드시 동일하게 유지)
KEEP_SPACE_IN_TABLE_NAME = True

# MongoDB 응답이 없을 때 화면이 오래 매달리지 않도록 제한
_SERVER_TIMEOUT_MS = 5000

_client = None


def _mongo_db():
    """MongoDB 연결 (프로세스당 1개 재사용 — pymongo 클라이언트는 커넥션 풀을 갖는다)."""
    global _client
    if _client is None:
        from pymongo import MongoClient
        _client = MongoClient(settings.MICO_MONGO_URL,
                              serverSelectionTimeoutMS=_SERVER_TIMEOUT_MS)
    return _client[settings.MICO_MONGO_DB]

# 차트 렌더링 상한 — 초과 시 균등 샘플링
MAX_ROWS = 8000

# web 조회에 사용하는 컬럼 (테이블에 존재하는 것만 선택)
META_COLUMNS = [
    'Date', 'ZONE', 'FB_Type', 'APC_Para', 'Thk_Para', 'Formula',
    'lot_id', 'substrate_id', 'eqp_id', 'eqp_model', 'recipe_id', 'process_id',
    'IDLE', 'pre_eq_ch', 'Consumable_Para',
]
VALUE_COLUMNS = [
    'THK', 'Target', 'Pre_Target', 'Pad_Seperation', 'APC_Value', 'Pol_Time', 'Consumable',
    'RR_Actual', 'RR_DB', 'RR_Normal', 'RR_Weighted', 'RR_Current', 'RR_IF',
    'Pre_Thk_VM', 'Pre_Thk_MA', 'Pre_Thk_ITM', 'Pre_Thk_Actual', 'Pre_Thk_Implied',
    'OFFSET_Learn', 'OFFSET_Actual',
]

# APC 산식(Simul_APC / Simul_THK) 재계산 재료.
# 배치(algorithm_new)는 산식을 적용하지 않고 이 '재료' 컬럼까지만 적재한다.
# 계산은 항상 web 의 apc_formula 가 조회 시점에 수행 — 화면에서 파라미터를 바꾸면
# 즉시 다시 계산되고, DB 에는 파라미터에 좌우되는 값이 남지 않는다.
#
# ※ 배치 적재측 algorithm_new/Common/Simulation.py 의 SAVE_COLUMNS 와 짝이다.
#   (두 환경이 분리 배포되므로 import 로 공유하지 않고 각자 정의 — 함께 수정할 것)
FORMULA_INPUT_COLUMNS = (
    ['Pol_Time_1', 'Pol_Time_2', 'Ref_Count', 'Ref_YN']
    # PRESSURE zone: 13P(중심) 대비 편차를 맞추므로 13P 계측·Target 이 재료로 필요하다.
    # (13P 시뮬 두께 Simul_THK_13P 는 산식 결과 — 저장하지 않고 조회 시 계산해 붙인다)
    + ['THK_13P', 'Target_13P']
    + [f'Ref_{i}_{suffix}'
       for i in range(1, 5)
       for suffix in ('APC', 'Post', '13P', 'Pre_VM', 'OFFSET', 'Pre_ITM')]
)

# 산식 결과 컬럼(FB_*/Simul_*/Bias_*)은 테이블에서 읽지 않는다.
# apc_formula.ALL_OUTPUT_COLUMNS 가 조회 후 계산으로 채운다.
VIEW_COLUMNS = META_COLUMNS + VALUE_COLUMNS + FORMULA_INPUT_COLUMNS


def table_name(lot_code, oper_desc, fab):
    oper = str(oper_desc)
    if not KEEP_SPACE_IN_TABLE_NAME:
        oper = oper.replace(' ', '_')
    return f'{TABLE_PREFIX}_{lot_code}_{oper}_{fab}'


def existing_tables():
    """MongoDB 에 실제 존재하는 Simulation 결과 컬렉션 집합."""
    return {c for c in _mongo_db().list_collection_names() if c.startswith(TABLE_PREFIX)}


def table_columns(table):
    """컬렉션에 실제로 들어있는 필드 목록.

    zone 마다 필드 구성이 다를 수 있어(PRESSURE 만 THK_13P 보유) 앞쪽 문서를
    여러 건 훑어 합집합을 만든다.
    """
    keys = set()
    for doc in _mongo_db()[table].find({}, limit=200):
        keys.update(doc.keys())
    keys.discard('_id')
    return sorted(keys)


def _as_datetime(value, end_of_day=False):
    """'YYYY-MM-DD' 또는 date/datetime → datetime (Mongo 의 Date 는 BSON date)."""
    from datetime import date, datetime, time

    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.max if end_of_day else time.min)
    parsed = datetime.strptime(str(value)[:10], '%Y-%m-%d')
    return parsed.replace(hour=23, minute=59, second=59, microsecond=999999) if end_of_day else parsed


def _filter(date_from, date_to, zone, apc_para):
    query = {}
    if date_from or date_to:
        rng = {}
        if date_from:
            rng['$gte'] = _as_datetime(date_from)
        if date_to:
            # 종료일 당일 23:59:59 포함
            rng['$lte'] = _as_datetime(date_to, end_of_day=True)
        query['Date'] = rng
    if zone:
        query['ZONE'] = zone
    if apc_para:
        query['APC_Para'] = apc_para
    return query


def distinct_values(table, column, date_from=None, date_to=None, zone=None):
    """필터 선택지용 distinct 값 목록 (없는 필드면 빈 리스트).

    zone 을 주면 그 zone 안에서만 뽑는다 — APC_Para 는 zone 마다 다르므로
    (13P=P3, EDGE=P3_ZONE1 …) zone 을 무시하면 0건 조회가 된다.
    """
    values = _mongo_db()[table].distinct(column, _filter(date_from, date_to, zone, None))
    return sorted(str(v) for v in values if v is not None)


def fetch(table, date_from=None, date_to=None, zone=None, apc_para=None,
          max_rows=MAX_ROWS):
    """조건에 맞는 행을 컬럼형(columns/rows)으로 반환.

    Returns: dict(columns, rows, total_rows, sampled)
    행 수가 max_rows 를 넘으면 시간순으로 균등 샘플링해 차트 렌더링 비용을 제한한다.
    max_rows=None 이면 샘플링하지 않는다 — PRESSURE zone 의 Simul_THK_13P 계산처럼
    substrate_id 를 빠짐없이 맞춰야 하는 조회에 사용.
    """
    collection = _mongo_db()[table]
    query      = _filter(date_from, date_to, zone, apc_para)
    total      = collection.count_documents(query)

    stride = max(1, -(-total // max_rows)) if (max_rows and total) else 1   # ceil

    projection = {c: 1 for c in VIEW_COLUMNS}
    projection['_id'] = 0

    docs = []
    for i, doc in enumerate(collection.find(query, projection).sort('Date', 1)):
        if i % stride == 0:
            docs.append(doc)

    # 실제로 값이 들어있는 필드만 컬럼으로 (조회 목록 순서 유지)
    present = set()
    for doc in docs:
        present.update(doc.keys())
    columns = [c for c in VIEW_COLUMNS if c in present]
    rows    = [[_json_safe(doc.get(c)) for c in columns] for doc in docs]

    return {
        'columns'   : columns,
        'rows'      : rows,
        'total_rows': total,
        'sampled'   : len(rows) < total,
    }


# ── APC 산식 설정 (SimulFormulaConfig) ─────────────────────────────────────
# 저장은 선택 사항 — 화면에서 key-in 한 값으로 즉시 재계산되고,
# '기본값으로 저장' 을 눌렀을 때만 여기에 남아 다음 조회 시 복원된다.

def _category(product, oper_desc):
    from .models import Category
    return Category.objects.filter(product=product, oper_desc=oper_desc).first()


def load_formula_params(product, oper_desc, zone=''):
    """저장된 산식 설정을 반환. 공통(zone='') 위에 zone 별 설정을 덮어쓴다.

    저장된 것이 없으면 빈 dict → apc_formula.resolve_config 가 기본값을 채운다.
    """
    from .models import SimulFormulaConfig

    category = _category(product, oper_desc)
    if category is None:
        return {}, ''

    rows = {c.zone: c for c in SimulFormulaConfig.objects.filter(
        category=category, zone__in=['', zone or '']
    )}

    params = dict((rows.get('').params if '' in rows else {}) or {})
    source = 'common' if '' in rows else ''
    if zone and zone in rows:
        params.update(rows[zone].params or {})
        source = 'zone'

    return params, source


def save_formula_params(product, oper_desc, zone, params, user=None):
    """산식 설정 저장 (zone='' 이면 해당 공정의 공통 기본값)."""
    from .models import SimulFormulaConfig

    category = _category(product, oper_desc)
    if category is None:
        raise ValueError(f'Set-up 에 없는 공정입니다: {product} / {oper_desc}')

    obj, _ = SimulFormulaConfig.objects.update_or_create(
        category=category, zone=zone or '',
        defaults={'params': params, 'updated_by': user if user and user.is_authenticated else None},
    )
    return obj


def delete_formula_params(product, oper_desc, zone):
    from .models import SimulFormulaConfig

    category = _category(product, oper_desc)
    if category is None:
        return 0
    deleted, _ = SimulFormulaConfig.objects.filter(
        category=category, zone=zone or ''
    ).delete()
    return deleted


def _json_safe(v):
    if v is None:
        return None
    if hasattr(v, 'isoformat'):
        return v.isoformat()
    if isinstance(v, (int, float, str, bool)):
        # NaN/Inf 는 JSON 으로 직렬화할 수 없으므로 None 처리
        if isinstance(v, float) and (v != v or v in (float('inf'), float('-inf'))):
            return None
        return v
    return str(v)
