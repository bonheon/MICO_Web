import sys
import os
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

_ALGO_DIR  = str(Path(__file__).parents[1])   # algorithm_source/
_MICO_WEB  = str(Path(__file__).parents[2])   # MICO_Web/
# CSV는 algorithm_new 에 위치
_CSV_PATH  = str(Path(__file__).parents[2] / 'algorithm_new' / 'merge_df_sample.csv')

if _MICO_WEB not in sys.path:
    sys.path.insert(0, _MICO_WEB)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()


class Get_data:

    def baseinfoGetData(Family, oper_desc):
        from setup_mico.models import Category, SubCategory, Detail, RecipeGroup

        cats = Category.objects.filter(family=Family, oper_desc=oper_desc)
        rows = []
        for cat in cats:
            for sub in cat.subcategories.all():
                rg = sub.recipe_groups.filter(category=cat).first()
                group_name = rg.name if rg else None

                for det in sub.details.all():
                    rows.append({
                        'Family'          : cat.family,
                        'Lot_Code'        : cat.product,
                        'Oper_Code'       : cat.oper_id,
                        'Oper_Desc'       : cat.oper_desc,
                        'Channel_ID'      : cat.channel_id,
                        'Fab'             : sub.fab,
                        'Maker'           : sub.maker,
                        'Recipe_ID'       : sub.recipe_id,
                        'APC_Para'        : det.apc_para,
                        'Thk_Para'        : det.thk_para,
                        'Target'          : det.target,
                        'Post_Target'     : det.target,
                        'Pre_Target'      : det.pre_target,
                        'Pre_Thk_Period'  : det.pre_thk_period,
                        'RR_Para'         : det.rr_para,
                        'Offset_Group'    : det.offset_group,
                        'RR_Para_Max'     : det.rr_max,
                        'RR_Period'       : det.rr_period,
                        'Pad_Seperation'  : det.rr_if,
                        'Pre_Thk_Para_ITM': det.pre_thk_para_itm,
                        'Pre_Oper_Code'   : det.pre_oper_code,
                        'Pre_Oper_Desc'   : det.pre_oper_desc,
                        'Pre_Oper_Para'   : det.pre_oper_para,
                        'Pre_Oper_Code2'  : det.pre_oper_code2,
                        'Pre_Oper_Desc2'  : det.pre_oper_desc2,
                        'Pre_Oper_Para2'  : det.pre_oper_para2,
                        'Pre_Oper_Code3'  : det.pre_oper_code3,
                        'Pre_Oper_Desc3'  : det.pre_oper_desc3,
                        'Pre_Oper_Para3'  : det.pre_oper_para3,
                        'Pre_Oper_Code4'  : det.pre_oper_code4,
                        'Pre_Oper_Desc4'  : det.pre_oper_desc4,
                        'Pre_Oper_Para4'  : det.pre_oper_para4,
                        'RR_Weight'       : det.rr_weight,
                        'RR_Count'        : det.rr_count,
                        'FB_Type'         : det.fb_type,
                        'RR_Alarm_Sigma'  : det.rr_alarm_sigma,
                        'Group_Name'      : group_name,
                    })

        df = pd.DataFrame(rows)
        if df.empty:
            raise ValueError(f'Set-up 정보 없음: Family={Family}, oper_desc={oper_desc}')
        return df


    def MongoDB_GetData(Family, Fab, Lot_Code, Oper_Desc):
        df = pd.read_csv(_CSV_PATH, parse_dates=['Date', 'pre_oper_time'])
        df['IDLE'] = df['IDLE'].fillna('')
        df['Lot_Code'] = Lot_Code
        return df


    def APCParaGet(APC_Para, pol_type):
        if pol_type == 3:
            return [APC_Para]
        if pol_type == 13:
            return [APC_Para]
        return [APC_Para]


    def PadParaGet(APC_Para):
        mapping = {
            'P1': 'AMAT_PAD_1',
            'P2': 'AMAT_PAD_2',
            'P3': 'AMAT_PAD_3',
        }
        return mapping.get(APC_Para, 'AMAT_PAD_3')


    def HeadParaGet(APC_Para):
        mapping = {
            'P1': 'AMAT_HEAD_1',
            'P2': 'AMAT_HEAD_2',
            'P3': 'AMAT_HEAD_1',
        }
        return mapping.get(APC_Para, 'AMAT_HEAD_1')


    def DiskParaGet(APC_Para):
        mapping = {
            'P1': 'AMAT_DISK_1',
            'P2': 'AMAT_DISK_2',
            'P3': 'AMAT_DISK_3',
        }
        return mapping.get(APC_Para, 'AMAT_DISK_3')


    def EQPMGetData_HUB(Fab, eqp_id_list, recipe_id_list):
        now = datetime.now()
        events = []
        for eqp_id in eqp_id_list:
            events.append({
                'EQP_ID'  : eqp_id,
                'EVENT_TM': now - timedelta(days=30),
                'EVENT_CD': 'PadPM',
            })
            for j in range(10):
                events.append({
                    'EQP_ID'  : eqp_id,
                    'EVENT_TM': now - timedelta(days=29) + timedelta(hours=j),
                    'EVENT_CD': 'EndLot',
                })
        return pd.DataFrame(events)


    def Cube_Msg(lot, oper, module, e, tb):
        print(f'  [Cube] {lot}/{oper}/{module} 오류: {e}')

    def Cube_Alarm_Msg(channel_id, message):
        print(f'  [Cube Alarm] ch={channel_id}: {message}')

    def Cube_Msg_RR_Alarm(EQ, rcp_id, message):
        print(f'  [Cube RR Alarm] {EQ}/{rcp_id}: {message}')
