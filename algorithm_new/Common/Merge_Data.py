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

def _set_eqp_ch(df, eqp_ch_mode):
    """AMAT: eqp_id 그대로 / EBARA: recipe AB·CD 기준 채널 분리"""
    if eqp_ch_mode == 'EBARA':
        df['CH']     = df['recipe_id'].apply(lambda x: 'AB' if 'AB' in x else 'CD')
        df['eqp_ch'] = df['eqp_id'] + '_' + df['CH']
    else:
        df['eqp_ch'] = df['eqp_id']
    return df


def _prepare_merge_df(df, Product, oper_desc, Fab, Lot_Code, eqp_ch_mode):
    df = df.rename(columns={'request_dtts': 'Date'})
    df = df.sort_values(by='Date')
    df['Product']   = Product
    df['OPER_DESC'] = oper_desc
    df['Fab']       = Fab
    df['Lot_Code']  = Lot_Code
    df = _set_eqp_ch(df, eqp_ch_mode)
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
                       Product, oper_desc, eqp_ch_mode):
    if mongo_db.count_row() > 0:
        return
    print('MongoDB 없어 DataLake 30일치 조회 시작!!')
    df = getdatalake(
        Fab, Maker, Lot_Code, Oper_Code,
        Pre_Oper_Code, Recipe_ID_List, Recipe_info, Days,
    )
    df = _prepare_merge_df(df, Product, oper_desc, Fab, Lot_Code, eqp_ch_mode)
    mongo_db.push_df(df)
    del df


# ── PRE_THK_INFO 컬렉션 관리 ───────────────────────────────────────────────

def _setup_pre_thk_db(Lot_Code, oper_desc, Fab):
    """PRE_THK_INFO 컬렉션 연결 + end_tm 인덱스 설정 후 collection 반환"""
    coll_name  = f'MICO_PRE_THK_INFO_{Lot_Code}_{oper_desc}_{Fab}'
    client     = MongoClient(_MICO_URL)
    collection = client[_MICO_DB][coll_name]

    pre_thk_db = mongodb_controller(_MICO_URL, _MICO_DB, coll_name)
    try:
        pre_thk_db.set_index('end_tm', 31)
    except:
        pre_thk_db.drop_index('end_tm')
        pre_thk_db.set_index('end_tm', 31)
    del pre_thk_db
    return collection


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


def _get_collection_query_key(info_df, pre_oper_config):
    """pivot Pre_Oper(para 여러 개)가 하나라도 있으면 substrate_id, 아니면 samp_matl_id"""
    for i in pre_oper_config:
        info = _get_pre_oper_info(info_df, i)
        if info and len(info['para_list']) > 1:
            return 'substrate_id'
    return 'samp_matl_id'


# ── Pivot 관련 헬퍼 ────────────────────────────────────────────────────────

def _classify_para_zones(para_list):
    """파라미터 리스트에서 13P / ED / EX(Z5) 구분"""
    para_13p = para_ed = para_ex = None
    for para in para_list:
        if 'ED1' in para or 'EDGE' in para:
            para_ed = para
        elif 'ED2' in para or 'EXED' in para or 'Z5' in para:
            para_ex = para
        else:
            para_13p = para
    return para_13p, para_ed, para_ex


def _apply_pivot_offsets(pivot_df, desc, para_13p, para_ed, para_ex, tgt_13p, tgt_ed, tgt_ex):
    """avg_col에 13P 기준 ED·EX offset 컬럼 추가, 원본 avg_col은 {desc}_{col}로 rename"""
    avg_cols = [c for c in pivot_df.columns if '_AVG' in c]
    for col in avg_cols:
        if 'ED1' in col or 'EDGE' in col:
            pivot_df[f'{desc}.{col}'] = pivot_df[col] - pivot_df[para_13p] - (tgt_ed - tgt_13p)
        elif 'ED2' in col or 'EXED' in col or 'Z5' in col:
            pivot_df[f'{desc}.{col}'] = pivot_df[col] - pivot_df[para_13p] - (tgt_ex - tgt_13p)
        else:
            pivot_df[f'{desc}.{col}'] = pivot_df[para_13p] - tgt_13p
    for col in avg_cols:
        pivot_df.rename(columns={col: f'{desc}_{col}'}, inplace=True)
    return pivot_df


# ── Pre_Oper 단일값 처리 ───────────────────────────────────────────────────

def _load_initial_simple_one(collection, info, data_source, Lot_Code, Fab, query_key):
    """단일값 사전공정 전체 초기 로드 (SRC / MES, HUB 없이)"""
    code  = info['code']
    desc  = info['desc']
    para  = info['para_list'][0]
    field = f'{desc}.{para}'

    if data_source == 'MES_HUB':
        df = Get_data.PRETHKGetData_MES(Fab, Lot_Code, code, para)
        df.columns = list(map(str.lower, df.columns))
        df.rename(columns={'lot_id': 'alias_lot_id', 'module_id': field}, inplace=True)
        # MES는 samp_matl_id가 query key → substrate_id 필요 시 rename
        if query_key == 'substrate_id':
            df.rename(columns={'samp_matl_id': 'substrate_id'}, inplace=True)
    else:  # SRC
        df = Get_data.PRETHKGetData_SRC(Lot_Code, code, para)
        df.rename(columns={'thk_value': field}, inplace=True)
        # SRC는 alias_lot_id + wf_id로 wafer key 구성
        df[query_key] = df['alias_lot_id'] + '.' + df['wf_id']

    if df.empty:
        return

    df = df.drop_duplicates(subset=query_key, keep='first').fillna('-')

    # substrate_id key 사용 시 query_key + field 컬럼만 적재
    if query_key == 'substrate_id':
        records = df[[query_key, field]].to_dict(orient='records')
    else:
        records = df.to_dict(orient='records')

    collection.insert_many(records)


def _process_pre_simple_one(collection, info, data_source, Lot_Code, Fab, Data_lv, query_key):
    """단일값 사전공정 처리

    collection에 해당 field가 없으면 전체 초기 로드(SRC/MES) 후,
    항상 HUB 최신 데이터 upsert 실행.
    """
    code  = info['code']
    desc  = info['desc']
    para  = info['para_list'][0]
    field = f'{desc}.{para}'

    # field가 하나도 없으면 전체 초기 로드
    if collection.count_documents({field: {'$exists': True}}) == 0:
        _load_initial_simple_one(collection, info, data_source, Lot_Code, Fab, query_key)

    # HUB 최신 데이터 upsert
    if data_source == 'MES_HUB':
        df = Get_data.PRETHKGetData_MES_HUB(Fab, Lot_Code, code, para, Data_lv)
        df.columns = list(map(str.lower, df.columns))
        rename_map = {'lot_id': 'alias_lot_id', 'module_id': field}
    else:  # SRC_HUB
        df = Get_data.PRETHKGetData_SRC_HUB(Lot_Code, code, para, Data_lv)
        df.columns = list(map(str.lower, df.columns))
        rename_map = {'lot_id': 'alias_lot_id', 'rslt_val': field}

    if query_key == 'substrate_id':
        rename_map['samp_matl_id'] = 'substrate_id'

    df.rename(columns=rename_map, inplace=True)

    if df.empty:
        return

    if query_key == 'substrate_id':
        df = df[[query_key, field]].copy()

    for _, row in df.iterrows():
        _upsert_pre_doc(
            collection,
            query_key=query_key,
            query_val=row[query_key],
            update_fields={field: row[field]},
            full_row_dict=row.to_dict(),
        )


# ── Pre_Oper Pivot 처리 ────────────────────────────────────────────────────

def _load_initial_pivot_one(collection, info, Lot_Code):
    """초기 로드: PRETHKGetData_SRC → pivot → offset 계산 → insert_many"""
    code      = info['code']
    desc      = info['desc']
    para_list = info['para_list']
    para_13p, para_ed, para_ex = _classify_para_zones(para_list)

    pre_df = Get_data.PRETHKGetData_SRC(Lot_Code, code, para_list)

    pivot = pd.pivot_table(
        data=pre_df,
        index=['end_tm', 'substrate_id'],
        columns='param_nm',
        values='thk_value',
    )
    pivot.reset_index(inplace=True)

    tgt_13p = pivot[para_13p].mean()
    tgt_ed  = pivot[para_ed].mean()
    tgt_ex  = pivot[para_ex].mean()
    pivot   = _apply_pivot_offsets(pivot, desc, para_13p, para_ed, para_ex, tgt_13p, tgt_ed, tgt_ex)
    pivot   = pivot.fillna('-')

    collection.insert_many(pivot.to_dict(orient='records'))
    return pivot


def _process_pre_pivot_one(collection, info, Lot_Code, Data_lv):
    """Pivot 사전공정 처리 (13P·ED·EX offset)

    collection 비어있으면 SRC 전체 로드 후 insert_many,
    항상 SRC_HUB 최신 데이터 pivot upsert.
    """
    code      = info['code']
    desc      = info['desc']
    para_list = info['para_list']
    para_13p, para_ed, para_ex = _classify_para_zones(para_list)

    # 기존 데이터 조회 → 없으면 초기 전체 로드
    pre_thk_all = pd.DataFrame(collection.find({}, {'_id': 0}))
    if pre_thk_all.empty:
        pre_thk_all = _load_initial_pivot_one(collection, info, Lot_Code)

    # 전체 데이터에서 최신 기준값 갱신
    pre_thk_all = pre_thk_all.replace('-', np.nan)
    col_13p = f'{desc}_{para_13p}'
    col_ed  = f'{desc}_{para_ed}'
    col_ex  = f'{desc}_{para_ex}'
    for col in (col_13p, col_ed, col_ex):
        pre_thk_all[col] = pd.to_numeric(pre_thk_all[col], errors='coerce')

    tgt_13p = pre_thk_all[col_13p].mean()
    tgt_ed  = pre_thk_all[col_ed].mean()
    tgt_ex  = pre_thk_all[col_ex].mean()

    # HUB 최신 데이터 → pivot → upsert
    hub_df = Get_data.PRETHKGetData_SRC_HUB(Lot_Code, code, para_list, Data_lv)
    if hub_df.empty:
        return

    hub_df.columns = list(map(str.lower, hub_df.columns))
    hub_df.rename(columns={'lot_id': 'alias_lot_id', 'samp_matl_id': 'substrate_id'}, inplace=True)

    pivot = pd.pivot_table(
        data=hub_df,
        index=['end_tm', 'substrate_id'],
        columns='dcol_item_cd',
        values='rslt_val',
    )
    pivot.reset_index(inplace=True)
    pivot = _apply_pivot_offsets(pivot, desc, para_13p, para_ed, para_ex, tgt_13p, tgt_ed, tgt_ex)

    for _, row in pivot.iterrows():
        _upsert_pre_doc(
            collection,
            query_key='substrate_id',
            query_val=row['substrate_id'],
            update_fields={
                f'{desc}.{para_13p}': row.get(f'{desc}.{para_13p}'),
                f'{desc}.{para_ed}':  row.get(f'{desc}.{para_ed}'),
                f'{desc}.{para_ex}':  row.get(f'{desc}.{para_ex}'),
            },
            full_row_dict=row.to_dict(),
        )


# ── Pre_Oper 디스패처 ──────────────────────────────────────────────────────

def _process_pre_oper(collection, info_df, i, data_source, Lot_Code, Fab, Data_lv, query_key):
    """Pre_Oper{i} 처리 메인 디스패처

    1. set-up 확인 (mico_info_key에 Pre_Oper_Code{i} 존재 여부)
    2. para_list 개수로 simple vs pivot 자동 판별
    3. 알맞은 처리 함수 호출
    """
    info = _get_pre_oper_info(info_df, i)
    if info is None:
        return  # web set-up 없음 → skip

    if len(info['para_list']) > 1:
        # para가 여러 개(13P/ED/EX) → pivot 방식
        _process_pre_pivot_one(collection, info, Lot_Code, Data_lv)
    else:
        # para가 하나 → 단일값 방식
        _process_pre_simple_one(collection, info, data_source, Lot_Code, Fab, Data_lv, query_key)


# ── 메인 실행 ──────────────────────────────────────────────────────────────

def run(Family, oper_desc,
        pre_oper_config=None,
        eqp_ch_mode='AMAT',
        Days=30):
    """Merge Hub 메인 실행

    Args:
        Family          : 'NAND' or 'DRAM'
        oper_desc       : 공정 이름 (예: 'M1 CU CMP')
        pre_oper_config : {인덱스: data_source} dict
                          예) {2: 'SRC_HUB', 3: 'SRC_HUB', 4: 'SRC_HUB'}
                              {2: 'MES_HUB', 3: 'MES_HUB'}
                              {} 또는 None → 사전공정 처리 없음
        eqp_ch_mode     : 'AMAT' (eqp_id 그대로) / 'EBARA' (AB·CD 채널 분리)
        Days            : DataLake 초기 로드 기간 (일)
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
            query_key      = _get_collection_query_key(info_df, pre_oper_config)

            print(f'\n[{key}] 처리 시작')

            try:
                # 1. merge DB 연결
                merge_coll_name  = f'MICO_Merge_df_{Lot_Code}_{Oper_Desc}_{Fab}'
                mongo_db         = mongodb_controller(_MERGE_URL, _MERGE_DB, merge_coll_name)
                merge_collection = MongoClient(_MERGE_URL)[_MERGE_DB][merge_coll_name]

                # 2. 초기 DataLake 로드
                _load_initial_lake(
                    mongo_db, Fab, Maker, Lot_Code, Oper_Code,
                    Pre_Oper_Code, Recipe_ID_List, Recipe_info, Days,
                    Product, oper_desc, eqp_ch_mode,
                )

                # 3. HUB 최신 데이터 업데이트
                hub_df = getdatahub(
                    Fab, Maker, Lot_Code, Oper_Code,
                    Pre_Oper_Code, Recipe_ID_List, Recipe_info, Oper_Desc,
                )
                if not hub_df.empty:
                    hub_df = _prepare_merge_df(hub_df, Product, oper_desc, Fab, Lot_Code, eqp_ch_mode)
                    _push_with_index(mongo_db, merge_collection, hub_df, c, f'{Fab} {Lot_Code} {Oper_Desc}')

                print(f'  merge 완료 ({time.time() - start_time:.1f}s)')

                # 4-5. 사전공정 처리 (Pre_Oper 2→3→4 순)
                if pre_oper_config:
                    collection = _setup_pre_thk_db(Lot_Code, oper_desc, Fab)
                    for i, data_source in pre_oper_config.items():
                        _process_pre_oper(
                            collection, info_df, i, data_source,
                            Lot_Code, Fab, Data_lv, query_key,
                        )

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
