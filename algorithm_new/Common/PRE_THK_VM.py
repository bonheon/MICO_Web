import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parents[1]))
from datetime import datetime, timedelta, date
import pandas as pd
import numpy as np


class PRE_THK_VM_Get:

    def pre_thk_vm_detrend(merge_df, APC_Para_merge, Thk_Para, Pre_Target, Post_Target, Pad_Para):

        pre_thk_df = pd.DataFrame()

        temp_df = merge_df[(merge_df['IDLE'] == '') | (merge_df['IDLE'].isna())]

        col_list = ['Date', 'process_id', 'recipe_id', 'eqp_id', 'operation_id', 'lot_id', 'substrate_id',
                    'pre_eqp_id', 'pre_eqp_ch', 'pre_oper_time', Thk_Para, Pad_Para, 'BIAS'] + APC_Para_merge

        temp_df = temp_df.loc[:, col_list]
        temp_df = temp_df.dropna(axis=0)
        temp_df.drop_duplicates(inplace=True)

        for i in range(len(APC_Para_merge)):
            if i == 0:
                temp_df['Pol_Time'] = temp_df[APC_Para_merge[0]]
            else:
                temp_df['Pol_Time'] += temp_df[APC_Para_merge[i]]

        if ('ED' in Thk_Para) | ('EX' in Thk_Para) | ('CENTER' in Thk_Para) | ('Z2' in Thk_Para):
            temp_df['RR'] = (Pre_Target - (Post_Target + temp_df['BIAS'])) / temp_df['Pol_Time']
        else:
            temp_df['RR'] = (Pre_Target - temp_df[Thk_Para]) / temp_df['Pol_Time']

        temp_df.sort_values(by='Date', inplace=True, ascending=False)

        eq_rcp_key = temp_df['eqp_id'] + '//' + temp_df['recipe_id']

        for i in eq_rcp_key.unique():

            EQP_ID = i.split('//')[0]
            RCP_ID = i.split('//')[1]

            temp_df2 = temp_df[(temp_df['eqp_id'] == EQP_ID) & (temp_df['recipe_id'] == RCP_ID)]
            temp_df2 = temp_df2.reset_index(drop=True)

            FIX_Time = temp_df['Pol_Time'].mean()

            temp_df2['Unctr_Thk'] = Pre_Target - (temp_df2['RR'] * FIX_Time)

            temp_df2['PAD_SHIFT'] = temp_df2[Pad_Para].shift(-1)

            idx = list(temp_df2[temp_df2[Pad_Para] - temp_df2['PAD_SHIFT'] < -0.5].index)
            idx.append(len(temp_df2))

            temp_df2['pad_cycle'] = None

            for i in range(len(idx)):
                if i == 0:
                    temp_df2.iloc[0:idx[i], -1] = int(i + 1)
                else:
                    temp_df2.iloc[idx[i - 1]:idx[i], -1] = int(i + 1)

            temp_df2 = temp_df2.dropna(axis=0)
            temp_df2.sort_values(by='Date', inplace=True)

            for i in range(len(idx), 0, -1):
                windows = 10

                temp_df3 = temp_df2[temp_df2['pad_cycle'] == i].copy()
                temp_df3['Unctr_Thk_MA'] = temp_df3['Unctr_Thk'].rolling(window=windows).mean()

                detrend_raw = temp_df3['Unctr_Thk'] - temp_df3['Unctr_Thk_MA']

                if i == len(idx):
                    detrend_list = detrend_raw
                    Unctr_Thk_MA = temp_df3['Unctr_Thk_MA']
                else:
                    detrend_list = np.append(detrend_list, detrend_raw)
                    Unctr_Thk_MA = np.append(Unctr_Thk_MA, temp_df3['Unctr_Thk_MA'])

            temp_df2['Detrend_Thk'] = detrend_list
            temp_df2['Unctr_Thk_MA'] = Unctr_Thk_MA

            if pre_thk_df.empty:
                pre_thk_df = temp_df2
            else:
                pre_thk_df = pd.concat([pre_thk_df, temp_df2])

        if pre_thk_df['pre_eqp_ch'].dtype != 'object':
            pre_thk_df['pre_eqp_ch'] = pre_thk_df['pre_eqp_ch'].astype(int).astype(str)

        pre_thk_df['pre_eq_ch'] = pre_thk_df['pre_eqp_id'].astype(str) + '_' + pre_thk_df['pre_eqp_ch'].astype(str)
        pre_thk_df['pre_oper_time'] = pd.to_datetime(pre_thk_df['pre_oper_time'])
        pre_thk_df.sort_values(by='pre_oper_time', inplace=True)
        pre_thk_df.reset_index(inplace=True, drop=True)

        return pre_thk_df


    def moving_avg_period(pre_thk_df, Pre_Target, Thk_Para, Pre_Thk_Period):

        pre_thk_df['pre_oper_time'] = pd.to_datetime(pre_thk_df['pre_oper_time'])
        pre_thk_df.sort_values(by='pre_oper_time', inplace=True)
        pre_thk_df.reset_index(inplace=True, drop=True)

        if ('ED' in Thk_Para) | ('EX' in Thk_Para):
            min_count = 5
        else:
            min_count = 10

        for j, i in enumerate(pre_thk_df['pre_eq_ch'].unique()):

            pre_thk_raw   = pre_thk_df[pre_thk_df['pre_eq_ch'] == i][['Detrend_Thk', 'pre_oper_time']].rolling(window=Pre_Thk_Period, on='pre_oper_time', min_periods=min_count).mean()['Detrend_Thk']
            pre_thk_count = pre_thk_df[pre_thk_df['pre_eq_ch'] == i][['Detrend_Thk', 'pre_oper_time']].rolling(window=Pre_Thk_Period, on='pre_oper_time', min_periods=min_count).count()['Detrend_Thk']

            if j == 0:
                pre_thk_list       = pre_thk_raw
                pre_thk_count_list = pre_thk_count
            else:
                pre_thk_list       = pd.concat([pre_thk_list, pre_thk_raw])
                pre_thk_count_list = pd.concat([pre_thk_count_list, pre_thk_count])

        pre_thk_df['Pre_Thk']       = pre_thk_list
        pre_thk_df['Pre_Thk_Count'] = pre_thk_count_list

        return pre_thk_df


    def pre_thk_itm_moving_avg(merge_df, Pre_Target, Pre_Thk_Para, Pre_Thk_Period):
        # ED/EX: BIAS 기준 rolling (이미 centering된 값이므로 평균 차감 불필요)
        # 그 외: Pre_Thk_Para 기준 rolling 후 전체 평균 차감
        use_bias  = ('ED' in Pre_Thk_Para) or ('EX' in Pre_Thk_Para)
        roll_col  = 'BIAS' if use_bias else Pre_Thk_Para
        min_count = 5 if use_bias else 10

        level_1q = merge_df[roll_col].quantile(0.25)
        level_3q = merge_df[roll_col].quantile(0.75)
        IQR      = level_3q - level_1q
        sigma    = 3
        merge_df = merge_df[
            (merge_df[roll_col] <= level_3q + (IQR * sigma)) &
            (merge_df[roll_col] >= level_1q - (IQR * sigma))
        ].copy()

        merge_df.drop(merge_df[merge_df['pre_eqp_ch'].isna()].index, axis=0, inplace=True)

        if merge_df['pre_eqp_ch'].dtype != 'object':
            merge_df['pre_eqp_ch'] = merge_df['pre_eqp_ch'].astype(int).astype(str)

        merge_df['pre_eq_ch'] = merge_df['pre_eqp_id'].astype(str) + '_' + merge_df['pre_eqp_ch'].astype(str)
        merge_df['pre_oper_time'] = pd.to_datetime(merge_df['pre_oper_time'])
        merge_df.sort_values(by='pre_oper_time', inplace=True)
        merge_df.reset_index(inplace=True, drop=True)
        merge_df.drop(merge_df[merge_df['pre_eq_ch'] == '_'].index, axis=0, inplace=True)
        merge_df = merge_df.dropna(subset=['pre_oper_time'])

        for j, i in enumerate(merge_df['pre_eq_ch'].unique()):

            pre_thk_raw   = merge_df[merge_df['pre_eq_ch'] == i][[roll_col, 'pre_oper_time']].rolling(window=Pre_Thk_Period, on='pre_oper_time', min_periods=min_count).mean()[roll_col]
            pre_thk_count = merge_df[merge_df['pre_eq_ch'] == i][[roll_col, 'pre_oper_time']].rolling(window=Pre_Thk_Period, on='pre_oper_time', min_periods=min_count).count()[roll_col]

            if j == 0:
                pre_thk_list       = pre_thk_raw
                pre_thk_count_list = pre_thk_count
            else:
                pre_thk_list       = pd.concat([pre_thk_list, pre_thk_raw])
                pre_thk_count_list = pd.concat([pre_thk_count_list, pre_thk_count])

        if use_bias:
            merge_df['Pre_Thk'] = pre_thk_list
        else:
            merge_df['Pre_Thk'] = pre_thk_list - merge_df[Pre_Thk_Para].mean()
        merge_df['Pre_Thk_Count'] = pre_thk_count_list

        return merge_df
