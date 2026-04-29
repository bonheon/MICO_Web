import os, sys
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
from day.auth.sdk import logon
from day.commc.cube import Cube_Connector
import traceback


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
                    Get_data.Cube_Msg(Lot_Code, oper_desc, Module_Name, e, tb)

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
                    Get_data.Cube_Msg(Lot_Code, oper_desc, Module_Name, e, tb)

except Exception as e:
    tb = traceback.format_exc()
    Get_Data.Cube_Msg(Family, oper_desc, Module_Name, e, tb)
