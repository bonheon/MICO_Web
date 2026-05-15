"""
DRAM M1 CU CMP — algorithm_source 파이프라인 테스트 러너
=========================================================
실행 위치: algorithm_source/
  python3 test_dram_m1cu_source.py

algorithm_new/test_dram_m1cu.py 와 동일한 merge_df(CSV)로 돌려
두 코드베이스 결과를 비교하기 위한 러너.

소스 코드 버그 (수정 없이 우회):
  - Module_Get_Merge: 'Oper_Desc' → 'oper_desc' (소문자) NameError
  - DRAM_M1_CU_CMP_Module.py: 'Get_Data' → 'Get_data' NameError
  → 파이프라인 스텝을 직접 호출하여 우회

Mock 대상:
  - MongoClient      : 빈 컬렉션 반환
  - Removal_getdata  : CSV merge_df 기반 VM=0 처리 (MongoDB 우회)
  - Offset_getdata   : 가상 B1/B0 삽입 (MongoDB RR 테이블 우회)
  - offset_getdata   : Offset_getdata 소문자 alias (소스 코드 버그 fix)
"""

import sys
import os
from pathlib import Path
from unittest.mock import MagicMock
import pandas as pd
import traceback as _tb

# ── sys.path: algorithm_source/ 를 최상위로 ──────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

# ────────────────────────────────────────────────────────────────────────
# 1. MongoClient 전역 Mock (pymongo 임포트 전에 교체)
# ────────────────────────────────────────────────────────────────────────
import pymongo as _pymongo

_mock_collection = MagicMock()
_mock_collection.find.return_value = iter([])
_mock_collection.list_collection_names.return_value = []

_mock_db = MagicMock()
_mock_db.__getitem__.return_value = _mock_collection
_mock_db.list_collection_names.return_value = []

_mock_mongo_client = MagicMock()
_mock_mongo_client.__getitem__.return_value = _mock_db
_mock_mongo_client.close.return_value = None

_pymongo.MongoClient = MagicMock(return_value=_mock_mongo_client)

# ────────────────────────────────────────────────────────────────────────
# 2. Common 모듈 임포트
# ────────────────────────────────────────────────────────────────────────
import Common.REMOVAL_RATE as _rr_mod
import Common.OFFSET as _offset_mod
from Common.Get_Data import Get_data
from Common.Module import Module_Get

# ────────────────────────────────────────────────────────────────────────
# 3. Removal_getdata Mock — algorithm_new 의 Excel 캐시와 동일한 로직으로 로드
#    (MongoDB Pre_Thk 대신 pre_thk_cache/*.xlsx 사용)
# ────────────────────────────────────────────────────────────────────────
def _mock_removal_getdata(merge_df, fab, lot_code, oper_code, pre_oper_code,
                           recipe_id, oper_desc, recipe_info, mico_info_key,
                           ai_studio_url=None):
    from pathlib import Path

    cache_dir  = Path(__file__).parents[1] / 'algorithm_new' / 'pre_thk_cache'
    cache_file = cache_dir / f'{lot_code}_{oper_desc.replace(" ", "_")}_{fab}.xlsx'

    merge_df_rr = merge_df.copy()
    # algorithm_source 는 request_dtts 컬럼이 없으므로 rename 조건부 적용
    merge_df_rr.rename(columns={'pre_oper_time': 'Pre_Oper_Date', 'request_dtts': 'Date'}, inplace=True)
    merge_df_rr['Pre_Oper_Date'] = pd.to_datetime(merge_df_rr['Pre_Oper_Date'], errors='coerce')
    merge_df_rr = merge_df_rr.sort_values('Pre_Oper_Date', ascending=True)

    if cache_file.exists():
        Pre_Thk_Table = pd.read_excel(cache_file, parse_dates=['pre_oper_time'])
        Pre_Thk_Table.rename(columns={'pre_oper_time': 'Pre_Oper_Date'}, inplace=True)
        Pre_Thk_Table['Pre_Oper_Date'] = pd.to_datetime(Pre_Thk_Table['Pre_Oper_Date'])

        for Thk_key in Pre_Thk_Table['THK_Para'].unique():
            temp_pre = Pre_Thk_Table[Pre_Thk_Table['THK_Para'] == Thk_key].drop(
                columns=[c for c in ['Date', 'THK_Para', 'Oper_Code'] if c in Pre_Thk_Table.columns]
            ).sort_values('Pre_Oper_Date')
            temp_pre = temp_pre.rename(columns={'Pre_Thk': Thk_key + '_VM', 'Count': Thk_key + '_Count'})

            cols_drop = [c for c in merge_df_rr.columns if c.endswith('_x') or c.endswith('_y')]
            merge_df_rr = merge_df_rr.drop(columns=cols_drop)
            merge_df_rr = pd.merge_asof(merge_df_rr, temp_pre, on='Pre_Oper_Date', by=['pre_eq_ch'])
            merge_df_rr.drop_duplicates(subset=['substrate_id'], inplace=True)

        print(f'    [mock] Removal_getdata: Excel 캐시 로드 ({cache_file.name})')
        vm_col = list(mico_info_key['Thk_Para'].unique())[0] + '_VM'
        print(f'    [mock] {vm_col} 매칭: {merge_df_rr[vm_col].notna().sum()}/{len(merge_df_rr)}')
    else:
        for thk_key in mico_info_key['Thk_Para'].unique():
            merge_df_rr[f'{thk_key}_VM'] = 0.0
        print(f'    [mock] Excel 캐시 없음 → VM=0.0')

    return merge_df_rr

_rr_mod.Removal_Rate_Get.Removal_getdata = staticmethod(_mock_removal_getdata)

# ────────────────────────────────────────────────────────────────────────
# 4. Offset_getdata Mock (source 함수명: Offset_getdata, 대문자 O)
#    MongoDB RR 테이블 조회 대신 가상 B1/B0 삽입
#    + 소문자 alias (Module.py 버그: offset_getdata 호출) 패치
# ────────────────────────────────────────────────────────────────────────
def _mock_offset_getdata(merge_df, Family, Fab, Lot_Code, Oper_Desc, APC_Para_List):
    merge_df_out = merge_df.copy()
    for para in APC_Para_List:
        merge_df_out[f'{para}_B1'] = 0.80
        merge_df_out[f'{para}_B0'] = 5.00
    print(f'    [mock] Offset_getdata: 가상 B1=0.80 / B0=5.00 삽입 for {list(APC_Para_List)}')
    return merge_df_out

_offset_mod.OFFSET_Get.Offset_getdata = staticmethod(_mock_offset_getdata)
# 소문자 alias — Common/Module.py 가 offset_getdata(소문자)로 호출하는 버그 수정
_offset_mod.OFFSET_Get.offset_getdata = staticmethod(_mock_offset_getdata)


# ────────────────────────────────────────────────────────────────────────
# 5. 파이프라인 직접 실행
#    (DRAM_M1_CU_CMP_Module.py 는 소스 버그가 있어 직접 호출)
# ────────────────────────────────────────────────────────────────────────
def run(Family, oper_desc, pol_type):
    print('#' * 60)
    print(f'  algorithm_source 학습 시작: Family={Family} | Oper_Desc={oper_desc}')
    print('#' * 60)

    mico_info_table = Get_data.baseinfoGetData(Family=Family, oper_desc=oper_desc)
    mico_info_table['Group_Name'] = mico_info_table['Group_Name'].fillna('not_group')
    mico_info_table['for_key_list'] = (
        mico_info_table['Lot_Code'] + '_' +
        mico_info_table['Oper_Code'] + '_' +
        mico_info_table['Fab']
    )

    group_name_list = mico_info_table['Group_Name'].unique()

    for group_name in group_name_list:

        if group_name == 'not_group':

            for_key_list = mico_info_table[
                mico_info_table['Group_Name'] == group_name
            ]['for_key_list'].unique()

            print(f'  처리 키 목록 ({len(for_key_list)}개):')
            for k in for_key_list:
                print(f'    - {k}  (단독)')

            for key in for_key_list:
                Lot_Code = key.split('_')[0]
                Oper_Code = key.split('_')[1]
                Fab = key.split('_')[2]

                mico_info_key = mico_info_table[
                    mico_info_table['for_key_list'] == key
                ].copy()

                print(f'\n[처리] {key}')
                merge_df = Get_data.MongoDB_GetData(Family, Fab, Lot_Code, oper_desc)
                print(f'    [데이터 조회] {Fab} | {Lot_Code} | {oper_desc} ... {len(merge_df)}행')
                merge_df = merge_df[merge_df['operation_id'] == Oper_Code].copy()
                print(f'    Oper 필터 후: {len(merge_df)}행')

                print('\n' + '=' * 60)
                print(f'  파이프라인 시작: {Fab} | {Lot_Code} | {oper_desc}')
                print('=' * 60)

                # Step 1: Pre_Thk_VM
                print(f'\n  [Pre_Thk_VM] {Fab} | {Lot_Code} | {oper_desc} 시작')
                try:
                    Module_Get.Module_Get_Pre_VM(Lot_Code, oper_desc, merge_df, Fab, pol_type, mico_info_key)
                    print(f'  [Pre_Thk_VM] {Fab} | {Lot_Code} | {oper_desc} 완료')
                except Exception as e:
                    print(f'  [Pre_Thk_VM] 오류: {e}')
                    print(_tb.format_exc())

                # Step 2: Removal Rate
                print(f'\n  [Removal Rate] {Fab} | {Lot_Code} | {oper_desc} 시작')
                try:
                    Module_Get.Module_Get_RR(merge_df, Lot_Code, oper_desc, pol_type, Fab, mico_info_key)
                    print(f'  [Removal Rate] {Fab} | {Lot_Code} | {oper_desc} 완료')
                except Exception as e:
                    print(f'  [Removal Rate] 오류: {e}')
                    print(_tb.format_exc())

                # Step 3: Offset
                print(f'\n  [Offset] {Fab} | {Lot_Code} | {oper_desc} 시작')
                try:
                    Module_Get.Module_Get_Offset(Lot_Code, oper_desc, merge_df, pol_type, Fab, mico_info_key)
                    print(f'  [Offset] {Fab} | {Lot_Code} | {oper_desc} 완료')
                except Exception as e:
                    print(f'  [Offset] 오류: {e}')
                    print(_tb.format_exc())

                # Step 4: Alarm
                print(f'\n  [Alarm 점검] {Fab} | {Lot_Code} | {oper_desc} 시작')
                try:
                    Module_Get.Module_Alarm(mico_info_key)
                    print(f'  [Alarm 점검] {Fab} | {Lot_Code} | {oper_desc} 완료')
                except Exception as e:
                    print(f'  [Alarm 점검] 오류: {e}')

                print('\n' + '=' * 60)
                print(f'  파이프라인 완료: {Fab} | {Lot_Code} | {oper_desc}')
                print('=' * 60)

        else:
            # 그룹 처리 (현재 테스트 대상 아님)
            print(f'  [GROUP] {group_name} 처리 (테스트 생략)')

    print('\n' + '#' * 60)
    print(f'  algorithm_source 학습 완료: Family={Family} | Oper_Desc={oper_desc}')
    print('#' * 60)


if __name__ == '__main__':
    run(Family='DRAM', oper_desc='M1 CU CMP', pol_type=3)
