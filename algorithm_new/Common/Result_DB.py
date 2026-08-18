"""Simulation 결과를 MICO Web Set-up 과 동일한 DB(관계형 DB)에 저장/조회.

기존에는 Simulation 결과를 Spotfire 연동용 CSV 파일로 떨어뜨렸으나,
web 에서 바로 조회할 수 있도록 Set-up 정보가 들어있는 Django DB 에 적재한다.

■ 테이블 명명 규칙 (다른 학습 테이블과 동일하게 공정명 포함)
      MICO_PRE_THK_{Lot_Code}_{Oper_Desc}_{Fab}_Period   (Pre Thk 학습)
      MICO_Removal_Rate_{Lot_Code}_{Oper_Desc}_{Fab}     (RR 학습)
      MICO_OFFSET_{Lot_Code}_{Oper_Desc}_{Fab}           (Offset 학습)
  →   MICO_Simulation_{Lot_Code}_{Oper_Desc}_{Fab}       (Simulation 결과, 본 모듈)

  zone(13P / EDGE / EXED / Z5 ...) 은 별도 테이블이 아니라 ZONE 컬럼으로 구분한다.
  (Spotfire 시절 Simul_13P / Simul_ED1 / Simul_ED2 / Simul_Other CSV 분리 → ZONE 컬럼)

■ 로컬 ↔ 사내 전환
  이 파일은 Django 의 default DB 연결(django.db.connection)만 사용한다.
  → 로컬은 config/settings.py 의 DATABASES 가 개인 PC DB,
     사내에서는 같은 자리에 사내 DB 접속 정보만 넣으면 코드 수정 없이 그대로 동작한다.
  (DB 종류별 컬럼 타입은 _TYPE_MAP 에서 vendor 별로 분기 — Oracle/MSSQL 도 지원)
"""

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ── Django setup (Get_Data.py 와 동일 방식 — Set-up 과 같은 DB 연결 재사용) ──
_MICO_WEB = str(Path(__file__).parents[2])   # MICO_Web/ (Django root)
if _MICO_WEB not in sys.path:
    sys.path.insert(0, _MICO_WEB)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.db import connection

# 테이블 명명 규칙은 web 조회측(setup_mico/simulation_db.py)과 한 곳에서 공유한다.
#   MICO_Simulation_{Lot_Code}_{Oper_Desc}_{Fab}
# 공백 유지 여부(KEEP_SPACE_IN_TABLE_NAME) 등 규칙 변경도 그 파일에서 한 번만 수정.
from setup_mico.simulation_db import TABLE_PREFIX, table_name

# DB 종류별 컬럼 타입 (vendor = django.db.connection.vendor)
_TYPE_MAP = {
    'postgresql': {'ts': 'TIMESTAMP',  'float': 'DOUBLE PRECISION', 'int': 'BIGINT',      'text': 'TEXT'},
    'sqlite':     {'ts': 'TIMESTAMP',  'float': 'REAL',             'int': 'INTEGER',     'text': 'TEXT'},
    'mysql':      {'ts': 'DATETIME',   'float': 'DOUBLE',           'int': 'BIGINT',      'text': 'TEXT'},
    'oracle':     {'ts': 'TIMESTAMP',  'float': 'BINARY_DOUBLE',    'int': 'NUMBER(19)',  'text': 'VARCHAR2(1000)'},
    'microsoft':  {'ts': 'DATETIME2',  'float': 'FLOAT',            'int': 'BIGINT',      'text': 'NVARCHAR(1000)'},
}
_DEFAULT_TYPES = _TYPE_MAP['postgresql']

# 식별자(테이블/컬럼) 최대 길이 — PostgreSQL 63, Oracle 128. 가장 짧은 쪽 기준.
_MAX_IDENT_LEN = 63

_INSERT_CHUNK = 500


# ── 이름 규칙 ──────────────────────────────────────────────────────────────

def _safe_columns(df):
    """DB 식별자 길이 제한을 넘는 컬럼명을 잘라내고 중복을 방지한 rename map 반환."""
    rename, used = {}, set()
    for col in df.columns:
        name = str(col)
        if len(name) > _MAX_IDENT_LEN:
            name = name[:_MAX_IDENT_LEN]
        base, i = name, 1
        while name in used:
            suffix = f'_{i}'
            name = base[:_MAX_IDENT_LEN - len(suffix)] + suffix
            i += 1
        used.add(name)
        if name != str(col):
            rename[col] = name
    return rename


# ── 타입 / 값 변환 ─────────────────────────────────────────────────────────

def _types():
    return _TYPE_MAP.get(connection.vendor, _DEFAULT_TYPES)


def _sql_type(series):
    t = _types()
    if pd.api.types.is_datetime64_any_dtype(series):
        return t['ts']
    if pd.api.types.is_bool_dtype(series):
        return t['int']
    if pd.api.types.is_integer_dtype(series):
        return t['int']
    if pd.api.types.is_float_dtype(series):
        return t['float']
    return t['text']


def _to_py_values(series):
    """DB 드라이버가 그대로 받을 수 있는 Python 값 리스트로 변환.

    numpy 스칼라(np.float64 등)는 psycopg2/cx_Oracle 이 인식하지 못하므로
    반드시 Python 기본형으로 변환하고, 결측(NaN/NaT/None)은 None 으로 통일한다.
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        return [None if pd.isna(v) else v.to_pydatetime() for v in series]
    if pd.api.types.is_integer_dtype(series) or pd.api.types.is_bool_dtype(series):
        return [None if pd.isna(v) else int(v) for v in series]
    if pd.api.types.is_float_dtype(series):
        return [None if pd.isna(v) else float(v) for v in series]

    out = []
    for v in series:
        if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NaT:
            out.append(None)
        elif isinstance(v, (pd.Timestamp,)):
            out.append(v.to_pydatetime())
        elif isinstance(v, (np.integer,)):
            out.append(int(v))
        elif isinstance(v, (np.floating,)):
            out.append(float(v))
        else:
            out.append(str(v))
    return out


# ── DDL / DML ──────────────────────────────────────────────────────────────

def _quote(name):
    return connection.ops.quote_name(name)


def table_exists(table):
    return table in connection.introspection.table_names()


def drop_table(table):
    if not table_exists(table):
        return
    with connection.cursor() as cur:
        cur.execute(f'DROP TABLE {_quote(table)}')


def _create_table(table, df):
    cols = ', '.join(f'{_quote(c)} {_sql_type(df[c])}' for c in df.columns)
    with connection.cursor() as cur:
        cur.execute(f'CREATE TABLE {_quote(table)} ({cols})')
        # 조회는 항상 기간 기준 → Date 인덱스만 생성
        if 'Date' in df.columns:
            idx = f'{table}_date_idx'[:_MAX_IDENT_LEN]
            cur.execute(f'CREATE INDEX {_quote(idx)} ON {_quote(table)} ({_quote("Date")})')


def _insert(table, df):
    cols     = list(df.columns)
    col_sql  = ', '.join(_quote(c) for c in cols)
    ph       = ', '.join(['%s'] * len(cols))
    sql      = f'INSERT INTO {_quote(table)} ({col_sql}) VALUES ({ph})'

    columns = [_to_py_values(df[c]) for c in cols]
    rows    = list(zip(*columns)) if columns else []

    with connection.cursor() as cur:
        for i in range(0, len(rows), _INSERT_CHUNK):
            cur.executemany(sql, rows[i:i + _INSERT_CHUNK])


# ── 공개 API ───────────────────────────────────────────────────────────────

def save_simulation(df, Lot_Code, Oper_Desc, Fab, mode='replace'):
    """Simulation 결과 DataFrame 을 MICO_Simulation_{Lot_Code}_{Oper_Desc}_{Fab} 에 저장.

    Args:
        df       : Simulation 결과 (zone 별 결과를 ZONE 컬럼으로 합친 프레임)
        mode     : 'replace' → 테이블 재생성(기존 CSV 덮어쓰기와 동일 의미)
                   'append'  → 기존 테이블에 추가 (컬럼이 동일할 때만 사용)
    Returns:
        (table_name, 저장 행 수)
    """
    table = table_name(Lot_Code, Oper_Desc, Fab)

    if df is None or df.empty:
        print(f'    [DB] {table}: 저장할 데이터 없음 → skip')
        return table, 0

    df = df.copy()
    rename = _safe_columns(df)
    if rename:
        df.rename(columns=rename, inplace=True)

    # object 컬럼에 섞인 Timestamp 는 문자열이 되므로 Date 계열은 명시적으로 변환
    for col in df.columns:
        if col == 'Date' or str(col).endswith('_Date') or str(col).endswith('_time'):
            df[col] = pd.to_datetime(df[col], errors='coerce')

    if mode == 'replace' or not table_exists(table):
        drop_table(table)
        _create_table(table, df)
    else:
        # append: 기존 테이블에 없는 컬럼은 버림 (스키마 변경은 replace 로 처리)
        with connection.cursor() as cur:
            existing = [c.name for c in connection.introspection.get_table_description(cur, table)]
        df = df[[c for c in df.columns if c in existing]]

    _insert(table, df)
    print(f'    [DB] {table}: {len(df)}행 저장 ({connection.vendor})')
    return table, len(df)


def load_simulation(Lot_Code, Oper_Desc, Fab, columns=None, date_from=None, date_to=None,
                    zone=None, limit=None):
    """저장된 Simulation 결과를 DataFrame 으로 조회 (노트북/검증용)."""
    table = table_name(Lot_Code, Oper_Desc, Fab)
    if not table_exists(table):
        return pd.DataFrame()

    col_sql = '*' if not columns else ', '.join(_quote(c) for c in columns)
    where, params = [], []
    if date_from:
        where.append(f'{_quote("Date")} >= %s'); params.append(date_from)
    if date_to:
        where.append(f'{_quote("Date")} <= %s'); params.append(date_to)
    if zone:
        where.append(f'{_quote("ZONE")} = %s');  params.append(zone)

    sql = f'SELECT {col_sql} FROM {_quote(table)}'
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += f' ORDER BY {_quote("Date")}'
    if limit:
        sql += f' LIMIT {int(limit)}'

    with connection.cursor() as cur:
        cur.execute(sql, params)
        cols = [c[0] for c in cur.description]
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=cols)


def list_simulation_tables():
    """DB 에 존재하는 Simulation 결과 테이블 목록."""
    return sorted(t for t in connection.introspection.table_names()
                  if t.startswith(TABLE_PREFIX))
