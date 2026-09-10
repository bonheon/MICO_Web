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
    # merge_df_rr에 'Fab' 컬럼이 있으면 fab별로 EQPMGetData_HUB를 호출해 결과를 합산한다
    if Maker == 'AMAT':
        eqp_col = 'eqp_id'
    elif Maker == 'EBARA':
        merge_df_rr['CH'] = merge_df_rr['recipe_id'].apply(lambda x: 'AB' if 'AB' in x else 'CD')
        merge_df_rr['eqp_id_ch'] = merge_df_rr['eqp_id'] + '_' + merge_df_rr['CH']
        eqp_col = 'eqp_id_ch'
    elif Maker == 'KCT':
        merge_df_rr['CH'] = merge_df_rr['recipe_id'].apply(lambda x: 'L' if '_L' in x else 'R')
        merge_df_rr['eqp_id_ch'] = merge_df_rr['eqp_id'] + '_' + merge_df_rr['CH']
        eqp_col = 'eqp_id_ch'

    if 'Fab' in merge_df_rr.columns:
        # 그룹 공정: fab별로 해당 fab의 장비·레시피 목록만 조회한 뒤 결과를 합산
        eqpm_parts = []
        for fab in merge_df_rr['Fab'].unique():
            if not fab or fab == '':
                continue
            fab_df         = merge_df_rr[merge_df_rr['Fab'] == fab]
            eqp_id_list    = tuple(fab_df[eqp_col].unique())
            recipe_id_list = tuple(fab_df['recipe_id'].unique())
            if eqp_id_list:
                eqpm_parts.append(Get_data.EQPMGetData_HUB(fab, eqp_id_list, recipe_id_list))
        EQPM_df = pd.concat(eqpm_parts, ignore_index=True) if eqpm_parts else pd.DataFrame()
    else:
        eqp_id_list    = tuple(merge_df_rr[eqp_col].unique())
        recipe_id_list = tuple(merge_df_rr['recipe_id'].unique())
        EQPM_df = Get_data.EQPMGetData_HUB(Fab, eqp_id_list, recipe_id_list)

    EQPM_df = EQPM_df.sort_values(by=['EQP_ID', 'EVENT_TM']).reset_index(drop=True)

    def compute_rank(group):
        # PM 이벤트 발생 시 rank를 0으로 리셋, EndLot/JobEnd마다 1씩 증가하여 PM 이후 누적 웨이퍼 수 산출
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

        print(f'    [데이터 조회] {Fab} | {Lot_Code} | {Oper_Desc}', end=' ... ', flush=True)
        try:
            result = Get_data.MongoDB_GetData(Family, Fab, Lot_Code, Oper_Desc)
            print(f'{len(result)}행')
            return result
        except Exception as e:
            print('실패')
            tb = traceback.format_exc()
            c.sendMsg('', '506204179', f'{Fab} {Lot_Code} {Oper_Desc} Module Merge Failed : {e}, {tb}')

    def compute_pre_thk_vm(merge_df, mico_info_key, pol_type):
        """
        ITM set-up 여부에 따라 자동 분기:
          - Pre_Thk_Para_ITM 있음 → ITM moving avg (detrend 없음),  Y(회귀) = BIAS (0-centered)
          - Pre_Thk_Para_ITM 없음 + Pre_Oper_Code 있음 → detrend + moving avg,  Y(회귀) = Detrend_Thk (0-centered)
        단, Set-up의 Pre_Thk_VM_Source == 'POST' 이면 ITM이 있어도 detrend(post thk) 경로로 학습.
        (사전공정 zone 차이가 입고 두께가 아닌 RR에 영향을 주는 공정용, ex. CBL HM NIT CMP.
         Pre_Thk_Para_ITM 자체는 유지되므로 Simulation·RR 학습의 ITM 사용은 영향 없음)
        Pre_Oper2~4 회귀식은 두 경로 공통 적용.
        """
        Fab       = mico_info_key['Fab'].unique()[0]
        Lot_Code  = mico_info_key['Lot_Code'].unique()[0]
        Oper_Desc = mico_info_key['Oper_Desc'].unique()[0]

        mongo = _make_pre_thk_mongo(Lot_Code, Oper_Desc, Fab)
        print(f'\n  [Pre_Thk_VM] {Fab} | {Lot_Code} | {Oper_Desc} 시작')

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

                # Pre_Thk_VM_Source == 'POST' → ITM set-up이 있어도 detrend(post thk) 경로 강제
                # (컬럼이 없는 구버전 mico_info_key는 기존 동작(AUTO) 유지)
                if 'Pre_Thk_VM_Source' in key_df.columns:
                    force_post = (key_df['Pre_Thk_VM_Source'].fillna('') == 'POST').any()
                else:
                    force_post = False

                use_itm   = len(itm_paras) > 0 and not force_post    # ITM 계측값 경로 여부

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

                path  = 'ITM' if use_itm else ('Detrend(POST 강제)' if force_post and len(itm_paras) > 0 else 'Detrend')
                path += '+MA'   if use_moving_avg  else ''
                path += '+회귀' if has_regression  else ''
                print(f'    Thk_Para={Thk_Para} | 경로={path}')

                # ITM, moving avg, 회귀 중 아무것도 없으면 Pre_Thk_VM 학습 불필요 → 스킵
                if not use_itm and not use_moving_avg and not has_regression:
                    print(f'    → 스킵 (학습 불필요)')
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

                elif use_moving_avg:
                    # pre_oper1 설정됨: detrend + MA (pre_eqp 채널별 rolling mean)
                    # compute_detrend는 pre_eqp_id/pre_eqp_ch/pre_oper_time 컬럼이 필요하므로
                    # pre_oper1이 설정된 경우에만 호출
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

                    if not pre_thk_df_merge.empty and 'Detrend_Thk' in pre_thk_df_merge.columns:
                        pre_thk_df_merge = PRE_THK_VM_Get.iqr_filter(pre_thk_df_merge, 'Detrend_Thk')
                    min_count        = 5 if ('ED' in Thk_Para or 'EX' in Thk_Para) else 10
                    pre_thk_df_merge = PRE_THK_VM_Get.rolling_mean(pre_thk_df_merge, 'Detrend_Thk', Pre_Thk_Period, min_count)
                    pre_thk_table    = _extract_latest(pre_thk_df_merge, ['pre_oper_time', 'pre_eq_ch', 'Pre_Thk', 'Pre_Thk_Count', 'THK_Para'])
                    y_col            = 'Detrend_Thk'

                else:
                    # pre_oper1 미설정, pre_oper2~4 회귀만 산출
                    # pre_eqp 채널 데이터 없이 BIAS(CMP 두께 편차, 0-centered)를 y축으로 직접 회귀
                    # ITM·detrend 경로와 동일하게 use_pressure로 분기해야 함.
                    #  - PRESSURE(ED/EX): 13P 대비 편차를 0-centering
                    #  - TIME(13P)     : 자기 자신 단독 0-centering
                    #    (13P는 Thk_Para == Thk_Para_13P 이므로 pressure 식을 쓰면
                    #     자기 자신을 빼 BIAS가 항상 0이 되어 학습값이 0으로 나오는 버그 발생)
                    ref          = key_df.iloc[0]
                    use_pressure = (key_df['FB_Type'] == 'PRESSURE').any()
                    if use_pressure:
                        Post_Target  = float(ref['Target'])
                        Target_13P   = mico_info_key[(mico_info_key['Recipe_ID'] == ref['Recipe_ID']) & (mico_info_key['FB_Type'] == 'TIME')]['Target'].unique()[0]
                        merge_df['BIAS']  = (merge_df[Thk_Para] - merge_df[Thk_Para_13P]) - (Post_Target - Target_13P)
                    else:
                        merge_df['BIAS']  = merge_df[Thk_Para] - merge_df[Thk_Para].mean()
                    pre_thk_df_merge  = merge_df[['substrate_id', 'BIAS']].dropna().copy()
                    pre_thk_table     = pd.DataFrame([{'THK_Para': Thk_Para}])
                    y_col             = 'BIAS'

                # ITM/detrend 경로 공통: Pre_Oper2~4 회귀계수 산출
                # join key(substrate_id vs lot_id/alias_lot_id)는 fit_pre_oper_regression 내부에서 자동 판별
                if has_regression:
                    client = MongoClient(_MONGO_URL)
                    try:
                        raw = client[_MONGO_DB]['MICO_PRE_THK_INFO_' + Lot_Code + '_' + Oper_Desc + '_' + Fab].find({}, {'_id': 0})
                        pre2_df = pd.DataFrame(raw)
                    finally:
                        client.close()
                    # 구컬럼(samp_matl_id)과 신규 substrate_id 공존 시 하나로 병합(중복 컬럼 방지)
                    pre2_df = Get_data.coalesce_substrate_id(pre2_df)
                    # 같은 웨이퍼 중복 문서는 최신 1건만 유지(merge 시 행 증식 방지)
                    if 'substrate_id' in pre2_df.columns:
                        pre2_df = pre2_df.drop_duplicates(subset='substrate_id', keep='last')

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

                # ── [TEST 삭제] Excel 캐시 저장 블록 ────────────────────────────────
                # MongoDB 없는 로컬 환경에서 load_pre_thk_data 가 캐시를 읽을 수 있도록
                # pre_thk_cache/{Lot_Code}_{Oper_Desc}_{Fab}.xlsx 로 저장.
                # 회사 실서버에서는 MongoDB 에 직접 저장되므로 아래 블록 전체 삭제.
                _cache_dir = Path(__file__).parents[1] / 'pre_thk_cache'
                _cache_dir.mkdir(exist_ok=True)
                _cache_file = _cache_dir / f'{Lot_Code}_{Oper_Desc.replace(" ", "_")}_{Fab}.xlsx'
                _cache_df = pre_thk_table.copy()
                _cache_df['pre_oper_time'] = pd.Timestamp('1970-01-01')
                _cache_df.to_excel(_cache_file, index=False)
                print(f'    → Excel 저장: {_cache_file.name}')
                # ── [TEST 삭제 끝] ────────────────────────────────────────────────────

                print(f'    → 저장 {len(pre_thk_table)}건')
                show_cols = [c for c in ['pre_eq_ch', 'Pre_Thk', 'Count'] if c in pre_thk_table.columns]
                if show_cols:
                    print(pre_thk_table[show_cols].to_string(index=False))

        except Exception as e:
            tb = traceback.format_exc()
            c.sendMsg('', '506204179', f'{Fab} {Lot_Code} {Oper_Desc} Module PRE VM Failed : {e}, {tb}')

        print(f'  [Pre_Thk_VM] {Fab} | {Lot_Code} | {Oper_Desc} 완료')

    def compute_removal_rate(merge_df, mico_info_key, pol_type, RR_Alarm=None):
        # 단일 Lot_Code 공정의 Removal Rate 학습값 산출.
        # Maker별(AMAT/EBARA/KCT) EQP 채널을 구성하고 PM 이벤트 기준 pad rank를 계산한 뒤 compute_rr 호출.

        Fab       = mico_info_key['Fab'].unique()[0]
        Lot_Code  = mico_info_key['Lot_Code'].unique()[0]
        Oper_Desc = mico_info_key['Oper_Desc'].unique()[0]

        print(f'\n  [Removal Rate] {Fab} | {Lot_Code} | {Oper_Desc} 시작')
        try:
            Maker         = mico_info_key['Maker'].unique()[0]
            Pre_Oper_Code = mico_info_key['Pre_Oper_Code'].unique()[0]
            Thk_Para_List = mico_info_key['Thk_Para'].unique()
            Thk_Para_13P  = mico_info_key[mico_info_key['FB_Type'] == 'TIME']['Thk_Para'].unique()[0]

            pre_oper2_vals = mico_info_key['Pre_Oper_Code2'].dropna()
            has_pre_oper2  = len(pre_oper2_vals[pre_oper2_vals != '']) > 0

            if Pre_Oper_Code == '' and not has_pre_oper2:
                print(f'    Pre_Oper_Code 없음 → VM=0 처리')
                merge_df_rr = merge_df.copy()
                for Thk_key in Thk_Para_List:
                    merge_df_rr[Thk_key + '_VM'] = 0
                Pre_Oper_Code2 = mico_info_key['Pre_Oper_Code2'].iloc[0]
                if isinstance(Pre_Oper_Code2, str) and Pre_Oper_Code2 != '':
                    print(f'    Pre_Oper2 회귀 보정 적용 중 ...')
                    merge_df_rr = Removal_Rate_Get.apply_pre_oper2_correction(merge_df_rr, mico_info_key, _MONGO_URL, _MONGO_DB)
            else:
                print(f'    Pre_Thk_VM 로드 중 ...')
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

                print(f'    APC_Para={key.APC_Para} | Recipe_ID={Recipe_ID} | Thk_Para={Thk_Para}')
                merge_df_rr['BIAS'] = merge_df_rr[Thk_Para] - merge_df_rr[Thk_Para_13P] - (Post_Target - Target_13P)

                Removal_Rate_Get.compute_rr(merge_df_rr, key, pol_type, EQPM_df, RR_Alarm, mongo)

        except Exception as e:
            tb = traceback.format_exc()
            c.sendMsg('', '506204179', f'{Fab} {Lot_Code} {Oper_Desc} Module RR Failed : {e}, {tb}')

        print(f'  [Removal Rate] {Fab} | {Lot_Code} | {Oper_Desc} 완료')

    def compute_removal_rate_group(merge_df, mico_info_key, pol_type, RR_Alarm=None):
        # 그룹 공정용 Removal Rate 학습값 산출.
        # 복수 Lot_Code 데이터가 합산된 merge_df를 Lot_Code별로 순회하며 Pre_Thk_VM을 조회한 뒤 compute_rr_group 호출.

        Fab       = mico_info_key['Fab'].unique()[0]
        Lot_Code  = mico_info_key['Lot_Code'].unique()[0]
        Oper_Desc = mico_info_key['Oper_Desc'].unique()[0]

        print(f'\n  [Removal Rate Group] {Fab} | {Lot_Code} | {Oper_Desc} 시작')
        try:
            Maker         = mico_info_key['Maker'].unique()[0]
            Pre_Oper_Code = mico_info_key['Pre_Oper_Code'].unique()[0]
            Thk_Para_List = mico_info_key['Thk_Para'].unique()
            Thk_Para_13P  = mico_info_key[mico_info_key['FB_Type'] == 'TIME']['Thk_Para'].unique()[0]
            Lot_Code_List = merge_df['Lot_Code'].unique()

            pre_oper2_vals = mico_info_key['Pre_Oper_Code2'].dropna()
            has_pre_oper2  = len(pre_oper2_vals[pre_oper2_vals != '']) > 0

            if Pre_Oper_Code == '' and not has_pre_oper2:
                print(f'    Pre_Oper_Code 없음 → VM=0 처리')
                merge_df_rr = merge_df.copy()
                for Thk_key in Thk_Para_List:
                    merge_df_rr[Thk_key + '_VM'] = 0
                Pre_Oper_Code2 = mico_info_key['Pre_Oper_Code2'].iloc[0]
                if isinstance(Pre_Oper_Code2, str) and Pre_Oper_Code2 != '':
                    print(f'    Pre_Oper2 회귀 보정 적용 중 ...')
                    merge_df_rr = Removal_Rate_Get.apply_pre_oper2_correction(merge_df_rr, mico_info_key, _MONGO_URL, _MONGO_DB)
            else:
                merge_df_rr = pd.DataFrame()
                for lc in Lot_Code_List:
                    print(f'    Pre_Thk_VM 로드: Lot_Code={lc}', end=' ... ', flush=True)
                    merge_df_filter = merge_df[merge_df['Lot_Code'] == lc].copy()
                    merge_df_temp   = Removal_Rate_Get.load_pre_thk_data(merge_df_filter, mico_info_key, _MONGO_URL, _MONGO_DB)
                    merge_df_rr     = pd.concat([merge_df_rr, merge_df_temp])
                    print(f'{len(merge_df_temp)}행')
                print(f'    합산 데이터: {len(merge_df_rr)}행')

            EQPM_df = _build_eqpm_df(merge_df_rr, Maker, Fab)

            mongo = _make_rr_mongo(Lot_Code, Oper_Desc, Fab)

            search_key = mico_info_key[mico_info_key['Fab'] == Fab]
            for i in range(len(search_key)):
                key         = search_key.iloc[i, :]
                Thk_Para    = key['Thk_Para']
                Post_Target = float(key['Target'])
                Recipe_ID   = key['Recipe_ID']
                Target_13P  = mico_info_key[(mico_info_key['Recipe_ID'] == Recipe_ID) & (mico_info_key['FB_Type'] == 'TIME')]['Target'].unique()[0]

                print(f'    APC_Para={key.APC_Para} | Recipe_ID={Recipe_ID} | Thk_Para={Thk_Para}')
                merge_df_rr['BIAS'] = merge_df_rr[Thk_Para] - merge_df_rr[Thk_Para_13P] - (Post_Target - Target_13P)

                Removal_Rate_Get.compute_rr_group(merge_df_rr, key, pol_type, EQPM_df, RR_Alarm, mongo)

        except Exception as e:
            tb = traceback.format_exc()
            c.sendMsg('', '506204179', f'{Fab} {Lot_Code} {Oper_Desc} Module RR Group Failed : {e}, {tb}')

        print(f'  [Removal Rate Group] {Fab} | {Lot_Code} | {Oper_Desc} 완료')

    def compute_offset_group(merge_df, mico_info_key, pol_type):
        # 그룹 공정용 Offset 학습값 산출.
        # 레시피 구분 없이 합산 데이터로 IDLE 구간 Offset 계산, recipe별로 저장.
        #
        # APC_Para(플래튼)별로 나눠 호출한다. OFFSET_Get.compute_offset_group 은
        # search_keys.iloc[0] 의 APC_Para 하나만 보고 Pol/Pad 파라미터와 B1/B0 를
        # 고르므로, 여러 플래튼을 한 번에 넘기면 첫 번째 것만 학습되고 나머지는
        # 누락된다(저장 행의 APC_Para 도 전부 첫 값으로 찍힘).
        # → 단독 경로(compute_offset)가 search_key 를 행마다 도는 것과 같은 구조로 맞춘다.

        mico_info_key = mico_info_key[mico_info_key['FB_Type'] == 'TIME'].copy()

        Fab       = mico_info_key['Fab'].unique()[0]
        Lot_Code  = mico_info_key['Lot_Code'].unique()[0]
        Oper_Desc = mico_info_key['Oper_Desc'].unique()[0]

        print(f'\n  [Offset Group] {Fab} | {Lot_Code} | {Oper_Desc} 시작')
        try:
            APC_Para_List = mico_info_key['APC_Para'].unique()
            Offset_Group  = mico_info_key['Offset_Group'].unique()[0]
            search_key    = mico_info_key[mico_info_key['Fab'] == Fab]

            print(f'    APC_Para 목록: {list(APC_Para_List)} | Offset_Group={Offset_Group}')
            merge_df = OFFSET_Get.load_rr_data(merge_df, Fab, Lot_Code, Oper_Desc, APC_Para_List, _MONGO_URL, _MONGO_DB)

            results = []
            for apc in APC_Para_List:
                sub_keys = search_key[search_key['APC_Para'] == apc]
                if sub_keys.empty:
                    continue
                temp = OFFSET_Get.compute_offset_group(merge_df, sub_keys, pol_type, Fab)
                if temp is None:
                    print(f'    APC_Para={apc} → RR 데이터 없음, 스킵')
                    continue
                results.append(temp)

            if not results:
                print(f'    RR 데이터 없음 → Offset 계산 스킵')
                return

            temp_df = pd.concat(results, axis=0)
            OFFSET_Get.compute_lc_offset(temp_df, Lot_Code, Oper_Desc, Fab, Offset_Group)

        except Exception as e:
            tb = traceback.format_exc()
            c.sendMsg('', '506204179', f'{Fab} {Lot_Code} {Oper_Desc} Module Offset Group Failed : {e}, {tb}')

        print(f'  [Offset Group] {Fab} | {Lot_Code} | {Oper_Desc} 완료')

    def compute_offset(merge_df, mico_info_key, pol_type):
        # FB_Type=TIME 기준으로 Offset 학습값을 산출하고 MongoDB에 저장.

        mico_info_key = mico_info_key[mico_info_key['FB_Type'] == 'TIME'].copy()

        Fab       = mico_info_key['Fab'].unique()[0]
        Lot_Code  = mico_info_key['Lot_Code'].unique()[0]
        Oper_Desc = mico_info_key['Oper_Desc'].unique()[0]

        print(f'\n  [Offset] {Fab} | {Lot_Code} | {Oper_Desc} 시작')
        try:
            APC_Para_List = mico_info_key['APC_Para'].unique()
            Offset_Group  = mico_info_key['Offset_Group'].unique()[0]
            search_key    = mico_info_key[mico_info_key['Fab'] == Fab]

            print(f'    APC_Para 목록: {list(APC_Para_List)} | Offset_Group={Offset_Group}')
            merge_df = OFFSET_Get.load_rr_data(merge_df, Fab, Lot_Code, Oper_Desc, APC_Para_List, _MONGO_URL, _MONGO_DB)

            results      = [OFFSET_Get.compute_offset(merge_df, key, pol_type, Fab)
                            for _, key in search_key.iterrows()]
            valid_results = [r for r in results if r is not None]
            if not valid_results:
                print(f'    RR 데이터 없음 → Offset 계산 스킵')
                return

            temp_df = pd.concat(valid_results, axis=0)
            OFFSET_Get.compute_lc_offset(temp_df, Lot_Code, Oper_Desc, Fab, Offset_Group)

        except Exception as e:
            tb = traceback.format_exc()
            c.sendMsg('', '506204179', f'{Fab} {Lot_Code} {Oper_Desc} Module Offset Failed : {e}, {tb}')

        print(f'  [Offset] {Fab} | {Lot_Code} | {Oper_Desc} 완료')

    def check_alarm(
        mico_info_key,
        ):
        # Pre_Thk_VM / RR / Offset 최신 학습값을 이전 실적 대비 N-Sigma 기준으로 점검하여 이상 시 Cube 메시지 발송.
        Family    = mico_info_key['Family'].unique()[0]
        Lot_Code  = mico_info_key['Lot_Code'].unique()[0]
        oper_desc = mico_info_key['Oper_Desc'].unique()[0]
        Fab       = mico_info_key['Fab'].unique()[0]
        Channel_ID = mico_info_key['Channel_ID'].unique()[0]

        Default_Channel_ID = '507358454'
        Default_Sigma      = 10

        print(f'\n  [Alarm 점검] {Fab} | {Lot_Code} | {oper_desc} 시작')

        client = MongoClient(_MONGO_URL)
        try:
            db_name     = client[_MONGO_DB]
            Pre_VM_df   = pd.DataFrame(list(db_name['MICO_PRE_THK_'      + Lot_Code + '_' + oper_desc + '_' + Fab + '_Period'].find()))
            RR_df       = pd.DataFrame(list(db_name['MICO_Removal_Rate_'  + Lot_Code + '_' + oper_desc + '_' + Fab].find()))
            OFFSET_df   = pd.DataFrame(list(db_name['MICO_OFFSET_'        + Lot_Code + '_' + oper_desc + '_' + Fab].find()))
        finally:
            client.close()

        print(f'    DB 로드: Pre_Thk_VM={len(Pre_VM_df)}건 | Removal Rate={len(RR_df)}건 | Offset={len(OFFSET_df)}건')

        if RR_df.empty:
            print(f'    RR 데이터 없음 → 알람 점검 스킵')
            print(f'  [Alarm 점검] {Fab} | {Lot_Code} | {oper_desc} 완료')
            return

        def send_if_out_of_sigma(filtered_data, latest_value, alarm_para, Sigma, message):
            # 이전 실적 10건 이상일 때 최신값이 N-Sigma 및 절대 오차 0.1 초과 시 Cube 채널로 알람 발송
            mean  = filtered_data[alarm_para].mean()
            std   = filtered_data[alarm_para].std()
            count = filtered_data[alarm_para].nunique()

            if count >= 10:
                if (np.abs(latest_value - mean) > Sigma * std) & (np.abs(latest_value - mean) > 0.1):
                    message += f": 현재 학습값 [[ {latest_value:.2f} ]] 이 ** {Sigma}Sigma ** 기준으로 초과했습니다. ( 이전 실적값 : (( {mean:.2f} )) ) "
                    print(f'    !! 알람 발생: {message}')
                    Get_data.Cube_Alarm_Msg(Channel_ID, message)
                    Get_data.Cube_Alarm_Msg(Default_Channel_ID, message)

        RR_df = RR_df.sort_values(by='Date')

        # 점검 대상은 이 키가 학습한 (Recipe_ID, APC_Para) 조합뿐이다.
        # RR 컬렉션은 Lot_Code(=device)+Oper_Desc+Fab 단위라 같은 device 의 다른
        # 그룹·미그룹 recipe 행까지 함께 들어 있다. 그 행의 Sigma 는 mico_info_key
        # 에 없으므로(해당 recipe 는 그것을 학습하는 키가 점검한다) 걸러내지
        # 않으면 Sigma 조회가 0행이 되어 IndexError 로 파이프라인이 중단된다.
        sigma_map = {}
        for _, key_row in mico_info_key.iterrows():
            key_sigma = key_row['RR_Alarm_Sigma']
            sigma_map.setdefault(
                (key_row['Recipe_ID'], key_row['APC_Para']),
                Default_Sigma if pd.isna(key_sigma) else key_sigma,
            )

        idx = RR_df.groupby(['EQ', 'Recipe_ID', 'APC_Para'])['Date'].idxmax()
        latest_data = RR_df.loc[idx].reset_index(drop=True)

        in_scope = pd.Series(
            [(rcp, apc) in sigma_map
             for rcp, apc in zip(latest_data['Recipe_ID'], latest_data['APC_Para'])],
            index=latest_data.index, dtype=bool,
        )
        out_of_scope = sorted(set(zip(latest_data.loc[~in_scope, 'Recipe_ID'],
                                      latest_data.loc[~in_scope, 'APC_Para'])))
        latest_data = latest_data[in_scope].reset_index(drop=True)
        if out_of_scope:
            print(f'    점검 제외(이 키의 학습 대상 아님) {len(out_of_scope)}건: {out_of_scope}')
        if latest_data.empty:
            print(f'    점검 대상 없음 → 알람 점검 스킵')
            print(f'  [Alarm 점검] {Fab} | {Lot_Code} | {oper_desc} 완료')
            return

        alarm_para_list = latest_data.select_dtypes(include='float').columns.tolist()
        print(f'    RR 알람 점검: 최신 {len(latest_data)}건 | 파라미터={alarm_para_list}')

        for _, row in latest_data.iterrows():
            EQ        = row['EQ']
            Recipe_ID = row['Recipe_ID']
            APC_Para  = row['APC_Para']
            Sigma     = sigma_map[(Recipe_ID, APC_Para)]
            Module_name = 'Removal_Rate'

            for para in alarm_para_list:
                latest_value  = row[para]
                filtered_data = RR_df[
                    (RR_df['Recipe_ID'] == Recipe_ID) &
                    (RR_df['APC_Para']  == APC_Para)  &
                    (RR_df['Date']      <  row['Date'])
                ]
                message = f"{Lot_Code} / {oper_desc} / {Module_name} / {EQ} / {Recipe_ID} / {APC_Para} / {para} "
                send_if_out_of_sigma(filtered_data, latest_value, para, Sigma, message)

        print(f'  [Alarm 점검] {Fab} | {Lot_Code} | {oper_desc} 완료')

# ── Runner helpers ────────────────────────────────────────────────────────────

def _filter_merge_by_recipes(merge_df, recipe_ids, label):
    # merge_df(= Lot_Code 단위 컬렉션 전체)를 학습 대상 Recipe_ID 로 좁힌다.
    #
    # merge 컬렉션은 Lot_Code(=device)+Oper_Desc+Fab 단위라 한 Lot_Code 의 모든
    # recipe 실적이 함께 들어 있다. 그룹 학습(compute_*_group)은 집계 키가
    # eqp_id//Group_Name / (eqp_id, IDLE) 라 recipe 축이 없어서, 이 단계에서
    # 걸러주지 않으면 다른 그룹·미그룹 recipe 의 웨이퍼가 그대로 평균에 섞인다.
    # 단독 경로(compute_offset/compute_rr)는 자체 recipe 필터가 있지만, 여기서
    # 먼저 좁혀 두면 학습 대상이 로그로 드러나고 불필요한 연산도 준다.
    # ※ Pre_Thk_VM 은 pre_eq_ch 단위라 recipe 축이 없다 → 이 필터를 적용하지 않는다.
    if 'recipe_id' not in merge_df.columns:
        print(f'    [경고] merge_df 에 recipe_id 컬럼 없음 → {label} recipe 필터 미적용')
        return merge_df
    before   = len(merge_df)
    filtered = merge_df[merge_df['recipe_id'].isin(list(recipe_ids))].copy()
    print(f'    Recipe 필터({label}) {sorted(set(recipe_ids))}: {before}행 → {len(filtered)}행')
    return filtered


def _run_pipeline(merge_df_rcp, merge_df_vm, mico_info_key, use_group_rr=False):
    # Pre VM → RR → Offset → Alarm 순서로 학습 모듈 전체 실행
    #
    # merge_df_rcp : RR / Offset 용. 학습 대상 Recipe_ID 로 좁혀진 merge_df.
    # merge_df_vm  : Pre_Thk_VM 용. recipe 필터 이전의 merge_df.
    #   Pre_Thk_VM 은 사전공정 장비채널(pre_eq_ch) 단위 학습값이라 recipe 축이 없다.
    #   결과도 MICO_PRE_THK_{Lot_Code}_{Oper_Desc}_{Fab}_Period 에 pre_eq_ch 기준으로
    #   쌓이고, load_pre_thk_data 의 조인도 by=['pre_eq_ch'] 다.
    #   → recipe 로 좁히면 사전공정 표본만 줄고, 같은 Lot_Code 를 grouped/single 두
    #     경로가 나눠 처리할 때 한 컬렉션에 서로 다른 VM 이 쌓인다. 그래서 분리한다.
    # use_group_rr : True 면 그룹 공정용 RR/Offset(compute_*_group) 사용.
    lot_code  = mico_info_key['Lot_Code'].unique()[0]
    oper_desc = mico_info_key['Oper_Desc'].unique()[0]
    fab       = mico_info_key['Fab'].unique()[0]

    # Category.pol_type (web DB set-up 값)에서 pol_type 결정
    pol_type_vals = mico_info_key['Pol_Type'].dropna().unique()
    pol_type = int(pol_type_vals[0]) if len(pol_type_vals) > 0 else None

    print(f'\n{"=" * 60}')
    print(f'  파이프라인 시작: {fab} | {lot_code} | {oper_desc}')
    print(f'{"=" * 60}')
    try:
        Module_Get.compute_pre_thk_vm(merge_df_vm, mico_info_key, pol_type)
        if use_group_rr:
            Module_Get.compute_removal_rate_group(merge_df_rcp, mico_info_key, pol_type)
            Module_Get.compute_offset_group(merge_df_rcp, mico_info_key, pol_type)
        else:
            Module_Get.compute_removal_rate(merge_df_rcp, mico_info_key, pol_type)
            Module_Get.compute_offset(merge_df_rcp, mico_info_key, pol_type)
        Module_Get.check_alarm(mico_info_key)
    except Exception as e:
        tb = traceback.format_exc()
        Get_data.Cube_Msg(lot_code, oper_desc, 'Module', e, tb)

    print(f'{"=" * 60}')
    print(f'  파이프라인 완료: {fab} | {lot_code} | {oper_desc}')
    print(f'{"=" * 60}')


def _run_single(mico_info_table, for_key_list):
    # 그룹 미지정 공정: for_key_list 키마다 독립적으로 merge_df 를 조회 후 실행
    #
    # for_key_list(Lot_Code+Oper_Code+Fab)에는 recipe 축이 없어 같은 Lot_Code 의
    # '그룹에 속한 recipe'까지 함께 걸린다. Group_Name='not_group' 조건을 더해
    # 미그룹 recipe 만 단독 학습하도록 한다.
    total = len(for_key_list)
    for idx, key in enumerate(for_key_list, 1):
        mico_info_key = mico_info_table[
            (mico_info_table['for_key_list'] == key) &
            (mico_info_table['Group_Name']   == 'not_group')
        ].copy()
        if mico_info_key.empty:
            continue

        # for_key_list 는 Lot_Code+Oper_Code+Fab 를 '_' 로 이어붙인 문자열이라
        # 되쪼개면 세 값 중 하나라도 '_' 를 포함할 때 잘못 나뉜다.
        # (예: Oper_Code='OP_01' → 'E2_OP_01_M10'.split('_') → oper_code='OP')
        # 그 경우 아래 operation_id 필터가 0행이 되어 학습이 조용히 통째로 누락된다.
        # → 키를 파싱하지 않고 원본 컬럼에서 직접 읽는다.
        oper_code = mico_info_key['Oper_Code'].unique()[0]

        print(f'\n[{idx}/{total}] {key}')
        # merge_df_vm : recipe 필터 전(= 이 Lot_Code 전체) → Pre_Thk_VM 용
        merge_df_vm = Module_Get.fetch_merge_data(mico_info_key)
        if merge_df_vm is None or merge_df_vm.empty:
            print(f'    → 조회 데이터 없음 (0행), 스킵')
            continue

        merge_df_vm = merge_df_vm[merge_df_vm['operation_id'] == oper_code].copy()
        print(f'    Oper 필터 후: {len(merge_df_vm)}행')
        if merge_df_vm.empty:
            print(f'    → Oper 필터 후 데이터 없음 (0행), 스킵')
            continue

        # merge_df_rcp : 학습 대상 recipe 로 좁힌 것 → RR / Offset 용
        merge_df_rcp = _filter_merge_by_recipes(
            merge_df_vm, mico_info_key['Recipe_ID'].unique(), '단독')
        if merge_df_rcp.empty:
            print(f'    → recipe 필터 후 데이터 없음 (0행), 스킵')
            continue

        _run_pipeline(merge_df_rcp, merge_df_vm, mico_info_key)


def _run_grouped(mico_info_table, group_name):
    # 그룹 지정 공정: 같은 Group_Name의 모든 키 데이터를 먼저 합산(merge_df_vm)한 후
    # 각 mico_info_key에 동일한 merge_df로 실행 → Group RR처럼 복수 Lot_Code 통합 처리
    mico_info_keys = []
    # merge_df_vm : 그룹의 모든 키를 합산한 것(= recipe 필터 전) → Pre_Thk_VM 용
    merge_df_vm    = pd.DataFrame()
    for_key_list   = mico_info_table[mico_info_table['Group_Name'] == group_name]['for_key_list'].unique()

    # 그룹 전체(복수 Lot_Code 가능)의 Recipe_ID — merge_df_vm 을 이 집합으로 좁혀
    # merge_df_rcp 를 만든다. mico_info_key 는 Lot_Code 단위로 쪼개지지만
    # merge_df_vm 은 그룹 전체가 합쳐진 것이므로, 필터 기준은 개별 키가 아니라
    # '그룹 전체 recipe' 여야 한다.
    group_recipes = mico_info_table[
        mico_info_table['Group_Name'] == group_name]['Recipe_ID'].unique()

    print(f'\n[그룹: {group_name}] 키 {len(for_key_list)}개 데이터 통합 중')
    for key in for_key_list:
        mico_info_key = mico_info_table[
            (mico_info_table['for_key_list'] == key) &
            (mico_info_table['Group_Name']   == group_name)
        ].copy()
        if mico_info_key.empty:
            continue
        mico_info_keys.append(mico_info_key)

        temp = Module_Get.fetch_merge_data(mico_info_key)
        if temp is not None and not temp.empty:
            temp['Fab'] = mico_info_key['Fab'].unique()[0]
            merge_df_vm = pd.concat([merge_df_vm, temp])

    if merge_df_vm.empty:
        print(f'  → 그룹 통합 데이터 없음 (0행), 스킵')
        return

    # merge_df_rcp : 그룹 전체 recipe 로 좁힌 것 → RR / Offset 용
    merge_df_rcp = _filter_merge_by_recipes(merge_df_vm, group_recipes, f'그룹 {group_name}')
    merge_df_rcp['Group_Name'] = group_name
    print(f'  그룹 통합 완료: {len(merge_df_rcp)}행')
    if merge_df_rcp.empty:
        print(f'  → 그룹 recipe 필터 후 데이터 없음 (0행), 스킵')
        return

    for mico_info_key in mico_info_keys:
        _run_pipeline(merge_df_rcp, merge_df_vm, mico_info_key, use_group_rr=True)


def run(family, oper_desc):
    # 최상위 진입점: set-up 정보 로드 → for_key_list(Lot_Code+Oper_Code+Fab) 생성
    # → Group 여부에 따라 _run_single / _run_grouped 분기
    # pol_type은 Category.pol_type (web DB set-up 값)에서 자동으로 읽어옴
    print(f'\n{"#" * 60}')
    print(f'  MICO 학습 시작: Family={family} | Oper_Desc={oper_desc}')
    print(f'{"#" * 60}')
    try:
        mico_info_table = Get_data.baseinfoGetData(Family=family, oper_desc=oper_desc)
        mico_info_table['Group_Name'] = mico_info_table['Group_Name'].fillna('not_group')
        mico_info_table['for_key_list'] = (
            mico_info_table['Lot_Code'] + '_' +
            mico_info_table['Oper_Code'] + '_' +
            mico_info_table['Fab']
        )

        key_list = mico_info_table['for_key_list'].unique()
        print(f'  처리 키 목록 ({len(key_list)}개):')
        for k in key_list:
            grps     = sorted(mico_info_table[mico_info_table['for_key_list'] == k]['Group_Name'].unique())
            grp      = ', '.join(grps)
            pol_vals = mico_info_table[mico_info_table['for_key_list'] == k]['Pol_Type'].dropna().unique()
            pol_label = f'pol_type={int(pol_vals[0])}' if len(pol_vals) > 0 else 'pol_type=미설정'
            grp_label = f'그룹={grp}' if grps != ['not_group'] else '단독'
            print(f'    - {k}  ({grp_label} | {pol_label})')

        for group_name in mico_info_table['Group_Name'].unique():
            for_key_list = mico_info_table[mico_info_table['Group_Name'] == group_name]['for_key_list'].unique()

            if group_name == 'not_group':
                _run_single(mico_info_table, for_key_list)
            else:
                _run_grouped(mico_info_table, group_name)

    except Exception as e:
        tb = traceback.format_exc()
        Get_data.Cube_Msg(family, oper_desc, 'Module', e, tb)

    print(f'\n{"#" * 60}')
    print(f'  MICO 학습 완료: Family={family} | Oper_Desc={oper_desc}')
    print(f'{"#" * 60}')
