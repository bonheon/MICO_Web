import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parents[1]))
from datetime import datetime, timedelta, date
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression


class PRE_THK_VM_Get:

    def compute_detrend(merge_df, APC_Para_merge, Thk_Para, Pre_Target, Post_Target, Pad_Para, use_pressure=False):
        # EQP/Recipe 조합별 Detrend_Thk 산출.
        # 패드 교체 주기(pad_cycle)로 구간을 분리한 뒤 rolling MA로 추세를 제거하여 CMP 두께 편차(0-centered) 반환.

        pre_thk_df = pd.DataFrame()

        temp_df  = merge_df[(merge_df['IDLE'] == '') | (merge_df['IDLE'].isna())]
        col_list = ['Date', 'process_id', 'recipe_id', 'eqp_id', 'operation_id', 'lot_id', 'substrate_id',
                    'pre_eqp_id', 'pre_eqp_ch', 'pre_oper_time', Thk_Para, Pad_Para, 'BIAS'] + APC_Para_merge

        temp_df = temp_df.loc[:, col_list].dropna(axis=0).drop_duplicates()

        temp_df['Pol_Time'] = temp_df[APC_Para_merge].sum(axis=1)

        if use_pressure:
            # FB_Type=PRESSURE: Post 두께 대신 BIAS(0-centered 편차값) 기준으로 RR 산출
            temp_df['RR'] = (Pre_Target - (Post_Target + temp_df['BIAS'])) / temp_df['Pol_Time']
        else:
            temp_df['RR'] = (Pre_Target - temp_df[Thk_Para]) / temp_df['Pol_Time']

        temp_df.sort_values(by='Date', inplace=True, ascending=False)

        FIX_Time   = temp_df['Pol_Time'].mean()  # 전체 기준 평균 연마시간 (EQP/RCP 공통 적용)
        windows    = 10
        eq_rcp_key = temp_df['eqp_id'] + '//' + temp_df['recipe_id']

        for eq_rcp in eq_rcp_key.unique():

            EQP_ID = eq_rcp.split('//')[0]
            RCP_ID = eq_rcp.split('//')[1]

            temp_df2 = temp_df[(temp_df['eqp_id'] == EQP_ID) & (temp_df['recipe_id'] == RCP_ID)].reset_index(drop=True)
            temp_df2.sort_values(by='Date', inplace=True)
            temp_df2.reset_index(drop=True, inplace=True)

            temp_df2['Unctr_Thk'] = Pre_Target - (temp_df2['RR'] * FIX_Time)

            # Pad_Para가 이전 행 대비 0.5 이상 급감 = 패드 교체 직후 첫 행 → cumsum으로 사이클 번호 부여
            temp_df2['pad_cycle'] = (temp_df2[Pad_Para].diff() < -0.5).cumsum() + 1

            for _, group in temp_df2.groupby('pad_cycle'):
                ma = group['Unctr_Thk'].rolling(window=windows).mean()
                temp_df2.loc[group.index, 'Unctr_Thk_MA'] = ma.values

            temp_df2['Detrend_Thk'] = temp_df2['Unctr_Thk'] - temp_df2['Unctr_Thk_MA']

            pre_thk_df = temp_df2 if pre_thk_df.empty else pd.concat([pre_thk_df, temp_df2])

        return pre_thk_df


    def rolling_mean(df, value_col, Pre_Thk_Period, min_count):
        # pre_eq_ch 구성 + time-window rolling. ITM(value_col='BIAS')·detrend(value_col='Detrend_Thk') 공통 사용
        df = df.drop(df[df['pre_eqp_ch'].isna()].index)
        if df['pre_eqp_ch'].dtype != 'object':
            df['pre_eqp_ch'] = df['pre_eqp_ch'].astype(int).astype(str)
        df['pre_eq_ch']     = df['pre_eqp_id'].astype(str) + '_' + df['pre_eqp_ch'].astype(str)
        df = df.drop(df[df['pre_eq_ch'] == '_'].index)
        df['pre_oper_time'] = pd.to_datetime(df['pre_oper_time'])
        df.sort_values(by='pre_oper_time', inplace=True)
        df.reset_index(inplace=True, drop=True)
        df = df.dropna(subset=['pre_oper_time'])

        # pre_eq_ch 유효 데이터가 없으면 루프 미실행 → UnboundLocalError 방지
        if df.empty or df['pre_eq_ch'].nunique() == 0:
            df['Pre_Thk']       = 0
            df['Pre_Thk_Count'] = 0
            return df

        pre_thk_list       = None
        pre_thk_count_list = None

        for j, i in enumerate(df['pre_eq_ch'].unique()):
            raw   = df[df['pre_eq_ch'] == i][[value_col, 'pre_oper_time']].rolling(window=Pre_Thk_Period, on='pre_oper_time', min_periods=min_count).mean()[value_col]
            count = df[df['pre_eq_ch'] == i][[value_col, 'pre_oper_time']].rolling(window=Pre_Thk_Period, on='pre_oper_time', min_periods=min_count).count()[value_col]
            pre_thk_list       = raw   if j == 0 else pd.concat([pre_thk_list, raw])
            pre_thk_count_list = count if j == 0 else pd.concat([pre_thk_count_list, count])

        df['Pre_Thk']       = pre_thk_list
        df['Pre_Thk_Count'] = pre_thk_count_list
        return df


    def iqr_filter(df, col, sigma=3):
        # IQR 기반 이상치 제거. 평균/표준편차 방식보다 극단값에 강건하여 노이즈 제거에 적합
        # sigma=3: 정규분포 기준 약 99.7% 범위 포함 → 실질적 이상치만 제거
        q1, q3 = df[col].quantile([0.25, 0.75])
        IQR    = q3 - q1
        return df[
            (df[col] >= q1 - sigma * IQR) &
            (df[col] <= q3 + sigma * IQR)
        ].copy()


    def fit_pre_oper_regression(pre_thk_df_merge, pre2_df, pre_thk_table, oper_pairs, y_col):
        """
        전공정(Pre_Oper2~4) 파라미터와 Pre_Thk_VM 학습값 사이의 단순선형회귀계수(b1, b0) 산출.
        oper_pairs: [(Pre_Oper_Desc, Pre_Oper_Para, 'PRE_OPER2'|'PRE_OPER3'|'PRE_OPER4'), ...]
        y_col: ITM 경로 → 'BIAS', detrend 경로 → 'Detrend_Thk' (둘 다 0-centered 학습값)
        """
        for desc, para, prefix in oper_pairs:
            if not (isinstance(para, str) and para != ''):
                continue
            merged = pd.merge(pre_thk_df_merge, pre2_df, on='substrate_id', how='left')
            col       = desc + '.' + para
            linear_df = merged[[col, y_col]].replace('-', np.nan).dropna()
            lr        = LinearRegression()
            lr.fit(linear_df[[col]], linear_df[[y_col]])
            pre_thk_table[f'{prefix}_b1'] = round(lr.coef_[0][0], 3)
            pre_thk_table[f'{prefix}_b0'] = round(lr.intercept_[0], 3)
