# ── [TEST] Mock 패치 — MongoClient / day SDK ─────────────────────────────
# algorithm_source 원본 로직 비교용 테스트 러너.
# 실행: algorithm_source/Module/DRAM_M1_CU_CMP/ 에서
#   python3 DRAM_M1_CU_CMP_Module.py
# ─────────────────────────────────────────────────────────────────────────
import sys
from unittest.mock import MagicMock
from pathlib import Path

# pymongo.MongoClient → insert_many 도 출력하는 Mock
# LC_Logic 이 collection.insert_many(records) 로 저장하므로 여기서 캡처
import pymongo as _pymongo
import pandas as _pd

def _make_mock_collection(collection_name):
    col = MagicMock()
    col.find.return_value = iter([])
    col.list_collection_names.return_value = []

    def _insert_many(records):
        if records:
            df = _pd.DataFrame(records)
            print(f'    [MongoDB mock] insert_many → {collection_name}: {len(records)}건 저장')
            print(df[['eqp_id', 'recipe_id', 'IDLE', 'OFFSET', 'APC_Para']].to_string(index=False))

    col.insert_many.side_effect = _insert_many
    return col

_collection_cache = {}

def _get_mock_collection(name):
    if name not in _collection_cache:
        _collection_cache[name] = _make_mock_collection(name)
    return _collection_cache[name]

_mock_db = MagicMock()
_mock_db.__getitem__ = MagicMock(side_effect=_get_mock_collection)
_mock_db.list_collection_names.return_value = []
_mock_mongo_client = MagicMock()
_mock_mongo_client.__getitem__ = MagicMock(return_value=_mock_db)
_mock_mongo_client.close.return_value = None
_pymongo.MongoClient = MagicMock(return_value=_mock_mongo_client)

# day.auth.sdk / day.commc.cube → Mock (Cube 메시지 no-op)
_day_mock = MagicMock()
sys.modules.setdefault('day', _day_mock)
sys.modules.setdefault('day.auth', _day_mock)
sys.modules.setdefault('day.auth.sdk', _day_mock)
sys.modules.setdefault('day.commc', _day_mock)
sys.modules.setdefault('day.commc.cube', _day_mock)
# ─────────────────────────────────────────────────────────────────────────

import os
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))))
from datetime import datetime, timedelta, date
import pandas as pd
import numpy as np
from Common.Get_Data import Get_data
from pymongo import MongoClient
from Common.MongoDB_Control import mongodb_controller
from Common.PRE_THK_VM import PRE_THK_VM_Get
from Common.REMOVAL_RATE import Removal_Rate_Get
from Common.OFFSET import OFFSET_Get
from Common.Module import Module_Get
from sklearn.linear_model import LinearRegression
import traceback


# ── [TEST] Removal_getdata 패치 — Pre_Thk Excel 캐시 로드 ────────────────
# Module_Get_Pre_VM 이 저장한 algorithm_source/pre_thk_cache/*.xlsx 를 읽어
# merge_asof 로 _VM 컬럼을 부착한다. (MongoDB Pre_Thk 조회 대체)
_CACHE_DIR = Path(__file__).parents[2] / 'pre_thk_cache'

def _cache_removal_getdata(merge_df, fab, lot_code, oper_code, pre_oper_code,
                            recipe_id, oper_desc, recipe_info, mico_info_key,
                            ai_studio_url=None):
    cache_file = _CACHE_DIR / f'{lot_code}_{oper_desc.replace(" ", "_")}_{fab}.xlsx'

    merge_df_rr = merge_df.copy()
    merge_df_rr.rename(columns={'pre_oper_time': 'Pre_Oper_Date',
                                 'request_dtts':  'Date'}, inplace=True)
    merge_df_rr['Pre_Oper_Date'] = pd.to_datetime(merge_df_rr['Pre_Oper_Date'], errors='coerce')
    merge_df_rr = merge_df_rr.sort_values('Pre_Oper_Date', ascending=True)

    if cache_file.exists():
        Pre_Thk_Table = pd.read_excel(cache_file, parse_dates=['pre_oper_time'])
        Pre_Thk_Table.rename(columns={'pre_oper_time': 'Pre_Oper_Date'}, inplace=True)
        Pre_Thk_Table['Pre_Oper_Date'] = pd.to_datetime(Pre_Thk_Table['Pre_Oper_Date'])

        for Thk_key in Pre_Thk_Table['THK_Para'].unique():
            temp_pre = Pre_Thk_Table[Pre_Thk_Table['THK_Para'] == Thk_key].drop(
                columns=[c for c in ['Date', 'THK_Para', 'Oper_Code']
                         if c in Pre_Thk_Table.columns]
            ).sort_values('Pre_Oper_Date')
            temp_pre = temp_pre.rename(columns={'Pre_Thk': Thk_key + '_VM',
                                                 'Count':    Thk_key + '_Count'})
            cols_drop = [c for c in merge_df_rr.columns
                         if c.endswith('_x') or c.endswith('_y')]
            merge_df_rr = merge_df_rr.drop(columns=cols_drop)
            merge_df_rr = pd.merge_asof(merge_df_rr, temp_pre,
                                         on='Pre_Oper_Date', by=['pre_eq_ch'])
            merge_df_rr.drop_duplicates(subset=['substrate_id'], inplace=True)

        vm_col = list(mico_info_key['Thk_Para'].unique())[0] + '_VM'
        print(f'    [TEST] Removal_getdata: Excel 캐시 로드 ({cache_file.name})')
        print(f'    [TEST] {vm_col} 매칭: '
              f'{merge_df_rr[vm_col].notna().sum()}/{len(merge_df_rr)}')
    else:
        for thk_key in mico_info_key['Thk_Para'].unique():
            merge_df_rr[f'{thk_key}_VM'] = 0.0
        print(f'    [TEST] Excel 캐시 없음 → VM=0.0 ({cache_file.name})')

    return merge_df_rr

Removal_Rate_Get.Removal_getdata = staticmethod(_cache_removal_getdata)

# [TEST] offset_getdata 소문자 버그 수정 — Module.py 가 lowercase 로 호출
# (원본 소스 버그: OFFSET_Get.offset_getdata 는 정의되어 있지 않음)
OFFSET_Get.offset_getdata = OFFSET_Get.Offset_getdata
# ─────────────────────────────────────────────────────────────────────────


Module_Name = 'Module'
Family = 'DRAM'
oper_desc = 'M1 CU CMP'
pol_type = 3

try:
    mico_info_table = Get_data.baseinfoGetData(
        Family=Family,
        oper_desc=oper_desc
    )

    mico_info_table['Group_Name'] = mico_info_table['Group_Name'].fillna('not_group')

    mico_info_table['for_key_list'] = mico_info_table['Lot_Code'] + '_' + mico_info_table['Oper_Code'] + '_' + mico_info_table['Fab']
    group_name_list = mico_info_table['Group_Name'].unique()

    for group_name in group_name_list:

        if group_name == 'not_group':

            for_key_list = mico_info_table[mico_info_table['Group_Name'] == group_name]['for_key_list'].unique()

            for key in for_key_list:
                print(key)
                Lot_Code = key.split('_')[0]
                Oper_Code = key.split('_')[1]
                Fab = key.split('_')[2]

                mico_info_key = mico_info_table[mico_info_table['for_key_list'] == key].copy()

                merge_df = Module_Get.Module_Get_Merge(Fab, Lot_Code, oper_desc, mico_info_key)
                merge_df = merge_df[merge_df['operation_id'] == Oper_Code].copy()

                try:
                    Module_Get.Module_Get_Pre_VM(Lot_Code, oper_desc, merge_df, Fab, pol_type, mico_info_key)
                    Module_Get.Module_Get_RR(merge_df, Lot_Code, oper_desc, pol_type, Fab, mico_info_key)
                    Module_Get.Module_Get_Offset(Lot_Code, oper_desc, merge_df, pol_type, Fab, mico_info_key)
                    Module_Get.Module_Alarm(mico_info_key)

                except Exception as e:
                    tb = traceback.format_exc()
                    Get_data.Cube_Msg(Lot_Code, oper_desc, Module_Name, e, tb)  # [TEST] 원본 버그 수정: Get_Data → Get_data

        else:

            for_key_list = mico_info_table[mico_info_table['Group_Name'] == group_name]['for_key_list'].unique()

            merge_df = pd.DataFrame()
            key_info_list = []

            for key in for_key_list:
                Lot_Code = key.split('_')[0]
                Oper_Code = key.split('_')[1]
                Fab = key.split('_')[2]

                mico_info_key = mico_info_table[mico_info_table['for_key_list'] == key].copy()

                key_info_list.append({
                    'key': key,
                    'Lot_Code': Lot_Code,
                    'Oper_Code': Oper_Code,
                    'Fab': Fab,
                    'mico_info_key': mico_info_key
                })

                merge_df_temp = Module_Get.Module_Get_Merge(Fab, Lot_Code, oper_desc, mico_info_key)
                if merge_df_temp is not None and not merge_df_temp.empty:
                    merge_df = pd.concat([merge_df, merge_df_temp])

            merge_df['Group_Name'] = group_name

            for info in key_info_list:
                print(info)
                Lot_Code = info['Lot_Code']
                Oper_Code = info['Oper_Code']
                Fab = info['Fab']
                mico_info_key = info['mico_info_key']

                try:
                    Module_Get.Module_Get_Pre_VM(Lot_Code, oper_desc, merge_df, Fab, pol_type, mico_info_key)
                    Module_Get.Module_Get_RR_Group(merge_df, Lot_Code, oper_desc, pol_type, Fab, mico_info_key)
                    Module_Get.Module_Get_Offset(Lot_Code, oper_desc, merge_df, pol_type, Fab, mico_info_key)
                    Module_Get.Module_Alarm(mico_info_key)

                except Exception as e:
                    tb = traceback.format_exc()
                    Get_data.Cube_Msg(Lot_Code, oper_desc, Module_Name, e, tb)  # [TEST] 원본 버그 수정: Get_Data → Get_data

except Exception as e:
    tb = traceback.format_exc()
    Get_data.Cube_Msg(Family, oper_desc, Module_Name, e, tb)  # [TEST] 원본 버그 수정: Get_Data → Get_data
