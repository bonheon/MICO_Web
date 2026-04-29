import os, sys
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))))
from Common.Get_Data import Get_data
from Common.Module import Module_Get
import pandas as pd
import traceback

MODULE_NAME = 'Module'
FAMILY      = 'DRAM'
OPER_DESC   = 'M1 CU CMP'
POL_TYPE    = 3


def _parse_key(key):
    parts = key.split('_')
    return parts[0], parts[1], parts[2]  # lot_code, oper_code, fab


def _execute(lot_code, fab, merge_df, mico_info_key, use_group_rr=False):
    try:
        Module_Get.Module_Get_Pre_VM(lot_code, OPER_DESC, merge_df, fab, POL_TYPE, mico_info_key)
        if use_group_rr:
            Module_Get.Module_Get_RR_Group(merge_df, lot_code, OPER_DESC, POL_TYPE, fab, mico_info_key)
        else:
            Module_Get.Module_Get_RR(merge_df, lot_code, OPER_DESC, POL_TYPE, fab, mico_info_key)
        Module_Get.Module_Get_Offset(lot_code, OPER_DESC, merge_df, POL_TYPE, fab, mico_info_key)
        Module_Get.Module_Alarm(mico_info_key)
    except Exception as e:
        tb = traceback.format_exc()
        Get_data.Cube_Msg(lot_code, OPER_DESC, MODULE_NAME, e, tb)


def _run_no_group(mico_info_table, for_key_list):
    for key in for_key_list:
        lot_code, oper_code, fab = _parse_key(key)
        mico_info_key = mico_info_table[mico_info_table['for_key_list'] == key].copy()

        merge_df = Module_Get.Module_Get_Merge(fab, lot_code, OPER_DESC, mico_info_key)
        merge_df = merge_df[merge_df['operation_id'] == oper_code].copy()

        _execute(lot_code, fab, merge_df, mico_info_key)


def _run_group(mico_info_table, for_key_list, group_name):
    keys = []
    merge_df = pd.DataFrame()

    for key in for_key_list:
        lot_code, oper_code, fab = _parse_key(key)
        mico_info_key = mico_info_table[mico_info_table['for_key_list'] == key].copy()
        keys.append((lot_code, oper_code, fab, mico_info_key))

        temp = Module_Get.Module_Get_Merge(fab, lot_code, OPER_DESC, mico_info_key)
        if temp is not None and not temp.empty:
            merge_df = pd.concat([merge_df, temp])

    merge_df['Group_Name'] = group_name

    for lot_code, oper_code, fab, mico_info_key in keys:
        _execute(lot_code, fab, merge_df, mico_info_key, use_group_rr=True)


try:
    mico_info_table = Get_data.baseinfoGetData(Family=FAMILY, oper_desc=OPER_DESC)
    mico_info_table['Group_Name'] = mico_info_table['Group_Name'].fillna('not_group')
    mico_info_table['for_key_list'] = (
        mico_info_table['Lot_Code'] + '_' +
        mico_info_table['Oper_Code'] + '_' +
        mico_info_table['Fab']
    )

    for group_name in mico_info_table['Group_Name'].unique():
        for_key_list = mico_info_table[mico_info_table['Group_Name'] == group_name]['for_key_list'].unique()

        if group_name == 'not_group':
            _run_no_group(mico_info_table, for_key_list)
        else:
            _run_group(mico_info_table, for_key_list, group_name)

except Exception as e:
    tb = traceback.format_exc()
    Get_data.Cube_Msg(FAMILY, OPER_DESC, MODULE_NAME, e, tb)
