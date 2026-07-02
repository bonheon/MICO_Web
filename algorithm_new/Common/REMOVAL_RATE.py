import sys, os
from pathlib import Path
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))
from Common.Get_Data import Get_data
from Common.MongoDB_Control import mongodb_controller
from sklearn.linear_model import LinearRegression
from datetime import datetime, timedelta, date
import pandas as pd
import numpy as np
from pymongo import MongoClient


class Removal_Rate_Get:


    def _detect_cycles(temp_data, consumable_Para):
        # EQP/Recipe 조합별 소모품 급감(교체) 기준으로 pad cycle 번호를 부여하여 반환
        temp_data['eq_recipe'] = temp_data['eqp_id'] + '//' + temp_data['recipe_id']
        temp_data3 = pd.DataFrame()

        for eq_rcp in temp_data['eq_recipe'].unique():
            EQP_ID     = eq_rcp.split('//')[0]
            RCP_ID     = eq_rcp.split('//')[1]
            temp_data2 = temp_data[(temp_data['eqp_id'] == EQP_ID) & (temp_data['recipe_id'] == RCP_ID)].sort_values(by='Date').reset_index(drop=True)
            raw = (temp_data2[consumable_Para].diff() < -3).cumsum()
            temp_data2['cycle'] = raw.max() + 1 - raw
            temp_data3 = temp_data2 if temp_data3.empty else pd.concat([temp_data3, temp_data2])

        return temp_data3


    def _check_rr_alarm(temp_data5, APC_Para, EQ, rcp_id):
        # TIME 파라미터 한정으로 최근 3건 RR 평균이 전체 3Sigma 범위를 이탈하면 Cube 알람 발송
        if 'TIME' not in APC_Para:
            return
        rr_sigma  = 3
        rr        = temp_data5.sort_values(by='Date', ascending=False)['RR']
        rr_recent = rr.iloc[:3].mean()
        ucl       = rr.mean() + rr.std() * rr_sigma
        lcl       = rr.mean() - rr.std() * rr_sigma
        if rr_recent > ucl:
            Get_data.Cube_Msg_RR_Alarm(EQ, rcp_id, f'현재 Removal Rate 값이 기준 대비 {rr_sigma}Sigma 이상 올라가고 있습니다.')
        if rr_recent < lcl:
            Get_data.Cube_Msg_RR_Alarm(EQ, rcp_id, f'현재 Removal Rate 값이 기준 대비 {rr_sigma}Sigma 이상 내려가고 있습니다.')


    def _fit_lr(df, x_col, y_col, lr):
        # 단순선형회귀 공통 래퍼. (b1, b0) 반환
        lr.fit(df[x_col].values.reshape(-1, 1), df[y_col].values.reshape(-1, 1))
        return round(lr.coef_[0][0], 4), round(lr.intercept_[0], 4)


    def _fit_weighted(temp_data5, consumable_Para, weight, include_recent, lr):
        # 최근 구간에 가중치를 부여한 회귀. include_recent 조건 불충족 시 '-' 반환
        if not include_recent:
            return '-', '-'
        repeat = temp_data5['group'].map(lambda g: weight[g])
        X_w    = np.repeat(temp_data5[consumable_Para], repeat).values.reshape(-1, 1)
        y_w    = np.repeat(temp_data5['RR'],            repeat)
        model  = lr.fit(X_w, y_w)
        return round(model.coef_[0], 4), round(model.intercept_, 4)


    def _get_current_cycle(temp_data5, consumable_Para, RR_Period):
        # 현재 패드 사이클(cycle==1) 데이터 추출. RR_Period가 있으면 해당 구간만 반환
        cycle1 = temp_data5[temp_data5['cycle'] == 1]
        if cycle1.empty:
            return pd.DataFrame()
        if pd.isna(RR_Period):
            return cycle1
        threshold = cycle1[consumable_Para].iloc[0] - float(RR_Period)
        return temp_data5[(temp_data5['cycle'] == 1) & (temp_data5[consumable_Para] >= threshold)]


    def _get_pm_rank(EQPM_df, Maker, EQ, rcp_id):
        # Maker별 EQP 채널 키를 구성하여 최신 PM 이후 누적 웨이퍼 수(rank) 반환
        if Maker == 'AMAT':
            eqp_key = EQ
        elif Maker == 'EBARA':
            eqp_key = EQ + ('_AB' if '_AB' in rcp_id else '_CD')
        elif Maker == 'KCT':
            eqp_key = EQ + ('_L' if '_L' in rcp_id else '_R')
        return EQPM_df[EQPM_df['EQP_ID'] == eqp_key].sort_values(by='EVENT_TM', ascending=False)['rank'].iloc[0]


    def _fit_current(current_cycle, consumable_Para, today_date, RR_Count,
                     EQPM_df, Maker, EQ, rcp_id,
                     weighted_b1, weighted_b0, b1, b0, RR_Period, lr):
        # 현재 사이클 회귀. 데이터 수·경과시간·PM rank 조건 불충족 시 '-' 반환
        if current_cycle.empty:
            return '-', '-', '-'
        count      = len(current_cycle)
        time_delta = today_date - current_cycle['Date'].iloc[-1]   # 최신 타점 기준 경과시간
        min_count  = Removal_Rate_Get._get_pm_rank(EQPM_df, Maker, EQ, rcp_id)
        if not ((count > RR_Count) and (time_delta < timedelta(hours=12)) and (min_count >= 2)):
            return '-', '-', '-'
        Simul_Date             = current_cycle['Date'].iloc[-1].strftime("%Y-%m-%d %H:%M:%S")
        current_b1, current_b0 = Removal_Rate_Get._fit_lr(current_cycle, consumable_Para, 'RR', lr)
        if pd.isna(RR_Period):
            range_b1   = weighted_b1 if weighted_b1 != '-' else b1
            range_b0   = weighted_b0 if weighted_b0 != '-' else b0
            current_b1 = min(current_b1, range_b1 * 2) if range_b1 >= 0 else max(current_b1, range_b1 * 2)
            current_b1 = max(current_b1, 0)            if range_b1 >= 0 else min(current_b1, 0)
            current_b0 = max(range_b0 * 0.9, min(current_b0, range_b0 * 1.1))
        return Simul_Date, current_b1, current_b0


    def _fit_if(temp_data5, consumable_Para, Pad_Seperation, lr):
        # Pad_Seperation 이하 구간 한정 회귀(IF 모델). 데이터 부족 시 '-' 반환
        if pd.isna(Pad_Seperation):
            return '-', '-'
        Pad_Seperation = int(Pad_Seperation)
        temp_data7     = temp_data5[temp_data5[consumable_Para] <= Pad_Seperation]
        if len(temp_data7) < 100:
            return '-', '-'
        step      = Pad_Seperation / 4
        if_counts = pd.cut(
            temp_data7[consumable_Para],
            bins=[0, step, step * 2, step * 3, Pad_Seperation],
            labels=['Q1', 'Q2', 'Q3', 'Q4']
        ).value_counts()
        if not (if_counts >= 25).all():
            return '-', '-'
        return Removal_Rate_Get._fit_lr(temp_data7, consumable_Para, 'RR', lr)


    def _process_models(temp_data3, key, today, consumable_Para, Pol_Para,
                              Head_Para, Pad_Para, Disk_Para,
                              EQPM_df, RR_Alarm, mongo, lr, group_mode=False):
        # eqp_model 루프 + 내부 순회 공통 연산.
        # group_mode=False → compute_rr 경로(eq_recipe 기준), True → compute_rr_group 경로(rr_key 기준)

        Fab            = key.Fab
        Lot_Code       = key.Lot_Code
        Oper_Code      = key.Oper_Code
        Oper_Desc      = key.Oper_Desc
        APC_Para       = key.APC_Para
        Recipe_ID      = key.Recipe_ID
        Thk_Para       = key.Thk_Para
        Pre_Thk_Para   = key.Pre_Thk_Para_ITM
        Maker          = key.Maker
        RR_Para_Max    = key.RR_Para_Max
        Pre_Target     = key.Pre_Target
        Post_Target    = float(key.Target)
        RR_Weight      = float(key.RR_Weight)
        RR_Count       = float(key.RR_Count)
        RR_Period      = key.RR_Period
        Pad_Seperation = key.Pad_Seperation

        if pd.notna(RR_Para_Max):
            RR_Para_Max = float(RR_Para_Max)
        if pd.notna(Pre_Target):
            Pre_Target = float(Pre_Target)

        no_pre_thk   = Pre_Thk_Para == '' or pd.isna(Pre_Thk_Para)
        is_bias_type = key.FB_Type == 'PRESSURE'
        vm_col       = (Thk_Para if no_pre_thk else Pre_Thk_Para) + '_VM'
        iter_col     = 'rr_key' if group_mode else 'eq_recipe'

        for x in temp_data3['eqp_model'].unique():
            temp_data4 = temp_data3[temp_data3['eqp_model'] == x].copy()

            part_max = temp_data4[consumable_Para].max()
            part_min = temp_data4[consumable_Para].min()
            if pd.notna(RR_Para_Max):
                part_max = RR_Para_Max
            part_1q = part_min + (part_max - part_min) / 4
            part_2q = part_min + (part_max - part_min) / 2
            part_3q = part_min + (part_max - part_min) * 3 / 4

            col_list = ['Date', 'substrate_id', 'eqp_id', 'recipe_id', 'process_id',
                        Pad_Para, Head_Para, Disk_Para, 'pre_eq_ch',
                        vm_col, Thk_Para, 'cycle', 'BIAS'] + Pol_Para
            if group_mode:
                col_list.append('Group_Name')
            temp_data4 = temp_data4[col_list].copy()
            temp_data4.drop_duplicates(inplace=True)

            temp_data4['Pol_Time'] = temp_data4[Pol_Para].sum(axis=1)
            temp_data4.dropna(axis=0, subset=[Thk_Para, consumable_Para], inplace=True)
            temp_data4.drop(temp_data4[temp_data4['Pol_Time'] == 0].index, inplace=True)

            temp_data4.fillna(value={vm_col: 0}, inplace=True)
            vm     = temp_data4[vm_col]
            is_rev = no_pre_thk and 'REV' in Thk_Para

            pre_thk  = Pre_Target + vm
            post_thk = (Post_Target + temp_data4['BIAS']) if is_bias_type else temp_data4[Thk_Para]

            temp_data4['RR'] = ((post_thk - pre_thk) if is_rev else (pre_thk - post_thk)) / temp_data4['Pol_Time']

            if group_mode:
                temp_data4['rr_key']    = temp_data4['eqp_id'] + '//' + temp_data4['Group_Name']
            else:
                temp_data4['eq_recipe'] = temp_data4['eqp_id'] + '//' + temp_data4['recipe_id']

            rr_avg = temp_data4['RR'].mean()
            rr_std = temp_data4['RR'].std()
            sigma  = 6
            temp_data4 = temp_data4[(temp_data4['RR'] < rr_avg + rr_std * sigma)
                                   & (temp_data4['RR'] > rr_avg - rr_std * sigma)].copy()

            for iter_val in temp_data4[iter_col].unique():
                temp_data5 = temp_data4[temp_data4[iter_col] == iter_val].copy()
                Count = len(temp_data5)
                if Count < 10:
                    continue

                EQ     = iter_val.split('//')[0]
                rcp_id = iter_val.split('//')[1] if not group_mode else Recipe_ID

                if RR_Alarm is not None:
                    Removal_Rate_Get._check_rr_alarm(temp_data5, APC_Para, EQ, rcp_id)

                temp_data5['group']         = pd.cut(temp_data5['Date'], bins=5, labels=False)
                temp_data5['date_seg']      = pd.cut(temp_data5['Date'], bins=5, labels=[0,1,2,3,4]).astype(str)
                temp_data5['part_seg']      = pd.cut(temp_data5[consumable_Para], bins=4, labels=[0,1,2,3]).astype(str)
                temp_data5['date_part_seg'] = temp_data5['date_seg'] + '_' + temp_data5['part_seg']

                seg_counts     = temp_data5.groupby(['eqp_id', 'date_part_seg']).size().reset_index(name='count')
                recent_counts  = seg_counts[seg_counts['date_part_seg'].str.startswith('4_')]
                include_recent = (len(recent_counts['date_part_seg'].unique()) == 4) and (recent_counts['count'] > 25).all()

                weight    = [1, 2, 3, 4, RR_Weight]

                quartile_counts = pd.cut(
                    temp_data5[consumable_Para],
                    bins=[part_min, part_1q, part_2q, part_3q, part_max],
                    labels=['Q1', 'Q2', 'Q3', 'Q4']
                ).value_counts()

                if (quartile_counts > 25).all():
                    b1, b0                             = Removal_Rate_Get._fit_lr(temp_data5, consumable_Para, 'RR', lr)
                    weighted_b1, weighted_b0           = Removal_Rate_Get._fit_weighted(temp_data5, consumable_Para, weight, include_recent, lr)

                    current_cycle                      = Removal_Rate_Get._get_current_cycle(temp_data5, consumable_Para, RR_Period)
                    Simul_Date, current_b1, current_b0 = Removal_Rate_Get._fit_current(
                        current_cycle, consumable_Para, datetime.now(),
                        RR_Count, EQPM_df, Maker, EQ, rcp_id,
                        weighted_b1, weighted_b0, b1, b0, RR_Period, lr
                    )

                    if_b1, if_b0                       = Removal_Rate_Get._fit_if(temp_data5, consumable_Para, Pad_Seperation, lr)

                    report = {'Date': today, 'Fab': Fab, 'Lot_Code': Lot_Code,
                              'Oper_Code': Oper_Code, 'Oper_Desc': Oper_Desc, 'APC_Para': APC_Para,
                              'EQ': EQ, 'Recipe_ID': rcp_id, 'Count': Count, 'b1': b1, 'b0': b0,
                              'b1_weighted': weighted_b1, 'b0_weighted': weighted_b0,
                              'Simul_Date': Simul_Date, 'b1_current': current_b1, 'b0_current': current_b0,
                              'if_b1': if_b1, 'if_b0': if_b0}
                    report = {k: v for k, v in report.items() if v != '-'}
                    mongo.insert_row(report)


    def compute_rr(merge_df, key, pol_type, EQPM_df, RR_Alarm, mongo):
        # 단일 공정(EQP/Recipe) 기준 Removal Rate 학습값 산출.
        # IDLE='' 데이터만 사용, 소모품 사이클 분리 후 EQP별로 회귀계수(b1/b0) 계산하여 MongoDB 저장.

        lr        = LinearRegression()
        today     = datetime.now()
        Oper_Code = key.Oper_Code
        APC_Para  = key.APC_Para
        Recipe_ID = key.Recipe_ID
        RR_Para   = key.RR_Para

        Pol_Para  = Get_data.APCParaGet(APC_Para, pol_type)
        Head_Para = Get_data.HeadParaGet(APC_Para)
        Pad_Para  = Get_data.PadParaGet(APC_Para)
        Disk_Para = Get_data.DiskParaGet(APC_Para)
        RR_Para   = RR_Para.upper()

        if RR_Para == 'HEAD':
            consumable_Para = Head_Para
        elif RR_Para == 'PAD':
            consumable_Para = Pad_Para
        elif RR_Para == 'DISK':
            consumable_Para = Disk_Para

        temp_data = merge_df[
            (merge_df['operation_id'] == Oper_Code) &
            (merge_df['recipe_id'] == Recipe_ID) &
            ((merge_df['IDLE'] == '') | (merge_df['IDLE'].isna()))
        ].copy()

        temp_data3 = Removal_Rate_Get._detect_cycles(temp_data, consumable_Para)
        if temp_data3.empty:
            return None

        Removal_Rate_Get._process_models(
            temp_data3, key, today, consumable_Para, Pol_Para,
            Head_Para, Pad_Para, Disk_Para,
            EQPM_df, RR_Alarm, mongo, lr, group_mode=False
        )


    def compute_rr_group(merge_df, key, pol_type, EQPM_df, RR_Alarm, mongo):
        # 복수 Lot_Code를 통합한 그룹 공정용 Removal Rate 학습값 산출.
        # compute_rr와 달리 Recipe 구분 없이 eqp+Group_Name(rr_key) 기준으로 집계.

        lr       = LinearRegression()
        today    = datetime.now()
        APC_Para = key.APC_Para
        RR_Para  = key.RR_Para

        Pol_Para  = Get_data.APCParaGet(APC_Para, pol_type)
        Head_Para = Get_data.HeadParaGet(APC_Para)
        Pad_Para  = Get_data.PadParaGet(APC_Para)
        Disk_Para = Get_data.DiskParaGet(APC_Para)
        RR_Para   = RR_Para.upper()

        if RR_Para == 'HEAD':
            consumable_Para = Head_Para
        elif RR_Para == 'PAD':
            consumable_Para = Pad_Para
        elif RR_Para == 'DISK':
            consumable_Para = Disk_Para

        temp_data = merge_df[
            ((merge_df['IDLE'] == '') | (merge_df['IDLE'].isna()))
        ].copy()

        temp_data3 = Removal_Rate_Get._detect_cycles(temp_data, consumable_Para)
        if temp_data3.empty:
            return None

        Removal_Rate_Get._process_models(
            temp_data3, key, today, consumable_Para, Pol_Para,
            Head_Para, Pad_Para, Disk_Para,
            EQPM_df, RR_Alarm, mongo, lr, group_mode=True
        )


    def load_pre_thk_data(merge_df, mico_info_key, mongo_url, mongo_db):
        # MongoDB에서 Pre_Thk_VM 학습값(_Period 컬렉션)을 로드하여 merge_df에 merge_asof로 결합.
        # Pre_Oper2~4 회귀계수(b1/b0)가 존재하면 해당 공정 측정값에 적용하여 _VM 컬럼을 보정 후 반환.

        Fab       = mico_info_key['Fab'].unique()[0]
        Lot_Code  = mico_info_key['Lot_Code'].unique()[0]
        Oper_Desc = mico_info_key['Oper_Desc'].unique()[0]

        # ── [TEST 삭제] Excel 캐시 분기 ──────────────────────────────────────
        # 로컬 환경에서 MongoDB 없이 pre_thk_cache/*.xlsx 를 대신 읽는 분기.
        # 회사 실서버에서는 MongoDB 에서 직접 읽으므로 아래 if 블록 전체(들여쓰기 포함) 삭제.
        # 삭제 범위: _cache_dir / _cache_file 선언부터 "return merge_df" 까지.
        _cache_dir = Path(__file__).parents[1] / 'pre_thk_cache'
        _cache_file = _cache_dir / f'{Lot_Code}_{Oper_Desc.replace(" ", "_")}_{Fab}.xlsx'

        if _cache_file.exists():
            print(f'    [Excel 캐시] {_cache_file.name} 로드')
            Pre_Thk_Table = pd.read_excel(_cache_file, parse_dates=['pre_oper_time'])
            # ITM 학습 시 Pre_THK_Para(ITM 파라)와 THK_Para(후공정 파라)가 모두 적재된 경우,
            # THK_Para를 제거하고 Pre_THK_Para를 THK_Para로 정규화하여 VM 컬럼명 일치
            if 'Pre_THK_Para' in Pre_Thk_Table.columns:
                Pre_Thk_Table = Pre_Thk_Table.drop(columns='THK_Para', errors='ignore')
                Pre_Thk_Table.rename(columns={'Pre_THK_Para': 'THK_Para', 'pre_oper_time': 'Pre_Oper_Date'}, inplace=True)
            Pre_Thk_Table.rename(columns={'pre_oper_time': 'Pre_Oper_Date'}, inplace=True)
            has_pre_thk = 'Pre_Thk' in Pre_Thk_Table.columns  # MA 기반 VM 존재 여부

            merge_df = merge_df.copy()
            merge_df.rename(columns={'request_dtts': 'Date'}, inplace=True)

            if has_pre_thk:
                Pre_Thk_Table['Pre_Oper_Date'] = pd.to_datetime(Pre_Thk_Table['Pre_Oper_Date'])
                merge_df.rename(columns={'pre_oper_time': 'Pre_Oper_Date'}, inplace=True)
                merge_df.dropna(subset=['Pre_Oper_Date'], inplace=True)
                merge_df['Pre_Oper_Date'] = pd.to_datetime(merge_df['Pre_Oper_Date'])
                merge_df = merge_df.sort_values(by='Pre_Oper_Date', ascending=True)

            for Thk_key in Pre_Thk_Table['THK_Para'].unique():
                key = mico_info_key[
                    (mico_info_key['Thk_Para'] == Thk_key) |
                    (mico_info_key['Pre_Thk_Para_ITM'] == Thk_key)
                ].copy()

                if has_pre_thk:
                    temp_pre_thk = Pre_Thk_Table[Pre_Thk_Table['THK_Para'] == Thk_key].drop(
                        columns=[c for c in ['Date', 'THK_Para', 'Oper_Code'] if c in Pre_Thk_Table.columns]
                    )
                    temp_pre_thk = temp_pre_thk.sort_values(by='Pre_Oper_Date', ascending=True)
                    temp_pre_thk.rename(columns={'Pre_Thk': Thk_key + '_VM', 'Count': Thk_key + '_Count'}, inplace=True)

                    cols_to_drop = [c for c in merge_df.columns if c.endswith('_x') or c.endswith('_y')]
                    merge_df = merge_df.drop(columns=cols_to_drop)
                    merge_df = pd.merge_asof(merge_df, temp_pre_thk, on='Pre_Oper_Date', by=['pre_eq_ch'])
                    merge_df.drop_duplicates(subset=['substrate_id'], inplace=True)
                    print(f'    → {Thk_key}_VM: {merge_df[Thk_key+"_VM"].notna().sum()}/{len(merge_df)} 매칭')
                else:
                    # pre_oper1 미설정: MA 기반 VM 없음 → 0 초기화 후 회귀 보정만 적용
                    merge_df[Thk_key + '_VM'] = 0.0
                    row_ptk = Pre_Thk_Table[Pre_Thk_Table['THK_Para'] == Thk_key].iloc[0]
                    for prefix in ['PRE_OPER2', 'PRE_OPER3', 'PRE_OPER4']:
                        b1_col, b0_col = f'{prefix}_b1', f'{prefix}_b0'
                        if b1_col in row_ptk.index and not pd.isna(row_ptk[b1_col]):
                            merge_df[b1_col] = float(row_ptk[b1_col])
                            merge_df[b0_col] = float(row_ptk[b0_col]) if b0_col in row_ptk.index and not pd.isna(row_ptk[b0_col]) else 0.0
                    print(f'    → {Thk_key}_VM: pre_oper1 미설정, 회귀 보정만 적용')

                ref = key.iloc[0]
                for desc, para, prefix, weight in [
                    (ref['Pre_Oper_Desc2'], ref['Pre_Oper_Para2'], 'PRE_OPER2', 1),
                    (ref['Pre_Oper_Desc3'], ref['Pre_Oper_Para3'], 'PRE_OPER3', 1),
                    (ref['Pre_Oper_Desc4'], ref['Pre_Oper_Para4'], 'PRE_OPER4', 1),
                ]:
                    if not (isinstance(desc, str) and desc != ''):
                        continue
                    b1_col, b0_col = f'{prefix}_b1', f'{prefix}_b0'
                    merge_df[[b1_col, b0_col]] = merge_df[[b1_col, b0_col]].fillna(
                        merge_df[[b1_col, b0_col]].mean()
                    ).fillna(0)
                    merge_df[Thk_key + '_VM'] += weight * (
                        merge_df[desc + '.' + para] * merge_df[b1_col] + merge_df[b0_col]
                    )
                    merge_df.drop(columns=[b1_col, b0_col], inplace=True)

            return merge_df
        # ── [TEST 삭제 끝] ────────────────────────────────────────────────────

        client = MongoClient(mongo_url)
        try:
            db = client[mongo_db]

            period_col    = 'MICO_PRE_THK_' + Lot_Code + '_' + Oper_Desc + '_' + Fab + '_Period'
            Pre_Thk_Table = pd.DataFrame(list(db[period_col].find({}, {'_id': False})))
            # ITM 학습 시 Pre_THK_Para(ITM 파라)와 THK_Para(후공정 파라)가 모두 적재된 경우,
            # THK_Para를 제거하고 Pre_THK_Para를 THK_Para로 정규화하여 VM 컬럼명 일치
            if 'Pre_THK_Para' in Pre_Thk_Table.columns:
                Pre_Thk_Table = Pre_Thk_Table.drop(columns='THK_Para', errors='ignore')
                Pre_Thk_Table.rename(columns={'Pre_THK_Para': 'THK_Para', 'pre_oper_time': 'Pre_Oper_Date'}, inplace=True)
            Pre_Thk_Table.rename(columns={'pre_oper_time': 'Pre_Oper_Date'}, inplace=True)
            has_pre_thk   = 'Pre_Thk' in Pre_Thk_Table.columns  # MA 기반 VM 존재 여부

            merge_df.rename(columns={'request_dtts': 'Date'}, inplace=True)

            if has_pre_thk:
                Pre_Thk_Table['Pre_Oper_Date'] = pd.to_datetime(Pre_Thk_Table['Pre_Oper_Date'])
                merge_df.rename(columns={'pre_oper_time': 'Pre_Oper_Date'}, inplace=True)
                merge_df.dropna(subset=['Pre_Oper_Date'], inplace=True)
                merge_df['Pre_Oper_Date'] = pd.to_datetime(merge_df['Pre_Oper_Date'])
                merge_df = merge_df.sort_values(by='Pre_Oper_Date', ascending=True)

            info_col = 'MICO_PRE_THK_INFO_' + Lot_Code + '_' + Oper_Desc + '_' + Fab
            if info_col in db.list_collection_names():
                Pre_Thk_info_Table = pd.DataFrame(list(db[info_col].find({}, {'_id': False})))
                # 구컬럼(samp_matl_id)과 신규 substrate_id 공존 시 하나로 병합 (중복 컬럼 방지)
                Pre_Thk_info_Table = Get_data.coalesce_substrate_id(Pre_Thk_info_Table)
                # 같은 웨이퍼가 구/신 문서로 중복될 수 있으므로 최신 1건만 유지 (merge 시 행 증식 방지)
                Pre_Thk_info_Table = Pre_Thk_info_Table.drop_duplicates(subset='substrate_id', keep='last')
                Pre_Thk_info_Table.replace('-', 0, inplace=True)

                exclude  = {'alias_lot_id', 'end_tm'}
                merge_kw = dict(on='substrate_id')

                col_name = [c for c in Pre_Thk_info_Table.columns if c not in exclude]
                merge_df = pd.merge(merge_df, Pre_Thk_info_Table[col_name], how='left', **merge_kw)

            for Thk_key in Pre_Thk_Table['THK_Para'].unique():

                key = mico_info_key[(mico_info_key['Thk_Para'] == Thk_key) | (mico_info_key['Pre_Thk_Para_ITM'] == Thk_key)].copy()

                if has_pre_thk:
                    temp_pre_thk = Pre_Thk_Table[Pre_Thk_Table['THK_Para'] == Thk_key].drop(columns=['Date', 'THK_Para'])
                    temp_pre_thk = temp_pre_thk.sort_values(by='Pre_Oper_Date', ascending=True)
                    temp_pre_thk.rename(columns={'Pre_Thk': Thk_key+'_VM', 'Count': Thk_key+'_Count'}, inplace=True)

                    cols_to_drop = [c for c in merge_df.columns if c.endswith('_x') or c.endswith('_y')]
                    merge_df = merge_df.drop(columns=cols_to_drop)
                    merge_df = pd.merge_asof(merge_df, temp_pre_thk, on='Pre_Oper_Date', by=['pre_eq_ch'])
                    merge_df.drop_duplicates(subset=['substrate_id'], inplace=True)
                else:
                    # pre_oper1 미설정: MA 기반 VM 없음 → 0 초기화 후 회귀 보정만 적용
                    merge_df[Thk_key + '_VM'] = 0.0
                    row_ptk = Pre_Thk_Table[Pre_Thk_Table['THK_Para'] == Thk_key].iloc[0]
                    for prefix in ['PRE_OPER2', 'PRE_OPER3', 'PRE_OPER4']:
                        b1_col, b0_col = f'{prefix}_b1', f'{prefix}_b0'
                        if b1_col in row_ptk.index and not pd.isna(row_ptk[b1_col]):
                            merge_df[b1_col] = float(row_ptk[b1_col])
                            merge_df[b0_col] = float(row_ptk[b0_col]) if b0_col in row_ptk.index and not pd.isna(row_ptk[b0_col]) else 0.0

                ref = key.iloc[0]
                oper_pairs = [
                    (ref['Pre_Oper_Desc2'], ref['Pre_Oper_Para2'], 'PRE_OPER2', 1),
                    (ref['Pre_Oper_Desc3'], ref['Pre_Oper_Para3'], 'PRE_OPER3', 1),
                    (ref['Pre_Oper_Desc4'], ref['Pre_Oper_Para4'], 'PRE_OPER4', 1),
                ]
                for desc, para, prefix, weight in oper_pairs:
                    if not (isinstance(desc, str) and desc != ''):
                        continue
                    b1_col, b0_col = f'{prefix}_b1', f'{prefix}_b0'
                    merge_df[[b1_col, b0_col]] = merge_df[[b1_col, b0_col]].fillna(merge_df[[b1_col, b0_col]].mean()).fillna(0)
                    merge_df[Thk_key+'_VM'] += weight * (
                        merge_df[desc + '.' + para] * merge_df[b1_col] + merge_df[b0_col]
                    )
                    merge_df.drop(columns=[b1_col, b0_col], inplace=True)

        finally:
            client.close()

        return merge_df


    def apply_pre_oper2_correction(merge_df, mico_info_key, mongo_url, mongo_db):
        """
        pre_oper1 미설정, pre_oper2~4만 set-up된 경우 VM=0 기준으로 전공정 회귀 보정 적용.
        Period 컬렉션(또는 Excel 캐시)에서 최신 b1/b0를 읽고,
        INFO 컬렉션에서 pre_oper2~4 파라미터 값을 substrate_id로 결합하여 _VM 컬럼에 보정값 적용.
        """
        Fab       = mico_info_key['Fab'].unique()[0]
        Lot_Code  = mico_info_key['Lot_Code'].unique()[0]
        Oper_Desc = mico_info_key['Oper_Desc'].unique()[0]

        def _apply_correction(merge_df, Pre_Thk_Table, mico_info_key):
            for Thk_key in Pre_Thk_Table['THK_Para'].unique():
                key = mico_info_key[
                    (mico_info_key['Thk_Para'] == Thk_key) |
                    (mico_info_key['Pre_Thk_Para_ITM'] == Thk_key)
                ].copy()
                if key.empty:
                    continue
                # 같은 THK_Para가 여러 날짜로 저장돼 있을 경우 최신 1행만 사용
                thk_rows = Pre_Thk_Table[Pre_Thk_Table['THK_Para'] == Thk_key]
                if 'Date' in thk_rows.columns:
                    thk_rows = thk_rows.sort_values('Date', ascending=False)
                row = thk_rows.iloc[0]
                ref = key.iloc[0]
                for desc, para, prefix, weight in [
                    (ref['Pre_Oper_Desc2'], ref['Pre_Oper_Para2'], 'PRE_OPER2', 1),
                    (ref['Pre_Oper_Desc3'], ref['Pre_Oper_Para3'], 'PRE_OPER3', 1),
                    (ref['Pre_Oper_Desc4'], ref['Pre_Oper_Para4'], 'PRE_OPER4', 1),
                ]:
                    if not (isinstance(desc, str) and desc != ''):
                        continue
                    b1_col = f'{prefix}_b1'
                    b0_col = f'{prefix}_b0'
                    col    = desc + '.' + para
                    if b1_col not in row.index or col not in merge_df.columns:
                        continue
                    b1 = float(row[b1_col])
                    b0 = float(row[b0_col])
                    param_vals = pd.to_numeric(
                        merge_df[col].replace('-', np.nan), errors='coerce'
                    ).fillna(0)
                    merge_df[Thk_key + '_VM'] = merge_df[Thk_key + '_VM'].fillna(0) + weight * (param_vals * b1 + b0)
            return merge_df

        # ── [TEST 삭제] Excel 캐시 분기 ──────────────────────────────────────
        _cache_dir  = Path(__file__).parents[1] / 'pre_thk_cache'
        _cache_file = _cache_dir / f'{Lot_Code}_{Oper_Desc.replace(" ", "_")}_{Fab}.xlsx'
        if _cache_file.exists():
            print(f'    [Excel 캐시] {_cache_file.name} 로드 (pre_oper2 보정)')
            Pre_Thk_Table = pd.read_excel(_cache_file)
            merge_df = _apply_correction(merge_df, Pre_Thk_Table, mico_info_key)
            return merge_df
        # ── [TEST 삭제 끝] ────────────────────────────────────────────────────

        client = MongoClient(mongo_url)
        try:
            db         = client[mongo_db]
            period_col = 'MICO_PRE_THK_' + Lot_Code + '_' + Oper_Desc + '_' + Fab + '_Period'
            Pre_Thk_Table = pd.DataFrame(list(db[period_col].find({}, {'_id': False})))
            if Pre_Thk_Table.empty:
                return merge_df

            # INFO 컬렉션에서 pre_oper2~4 파라미터 값 결합
            info_col = 'MICO_PRE_THK_INFO_' + Lot_Code + '_' + Oper_Desc + '_' + Fab
            if info_col in db.list_collection_names():
                info_df = pd.DataFrame(list(db[info_col].find({}, {'_id': False})))
                # 구컬럼(samp_matl_id)과 신규 substrate_id 공존 시 하나로 병합 (중복 컬럼 방지)
                info_df = Get_data.coalesce_substrate_id(info_df)
                # 같은 웨이퍼가 구/신 문서로 중복될 수 있으므로 최신 1건만 유지 (merge 시 행 증식 방지)
                info_df = info_df.drop_duplicates(subset='substrate_id', keep='last')
                info_df.replace('-', 0, inplace=True)
                exclude  = {'alias_lot_id', 'end_tm'}
                col_name = [c for c in info_df.columns if c not in exclude]
                merge_df = pd.merge(merge_df, info_df[col_name], on='substrate_id', how='left')

            merge_df = _apply_correction(merge_df, Pre_Thk_Table, mico_info_key)
        finally:
            client.close()

        return merge_df
