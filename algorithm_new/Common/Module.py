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


def _make_pre_thk_mongo(Lot_Code, Oper_Desc, Fab):
    # Pre_Thk_VM 결과를 저장할 MongoDB 컬렉션 이름 구성 후 controller 반환
    collection = 'MICO_PRE_THK_' + Lot_Code + '_' + Oper_Desc + '_' + Fab + '_Period'
    return mongodb_controller(_MONGO_URL, _MONGO_DB, collection)


def _make_rr_mongo(Lot_Code, Oper_Desc, Fab):
    # Removal Rate 결과를 저장할 MongoDB 컬렉션 이름 구성 후 controller 반환
    collection = 'MICO_Removal_Rate_' + Lot_Code + '_' + Oper_Desc + '_' + Fab
    return mongodb_controller(_MONGO_URL, _MONGO_DB, collection)


def _build_eqpm_df(merge_df_rr, Maker, Fab):
    # Maker별 EQP 채널 컬럼 구성 후 PM 이벤트 기준 pad rank 산출하여 EQPM_df 반환
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
    return EQPM_df


def _extract_latest(pre_thk_df_merge, cols):
    # pre_eq_ch(전공정 장비_채널) 별로 가장 최근 데이터 1행만 추출
    # rank=1이 최신행; method='first'로 동일 시간 존재 시 첫 번째 행만 선택
    pre_thk_df_merge['pre_oper_time'] = pd.to_datetime(pre_thk_df_merge['pre_oper_time'])
    pre_thk_df_merge['rank'] = pre_thk_df_merge.groupby('pre_eq_ch')['pre_oper_time'].rank(method='first', ascending=False)
    pre_thk_df_recent = pre_thk_df_merge[pre_thk_df_merge['rank'] == 1].copy()
    pre_thk_table = pre_thk_df_recent[cols].copy()
    pre_thk_table.dropna(axis=0, inplace=True)
    return pre_thk_table



class Module_Get:

    def fetch_merge_data(mico_info_key):
        # Set-up 키(Family/Fab/Lot_Code/Oper_Desc)로 MongoDB에서 CMP 실측 데이터를 조회하여 merge_df 반환.
        Fab       = mico_info_key['Fab'].unique()[0]
        Lot_Code  = mico_info_key['Lot_Code'].unique()[0]
        Oper_Desc = mico_info_key['Oper_Desc'].unique()[0]
        Family    = mico_info_key['Family'].unique()[0]

        try:
            return Get_data.MongoDB_GetData(Family, Fab, Lot_Code, Oper_Desc)
        except Exception as e:
            tb = traceback.format_exc()
            c.sendMsg('', '506204179', f'{Fab} {Lot_Code} {Oper_Desc} Module Merge Failed : {e}, {tb}')

    def compute_pre_thk_vm(merge_df, mico_info_key, pol_type):
        """
        ITM set-up 여부에 따라 자동 분기:
          - Pre_Thk_Para_ITM 있음 → ITM moving avg (detrend 없음),  Y(회귀) = BIAS (0-centered)
          - Pre_Thk_Para_ITM 없음 + Pre_Oper_Code 있음 → detrend + moving avg,  Y(회귀) = Detrend_Thk (0-centered)
        Pre_Oper2~4 회귀식은 두 경로 공통 적용.
        """
        Fab       = mico_info_key['Fab'].unique()[0]
        Lot_Code  = mico_info_key['Lot_Code'].unique()[0]
        Oper_Desc = mico_info_key['Oper_Desc'].unique()[0]

        mongo = _make_pre_thk_mongo(Lot_Code, Oper_Desc, Fab)

        try:
            Oper_Code      = mico_info_key['Oper_Code'].unique()[0]
            Pre_Thk_Period = str(mico_info_key['Pre_Thk_Period'].unique()[0]) + 'D'
            Thk_Para_13P   = mico_info_key[mico_info_key['FB_Type'] == 'TIME']['Thk_Para'].unique()[0]
            today          = datetime.now()

            itm_13p_rows     = mico_info_key[
                (mico_info_key['FB_Type'] == 'TIME') &
                mico_info_key['Pre_Thk_Para_ITM'].notna() &
                (mico_info_key['Pre_Thk_Para_ITM'] != '')
            ]
            Pre_Thk_Para_13P = itm_13p_rows['Pre_Thk_Para_ITM'].unique()[0] if len(itm_13p_rows) > 0 else None

            # for_key_list 키 = Lot_Code + Oper_Code + Fab → Detail 단위가 아님
            # 동일 키 내에 Thk_Para가 여러 개(예: DRAM STI처럼 ED/CENTER 혼재)일 수 있으므로 루프 필요
            for Thk_Para in mico_info_key['Thk_Para'].unique():

                key_df    = mico_info_key[mico_info_key['Thk_Para'] == Thk_Para].copy()
                itm_paras = key_df['Pre_Thk_Para_ITM'].dropna()
                itm_paras = itm_paras[itm_paras != ''].unique()
                use_itm   = len(itm_paras) > 0          # ITM 계측값 경로 여부

                ref_key        = key_df.iloc[0]
                Pre_Oper_Code2 = ref_key['Pre_Oper_Code2']
                Pre_Oper_Desc2 = ref_key['Pre_Oper_Desc2']
                Pre_Oper_Para2 = ref_key['Pre_Oper_Para2']
                Pre_Oper_Desc3 = ref_key['Pre_Oper_Desc3']
                Pre_Oper_Para3 = ref_key['Pre_Oper_Para3']
                Pre_Oper_Desc4 = ref_key['Pre_Oper_Desc4']
                Pre_Oper_Para4 = ref_key['Pre_Oper_Para4']

                pre_oper_vals  = key_df['Pre_Oper_Code'].dropna()
                use_moving_avg = (not use_itm) and len(pre_oper_vals[pre_oper_vals != '']) > 0  # detrend + moving avg 경로
                has_regression = isinstance(Pre_Oper_Code2, str) and Pre_Oper_Code2 != ''       # Pre_Oper2~4 회귀식 산출 여부

                # ITM, moving avg, 회귀 중 아무것도 없으면 Pre_Thk_VM 학습 불필요 → 스킵
                if not use_itm and not use_moving_avg and not has_regression:
                    continue

                if use_itm:

                    Pre_Thk_Para = itm_paras[0]
                    itm_rows     = key_df[key_df['Pre_Thk_Para_ITM'].notna() & (key_df['Pre_Thk_Para_ITM'] != '')]
                    use_pressure = (itm_rows['FB_Type'] == 'PRESSURE').any()

                    if use_pressure:
                        # Pressure ITM(ED/EX): 두 계측 파라미터 간 차이를 0-centering
                        merge_df['BIAS'] = (
                            merge_df[Pre_Thk_Para] - merge_df[Pre_Thk_Para_13P]
                            - (merge_df[Pre_Thk_Para].mean() - merge_df[Pre_Thk_Para_13P].mean())
                        )
                    else:
                        # 그 외 ITM: Pre_Thk_Para 단독 0-centering
                        merge_df['BIAS'] = merge_df[Pre_Thk_Para] - merge_df[Pre_Thk_Para].mean()

                    merge_df         = PRE_THK_VM_Get.iqr_filter(merge_df, 'BIAS')
                    min_count        = 5 if ('ED' in Thk_Para or 'EX' in Thk_Para) else 10
                    pre_thk_df_merge = PRE_THK_VM_Get.rolling_mean(merge_df, 'BIAS', Pre_Thk_Period, min_count=min_count)
                    pre_thk_table    = _extract_latest(pre_thk_df_merge, ['pre_oper_time', 'pre_eq_ch', 'Pre_Thk', 'Pre_Thk_Count'])
                    pre_thk_table['THK_Para']     = Thk_Para
                    pre_thk_table['Pre_THK_Para'] = Pre_Thk_Para
                    y_col = 'BIAS'  # 두 경우 모두 BIAS가 0-centered → 회귀 y축 통일

                else:

                    pre_thk_df_merge = pd.DataFrame()

                    for i in range(len(key_df)):

                        key          = key_df.iloc[i]
                        APC_Para     = key['APC_Para']
                        Recipe_ID    = key['Recipe_ID']
                        Pre_Target   = float(key['Pre_Target'])
                        Post_Target  = float(key['Target'])
                        use_pressure = key['FB_Type'] == 'PRESSURE'
                        Target_13P   = mico_info_key[(mico_info_key['Recipe_ID'] == Recipe_ID) & (mico_info_key['FB_Type'] == 'TIME')]['Target'].unique()[0]

                        merge_df['BIAS']       = (merge_df[Thk_Para] - merge_df[Thk_Para_13P]) - (Post_Target - Target_13P)
                        Pad_Para               = Get_data.PadParaGet(APC_Para)
                        APC_Para_merge         = Get_data.APCParaGet(APC_Para, pol_type)

                        pre_thk_df             = PRE_THK_VM_Get.compute_detrend(merge_df, APC_Para_merge, Thk_Para, Pre_Target, Post_Target, Pad_Para, use_pressure=use_pressure)
                        pre_thk_df['THK_Para'] = Thk_Para
                        pre_thk_df_merge       = pre_thk_df if pre_thk_df_merge.empty else pd.concat([pre_thk_df_merge, pre_thk_df])

                    pre_thk_df_merge = PRE_THK_VM_Get.iqr_filter(pre_thk_df_merge, 'Detrend_Thk')

                    if use_moving_avg:
                        min_count        = 5 if ('ED' in Thk_Para or 'EX' in Thk_Para) else 10
                        pre_thk_df_merge = PRE_THK_VM_Get.rolling_mean(pre_thk_df_merge, 'Detrend_Thk', Pre_Thk_Period, min_count)
                        pre_thk_table    = _extract_latest(pre_thk_df_merge, ['pre_oper_time', 'pre_eq_ch', 'Pre_Thk', 'Pre_Thk_Count', 'THK_Para'])
                    else:
                        # pre_oper_time/pre_eq_ch 데이터 없음 → _extract_latest 불필요
                        # has_regression 결과(b1/b0)만 저장할 1행 테이블 생성
                        pre_thk_table = pd.DataFrame([{'THK_Para': Thk_Para}])

                    y_col = 'Detrend_Thk'   # 회귀 y축: 0-centered 후 CMP 두께 편차

                # ITM/detrend 경로 공통: Pre_Oper2~4 회귀계수 산출
                # join key(substrate_id vs lot_id/alias_lot_id)는 fit_pre_oper_regression 내부에서 자동 판별
                if has_regression:
                    client = MongoClient(_MONGO_URL)
                    try:
                        raw = client[_MONGO_DB]['MICO_PRE_THK_INFO_' + Lot_Code + '_' + Oper_Desc + '_' + Fab].find({}, {'_id': 0})
                        pre2_df = pd.DataFrame(raw)
                    finally:
                        client.close()
                    pre2_df.rename(columns={'samp_matl_id': 'substrate_id'}, inplace=True)
                    pre2_df.drop_duplicates(subset=['substrate_id'], inplace=True)

                    oper_pairs = [
                        (Pre_Oper_Desc2, Pre_Oper_Para2, 'PRE_OPER2'),
                        (Pre_Oper_Desc3, Pre_Oper_Para3, 'PRE_OPER3'),
                        (Pre_Oper_Desc4, Pre_Oper_Para4, 'PRE_OPER4'),
                    ]
                    PRE_THK_VM_Get.fit_pre_oper_regression(
                        pre_thk_df_merge, pre2_df, pre_thk_table, oper_pairs, y_col
                    )

                # 두 경로(ITM/detrend) 공통 마무리: Date 기록 후 MongoDB 저장
                pre_thk_table['Date'] = pd.to_datetime(today)
                pre_thk_table.rename(columns={'Pre_Thk_Count': 'Count'}, inplace=True)
                pre_thk_table['Oper_Code'] = Oper_Code
                mongo.push_df(pre_thk_table)

        except Exception as e:
            tb = traceback.format_exc()
            c.sendMsg('', '506204179', f'{Fab} {Lot_Code} {Oper_Desc} Module PRE VM Failed : {e}, {tb}')

    def compute_removal_rate(merge_df, mico_info_key, pol_type, RR_Alarm=None):
        # 단일 Lot_Code 공정의 Removal Rate 학습값 산출.
        # Maker별(AMAT/EBARA/KCT) EQP 채널을 구성하고 PM 이벤트 기준 pad rank를 계산한 뒤 compute_rr 호출.

        Fab       = mico_info_key['Fab'].unique()[0]
        Lot_Code  = mico_info_key['Lot_Code'].unique()[0]
        Oper_Desc = mico_info_key['Oper_Desc'].unique()[0]

        try:
            Maker         = mico_info_key['Maker'].unique()[0]
            Pre_Oper_Code = mico_info_key['Pre_Oper_Code'].unique()[0]
            Thk_Para_List = mico_info_key['Thk_Para'].unique()
            Thk_Para_13P  = mico_info_key[mico_info_key['FB_Type'] == 'TIME']['Thk_Para'].unique()[0]

            if Pre_Oper_Code == '':
                merge_df_rr = merge_df.copy()
                for Thk_key in Thk_Para_List:
                    merge_df_rr[Thk_key + '_VM'] = 0
            else:
                merge_df_rr = Removal_Rate_Get.load_pre_thk_data(merge_df, mico_info_key, _MONGO_URL, _MONGO_DB)

            EQPM_df = _build_eqpm_df(merge_df_rr, Maker, Fab)

            mongo = _make_rr_mongo(Lot_Code, Oper_Desc, Fab)

            search_key = mico_info_key[mico_info_key['Fab'] == Fab]
            for i in range(len(search_key)):
                key         = search_key.iloc[i, :]
                Thk_Para    = key['Thk_Para']
                Post_Target = float(key['Target'])
                Recipe_ID   = key['Recipe_ID']
                Target_13P  = mico_info_key[(mico_info_key['Recipe_ID'] == Recipe_ID) & (mico_info_key['FB_Type'] == 'TIME')]['Target'].unique()[0]

                merge_df_rr['BIAS'] = merge_df_rr[Thk_Para] - merge_df_rr[Thk_Para_13P] - (Post_Target - Target_13P)

                Removal_Rate_Get.compute_rr(merge_df_rr, key, pol_type, EQPM_df, RR_Alarm, mongo)

        except Exception as e:
            tb = traceback.format_exc()
            c.sendMsg('', '506204179', f'{Fab} {Lot_Code} {Oper_Desc} Module RR Failed : {e}, {tb}')

    def compute_removal_rate_group(merge_df, mico_info_key, pol_type, RR_Alarm=None):
        # 그룹 공정용 Removal Rate 학습값 산출.
        # 복수 Lot_Code 데이터가 합산된 merge_df를 Lot_Code별로 순회하며 Pre_Thk_VM을 조회한 뒤 compute_rr_group 호출.

        Fab       = mico_info_key['Fab'].unique()[0]
        Lot_Code  = mico_info_key['Lot_Code'].unique()[0]
        Oper_Desc = mico_info_key['Oper_Desc'].unique()[0]

        try:
            Maker         = mico_info_key['Maker'].unique()[0]
            Pre_Oper_Code = mico_info_key['Pre_Oper_Code'].unique()[0]
            Thk_Para_List = mico_info_key['Thk_Para'].unique()
            Thk_Para_13P  = mico_info_key[mico_info_key['FB_Type'] == 'TIME']['Thk_Para'].unique()[0]
            Lot_Code_List = merge_df['Lot_Code'].unique()

            if Pre_Oper_Code == '':
                merge_df_rr = merge_df.copy()
                for Thk_key in Thk_Para_List:
                    merge_df_rr[Thk_key + '_VM'] = 0
            else:
                merge_df_rr = pd.DataFrame()
                for lc in Lot_Code_List:
                    merge_df_filter = merge_df[merge_df['Lot_Code'] == lc].copy()
                    merge_df_temp   = Removal_Rate_Get.load_pre_thk_data(merge_df_filter, mico_info_key, _MONGO_URL, _MONGO_DB)
                    merge_df_rr     = pd.concat([merge_df_rr, merge_df_temp])

            EQPM_df = _build_eqpm_df(merge_df_rr, Maker, Fab)

            mongo = _make_rr_mongo(Lot_Code, Oper_Desc, Fab)

            search_key = mico_info_key[mico_info_key['Fab'] == Fab]
            for i in range(len(search_key)):
                key         = search_key.iloc[i, :]
                Thk_Para    = key['Thk_Para']
                Post_Target = float(key['Target'])
                Recipe_ID   = key['Recipe_ID']
                Target_13P  = mico_info_key[(mico_info_key['Recipe_ID'] == Recipe_ID) & (mico_info_key['FB_Type'] == 'TIME')]['Target'].unique()[0]

                merge_df_rr['BIAS'] = merge_df_rr[Thk_Para] - merge_df_rr[Thk_Para_13P] - (Post_Target - Target_13P)

                Removal_Rate_Get.compute_rr_group(merge_df_rr, key, pol_type, EQPM_df, RR_Alarm, mongo)

        except Exception as e:
            tb = traceback.format_exc()
            c.sendMsg('', '506204179', f'{Fab} {Lot_Code} {Oper_Desc} Module RR Group Failed : {e}, {tb}')

    def compute_offset(merge_df, mico_info_key, pol_type):
        # FB_Type=TIME 기준으로 Offset 학습값을 산출하고 MongoDB에 저장.

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

    def check_alarm(
        mico_info_key,
        ):
        # Pre_Thk_VM / RR / Offset 최신 학습값을 이전 실적 대비 N-Sigma 기준으로 점검하여 이상 시 Cube 메시지 발송.
        Family = mico_info_key['Family'].unique()[0]
        Lot_Code = mico_info_key['Lot_Code'].unique()[0]
        oper_desc = mico_info_key['Oper_Desc'].unique()[0]
        Fab = mico_info_key['Fab'].unique()[0]
        Channel_ID = mico_info_key['Channel_ID'].unique()[0]

        Default_Channel_ID = '507358454'
        Sigma = 10


        client = MongoClient(_MONGO_URL)
        try:
            db_name     = client[_MONGO_DB]
            Pre_VM_df   = pd.DataFrame(list(db_name['MICO_PRE_THK_'      + Lot_Code + '_' + oper_desc + '_' + Fab + '_Period'].find()))
            RR_df       = pd.DataFrame(list(db_name['MICO_Removal_Rate_'  + Lot_Code + '_' + oper_desc + '_' + Fab].find()))
            OFFSET_df   = pd.DataFrame(list(db_name['MICO_OFFSET_'        + Lot_Code + '_' + oper_desc + '_' + Fab].find()))
        finally:
            client.close()
        print('Pre Len : ', len(Pre_VM_df))
        print('RR Len : ',  len(RR_df))
        print('OFFSET Len : ', len(OFFSET_df))

        
        def send_if_out_of_sigma(filtered_data, latest_value, alarm_para, Sigma, message):

            mean  = filtered_data[alarm_para].mean()
            std   = filtered_data[alarm_para].std()
            count = filtered_data[alarm_para].nunique()

            if count >= 10:
                if (np.abs(latest_value - mean) > Sigma * std) & (np.abs(latest_value - mean) > 0.1):
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

                send_if_out_of_sigma(filtered_data, latest_value, alarm_para, Sigma, message)

# ── Runner helpers ────────────────────────────────────────────────────────────

def _parse_for_key(key):
    # for_key_list 키(Lot_Code_Oper_Code_Fab)를 언더스코어로 분리하여 각 구성요소 반환.
    parts = key.split('_')
    return parts[0], parts[1], parts[2]  # lot_code, oper_code, fab


def _run_pipeline(merge_df, mico_info_key, pol_type, use_group_rr=False):
    # Pre VM → RR → Offset → Alarm 순서로 학습 모듈 전체 실행
    # use_group_rr=True: 여러 Lot_Code가 합쳐진 merge_df로 RR_Group 실행 (그룹 공정용)
    try:
        Module_Get.compute_pre_thk_vm(merge_df, mico_info_key, pol_type)
        if use_group_rr:
            Module_Get.compute_removal_rate_group(merge_df, mico_info_key, pol_type)
        else:
            Module_Get.compute_removal_rate(merge_df, mico_info_key, pol_type)
        Module_Get.compute_offset(merge_df, mico_info_key, pol_type)
        Module_Get.check_alarm(mico_info_key)
    except Exception as e:
        tb  = traceback.format_exc()
        lot_code  = mico_info_key['Lot_Code'].unique()[0]
        oper_desc = mico_info_key['Oper_Desc'].unique()[0]
        Get_data.Cube_Msg(lot_code, oper_desc, 'Module', e, tb)


def _run_single(mico_info_table, for_key_list, pol_type):
    # 그룹 미지정 공정: for_key_list 키마다 독립적으로 merge_df를 조회 후 실행
    for key in for_key_list:
        _, oper_code, _ = _parse_for_key(key)
        mico_info_key   = mico_info_table[mico_info_table['for_key_list'] == key].copy()

        merge_df = Module_Get.fetch_merge_data(mico_info_key)
        merge_df = merge_df[merge_df['operation_id'] == oper_code].copy()

        _run_pipeline(merge_df, mico_info_key, pol_type)


def _run_grouped(mico_info_table, group_name, pol_type):
    # 그룹 지정 공정: 같은 Group_Name의 모든 키 데이터를 먼저 합산(merge_df)한 후
    # 각 mico_info_key에 동일한 merge_df로 실행 → Group RR처럼 복수 Lot_Code 통합 처리
    mico_info_keys = []
    merge_df       = pd.DataFrame()
    for_key_list   = mico_info_table[mico_info_table['Group_Name'] == group_name]['for_key_list'].unique()

    for key in for_key_list:
        mico_info_key = mico_info_table[mico_info_table['for_key_list'] == key].copy()
        mico_info_keys.append(mico_info_key)

        temp = Module_Get.fetch_merge_data(mico_info_key)
        if temp is not None and not temp.empty:
            merge_df = pd.concat([merge_df, temp])

    merge_df['Group_Name'] = group_name

    for mico_info_key in mico_info_keys:
        _run_pipeline(merge_df, mico_info_key, pol_type, use_group_rr=True)


def run(family, oper_desc, pol_type):
    # 최상위 진입점: set-up 정보 로드 → for_key_list(Lot_Code+Oper_Code+Fab) 생성
    # → Group 여부에 따라 _run_single / _run_grouped 분기
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
                _run_single(mico_info_table, for_key_list, pol_type)
            else:
                _run_grouped(mico_info_table, group_name, pol_type)

    except Exception as e:
        tb = traceback.format_exc()
        Get_data.Cube_Msg(family, oper_desc, 'Module', e, tb)
