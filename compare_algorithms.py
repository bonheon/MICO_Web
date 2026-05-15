"""
algorithm_new vs algorithm_source 수치 비교 스크립트
======================================================
python3 compare_algorithms.py
"""

import sys
import os
from pathlib import Path
from unittest.mock import MagicMock
import pandas as pd
import numpy as np

MICO_WEB = str(Path(__file__).parent)
CSV_PATH = str(Path(__file__).parent / 'algorithm_new' / 'merge_df_sample.csv')

# ── MongoClient Mock ──────────────────────────────────────────────────────
import pymongo as _pymongo
_mock_collection = MagicMock()
_mock_collection.find.return_value = iter([])
_mock_collection.list_collection_names.return_value = []
_mock_db = MagicMock()
_mock_db.__getitem__.return_value = _mock_collection
_mock_db.list_collection_names.return_value = []
_mock_client = MagicMock()
_mock_client.__getitem__.return_value = _mock_db
_mock_client.close.return_value = None
_pymongo.MongoClient = MagicMock(return_value=_mock_client)

# ── 공통 입력 데이터 ──────────────────────────────────────────────────────
merge_df_raw = pd.read_csv(CSV_PATH, parse_dates=['Date', 'pre_oper_time'])
merge_df_raw['IDLE'] = merge_df_raw['IDLE'].fillna('')

OPER_CODE = 'V5077000E'
merge_df = merge_df_raw[merge_df_raw['operation_id'] == OPER_CODE].copy()

# mico_info_table 상수 (DB에서 읽어온 값과 동일)
mico_info = {
    'Family': 'DRAM', 'Lot_Code': 'LC', 'Oper_Code': 'V5077000E',
    'Oper_Desc': 'M1 CU CMP', 'Channel_ID': '500019173',
    'Fab': 'M10', 'Maker': 'AMAT', 'Recipe_ID': 'E2_M1CU_R12_TSV.CAS',
    'APC_Para': 'P3', 'Thk_Para': 'AMAT_POST_OCD_AVG',
    'Target': 1900.0, 'Post_Target': 1900.0, 'Pre_Target': 2350.0,
    'Pre_Thk_Period': 3, 'RR_Para': 'pad', 'Offset_Group': 'Y',
    'RR_Para_Max': None, 'RR_Period': None, 'Pad_Seperation': None,
    'Pre_Thk_Para_ITM': '', 'Pre_Oper_Code': 'A111111B',
    'Pre_Oper_Desc': None, 'Pre_Oper_Para': None,
    'Pre_Oper_Code2': '', 'Pre_Oper_Desc2': None, 'Pre_Oper_Para2': None,
    'Pre_Oper_Code3': '', 'Pre_Oper_Desc3': None, 'Pre_Oper_Para3': None,
    'Pre_Oper_Code4': '', 'Pre_Oper_Desc4': None, 'Pre_Oper_Para4': None,
    'RR_Weight': 30.0, 'RR_Count': 50.0, 'FB_Type': 'TIME',
    'RR_Alarm_Sigma': 10.0, 'Group_Name': 'not_group',
}
mico_info_key = pd.DataFrame([mico_info])

pol_type = 3

# ────────────────────────────────────────────────────────────────────────
# A. algorithm_new
# ────────────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent / 'algorithm_new'))

import Common.PRE_THK_VM as _new_prethk_mod
import Common.REMOVAL_RATE as _new_rr_mod

# Mock Pre_Thk VM load
def _mock_load_pre_thk_new(merge_df, mico_info_key, mongo_url, mongo_db):
    df = merge_df.copy()
    for k in mico_info_key['Thk_Para'].unique():
        df[f'{k}_VM'] = 0.0
    return df

_new_rr_mod.Removal_Rate_Get.load_pre_thk_data = staticmethod(_mock_load_pre_thk_new)

from Common.PRE_THK_VM import PRE_THK_VM_Get as NEW_PRE_THK
from Common.REMOVAL_RATE import Removal_Rate_Get as NEW_RR
from Common.Get_Data import Get_data as NEW_Get_data

def run_new_prethk(merge_df, mico_info_key, pol_type):
    """algorithm_new Pre_Thk_VM 계산 (detrend+MA 경로)"""
    from Common.PRE_THK_VM import PRE_THK_VM_Get
    Thk_Para = mico_info_key['Thk_Para'].unique()[0]
    APC_Para = mico_info_key['APC_Para'].unique()[0]
    Pre_Target = float(mico_info_key['Pre_Target'].unique()[0])
    Post_Target = float(mico_info_key['Target'].unique()[0])
    Pad_Para = NEW_Get_data.PadParaGet(APC_Para)
    APC_Para_merge = NEW_Get_data.APCParaGet(APC_Para, pol_type)
    Pre_Thk_Period = str(mico_info_key['Pre_Thk_Period'].unique()[0]) + 'D'

    merge_df_c = merge_df.copy()
    Thk_Para_13P = mico_info_key[mico_info_key['FB_Type'] == 'TIME']['Thk_Para'].unique()[0]
    merge_df_c['BIAS'] = 0.0

    pre_thk_df = PRE_THK_VM_Get.compute_detrend(merge_df_c, APC_Para_merge, Thk_Para, Pre_Target, Post_Target, Pad_Para)
    if pre_thk_df is None or pre_thk_df.empty:
        return pd.DataFrame()

    q1, q3 = pre_thk_df['Detrend_Thk'].quantile([0.25, 0.75])
    iqr = q3 - q1
    pre_thk_df = pre_thk_df[(pre_thk_df['Detrend_Thk'] <= q3 + 3*iqr) &
                              (pre_thk_df['Detrend_Thk'] >= q1 - 3*iqr)]

    pre_thk_df = PRE_THK_VM_Get.rolling_mean(pre_thk_df, Pre_Target, Thk_Para, Pre_Thk_Period)
    pre_thk_df['pre_oper_time'] = pd.to_datetime(pre_thk_df['pre_oper_time'])
    pre_thk_df['rank'] = pre_thk_df.groupby('pre_eq_ch')['pre_oper_time'].rank(method='first', ascending=False)
    result = pre_thk_df[pre_thk_df['rank'] == 1][['pre_eq_ch', 'Pre_Thk', 'Pre_Thk_Count']].copy()
    result = result.dropna().sort_values('pre_eq_ch').reset_index(drop=True)
    return result


def run_new_rr(merge_df, mico_info_key, pol_type):
    """algorithm_new Removal Rate 계산"""
    from Common.REMOVAL_RATE import Removal_Rate_Get
    # VM=0 추가
    merge_df_rr = merge_df.copy()
    merge_df_rr['AMAT_POST_OCD_AVG_VM'] = 0.0
    merge_df_rr['BIAS'] = 0.0

    key = mico_info_key.iloc[0]
    results = []
    rr_df = Removal_Rate_Get.compute_rr(merge_df_rr, key, pol_type,
                                          'AMAT_POST_OCD_AVG', '', None)
    return rr_df


# ────────────────────────────────────────────────────────────────────────
# B. algorithm_source
# ────────────────────────────────────────────────────────────────────────
# algorithm_new を sys.path から削除してから algorithm_source を挿入
sys.path = [p for p in sys.path if 'algorithm_new' not in p]
sys.path.insert(0, str(Path(__file__).parent / 'algorithm_source'))

# モジュールキャッシュをクリア (同名モジュールの衝突回避)
_new_mods = [k for k in sys.modules if k.startswith('Common.')]
for k in _new_mods:
    del sys.modules[k]

import Common.PRE_THK_VM as _src_prethk_mod
import Common.REMOVAL_RATE as _src_rr_mod
from Common.PRE_THK_VM import PRE_THK_VM_Get as SRC_PRE_THK
from Common.Get_Data import Get_data as SRC_Get_data


def run_src_prethk(merge_df, mico_info_key, pol_type):
    """algorithm_source Pre_Thk_VM 계산 (pre_thk_vm_detrend 경로)"""
    Thk_Para = mico_info_key['Thk_Para'].unique()[0]
    APC_Para = mico_info_key['APC_Para'].unique()[0]
    Pre_Target = float(mico_info_key['Pre_Target'].unique()[0])
    Post_Target = float(mico_info_key['Target'].unique()[0])
    Pad_Para = SRC_Get_data.PadParaGet(APC_Para)
    APC_Para_merge = SRC_Get_data.APCParaGet(APC_Para, pol_type)
    Pre_Thk_Period = str(mico_info_key['Pre_Thk_Period'].unique()[0]) + 'D'

    merge_df_c = merge_df.copy()
    merge_df_c['BIAS'] = 0.0

    pre_thk_df = SRC_PRE_THK.pre_thk_vm_detrend(merge_df_c, APC_Para_merge, Thk_Para, Pre_Target, Post_Target, Pad_Para)
    if pre_thk_df is None or pre_thk_df.empty:
        return pd.DataFrame()

    q1, q3 = pre_thk_df['Detrend_Thk'].quantile([0.25, 0.75])
    iqr = q3 - q1
    pre_thk_df = pre_thk_df[(pre_thk_df['Detrend_Thk'] <= q3 + 3*iqr) &
                              (pre_thk_df['Detrend_Thk'] >= q1 - 3*iqr)]

    pre_thk_df = SRC_PRE_THK.moving_avg_period(pre_thk_df, Pre_Target, Thk_Para, Pre_Thk_Period)
    pre_thk_df['pre_oper_time'] = pd.to_datetime(pre_thk_df['pre_oper_time'])
    pre_thk_df['rank'] = pre_thk_df.groupby('pre_eq_ch')['pre_oper_time'].rank(method='first', ascending=False)
    result = pre_thk_df[pre_thk_df['rank'] == 1][['pre_eq_ch', 'Pre_Thk', 'Pre_Thk_Count']].copy()
    result = result.dropna().sort_values('pre_eq_ch').reset_index(drop=True)
    return result


# ────────────────────────────────────────────────────────────────────────
# 비교 실행
# ────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':

    print('=' * 70)
    print('  Pre_Thk_VM 비교')
    print('=' * 70)

    new_prethk = run_new_prethk(merge_df, mico_info_key, pol_type)
    src_prethk = run_src_prethk(merge_df, mico_info_key, pol_type)

    print('\n[algorithm_new]')
    print(new_prethk.to_string(index=False))
    print(f'\n  총 {len(new_prethk)}개 pre_eq_ch')

    print('\n[algorithm_source]')
    print(src_prethk.to_string(index=False))
    print(f'\n  총 {len(src_prethk)}개 pre_eq_ch')

    # 공통 pre_eq_ch 비교
    common = set(new_prethk['pre_eq_ch']) & set(src_prethk['pre_eq_ch'])
    only_new = set(new_prethk['pre_eq_ch']) - set(src_prethk['pre_eq_ch'])
    only_src = set(src_prethk['pre_eq_ch']) - set(new_prethk['pre_eq_ch'])
    print(f'\n  공통 pre_eq_ch: {sorted(common)}')
    if only_new:
        print(f'  new 에만 존재:  {sorted(only_new)}')
    if only_src:
        print(f'  source 에만 존재: {sorted(only_src)}')

    if common:
        merged = pd.merge(
            new_prethk.rename(columns={'Pre_Thk': 'new_Pre_Thk', 'Pre_Thk_Count': 'new_Count'}),
            src_prethk.rename(columns={'Pre_Thk': 'src_Pre_Thk', 'Pre_Thk_Count': 'src_Count'}),
            on='pre_eq_ch'
        )
        merged['diff_Pre_Thk'] = merged['new_Pre_Thk'] - merged['src_Pre_Thk']
        print('\n  Pre_Thk 수치 비교 (공통):')
        print(merged[['pre_eq_ch', 'new_Pre_Thk', 'src_Pre_Thk', 'diff_Pre_Thk']].to_string(index=False))
        print(f'\n  최대 차이: {merged["diff_Pre_Thk"].abs().max():.4f} Å')
