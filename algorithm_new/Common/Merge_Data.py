import sys, time, traceback
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from pymongo import MongoClient, UpdateOne

sys.path.append(str(Path(__file__).parents[1]))
from Common.MongoDB_Control import mongodb_controller
from Common.Get_Data import Get_data
from day.commc.cube import Cube_Connector

_MERGE_URL = 'mongodb:// ... '
_MERGE_DB  = 'mico-platform-merge-data'
_MICO_URL  = 'mongodb://cncmico:/...'
_MICO_DB   = 'mico-platform-mongodb'
_WEB_URL   = 'mongodb://micoweb: ... '
_WEB_DB    = 'mico-platform-web-db'

_CUBE_BOT_ID    = 'C0000361'
_CUBE_BOT_TOKEN = 'C000036-0D1CHDB40- ... '


# ── Merge GetData (회사 서버 Merge_Get_Data.py 내용 붙여넣기) ──────────────
# 회사 구조와 동일하게 class Merge_Get_data 로 묶음.
# 회사 코드처럼 self 없이 정의 → Merge_Get_data.getdatalake(...) 형태로 호출.

class Merge_Get_data:

    def getdatalake(Fab, Maker, Lot_Code, Oper_Code,
                    Pre_Oper_Code, Recipe_ID_List, Recipe_info, Days):
        pass  # TODO: Merge_Get_Data.getdatalake 본문 붙여넣기

    def getdatahub(Fab, Maker, Lot_Code, Oper_Code,
                   Pre_Oper_Code, Recipe_ID_List, Recipe_info, Oper_Desc):
        pass  # TODO: Merge_Get_Data.getdatahub 본문 붙여넣기


# ── Set-up 조회 ────────────────────────────────────────────────────────────

def _build_mico_info_table(Family, oper_desc):
    return Get_data.baseinfoGetData(Family=Family, oper_desc=oper_desc)


# ── Merge DF 공통 처리 ─────────────────────────────────────────────────────

def _set_eqp_ch(df, Maker):
    """장비 채널(eqp_ch) 설정 (web Set-up 의 Maker 기준, 대소문자 무시).

    - EBARA : recipe_id 의 AB/CD 로 채널 분리        → {eqp_id}_AB / {eqp_id}_CD
    - KCT   : recipe_id 의 _L_/_R_ (중간) 또는
              _L/_R (끝) 로 채널 분리                 → {eqp_id}_L / {eqp_id}_R
              (L/R 표기 없으면 채널 분리 없이 eqp_id 그대로)
    - 그 외(AMAT 등) : eqp_id 그대로
    """
    maker = str(Maker).upper()
    if 'EBARA' in maker:
        df['CH']     = df['recipe_id'].apply(lambda x: 'AB' if 'AB' in x else 'CD')
        df['eqp_ch'] = df['eqp_id'] + '_' + df['CH']
    elif 'KCT' in maker:
        # _L_/_R_ (중간) 또는 _L/_R (끝) 로 좌/우 판별. 둘 다 없으면 '' (채널 없음)
        def _kct_ch(x):
            x = str(x)
            if '_L_' in x or x.endswith('_L'):
                return 'L'
            if '_R_' in x or x.endswith('_R'):
                return 'R'
            return ''
        df['CH']     = df['recipe_id'].apply(_kct_ch)
        has_ch       = df['CH'] != ''
        df['eqp_ch'] = df['eqp_id']
        df.loc[has_ch, 'eqp_ch'] = df.loc[has_ch, 'eqp_id'] + '_' + df.loc[has_ch, 'CH']
    else:
        df['eqp_ch'] = df['eqp_id']
    return df


def _prepare_merge_df(df, Product, oper_desc, Fab, Lot_Code, Maker):
    df = df.rename(columns={'request_dtts': 'Date'})
    df = df.sort_values(by='Date')
    df['Product']   = Product
    df['OPER_DESC'] = oper_desc
    df['Fab']       = Fab
    df['Lot_Code']  = Lot_Code
    df = _set_eqp_ch(df, Maker)
    df = df.fillna('-')
    return df


def _push_with_index(mongo_db, collection, df, c, ctx):
    try:
        if not df.empty:
            ops = [
                UpdateOne(
                    {'substrate_id': row['substrate_id']},
                    {'$set': row.to_dict()},
                    upsert=True,
                )
                for _, row in df.iterrows()
            ]
            collection.bulk_write(ops, ordered=False)
        try:
            mongo_db.set_index('Date', 31)
        except:
            mongo_db.drop_index('Date')
            mongo_db.set_index('Date', 31)
    except Exception as e:
        tb = traceback.format_exc()
        c.sendMsg('', '506204179', f'{ctx} Merge push Failed : {e}, {tb}')


def _load_initial_lake(mongo_db, Fab, Maker, Lot_Code, Oper_Code,
                       Pre_Oper_Code, Recipe_ID_List, Recipe_info, Days,
                       Product, oper_desc):
    if mongo_db.count_row() > 0:
        return
    print('MongoDB 없어 DataLake 30일치 조회 시작!!')
    df = Merge_Get_data.getdatalake(
        Fab, Maker, Lot_Code, Oper_Code,
        Pre_Oper_Code, Recipe_ID_List, Recipe_info, Days,
    )
    df = _prepare_merge_df(df, Product, oper_desc, Fab, Lot_Code, Maker)
    mongo_db.push_df(df)
    del df


# ── PRE_THK_INFO 컬렉션 관리 ───────────────────────────────────────────────

def _get_pre_thk_collection(Lot_Code, oper_desc, Fab):
    """PRE_THK_INFO 컬렉션 handle 반환 (연결만 — 컬렉션/인덱스를 생성하지 않음).

    MongoDB 는 write(insert) 가 있어야 컬렉션이 실제 생성되므로, 연결만 해서는
    빈 테이블이 만들어지지 않는다. (인덱스 생성은 데이터가 생긴 뒤 _ensure_pre_thk_index)
    """
    coll_name = f'MICO_PRE_THK_INFO_{Lot_Code}_{oper_desc}_{Fab}'
    return MongoClient(_MICO_URL)[_MICO_DB][coll_name]


def _ensure_pre_thk_index(Lot_Code, oper_desc, Fab):
    """PRE_THK_INFO 컬렉션에 end_tm 인덱스 설정.

    반드시 문서가 1건 이상 적재된 뒤에만 호출할 것.
    (빈 컬렉션에 인덱스를 걸면 substrate_id 컬럼 없는 빈 테이블이 생성되어
     Removal_Rate.load_pre_thk_data 에서 오류 발생)
    """
    coll_name  = f'MICO_PRE_THK_INFO_{Lot_Code}_{oper_desc}_{Fab}'
    pre_thk_db = mongodb_controller(_MICO_URL, _MICO_DB, coll_name)
    try:
        pre_thk_db.set_index('end_tm', 31)
    except:
        pre_thk_db.drop_index('end_tm')
        pre_thk_db.set_index('end_tm', 31)
    del pre_thk_db


def _has_literal_field(collection, field):
    """literal 점(.) 포함 키(예: 'PRE_OPER2.PARA')를 top-level 키로 가진
    문서가 하나라도 있는지 확인.

    주의: INFO 테이블은 필드명을 f'{desc}.{para}' 형태의 '점 포함 literal 키'로
    저장한다(회사 코드 그대로: row.to_dict() / update_doc['desc.para']=...).
    반면 MongoDB 는 쿼리에서 필드명의 '.'을 nested path 로 해석하므로
    {field: {'$exists': True}} 는 'desc 라는 하위문서의 para' 를 찾게 되어
    literal 점 포함 키를 절대 못 찾는다(문서가 6800개여도 count=0).
    → $objectToArray 로 실제 키 목록을 만들어 literal 매칭한다.
    """
    hit = collection.aggregate([
        {'$project': {'_keys': {'$map': {
            'input': {'$objectToArray': '$$ROOT'}, 'as': 'kv', 'in': '$$kv.k'}}}},
        {'$match': {'_keys': field}},
        {'$limit': 1},
    ])
    return next(iter(hit), None) is not None


def _upsert_pre_doc(collection, query_key, query_val, update_fields, full_row_dict=None):
    """사전공정 단건 upsert
    - 문서 없음 → insert (full_row_dict 우선)
    - 첫 번째 필드 없거나 NaN → 해당 필드 업데이트
    - 이미 유효값 존재 → skip
    """
    doc         = collection.find_one({query_key: query_val})
    first_field = next(iter(update_fields))

    if doc is None:
        new_doc = (full_row_dict.copy() if full_row_dict else {query_key: query_val})
        new_doc.update(update_fields)
        collection.insert_one(new_doc)
    elif first_field not in doc or pd.isna(doc.get(first_field)):
        update_doc = {**doc, **update_fields}
        collection.delete_one({'_id': doc['_id']})
        collection.insert_one(update_doc)


# ── Pre_Oper 정보 파싱 ─────────────────────────────────────────────────────

def _get_pre_oper_info(info_df, i):
    """Pre_Oper{i}의 code·desc·para_list 반환. set-up 없으면 None"""
    code_col = f'Pre_Oper_Code{i}'
    desc_col = f'Pre_Oper_Desc{i}'
    para_col = f'Pre_Oper_Para{i}'

    if code_col not in info_df.columns:
        return None

    valid_codes = [x for x in info_df[code_col].unique()
                   if x and str(x) not in ('', '-', 'nan', 'None')]
    if not valid_codes:
        return None

    code      = valid_codes[0]
    desc      = [x for x in info_df[desc_col].unique() if x][0]
    para_list = tuple(x for x in info_df[para_col].unique()
                      if x and str(x) not in ('', '-', 'nan', 'None'))

    return {'code': code, 'desc': desc, 'para_list': para_list}


# ── Pivot 관련 헬퍼 ────────────────────────────────────────────────────────

def _classify_para_zones(para_list):
    """파라미터 리스트에서 13P / ED / EX / Z5 / WEAK zone 구분.

    zone 마다 파라미터 이름 규칙이 공정별로 달라 여러 패턴을 함께 인식한다.
    각 zone 은 자기 자신의 Target(mean)으로 offset 을 계산하므로 서로 분리한다.
      - ED   : ED1 / EDGE / _A_
      - EX   : ED2 / EXED / _B_
      - Z5   : Z5
      - WEAK : _E_
      - 그 외: 13P
    """
    para_13p = para_ed = para_ex = para_z5 = para_weak = None
    for para in para_list:
        if 'ED1' in para or 'EDGE' in para or '_A_' in para:
            para_ed = para
        elif 'ED2' in para or 'EXED' in para or '_B_' in para:
            para_ex = para
        elif 'Z5' in para:
            para_z5 = para
        elif '_E_' in para:
            para_weak = para
        else:
            para_13p = para
    return para_13p, para_ed, para_ex, para_z5, para_weak


def _safe_mean(df, col):
    """col 이 None 이거나 df 에 없으면 np.nan, 있으면 평균."""
    if col and col in df.columns:
        return df[col].mean()
    return np.nan


def _apply_pivot_offsets(pivot_df, desc, para_13p, tgt_13p, tgt_ed, tgt_ex, tgt_z5, tgt_weak):
    """avg_col에 13P 기준 ED·EX·Z5·WEAK offset(BIAS) 컬럼 추가, 원본 avg_col은 {desc}_{col}로 rename.

    각 zone 은 자기 Target 기준으로 뺀다:
      ED1/EDGE/_A_ → tgt_ed / ED2/EXED/_B_ → tgt_ex / Z5 → tgt_z5 / _E_ → tgt_weak / 그 외 → 13P
    """
    avg_cols = [c for c in pivot_df.columns if '_AVG' in c]
    for col in avg_cols:
        if 'ED1' in col or 'EDGE' in col or '_A_' in col:
            pivot_df[f'{desc}.{col}'] = pivot_df[col] - pivot_df[para_13p] - (tgt_ed - tgt_13p)
        elif 'ED2' in col or 'EXED' in col or '_B_' in col:
            pivot_df[f'{desc}.{col}'] = pivot_df[col] - pivot_df[para_13p] - (tgt_ex - tgt_13p)
        elif 'Z5' in col:
            pivot_df[f'{desc}.{col}'] = pivot_df[col] - pivot_df[para_13p] - (tgt_z5 - tgt_13p)
        elif '_E_' in col:
            pivot_df[f'{desc}.{col}'] = pivot_df[col] - pivot_df[para_13p] - (tgt_weak - tgt_13p)
        else:
            pivot_df[f'{desc}.{col}'] = pivot_df[para_13p] - tgt_13p
    for col in avg_cols:
        pivot_df.rename(columns={col: f'{desc}_{col}'}, inplace=True)
    return pivot_df


# ── Pre_Oper 단일값 처리 ───────────────────────────────────────────────────

def _load_initial_simple_one(collection, info, data_source, Lot_Code, Fab):
    """단일값 사전공정 전체 초기 로드 (SRC / MES, HUB 없이). 저장 키는 substrate_id."""
    code  = info['code']
    desc  = info['desc']
    para  = info['para_list'][0]
    field = f'{desc}.{para}'

    if data_source == 'MES_HUB':
        df = Get_data.PRETHKGetData_MES(Fab, Lot_Code, code, para)
        df.columns = list(map(str.lower, df.columns))
        # MES는 samp_matl_id → substrate_id
        df.rename(columns={'lot_id': 'alias_lot_id', 'module_id': field,
                           'samp_matl_id': 'substrate_id'}, inplace=True)
    else:  # SRC
        df = Get_data.PRETHKGetData_SRC(Lot_Code, code, para)
        df.rename(columns={'thk_value': field}, inplace=True)
        # SRC는 alias_lot_id + wf_id로 substrate_id 구성
        df['substrate_id'] = df['alias_lot_id'] + '.' + df['wf_id']

    if df.empty:
        return 0

    df = df.drop_duplicates(subset='substrate_id', keep='first').fillna('-')
    # substrate_id/field 외에 end_tm·wf_id·alias_lot_id 도 함께 적재 (있을 때만)
    keep = ['substrate_id', field] + [c for c in ('end_tm', 'wf_id', 'alias_lot_id') if c in df.columns]
    records = df[keep].to_dict(orient='records')

    collection.insert_many(records)
    return len(records)


def _process_pre_simple_one(collection, info, data_source, Lot_Code, Fab, Data_lv):
    """단일값 사전공정 처리 (저장 키 substrate_id)

    collection에 해당 field가 없으면 전체 초기 로드(SRC/MES) 후,
    항상 HUB 최신 데이터 upsert 실행.
    """
    code  = info['code']
    desc  = info['desc']
    para  = info['para_list'][0]
    field = f'{desc}.{para}'

    # field(점 포함 literal 키)가 하나도 없으면 전체 초기 로드.
    # count_documents({field: {'$exists': True}})는 '.'을 nested path 로 해석해
    # literal 키를 못 찾으므로(항상 0) 사용 금지 → _has_literal_field 사용.
    created = 0
    if not _has_literal_field(collection, field):
        n = _load_initial_simple_one(collection, info, data_source, Lot_Code, Fab)
        created += n or 0
        print(f'    - 초기 전체 로드 {created}건')

    # HUB 최신 데이터 upsert (samp_matl_id → substrate_id)
    if data_source == 'MES_HUB':
        df = Get_data.PRETHKGetData_MES_HUB(Fab, Lot_Code, code, para, Data_lv)
        df.columns = list(map(str.lower, df.columns))
        rename_map = {'lot_id': 'alias_lot_id', 'module_id': field, 'samp_matl_id': 'substrate_id'}
    else:  # SRC_HUB
        df = Get_data.PRETHKGetData_SRC_HUB(Lot_Code, code, para, Data_lv)
        df.columns = list(map(str.lower, df.columns))
        rename_map = {'lot_id': 'alias_lot_id', 'rslt_val': field, 'samp_matl_id': 'substrate_id'}

    df.rename(columns=rename_map, inplace=True)

    if df.empty:
        return created

    # substrate_id/field 외에 end_tm·wf_id·alias_lot_id 도 함께 적재 (있을 때만).
    # 신규 문서는 full_row_dict 로 삽입되므로 keep 에 포함하면 함께 저장됨.
    keep = ['substrate_id', field] + [c for c in ('end_tm', 'wf_id', 'alias_lot_id') if c in df.columns]
    df = df[keep].copy()

    for _, row in df.iterrows():
        _upsert_pre_doc(
            collection,
            query_key='substrate_id',
            query_val=row['substrate_id'],
            update_fields={field: row[field]},
            full_row_dict=row.to_dict(),
        )
    return created + len(df)


# ── Pre_Oper Pivot 처리 ────────────────────────────────────────────────────

def _load_initial_pivot_one(collection, info, Lot_Code):
    """초기 로드: PRETHKGetData_SRC → pivot → offset 계산 → insert_many"""
    code      = info['code']
    desc      = info['desc']
    para_list = info['para_list']
    para_13p, para_ed, para_ex, para_z5, para_weak = _classify_para_zones(para_list)

    pre_df = Get_data.PRETHKGetData_SRC(Lot_Code, code, para_list)

    pivot = pd.pivot_table(
        data=pre_df,
        index=['end_tm', 'substrate_id'],
        columns='param_nm',
        values='thk_value',
    )
    pivot.reset_index(inplace=True)

    tgt_13p  = _safe_mean(pivot, para_13p)
    tgt_ed   = _safe_mean(pivot, para_ed)
    tgt_ex   = _safe_mean(pivot, para_ex)
    tgt_z5   = _safe_mean(pivot, para_z5)
    tgt_weak = _safe_mean(pivot, para_weak)
    pivot    = _apply_pivot_offsets(pivot, desc, para_13p, tgt_13p, tgt_ed, tgt_ex, tgt_z5, tgt_weak)
    pivot    = pivot.fillna('-')

    collection.insert_many(pivot.to_dict(orient='records'))
    return pivot


def _process_pre_pivot_one(collection, info, Lot_Code, Data_lv):
    """Pivot 사전공정 처리 (13P·ED·EX·Z5·WEAK offset)

    collection 비어있으면 SRC 전체 로드 후 insert_many,
    항상 SRC_HUB 최신 데이터 pivot upsert.
    """
    code      = info['code']
    desc      = info['desc']
    para_list = info['para_list']
    para_13p, para_ed, para_ex, para_z5, para_weak = _classify_para_zones(para_list)

    # 이 pre_oper 의 pivot 기준 컬럼명 (underscore → dot-path 이슈 없음)
    col_13p  = f'{desc}_{para_13p}'
    col_ed   = f'{desc}_{para_ed}' if para_ed else None
    col_ex   = f'{desc}_{para_ex}' if para_ex else None
    col_z5   = f'{desc}_{para_z5}' if para_z5 else None
    col_weak = f'{desc}_{para_weak}' if para_weak else None

    # 기존 데이터 조회 → collection 이 비었거나, (공유 collection 에 다른
    # pre_oper 데이터만 있어) 이 pre_oper 의 컬럼이 아직 없으면 초기 전체 로드.
    # 예전엔 empty 만 봐서, 다른 pre_oper 가 collection 을 이미 채운 경우
    # 자기 초기 로드를 건너뛰고 col_13p 접근에서 KeyError 발생했음.
    created = 0
    pre_thk_all = pd.DataFrame(collection.find({}, {'_id': 0}))
    if pre_thk_all.empty or col_13p not in pre_thk_all.columns:
        pre_thk_all = _load_initial_pivot_one(collection, info, Lot_Code)
        created += len(pre_thk_all)
        print(f'    - 초기 전체 로드 {created}건')

    # 전체 데이터에서 최신 기준값(zone별 Target) 갱신
    pre_thk_all = pre_thk_all.replace('-', np.nan)
    for col in (col_13p, col_ed, col_ex, col_z5, col_weak):
        if col and col in pre_thk_all.columns:
            pre_thk_all[col] = pd.to_numeric(pre_thk_all[col], errors='coerce')

    tgt_13p  = _safe_mean(pre_thk_all, col_13p)
    tgt_ed   = _safe_mean(pre_thk_all, col_ed)
    tgt_ex   = _safe_mean(pre_thk_all, col_ex)
    tgt_z5   = _safe_mean(pre_thk_all, col_z5)
    tgt_weak = _safe_mean(pre_thk_all, col_weak)

    # HUB 최신 데이터 → pivot → upsert
    hub_df = Get_data.PRETHKGetData_SRC_HUB(Lot_Code, code, para_list, Data_lv)
    if hub_df.empty:
        return created

    hub_df.columns = list(map(str.lower, hub_df.columns))
    hub_df.rename(columns={'lot_id': 'alias_lot_id', 'samp_matl_id': 'substrate_id'}, inplace=True)

    pivot = pd.pivot_table(
        data=hub_df,
        index=['end_tm', 'substrate_id'],
        columns='dcol_item_cd',
        values='rslt_val',
    )
    pivot.reset_index(inplace=True)
    pivot = _apply_pivot_offsets(pivot, desc, para_13p, tgt_13p, tgt_ed, tgt_ex, tgt_z5, tgt_weak)

    # 존재하는 zone(13P/ED/EX/Z5/WEAK)만 update_fields 구성
    zone_paras = [p for p in (para_13p, para_ed, para_ex, para_z5, para_weak) if p]
    for _, row in pivot.iterrows():
        _upsert_pre_doc(
            collection,
            query_key='substrate_id',
            query_val=row['substrate_id'],
            update_fields={f'{desc}.{p}': row.get(f'{desc}.{p}') for p in zone_paras},
            full_row_dict=row.to_dict(),
        )
    return created + len(pivot)


# ── Pre_Oper 디스패처 ──────────────────────────────────────────────────────

def _process_pre_oper(collection, info_df, i, data_source, Lot_Code, Fab, Data_lv):
    """Pre_Oper{i} 처리 메인 디스패처

    1. set-up 확인 (mico_info_key에 Pre_Oper_Code{i} 존재 여부)
    2. para_list 개수로 simple vs pivot 자동 판별
    3. 알맞은 처리 함수 호출
    """
    info = _get_pre_oper_info(info_df, i)
    if info is None:
        return None  # web set-up 없음 → skip

    if len(info['para_list']) > 1:
        # para가 여러 개(13P/ED/EX) → pivot 방식
        return _process_pre_pivot_one(collection, info, Lot_Code, Data_lv)
    else:
        # para가 하나 → 단일값 방식
        return _process_pre_simple_one(collection, info, data_source, Lot_Code, Fab, Data_lv)


# ── 메인 실행 ──────────────────────────────────────────────────────────────

def run(Family, oper_desc,
        pre_oper_config=None,
        Days=30):
    """Merge Hub 메인 실행

    Args:
        Family          : 'NAND' or 'DRAM'
        oper_desc       : 공정 이름 (예: 'M1 CU CMP')
        pre_oper_config : {인덱스: data_source} dict
                          예) {2: 'SRC_HUB', 3: 'SRC_HUB', 4: 'SRC_HUB'}
                              {2: 'MES_HUB', 3: 'MES_HUB'}
                              {} 또는 None → 사전공정 처리 없음
        Days            : DataLake 초기 로드 기간 (일)

    (채널 분리(AB/CD, L/R)는 web Set-up 의 Maker 값으로 키별 자동 처리)
    """
    if pre_oper_config is None:
        pre_oper_config = {}

    c          = Cube_Connector(_CUBE_BOT_ID, _CUBE_BOT_TOKEN)
    start_time = time.time()
    Data_lv    = 'Wafer'

    print(f'\n{"=" * 60}')
    print(f'  Merge Hub 시작: Family={Family} | Oper_Desc={oper_desc}')
    print(f'{"=" * 60}')

    try:
        mico_info_table = _build_mico_info_table(Family, oper_desc)

        # Lot_Code + Oper_Code + Fab 조합으로 단일 처리 키 생성
        mico_info_table['for_key'] = (
            mico_info_table['Lot_Code'] + '_' +
            mico_info_table['Oper_Code'] + '_' +
            mico_info_table['Fab']
        )
        key_list = mico_info_table['for_key'].unique()

        print(f'  처리 키 목록 ({len(key_list)}개):')
        for k in key_list:
            print(f'    - {k}')

        for key in key_list:
            info_df = mico_info_table[mico_info_table['for_key'] == key].copy()

            Lot_Code       = info_df['Lot_Code'].unique()[0]
            Oper_Code      = info_df['Oper_Code'].unique()[0]
            Fab            = info_df['Fab'].unique()[0]
            Product        = info_df['Product'].unique()[0]
            Maker          = info_df['Maker'].unique()[0]
            Pre_Oper_Code  = info_df['Pre_Oper_Code'].unique()[0]
            THK_Para_list  = list(info_df['Thk_Para'].unique())
            Recipe_ID_List = tuple(info_df['Recipe_ID'].unique())
            Recipe_info    = Recipe_ID_List[0].split('_')[0] + '_' + Recipe_ID_List[0].split('_')[1]
            Oper_Desc      = info_df['Oper_Desc'].unique()[0]

            print(f'\n[{key}] 처리 시작 (Maker={Maker})')

            try:
                # 1. merge DB 연결
                merge_coll_name  = f'MICO_Merge_df_{Lot_Code}_{Oper_Desc}_{Fab}'
                mongo_db         = mongodb_controller(_MERGE_URL, _MERGE_DB, merge_coll_name)
                merge_collection = MongoClient(_MERGE_URL)[_MERGE_DB][merge_coll_name]

                # 2. 초기 DataLake 로드
                print('  [merge] merge data 생성 중...')
                _load_initial_lake(
                    mongo_db, Fab, Maker, Lot_Code, Oper_Code,
                    Pre_Oper_Code, Recipe_ID_List, Recipe_info, Days,
                    Product, oper_desc,
                )

                # 3. HUB 최신 데이터 업데이트
                hub_df = Merge_Get_data.getdatahub(
                    Fab, Maker, Lot_Code, Oper_Code,
                    Pre_Oper_Code, Recipe_ID_List, Recipe_info, Oper_Desc,
                )
                hub_cnt = 0
                if not hub_df.empty:
                    hub_df = _prepare_merge_df(hub_df, Product, oper_desc, Fab, Lot_Code, Maker)
                    hub_cnt = len(hub_df)
                    _push_with_index(mongo_db, merge_collection, hub_df, c, f'{Fab} {Lot_Code} {Oper_Desc}')

                print(f'  [merge] merge data 생성 완료: 이번 {hub_cnt}건 / 누적 {mongo_db.count_row()}건 '
                      f'({time.time() - start_time:.1f}s)')

                # 4-5. 사전공정 처리 (Pre_Oper 2→3→4 순)
                # set-up 있는(실제 처리 가능한) pre_oper 만 선별 → 하나도 없으면
                # PRE_THK 테이블을 아예 만들지 않는다(빈 테이블 방지).
                if pre_oper_config:
                    valid_pre = {i: ds for i, ds in pre_oper_config.items()
                                 if _get_pre_oper_info(info_df, i) is not None}
                    skipped = [i for i in pre_oper_config if i not in valid_pre]
                    for i in skipped:
                        print(f'  [Pre_Oper{i}] set-up 없음 → skip')

                    if not valid_pre:
                        print('  [Pre_Oper] 처리할 set-up 없음 → PRE_THK 테이블 생성 skip')
                    else:
                        # 연결만(테이블 미생성). 실제 insert 가 일어나야 컬렉션 생성됨.
                        collection = _get_pre_thk_collection(Lot_Code, oper_desc, Fab)
                        for i, data_source in valid_pre.items():
                            print(f'  [Pre_Oper{i}] 생성 중...')
                            cnt = _process_pre_oper(
                                collection, info_df, i, data_source,
                                Lot_Code, Fab, Data_lv,
                            )
                            print(f'  [Pre_Oper{i}] 생성 완료: {cnt}건')

                        # 문서가 실제로 적재됐을 때만 인덱스 생성 (빈 테이블 방지)
                        if collection.count_documents({}) > 0:
                            _ensure_pre_thk_index(Lot_Code, oper_desc, Fab)
                        else:
                            print('  [Pre_Oper] 생성된 데이터 없음 → 인덱스/테이블 생성 skip')

                # 6. Report 업데이트
                print('  report data 조회 함수 실행')
                report_db = mongodb_controller(_WEB_URL, _WEB_DB, 'MICO_Report')
                today_    = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
                condition = {
                    'Lot_Code': Lot_Code, 'OPER_DESC': Oper_Desc,
                    'Fab': Fab, 'Date': {'$gte': today_},
                }
                report_df = report_db.get_df(condition)
                if report_df.empty:
                    print(f'  report data 생성 {today_}')
                    merge_df = mongo_db.get_df()
                    Get_data.Report(merge_df, THK_Para_list)
                    print('  report Upload 완료')

            except Exception as e:
                tb = traceback.format_exc()
                c.sendMsg('', '506204179', f'{Fab} {Lot_Code} {Oper_Desc} Merge HUB Failed : {e}, {tb}')

    except Exception as e:
        tb = traceback.format_exc()
        c.sendMsg('', '506204179', f'{Family} {oper_desc} Merge HUB Failed : {e}, {tb}')

    print(f'\n{"=" * 60}')
    print(f'  Merge Hub 완료: Family={Family} | Oper_Desc={oper_desc}')
    print(f'{"=" * 60}')
