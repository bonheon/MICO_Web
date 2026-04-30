import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parents[1]))
from Common.Get_Data import Get_data
from Common.MongoDB_Control import mongodb_controller, multi_uploader
from Common.PRE_THK_VM import PRE_THK_VM_Get
from Common.REMOVAL_RATE import Removal_Rate_Get
from Common.OFFSET import OFFSET_Get
from datetime import datetime, timedelta, date
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
import time
import traceback
from day.auth.sdk import logon
from day.commc.cube import Cube_Connector
from pymongo import MongoClient
import pytz

cube_bot_id = "C0000361"
cube_bot_token = "C00003610-dfd..."
c = Cube_Connector(cube_bot_id, cube_bot_token)

_MONGO_URL = 'mongodb://cncmico : ....'
_MONGO_DB  = 'mico-platform-mongodb'


def _setup_mongo(Lot_Code, Oper_Desc, Fab):
    collection = 'MICO_PRE_THK_' + Lot_Code + '_' + Oper_Desc + '_' + Fab + '_Period'
    return mongodb_controller(_MONGO_URL, _MONGO_DB, collection)


def _extract_latest(pre_thk_df_merge, cols):
    pre_thk_df_merge['pre_oper_time'] = pd.to_datetime(pre_thk_df_merge['pre_oper_time'])
    pre_thk_df_merge['rank'] = pre_thk_df_merge.groupby('pre_eq_ch')['pre_oper_time'].rank(method='first', ascending=False)
    pre_thk_df_recent = pre_thk_df_merge[pre_thk_df_merge['rank'] == 1].copy()
    pre_thk_table = pre_thk_df_recent[cols].copy()
    pre_thk_table.dropna(axis=0, inplace=True)
    return pre_thk_table


def _fit_linear(pre_thk_df_merge, pre2_df, col, left_on=None, right_on=None):
    if left_on and right_on:
        merged = pd.merge(pre_thk_df_merge, pre2_df, left_on=left_on, right_on=right_on, how='left')
    else:
        merged = pd.merge(pre_thk_df_merge, pre2_df, on='substrate_id', how='left')
    linear_df = merged[[col, 'Detrend_Thk']].copy()
    linear_df.replace('-', np.nan, inplace=True)
    linear_df.dropna(axis=0, inplace=True)
    lr = LinearRegression()
    lr.fit(linear_df[[col]], linear_df[['Detrend_Thk']])
    return round(lr.coef_[0][0], 3), round(lr.intercept_[0], 3)


class Module_Get:

    def Module_Get_Merge(mico_info_key):

        Fab      = mico_info_key['Fab'].unique()[0]
        Lot_Code = mico_info_key['Lot_Code'].unique()[0]
        Oper_Desc = mico_info_key['Oper_Desc'].unique()[0]

        try:
            Family        = mico_info_key['Family'].unique()[0]
            Fab_List      = mico_info_key['Fab'].unique()
            Oper_Code     = mico_info_key['Oper_Code'].unique()[0]
            Pre_Oper_Code = mico_info_key['Pre_Oper_Code'].unique()[0]
            Pre_Oper_Code2 = mico_info_key['Pre_Oper_Code2'].unique()[0]
            Pre_Oper_Para2 = mico_info_key['Pre_Oper_Para2'].unique()[0]
            Recipe_ID     = mico_info_key['Recipe_ID'].unique()[0]
            Recipe_ID_List = tuple(mico_info_key['Recipe_ID'].unique())
            APC_Para_List = mico_info_key['APC_Para'].unique()
            Thk_Para_List = mico_info_key['Thk_Para'].unique()
            Pre_Target    = mico_info_key['Pre_Target'].unique()[0]
            if pd.notna(Pre_Target):
                Pre_Target = float(Pre_Target)
            Offset_Group  = mico_info_key['Offset_Group'].unique()
            Recipe_info   = Recipe_ID.split('_')[0] + '_' + Recipe_ID.split('_')[1]

            merge_df = Get_data.MongoDB_GetData(Family, Fab, Lot_Code, Oper_Desc)

            return merge_df

        except Exception as e:
            tb = traceback.format_exc()
            c.sendMsg('', '506204179', f'{Fab} {Lot_Code} {Oper_Desc} Module Merge Failed : {e}, {tb}')

    def Module_Get_Pre_VM(merge_df, mico_info_key, pol_type):

        Fab       = mico_info_key['Fab'].unique()[0]
        Lot_Code  = mico_info_key['Lot_Code'].unique()[0]
        Oper_Desc = mico_info_key['Oper_Desc'].unique()[0]

        mongo = _setup_mongo(Lot_Code, Oper_Desc, Fab)

        try:
            Family         = mico_info_key['Family'].unique()[0]
            Fab_List       = mico_info_key['Fab'].unique()
            Oper_Code      = mico_info_key['Oper_Code'].unique()[0]
            Pre_Oper_Code  = mico_info_key['Pre_Oper_Code'].unique()[0]
            Pre_Oper_Code2 = mico_info_key['Pre_Oper_Code2'].unique()[0]
            Pre_Oper_Para2 = tuple(mico_info_key['Pre_Oper_Para2'].unique())
            Recipe_ID      = mico_info_key['Recipe_ID'].unique()[0]
            Recipe_ID_List = tuple(mico_info_key['Recipe_ID'].unique())
            APC_Para_List  = mico_info_key['APC_Para'].unique()
            Thk_Para_List  = mico_info_key['Thk_Para'].unique()
            Thk_Para_13P   = mico_info_key[mico_info_key['FB_Type'] == 'TIME']['Thk_Para'].unique()[0]
            Pre_Target     = float(mico_info_key['Pre_Target'].unique()[0])
            Target_13P     = float(mico_info_key[mico_info_key['FB_Type'] == 'TIME']['Target'].unique()[0])
            Offset_Group   = mico_info_key['Offset_Group'].unique()
            Recipe_info    = Recipe_ID.split('_')[0] + '_' + Recipe_ID.split('_')[1]
            Pre_Thk_Period = str(mico_info_key['Pre_Thk_Period'].unique()[0]) + 'D'
            Pre_Oper_Code3 = mico_info_key['Pre_Oper_Code3'].unique()[0]
            Pre_Oper_Desc3 = mico_info_key['Pre_Oper_Desc3'].unique()[0]
            Pre_Oper_Para3_APC_List = tuple(mico_info_key['Pre_Oper_Para3'].unique())

            today = datetime.now()

            for Thk_Para in Thk_Para_List:

                search_key = mico_info_key[(mico_info_key['Thk_Para'] == Thk_Para)].copy()
                pre_thk_df_merge = pd.DataFrame()

                for i in range(len(search_key)):

                    key = search_key.iloc[i, :]

                    APC_Para       = key['APC_Para']
                    Recipe_ID      = key['Recipe_ID']
                    Pre_Target     = float(key['Pre_Target'])
                    Post_Target    = float(key['Target'])
                    Pre_Thk_Para   = key['Pre_Thk_Para_ITM']
                    Pre_Oper_Code2 = key['Pre_Oper_Code2']
                    Pre_Oper_Desc2 = key['Pre_Oper_Desc2']
                    Pre_Oper_Para2 = key['Pre_Oper_Para2']
                    Pre_Oper_Desc3 = key['Pre_Oper_Desc3']
                    Pre_Oper_Para3 = key['Pre_Oper_Para3']
                    Pre_Oper_Desc4 = key['Pre_Oper_Desc4']
                    Pre_Oper_Para4 = key['Pre_Oper_Para4']

                    Target_13P = mico_info_key[(mico_info_key['Recipe_ID'] == Recipe_ID) & (mico_info_key['FB_Type'] == 'TIME')]['Target'].unique()[0]

                    merge_df['BIAS'] = (merge_df[Thk_Para] - merge_df[Thk_Para_13P]) - (Post_Target - Target_13P)

                    Pad_Para      = Get_data.PadParaGet(APC_Para)
                    APC_Para_merge = Get_data.APCParaGet(APC_Para, pol_type)

                    pre_thk_df = PRE_THK_VM_Get.pre_thk_vm_detrend(merge_df, APC_Para_merge, Thk_Para, Pre_Target, Post_Target, Pad_Para)
                    pre_thk_df['THK_Para'] = Thk_Para

                    if pre_thk_df_merge.empty:
                        pre_thk_df_merge = pre_thk_df
                    else:
                        pre_thk_df_merge = pd.concat([pre_thk_df_merge, pre_thk_df])

                level_1q = pre_thk_df_merge['Detrend_Thk'].quantile(0.25)
                level_3q = pre_thk_df_merge['Detrend_Thk'].quantile(0.75)
                IQR      = level_3q - level_1q
                sigma    = 3
                pre_thk_df_merge = pre_thk_df_merge[
                    (pre_thk_df_merge['Detrend_Thk'] <= level_3q + (IQR * sigma)) &
                    (pre_thk_df_merge['Detrend_Thk'] >= level_1q - (IQR * sigma))
                ].copy()

                pre_thk_df_merge = PRE_THK_VM_Get.moving_avg_period(pre_thk_df_merge, Pre_Target, Thk_Para, Pre_Thk_Period)

                pre_thk_table = _extract_latest(pre_thk_df_merge, ['pre_oper_time', 'pre_eq_ch', 'Pre_Thk', 'Pre_Thk_Count', 'THK_Para'])

                if (type(Pre_Oper_Code2) == str) & (Pre_Oper_Code2 != ''):
                    client          = MongoClient(_MONGO_URL)
                    db_name         = client[_MONGO_DB]
                    collection_name = db_name['MICO_PRE_THK_INFO_' + Lot_Code + '_' + Oper_Desc + '_' + Fab]
                    raw_data        = collection_name.find({}, {'_id': 0})
                    pre2_df         = pd.DataFrame(raw_data)
                    pre2_df.rename(columns={'samp_matl_id': 'substrate_id'}, inplace=True)
                    pre2_df.drop_duplicates(subset=['substrate_id'], inplace=True)
                else:
                    pre2_df = None

                if (pre2_df is not None) & (Pre_Oper_Para2 != ''):
                    left_on  = 'lot_id'       if Oper_Desc == 'SOURCE OX CMP' else None
                    right_on = 'alias_lot_id' if Oper_Desc == 'SOURCE OX CMP' else None
                    b1, b0 = _fit_linear(pre_thk_df_merge, pre2_df, Pre_Oper_Desc2 + '.' + Pre_Oper_Para2, left_on=left_on, right_on=right_on)
                    pre_thk_table['PRE_OPER2_b1'] = b1
                    pre_thk_table['PRE_OPER2_b0'] = b0

                if (pre2_df is not None) & (Pre_Oper_Para3 != ''):
                    b1, b0 = _fit_linear(pre_thk_df_merge, pre2_df, Pre_Oper_Desc3 + '.' + Pre_Oper_Para3)
                    pre_thk_table['PRE_OPER3_b1'] = b1
                    pre_thk_table['PRE_OPER3_b0'] = b0

                if (pre2_df is not None) & (Pre_Oper_Para4 != ''):
                    b1, b0 = _fit_linear(pre_thk_df_merge, pre2_df, Pre_Oper_Desc4 + '.' + Pre_Oper_Para4)
                    pre_thk_table['PRE_OPER4_b1'] = b1
                    pre_thk_table['PRE_OPER4_b0'] = b0

                pre_thk_table['Date'] = pd.to_datetime(today)
                pre_thk_table.rename(columns={'Pre_Thk_Count': 'Count'}, inplace=True)
                pre_thk_table['Oper_Code'] = Oper_Code

                mongo.push_df(pre_thk_table)

        except Exception as e:
            tb = traceback.format_exc()
            c.sendMsg('', '506204179', f'{Fab} {Lot_Code} {Oper_Desc} Module PRE VM Failed : {e}, {tb}')

    def Module_Get_Pre_VM_ITM(merge_df, mico_info_key, pol_type):

        Fab       = mico_info_key['Fab'].unique()[0]
        Lot_Code  = mico_info_key['Lot_Code'].unique()[0]
        Oper_Desc = mico_info_key['Oper_Desc'].unique()[0]

        mongo = _setup_mongo(Lot_Code, Oper_Desc, Fab)

        try:
            Family             = mico_info_key['Family'].unique()[0]
            Oper_Code          = mico_info_key['Oper_Code'].unique()[0]
            Pre_Oper_Code      = mico_info_key['Pre_Oper_Code'].unique()[0]
            Pre_Oper_Code2     = mico_info_key['Pre_Oper_Code2'].unique()[0]
            Recipe_ID          = mico_info_key['Recipe_ID'].unique()[0]
            Recipe_ID_List     = tuple(mico_info_key['Recipe_ID'].unique())
            Thk_Para_List      = mico_info_key['Thk_Para'].unique()
            Pre_Thk_Para_list  = mico_info_key['Pre_Thk_Para_ITM'].unique()
            Pre_Thk_Para_13P   = mico_info_key[mico_info_key['FB_Type'] == 'TIME']['Pre_Thk_Para_ITM'].unique()[0]
            Thk_Para_13P       = mico_info_key[mico_info_key['FB_Type'] == 'TIME']['Thk_Para'].unique()[0]
            Pre_Target         = float(mico_info_key['Pre_Target'].unique()[0])
            Pre_Thk_Period     = str(mico_info_key['Pre_Thk_Period'].unique()[0]) + 'D'

            today = datetime.now()

            for Pre_Thk_Para in Pre_Thk_Para_list:

                Pre_Target = float(mico_info_key[mico_info_key['Pre_Thk_Para_ITM'] == Pre_Thk_Para]['Pre_Target'].unique()[0])

                merge_df['BIAS'] = merge_df[Pre_Thk_Para] - merge_df[Pre_Thk_Para_13P] - (merge_df[Pre_Thk_Para].mean() - merge_df[Pre_Thk_Para_13P].mean())

                pre_thk_df_merge = PRE_THK_VM_Get.pre_thk_itm_moving_avg(merge_df, Pre_Target, Pre_Thk_Para, Pre_Thk_Period)

                pre_thk_table = _extract_latest(pre_thk_df_merge, ['pre_oper_time', 'pre_eq_ch', 'Pre_Thk', 'Pre_Thk_Count'])

                for i in range(len(pre_thk_table)):
                    temp_row = pre_thk_table.iloc[i, :].copy()
                    mongo.insert_row({
                        'Date':         today,
                        'pre_oper_time': temp_row['pre_oper_time'],
                        'pre_eq_ch':    temp_row['pre_eq_ch'],
                        'Pre_Thk':      temp_row['Pre_Thk'],
                        'Count':        temp_row['Pre_Thk_Count'],
                        'Pre_THK_Para': Pre_Thk_Para
                    })

            print('PRE THK VM Completed!!!')

        except Exception as e:
            tb = traceback.format_exc()
            c.sendMsg('', '506204179', f'{Fab} {Lot_Code} {Oper_Desc} Module PRE VM ITM Failed : {e}, {tb}')

    def Module_Get_RR(merge_df, mico_info_key, pol_type, ai_studio_url=None, RR_Alarm=None):

        Fab       = mico_info_key['Fab'].unique()[0]
        Lot_Code  = mico_info_key['Lot_Code'].unique()[0]
        Oper_Desc = mico_info_key['Oper_Desc'].unique()[0]

        try:
            Family         = mico_info_key['Family'].unique()[0]
            Fab_List       = mico_info_key['Fab'].unique()
            Maker          = mico_info_key['Maker'].unique()[0]
            Oper_Code      = mico_info_key['Oper_Code'].unique()[0]
            Pre_Oper_Code  = mico_info_key['Pre_Oper_Code'].unique()[0]
            Pre_Oper_Code2 = mico_info_key['Pre_Oper_Code2'].unique()[0]
            Recipe_ID      = mico_info_key['Recipe_ID'].unique()[0]
            Recipe_ID_List = tuple(mico_info_key['Recipe_ID'].unique())
            APC_Para_List  = mico_info_key['APC_Para'].unique()
            Thk_Para_List  = mico_info_key['Thk_Para'].unique()
            Thk_Para_13P   = mico_info_key[mico_info_key['FB_Type'] == 'TIME']['Thk_Para'].unique()[0]
            Pre_Target     = mico_info_key['Pre_Target'].unique()[0]
            if Pre_Target is not None:
                Pre_Target = float(Pre_Target)
            Offset_Group = mico_info_key['Offset_Group'].unique()
            Recipe_info  = Recipe_ID.split('_')[0] + '_' + Recipe_ID.split('_')[1]

            today = datetime.now()

            if Pre_Oper_Code == '':
                merge_df_rr = merge_df.copy()
                for Thk_key in Thk_Para_List:
                    merge_df_rr[Thk_key + '_VM'] = 0
            else:
                merge_df_rr = Removal_Rate_Get.Removal_getdata(merge_df, Fab, Lot_Code, Oper_Code, Pre_Oper_Code, Recipe_ID, Oper_Desc, Recipe_info, mico_info_key, ai_studio_url=ai_studio_url)

            if Maker == 'AMAT':
                eqp_id_list = tuple(merge_df_rr['eqp_id'].unique())
            elif Maker == 'EBARA':
                merge_df_rr['CH'] = merge_df_rr['recipe_id'].apply(lambda x: 'AB' if 'AB' in x else 'CD')
                merge_df_rr['eqp_id_ch'] = merge_df_rr['eqp_id'] + '_' + merge_df_rr['CH']
                eqp_id_list = tuple(merge_df_rr['eqp_id_ch'].unique())
            elif Maker == 'KCT':
                merge_df_rr['CH'] = merge_df_rr['recipe_id'].apply(lambda x: 'L' if '_L' in x else 'R')
                merge_df_rr['eqp_id_ch'] = merge_df_rr['eqp_id'] + '_' + merge_df_rr['CH']
                eqp_id_list = tuple(merge_df_rr['eqp_id_ch'].unique())

            recipe_id_list = tuple(merge_df_rr['recipe_id'].unique())
            EQPM_df = Get_data.EQPMGetData_HUB(Fab, eqp_id_list, recipe_id_list)
            EQPM_df = EQPM_df.sort_values(by=['EQP_ID', 'EVENT_TM']).reset_index(drop=True)

            def compute_rank(group):
                event_pm_index = group[group['EVENT_CD'].str.contains('PM')].index
                ranks = []
                current_rank = 0
                for idx in group.index:
                    if idx in event_pm_index:
                        current_rank = 0
                    else:
                        if group.loc[idx, 'EVENT_CD'] in ['EndLot', 'JobEnd']:
                            current_rank += 1
                    ranks.append(current_rank)
                return ranks

            EQPM_df['rank'] = EQPM_df.groupby('EQP_ID').apply(lambda x: pd.Series(compute_rank(x))).reset_index(level=0, drop=True).values.reshape(-1)
            EQPM_df['EVENT_TM'] = pd.to_datetime(EQPM_df['EVENT_TM'])

            for Thk_Para in Thk_Para_List:
                search_key = mico_info_key[
                    (mico_info_key['Thk_Para'] == Thk_Para) &
                    (mico_info_key['Fab'] == Fab)
                ]
                for i in range(len(search_key)):
                    key          = search_key.iloc[i, :]
                    Pre_Thk_Para = key['Pre_Thk_Para_ITM']
                    Post_Target  = float(key['Target'])
                    Recipe_ID    = key['Recipe_ID']
                    Target_13P   = mico_info_key[(mico_info_key['Recipe_ID'] == Recipe_ID) & (mico_info_key['FB_Type'] == 'TIME')]['Target'].unique()[0]

                    merge_df_rr['BIAS'] = merge_df_rr[Thk_Para] - merge_df_rr[Thk_Para_13P] - (Post_Target - Target_13P)

                    Removal_Rate_Get.Logic(merge_df_rr, key, pol_type, Thk_Para, Pre_Thk_Para, EQPM_df, Maker, RR_Alarm)

        except Exception as e:
            tb = traceback.format_exc()
            c.sendMsg('', '506204179', f'{Fab} {Lot_Code} {Oper_Desc} Module RR Failed : {e}, {tb}')

    def Module_Get_RR_Group(merge_df, mico_info_key, pol_type, ai_studio_url=None, RR_Alarm=None):

        Fab       = mico_info_key['Fab'].unique()[0]
        Lot_Code  = mico_info_key['Lot_Code'].unique()[0]
        Oper_Desc = mico_info_key['Oper_Desc'].unique()[0]

        try:
            Family         = mico_info_key['Family'].unique()[0]
            Fab_List       = mico_info_key['Fab'].unique()
            Maker          = mico_info_key['Maker'].unique()[0]
            Oper_Code      = mico_info_key['Oper_Code'].unique()[0]
            Pre_Oper_Code  = mico_info_key['Pre_Oper_Code'].unique()[0]
            Pre_Oper_Code2 = mico_info_key['Pre_Oper_Code2'].unique()[0]
            Recipe_ID      = mico_info_key['Recipe_ID'].unique()[0]
            Recipe_ID_List = tuple(mico_info_key['Recipe_ID'].unique())
            APC_Para_List  = mico_info_key['APC_Para'].unique()
            Thk_Para_List  = mico_info_key['Thk_Para'].unique()
            Thk_Para_13P   = mico_info_key[mico_info_key['FB_Type'] == 'TIME']['Thk_Para'].unique()[0]
            Pre_Target     = mico_info_key['Pre_Target'].unique()[0]
            if Pre_Target is not None:
                Pre_Target = float(Pre_Target)
            Offset_Group = mico_info_key['Offset_Group'].unique()
            Recipe_info  = Recipe_ID.split('_')[0] + '_' + Recipe_ID.split('_')[1]

            today = datetime.now()
            Lot_Code_List = merge_df['Lot_Code'].unique()

            if Pre_Oper_Code == '':
                merge_df_rr = merge_df.copy()
                for Thk_key in Thk_Para_List:
                    merge_df_rr[Thk_key + '_VM'] = 0
            else:
                merge_df_rr = pd.DataFrame()
                for lc in Lot_Code_List:
                    merge_df_filter = merge_df[merge_df['Lot_Code'] == lc].copy()
                    merge_df_temp   = Removal_Rate_Get.Removal_getdata(merge_df_filter, Fab, Lot_Code, Oper_Code, Pre_Oper_Code, Recipe_ID, Oper_Desc, Recipe_info, mico_info_key, ai_studio_url=ai_studio_url)
                    merge_df_rr     = pd.concat([merge_df_rr, merge_df_temp])

            if Maker == 'AMAT':
                eqp_id_list = tuple(merge_df_rr['eqp_id'].unique())
            elif Maker == 'EBARA':
                merge_df_rr['CH'] = merge_df_rr['recipe_id'].apply(lambda x: 'AB' if 'AB' in x else 'CD')
                merge_df_rr['eqp_id_ch'] = merge_df_rr['eqp_id'] + '_' + merge_df_rr['CH']
                eqp_id_list = tuple(merge_df_rr['eqp_id_ch'].unique())
            elif Maker == 'KCT':
                merge_df_rr['CH'] = merge_df_rr['recipe_id'].apply(lambda x: 'L' if '_L' in x else 'R')
                merge_df_rr['eqp_id_ch'] = merge_df_rr['eqp_id'] + '_' + merge_df_rr['CH']
                eqp_id_list = tuple(merge_df_rr['eqp_id_ch'].unique())

            recipe_id_list = tuple(merge_df_rr['recipe_id'].unique())
            EQPM_df = Get_data.EQPMGetData_HUB(Fab, eqp_id_list, recipe_id_list)
            EQPM_df = EQPM_df.sort_values(by=['EQP_ID', 'EVENT_TM']).reset_index(drop=True)

            def compute_rank(group):
                event_pm_index = group[group['EVENT_CD'].str.contains('PM')].index
                ranks = []
                current_rank = 0
                for idx in group.index:
                    if idx in event_pm_index:
                        current_rank = 0
                    else:
                        if group.loc[idx, 'EVENT_CD'] in ['EndLot', 'JobEnd']:
                            current_rank += 1
                    ranks.append(current_rank)
                return ranks

            EQPM_df['rank'] = EQPM_df.groupby('EQP_ID').apply(lambda x: pd.Series(compute_rank(x))).reset_index(level=0, drop=True).values.reshape(-1)
            EQPM_df['EVENT_TM'] = pd.to_datetime(EQPM_df['EVENT_TM'])

            search_key = mico_info_key[mico_info_key['Fab'] == Fab]
            for i in range(len(search_key)):
                key          = search_key.iloc[i, :]
                Thk_Para     = key['Thk_Para']
                Pre_Thk_Para = key['Pre_Thk_Para_ITM']
                Post_Target  = float(key['Target'])
                Recipe_ID    = key['Recipe_ID']
                Target_13P   = mico_info_key[(mico_info_key['Recipe_ID'] == Recipe_ID) & (mico_info_key['FB_Type'] == 'TIME')]['Target'].unique()[0]

                merge_df_rr['BIAS'] = merge_df_rr[Thk_Para] - merge_df_rr[Thk_Para_13P] - (Post_Target - Target_13P)

                Removal_Rate_Get.Logic(merge_df_rr, key, pol_type, Thk_Para, Pre_Thk_Para, EQPM_df, Maker, RR_Alarm)

        except Exception as e:
            tb = traceback.format_exc()
            c.sendMsg('', '506204179', f'{Fab} {Lot_Code} {Oper_Desc} Module RR Group Failed : {e}, {tb}')

    def Module_Get_Offset(merge_df, mico_info_key, pol_type):

        mico_info_key = mico_info_key[mico_info_key['FB_Type'] == 'TIME'].copy()

        Fab       = mico_info_key['Fab'].unique()[0]
        Lot_Code  = mico_info_key['Lot_Code'].unique()[0]
        Oper_Desc = mico_info_key['Oper_Desc'].unique()[0]

        try:
            Family        = mico_info_key['Family'].unique()[0]
            Fab_List      = mico_info_key['Fab'].unique()
            Oper_Code     = mico_info_key['Oper_Code'].unique()[0]
            Pre_Oper_Code = mico_info_key['Pre_Oper_Code'].unique()[0]
            Recipe_ID     = mico_info_key['Recipe_ID'].unique()[0]
            Recipe_ID_List = tuple(mico_info_key['Recipe_ID'].unique())
            APC_Para_List = mico_info_key['APC_Para'].unique()
            Thk_Para_List = mico_info_key['Thk_Para'].unique()
            Pre_Target    = mico_info_key['Pre_Target'].unique()[0]
            if Pre_Target is not None:
                Pre_Target = float(Pre_Target)
            Offset_Group = mico_info_key['Offset_Group'].unique()

            temp_df    = pd.DataFrame()
            search_key = mico_info_key[mico_info_key['Fab'] == Fab]

            merge_df = OFFSET_Get.offset_getdata(merge_df, Family, Fab, Lot_Code, Oper_Desc, APC_Para_List)

            for i in range(len(search_key)):
                key       = search_key.iloc[i, :]
                temp_data = OFFSET_Get.Logic(merge_df, key, pol_type, Fab)

                if temp_df is None or temp_df.empty:
                    temp_df = temp_data
                else:
                    temp_df = pd.concat([temp_df, temp_data], axis=0)

            OFFSET_Get.LC_Logic(temp_df, Family, Lot_Code, Oper_Desc, Fab, Offset_Group)

        except Exception as e:
            tb = traceback.format_exc()
            c.sendMsg('', '506204179', f'{Fab} {Lot_Code} {Oper_Desc} Module Offset Failed : {e}, {tb}')

    def Module_Alarm(
        mico_info_key,
        ) :
        Family = mico_info_key['Family'].unique()[0]
        Lot_Code = mico_info_key['Lot_Code'].unique()[0]
        oper_desc = mico_info_key['Oper_Desc'].unique()[0]
        Fab = mico_info_key['Fab'].unique()[0]
        Channel_ID = mico_info_key['Channel_ID'].unique()[0]

        Default_Channel_ID = '507358454'
        Sigma = 10


        url = 'mongodb://cncmico:....'
        db = 'mico-platform-mongodb'

        client = MongoClient(url)
        db_name = client[db]



        collection_name = 'MICO_PRE_THK_' + Lot_Code + '_' + oper_desc + '_' + Fab + '_Period'

        collection = db_name[collection_name]
        data = list(collection.find())
        Pre_VM_df = pd.DataFrame(data)
        print('Pre Len : ', len(Pre_VM_df))

        collection_name = 'MICO_Removal_Rate_' + Lot_Code + '_' + oper_desc + '_' + Fab

        collection = db_name[collection_name]
        data = list(collection.find())
        RR_df = pd.DataFrame(data)
        print('RR Len : ', len(RR_df))

        collection_name = 'MICO_OFFSET_' + Lot_Code + '_' + oper_desc + '_' + Fab

        collection = db_name[collection_name]
        data = list(collection.find())
        OFFSET_df = pd.DataFrame(data)
        print('OFFSET Len : ', len(OFFSET_df))

        
        def check_alarm(filtered_data, latest_value, alarm_para, Sigma, message):

            mean = filtered_data[alarm_para].mean()
            std = filtered_data[alarm_para].std()

            count = filtered_data[alarm_para].nunique()

            if count >= 10 :
        
                if (np.abs(latest_value - mean) > Sigma * std) & (np.abs(latest_value - mean) > 0.1) :

                    message += f": 현재 학습값 [[ {latest_value:.2f} ]] 이 ** {Sigma}Sigma ** 기준으로 초과했습니다. ( 이전 실적값 : (( {mean:.2f} )) ) "
                    Get_data.Cube_Alarm_Msg(Channel_ID, message)
                    Get_data.Cube_Alarm_Msg(Default_Channel_ID, message)

        RR_df = RR_df.sort_values(by='Date')

        idx = RR_df.groupby(['EQ', 'Recipe_ID', 'APC_Para'])['Date'].idxmax()
        latest_data = RR_df.loc[idx].reset_index(drop=True)

        print(latest_data.select_dtypes(include='float').columns.tolist())

        for _, row in latest_data.iterrows():
            EQ = row['EQ']
            Recipe_ID = row['Recipe_ID']
            APC_Para = row['APC_Para']
            Sigma = mico_info_key[(mico_info_key['Recipe_ID'] == Recipe_ID)&(mico_info_key['APC_Para'] == APC_Para)]['RR_Alarm_Sigma'].unique()[0]
            Module_name = 'Removal_Rate'
            alarm_para_list = latest_data.select_dtypes(include='float').columns.tolist()

            for para in alarm_para_list : 
            
                latest_value = row[para]
                alarm_para = para

                filtered_data = RR_df[ (RR_df['Recipe_ID'] == Recipe_ID) &
                                    (RR_df['APC_Para'] == APC_Para) & 
                                    (RR_df['Date'] < row['Date'])]

                message = f"{Lot_Code} / {oper_desc} / {Module_name} / {EQ} / {Recipe_ID} / {APC_Para} / {para} " 

                check_alarm(filtered_data, latest_value, alarm_para, Sigma, message)

# ── Runner helpers ────────────────────────────────────────────────────────────

def _parse_key(key):
    parts = key.split('_')
    return parts[0], parts[1], parts[2]  # lot_code, oper_code, fab


def _execute(merge_df, mico_info_key, pol_type, use_group_rr=False):
    try:
        has_itm = (
            mico_info_key['Pre_Thk_Para_ITM'].notna().any() and
            (mico_info_key['Pre_Thk_Para_ITM'] != '').any()
        )
        if has_itm:
            Module_Get.Module_Get_Pre_VM_ITM(merge_df, mico_info_key, pol_type)
        else:
            Module_Get.Module_Get_Pre_VM(merge_df, mico_info_key, pol_type)
        if use_group_rr:
            Module_Get.Module_Get_RR_Group(merge_df, mico_info_key, pol_type)
        else:
            Module_Get.Module_Get_RR(merge_df, mico_info_key, pol_type)
        Module_Get.Module_Get_Offset(merge_df, mico_info_key, pol_type)
        Module_Get.Module_Alarm(mico_info_key)
    except Exception as e:
        tb  = traceback.format_exc()
        lot_code  = mico_info_key['Lot_Code'].unique()[0]
        oper_desc = mico_info_key['Oper_Desc'].unique()[0]
        Get_data.Cube_Msg(lot_code, oper_desc, 'Module', e, tb)


def _run_no_group(mico_info_table, for_key_list, pol_type):
    for key in for_key_list:
        _, oper_code, _ = _parse_key(key)
        mico_info_key   = mico_info_table[mico_info_table['for_key_list'] == key].copy()

        merge_df = Module_Get.Module_Get_Merge(mico_info_key)
        merge_df = merge_df[merge_df['operation_id'] == oper_code].copy()

        _execute(merge_df, mico_info_key, pol_type)


def _run_group(mico_info_table, group_name, pol_type):
    mico_info_keys = []
    merge_df       = pd.DataFrame()
    for_key_list   = mico_info_table[mico_info_table['Group_Name'] == group_name]['for_key_list'].unique()

    for key in for_key_list:
        mico_info_key = mico_info_table[mico_info_table['for_key_list'] == key].copy()
        mico_info_keys.append(mico_info_key)

        temp = Module_Get.Module_Get_Merge(mico_info_key)
        if temp is not None and not temp.empty:
            merge_df = pd.concat([merge_df, temp])

    merge_df['Group_Name'] = group_name

    for mico_info_key in mico_info_keys:
        _execute(merge_df, mico_info_key, pol_type, use_group_rr=True)


def run(family, oper_desc, pol_type):
    try:
        mico_info_table = Get_data.baseinfoGetData(Family=family, oper_desc=oper_desc)
        mico_info_table['Group_Name'] = mico_info_table['Group_Name'].fillna('not_group')
        mico_info_table['for_key_list'] = (
            mico_info_table['Lot_Code'] + '_' +
            mico_info_table['Oper_Code'] + '_' +
            mico_info_table['Fab']
        )

        for group_name in mico_info_table['Group_Name'].unique():
            for_key_list = mico_info_table[mico_info_table['Group_Name'] == group_name]['for_key_list'].unique()

            if group_name == 'not_group':
                _run_no_group(mico_info_table, for_key_list, pol_type)
            else:
                _run_group(mico_info_table, group_name, pol_type)

    except Exception as e:
        tb = traceback.format_exc()
        Get_data.Cube_Msg(family, oper_desc, 'Module', e, tb)
