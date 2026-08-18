"""Simulation 결과 테이블 (MICO_Simulation_*) 명명 규칙 및 조회 helper.

Simulation 결과는 Spotfire 연동 CSV 대신 Set-up 과 동일한 DB 에 적재된다.
쓰기(적재)는 algorithm_new/Common/Result_DB.py, 읽기(web 조회)는 이 모듈이 담당하며
테이블 명명 규칙은 이 파일 하나만 참조한다.

    MICO_Simulation_{Lot_Code}_{Oper_Desc}_{Fab}

  · Lot_Code  : web Set-up 의 Category.product
  · Oper_Desc : Category.oper_desc  (예: 'M1 CU CMP')
  · Fab       : SubCategory.fab
  · zone(13P / EDGE / EXED / Z5 ...) 은 ZONE 컬럼으로 구분

사내 전환 시 별도 수정 없음 — Django settings 의 DATABASES 만 사내 DB 로 바꾸면
같은 코드가 사내 DB 의 같은 이름 테이블을 읽는다.
"""

from django.db import connection

TABLE_PREFIX = 'MICO_Simulation'

# 테이블명에 Oper_Desc 의 공백을 그대로 둘지 여부.
# (algorithm_new/Common/Result_DB.KEEP_SPACE_IN_TABLE_NAME 과 반드시 동일하게 유지)
KEEP_SPACE_IN_TABLE_NAME = True

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
VIEW_COLUMNS = META_COLUMNS + VALUE_COLUMNS


def table_name(lot_code, oper_desc, fab):
    oper = str(oper_desc)
    if not KEEP_SPACE_IN_TABLE_NAME:
        oper = oper.replace(' ', '_')
    return f'{TABLE_PREFIX}_{lot_code}_{oper}_{fab}'


def existing_tables():
    """DB 에 실제 존재하는 Simulation 결과 테이블 집합."""
    return {t for t in connection.introspection.table_names() if t.startswith(TABLE_PREFIX)}


def table_columns(table):
    with connection.cursor() as cur:
        return [c.name for c in connection.introspection.get_table_description(cur, table)]


def _q(name):
    return connection.ops.quote_name(name)


def _where(date_from, date_to, zone, apc_para):
    clauses, params = [], []
    if date_from:
        clauses.append(f'{_q("Date")} >= %s')
        params.append(date_from)
    if date_to:
        # 종료일 당일 23:59:59 포함
        clauses.append(f'{_q("Date")} < %s')
        params.append(f'{date_to} 23:59:59.999999')
    if zone:
        clauses.append(f'{_q("ZONE")} = %s')
        params.append(zone)
    if apc_para:
        clauses.append(f'{_q("APC_Para")} = %s')
        params.append(apc_para)
    return (' WHERE ' + ' AND '.join(clauses) if clauses else ''), params


def distinct_values(table, column, date_from=None, date_to=None):
    """필터 선택지용 distinct 값 목록 (없는 컬럼이면 빈 리스트)."""
    if column not in table_columns(table):
        return []
    where, params = _where(date_from, date_to, None, None)
    sql = f'SELECT DISTINCT {_q(column)} FROM {_q(table)}{where}'
    with connection.cursor() as cur:
        cur.execute(sql, params)
        return sorted(str(r[0]) for r in cur.fetchall() if r[0] is not None)


def fetch(table, date_from=None, date_to=None, zone=None, apc_para=None,
          max_rows=MAX_ROWS):
    """조건에 맞는 행을 컬럼형(columns/rows)으로 반환.

    Returns: dict(columns, rows, total_rows, sampled)
    행 수가 max_rows 를 넘으면 시간순으로 균등 샘플링해 차트 렌더링 비용을 제한한다.
    """
    available = set(table_columns(table))
    columns   = [c for c in VIEW_COLUMNS if c in available]
    col_sql   = ', '.join(_q(c) for c in columns)
    where, params = _where(date_from, date_to, zone, apc_para)

    with connection.cursor() as cur:
        cur.execute(f'SELECT COUNT(*) FROM {_q(table)}{where}', params)
        total = cur.fetchone()[0]

        stride = max(1, -(-total // max_rows)) if total else 1   # ceil
        cur.execute(f'SELECT {col_sql} FROM {_q(table)}{where} ORDER BY {_q("Date")}', params)

        rows, i = [], 0
        while True:
            batch = cur.fetchmany(2000)
            if not batch:
                break
            for row in batch:
                if i % stride == 0:
                    rows.append([_json_safe(v) for v in row])
                i += 1

    return {
        'columns'   : columns,
        'rows'      : rows,
        'total_rows': total,
        'sampled'   : len(rows) < total,
    }


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
