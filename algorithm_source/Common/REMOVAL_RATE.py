import sys, os
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))
from Common.Get_Data import Get_data
from Common.MongoDB_Control import mongodb_controller
from sklearn.linear_model import LinearRegression
from datetime import datetime, timedelta, date
import pandas as pd
import numpy as np
from pymongo import MongoClient
import requests
import json


class Removal_Rate_Get:


    def Logic(
        merge_df,
        search_key,
        pol_type,
        Thk_Para,
        Pre_Thk_Para,
        EQPM_df,
        Maker,
        RR_Alarm
        ):

        lr = LinearRegression()


        today = datetime.now()
        Family = search_key.Family
        Fab = search_key.Fab
        Lot_Code = search_key.Lot_Code
        Oper_Code = search_key.Oper_Code
        Oper_Desc = search_key.Oper_Desc
        APC_Para = search_key.APC_Para
        Recipe_ID = search_key.Recipe_ID
        FB_Type = search_key.FB_Type
        RR_Para = search_key.RR_Para
        RR_Para_Max = search_key.RR_Para_Max
        if pd.notna(RR_Para_Max):
            RR_Para_Max = float(RR_Para_Max)
        Pre_Target = search_key.Pre_Target
        if pd.notna(Pre_Target):
            Pre_Target = float(Pre_Target)
        Post_Target = float(search_key.Post_Target)
        RR_Period = search_key.RR_Period
        RR_Count = float(search_key.RR_Count)
        RR_Weight = float(search_key.RR_Weight)
        Pad_Seperation = search_key.Pad_Seperation
        Pre_Oper_Code3 = search_key.Pre_Oper_Code3


        Pol_Para = Get_data.APCParaGet(APC_Para, pol_type)
        Head_Para = Get_data.HeadParaGet(APC_Para)
        Pad_Para = Get_data.PadParaGet(APC_Para)
        Disk_Para = Get_data.DiskParaGet(APC_Para)
        RR_Para = RR_Para.upper()


        if 'HEAD' == RR_Para:
            consumable_Para = Head_Para

        elif 'PAD' == RR_Para:
            consumable_Para = Pad_Para

        elif 'DISK' == RR_Para:
            consumable_Para = Disk_Para


        temp_data = merge_df[(merge_df['operation_id'] == Oper_Code)
                            & (merge_df['recipe_id'] == Recipe_ID)
                            & ((merge_df['IDLE'] == '') | (merge_df['IDLE'].isna()))].copy()


        url = 'mongodb://cncmico...'
        db = 'mico-platform-mongodb'
        collection = 'MICO_Removal_Rate_' + Lot_Code + '_' + Oper_Desc + '_' + Fab

        mongo = mongodb_controller(url, db, collection)


        temp_data['eq_recipe'] = temp_data['eqp_id'] + '//' + temp_data['recipe_id']

        temp_data3 = pd.DataFrame()


        temp_data.sort_values(by=('Date'), inplace=True, ascending=False)


        for i in temp_data['eq_recipe'].unique():

            EQP_ID = i.split('//')[0]
            RCP_ID = i.split('//')[1]

            temp_data2 = temp_data[(temp_data['eqp_id'] == EQP_ID) & (temp_data['recipe_id'] == RCP_ID)]

            temp_data2 = temp_data2.reset_index(drop=True)

            temp_data2['SHIFT'] = temp_data2[consumable_Para].shift(-1)
            idx = list(temp_data2[(temp_data2[consumable_Para] - temp_data2['SHIFT']) < -3].index)

            idx.append(len(temp_data2))

            temp_data2['cycle'] = None

            for i in range(len(idx)):

                if i == 0:
                    temp_data2.iloc[0:idx[i], -1] = int(i+1)

                else:
                    temp_data2.iloc[idx[i-1]:idx[i], -1] = int(i+1)

            if temp_data3.empty:
                temp_data3 = temp_data2

            else:
                temp_data3 = pd.concat([temp_data3, temp_data2])


        if temp_data3.empty:

            return None


        for x in temp_data3['eqp_model'].unique():

            temp_data4 = temp_data3[temp_data3['eqp_model'] == x].copy()

            part_max = temp_data4[consumable_Para].max()
            part_min = temp_data4[consumable_Para].min()



            if pd.notna(RR_Para_Max):
                part_max = RR_Para_Max

            part_1q = part_min + (part_max - part_min) / 4
            part_2q = part_min + (part_max - part_min) / 2
            part_3q = part_min + (part_max - part_min) * 3 / 4


            if (Pre_Thk_Para == ''):
                col_list = ['Date', 'substrate_id', 'eqp_id', 'recipe_id', 'process_id', Pad_Para, Head_Para, Disk_Para,
                                  'pre_eq_ch', Thk_Para+'_VM', Thk_Para, 'cycle', 'BIAS'] + Pol_Para
                temp_data4 = temp_data4[col_list].copy()

            else:
                col_list = ['Date', 'substrate_id', 'eqp_id', 'recipe_id', 'process_id', Pad_Para, Head_Para, Disk_Para,
                                  'pre_eq_ch', Pre_Thk_Para+'_VM', Thk_Para, 'cycle', 'BIAS'] + Pol_Para
                temp_data4 = temp_data4[col_list].copy()

            temp_data4.drop_duplicates(inplace=True)

            for i in range(len(Pol_Para)):
                if i == 0:
                    temp_data4['Pol_Time'] = temp_data4[Pol_Para[0]]
                else:
                    temp_data4['Pol_Time'] += temp_data4[Pol_Para[i]]

            temp_data4.dropna(axis=0, subset=[Thk_Para, consumable_Para], inplace=True)
            temp_data4.drop(temp_data4[temp_data4['Pol_Time'] == 0].index, inplace=True)



            if 'ED' in Thk_Para or 'EX' in Thk_Para or 'CENTER' in Thk_Para or 'Z2' in Thk_Para:
                if (Pre_Thk_Para == '') & ('REV' in Thk_Para):
                    temp_data4.fillna(value={Thk_Para+'_VM': 0}, inplace=True)
                    temp_data4['RR'] = (Post_Target + temp_data4['BIAS'] - (Pre_Target + temp_data4[Thk_Para+'_VM'])) / temp_data4['Pol_Time']

                elif ((Pre_Thk_Para == '') | (Pre_Thk_Para == '')):
                    temp_data4.fillna(value={Thk_Para+'_VM': 0}, inplace=True)
                    temp_data4['RR'] = (Pre_Target + temp_data4[Thk_Para+'_VM'] - (Post_Target + temp_data4['BIAS'])) / temp_data4['Pol_Time']

                else:
                    temp_data4.fillna(value={Pre_Thk_Para+'_VM': 0}, inplace=True)
                    temp_data4['RR'] = (Pre_Target + temp_data4[Pre_Thk_Para+'_VM'] - (Post_Target + temp_data4['BIAS'])) / temp_data4['Pol_Time']

            else:
                if (Pre_Thk_Para == '') & ('REV' in Thk_Para):
                    temp_data4.fillna(value={Thk_Para+'_VM': 0}, inplace=True)
                    temp_data4['RR'] = (temp_data4[Thk_Para] - (Pre_Target + temp_data4[Thk_Para+'_VM'])) / temp_data4['Pol_Time']

                elif ((Pre_Thk_Para == '') | (Pre_Thk_Para == '')):
                    temp_data4.fillna(value={Thk_Para+'_VM': 0}, inplace=True)
                    temp_data4['RR'] = (Pre_Target + temp_data4[Thk_Para+'_VM'] - temp_data4[Thk_Para]) / temp_data4['Pol_Time']

                else:
                    temp_data4.fillna(value={Pre_Thk_Para+'_VM': 0}, inplace=True)
                    temp_data4['RR'] = (Pre_Target + temp_data4[Pre_Thk_Para+'_VM'] - temp_data4[Thk_Para]) / temp_data4['Pol_Time']


            temp_data4['eq_recipe'] = temp_data4['eqp_id'] + '//' + temp_data4['recipe_id']


            rr_avg = temp_data4['RR'].mean()
            rr_std = temp_data4['RR'].std()
            sigma = 6

            temp_data4 = temp_data4[(temp_data4['RR'] < rr_avg + rr_std * sigma)
                                  & (temp_data4['RR'] > rr_avg - rr_std * sigma)].copy()

            for i in temp_data4['eq_recipe'].unique():

                temp_data5 = temp_data4[temp_data4['eq_recipe'] == i].copy()

                Count = len(temp_data5)

                if Count < 10:
                    continue

                EQ = i.split('//')[0]
                Recipe_ID = i.split('//')[1]


                if RR_Alarm is not None:

                    temp_data5.sort_values(by=('Date'), inplace=True, ascending=False)

                    if 'TIME' in APC_Para:
                        rr_sigma = 3
                        rr_recent = temp_data5['RR'][:3].mean()
                        ucl = temp_data5['RR'].mean() + temp_data5['RR'].std() * rr_sigma
                        lcl = temp_data5['RR'].mean() - temp_data5['RR'].std() * rr_sigma

                        if rr_recent > ucl:
                            Alarm = f'현재 Removal Rate 값이 기준 대비 {rr_sigma}Sigma 이상 올라가고 있습니다.'
                            Get_data.Cube_Msg_RR_Alarm(EQ, Recipe_ID, Alarm)

                        if rr_recent < lcl:
                            Alarm = f'현재 Removal Rate 값이 기준 대비 {rr_sigma}Sigma 이상 내려가고 있습니다.'
                            Get_data.Cube_Msg_RR_Alarm(EQ, Recipe_ID, Alarm)


                temp_data5['group'] = pd.cut(temp_data5['Date'], bins=5, labels=False)

                date_seg = [0, 1, 2, 3, 4]
                part_seg = [0, 1, 2, 3]
                temp_data5['date_seg'] = pd.cut(temp_data5['Date'], bins=5, labels=date_seg).astype('str')
                temp_data5['part_seg'] = pd.cut(temp_data5[consumable_Para], bins=4, labels=part_seg).astype('str')
                temp_data5['date_part_seg'] = temp_data5['date_seg'] + '_' + temp_data5['part_seg']
                grouped_counts = temp_data5.groupby(['eqp_id', 'date_part_seg']).size().reset_index(name='count')
                grouped_counts = grouped_counts.sort_values('date_part_seg')

                temp_data6 = pd.merge(temp_data5, grouped_counts, on=['eqp_id', 'date_part_seg'], how='left')

                def custom_filter(group):
                    if group.name == '4':
                        return group['count'].gt(25).all()
                    return True
                filtered_temp_data6 = temp_data6.groupby('date_seg').filter(custom_filter)


                weight = [1, 2, 3, 4, RR_Weight]


                data_cut = pd.cut(np.array(temp_data5[consumable_Para]), bins=[part_min, part_1q, part_2q, part_3q, part_max], labels=['Q1', 'Q2', 'Q3', 'Q4']).describe()

                Count_min = 25

                print(today, Fab, Lot_Code, Oper_Code, Oper_Desc, APC_Para, EQ, Recipe_ID)


                if (data_cut.loc['Q1', 'counts'] > Count_min) & (data_cut.loc['Q2', 'counts'] > Count_min) & (data_cut.loc['Q3', 'counts'] > Count_min) & (data_cut.loc['Q4', 'counts'] > Count_min):

                    X = temp_data5[consumable_Para].values.reshape(-1, 1)
                    Y = temp_data5['RR'].values.reshape(-1, 1)

                    lr.fit(X, Y)

                    b0 = round(lr.intercept_[0], 4)
                    b1 = round(lr.coef_[0][0], 4)


                    if ('4' in filtered_temp_data6['date_seg'].unique()) & (grouped_counts['date_part_seg'].str.contains('4').sum() == 4):

                        X_weighted = np.repeat(temp_data5[consumable_Para], temp_data5['group'].map(lambda g: weight[g]))
                        y_weighted = np.repeat(temp_data5['RR'], temp_data5['group'].map(lambda g: weight[g]))

                        model = lr.fit(X_weighted.values.reshape(-1, 1), y_weighted)

                        weighted_b0 = round(model.intercept_, 4)
                        weighted_b1 = round(model.coef_[0], 4)

                    else:

                        weighted_b0 = '-'
                        weighted_b1 = '-'

                    today_date = datetime.now()



                    if temp_data5[temp_data5['cycle'] == 1].empty == False:

                        if pd.isna(RR_Period):
                            current_cycle = temp_data5[temp_data5['cycle'] == 1]
                        else:

                            RR_Period = float(RR_Period)

                            current_period = temp_data5[temp_data5['cycle'] == 1][consumable_Para].iloc[0] - RR_Period
                            current_cycle = temp_data5[(temp_data5['cycle'] == 1)
                                                      & (temp_data5[consumable_Para] >= current_period)]
                    else:
                        current_cycle = pd.DataFrame()


                    if current_cycle.empty == False:

                        count = len(current_cycle)

                        current_date = current_cycle['Date'].iloc[0]
                        time_delta = (today_date - current_date)


                        if Maker == 'AMAT':
                            EQPM_df_R1 = EQPM_df[EQPM_df['EQP_ID'] == EQ]
                            min_count = EQPM_df_R1.sort_values(by='EVENT_TM', ascending=False)['rank'].iloc[0]

                        elif Maker == 'EBARA':
                            CH = '_AB' if '_AB' in Recipe_ID else '_CD'
                            EQ_CH = EQ + CH
                            EQPM_df_R1 = EQPM_df[EQPM_df['EQP_ID'] == EQ_CH]
                            min_count = EQPM_df_R1.sort_values(by='EVENT_TM', ascending=False)['rank'].iloc[0]

                        elif Maker == 'KCT':
                            CH = '_L' if '_L' in Recipe_ID else '_R'
                            EQ_CH = EQ + CH
                            EQPM_df_R1 = EQPM_df[EQPM_df['EQP_ID'] == EQ_CH]
                            min_count = EQPM_df_R1.sort_values(by='EVENT_TM', ascending=False)['rank'].iloc[0]

                        print(count, time_delta, min_count)


                        if (count > RR_Count) & (time_delta < timedelta(hours=12)) & (min_count >= 2):

                            Simul_Date = current_cycle['Date'].iloc[0].strftime("%Y-%m-%d %H:%M:%S")

                            X = current_cycle[consumable_Para].values.reshape(-1, 1)
                            Y = current_cycle['RR'].values.reshape(-1, 1)

                            lr.fit(X, Y)

                            current_b0 = round(lr.intercept_[0], 4)
                            current_b1 = round(lr.coef_[0][0], 4)

                            if pd.isna(RR_Period):

                                if weighted_b1 != '-':
                                    range_b1 = weighted_b1
                                    range_b0 = weighted_b0
                                else:
                                    range_b1 = b1
                                    range_b0 = b0

                                if range_b1 >= 0:
                                    current_b1 = min(current_b1, range_b1 * 2)
                                    current_b1 = max(current_b1, 0)
                                else:
                                    current_b1 = max(current_b1, range_b1 * 2)
                                    current_b1 = min(current_b1, 0)

                                lower_bound = range_b0 * 0.9
                                upper_bound = range_b0 * 1.1
                                current_b0 = max(lower_bound, min(current_b0, upper_bound))

                        else:
                            Simul_Date = '-'
                            current_b0 = '-'
                            current_b1 = '-'
                    else:
                        Simul_Date = '-'
                        current_b0 = '-'
                        current_b1 = '-'


                    if pd.notna(Pad_Seperation):
                        Pad_Seperation = int(Pad_Seperation)

                        temp_data7 = temp_data5[temp_data5[consumable_Para] <= Pad_Seperation]
                        temp_data7_len = len(temp_data7)

                        part_max_if = Pad_Seperation
                        part_min_if = 0

                        part_1q_if = part_min_if + (part_max_if - part_min_if) / 4
                        part_2q_if = part_min_if + (part_max_if - part_min_if) / 2
                        part_3q_if = part_min_if + (part_max_if - part_min_if) * 3 / 4

                        data_cut_if = pd.cut(np.array(temp_data7[consumable_Para]), bins=[part_min_if, part_1q_if, part_2q_if, part_3q_if, part_max_if], labels=['Q1', 'Q2', 'Q3', 'Q4']).describe()

                        if_data_Q1 = data_cut_if.loc['Q1', 'counts']
                        if_data_Q2 = data_cut_if.loc['Q2', 'counts']
                        if_data_Q3 = data_cut_if.loc['Q3', 'counts']
                        if_data_Q4 = data_cut_if.loc['Q4', 'counts']

                        print(if_data_Q1, if_data_Q2, if_data_Q3, if_data_Q4)

                        if_judge = (if_data_Q1 >= 25) & (if_data_Q2 >= 25) & (if_data_Q3 >= 25) & (if_data_Q4 >= 25)

                        if (temp_data7_len >= 100) & (if_judge):
                            X_if = temp_data7[consumable_Para].values.reshape(-1, 1)
                            Y_if = temp_data7['RR'].values.reshape(-1, 1)

                            lr.fit(X_if, Y_if)

                            if_b1 = round(lr.coef_[0][0], 4)
                            if_b0 = round(lr.intercept_[0], 4)

                        else:
                            if_b1 = '-'
                            if_b0 = '-'

                    else:
                        if_b1 = '-'
                        if_b0 = '-'

                    report = {'Date': today, 'Fab': Fab, 'Lot_Code': Lot_Code,
                              'Oper_Code': Oper_Code, 'Oper_Desc': Oper_Desc, 'APC_Para': APC_Para,
                              'EQ': EQ, 'Recipe_ID': Recipe_ID, 'Count': Count, 'b1': b1, 'b0': b0,
                              'b1_weighted': weighted_b1, 'b0_weighted': weighted_b0,
                              'Simul_Date': Simul_Date, 'b1_current': current_b1, 'b0_current': current_b0, 'if_b1': if_b1, 'if_b0': if_b0}

                    report = {k: v for k, v in report.items() if v != '-'}

                    mongo.insert_row(report)



                else:
                    print(data_cut)


    def Logic_group(
        merge_df,
        search_key,
        pol_type,
        Thk_Para,
        Pre_Thk_Para,
        EQPM_df,
        Maker,
        RR_Alarm
        ):

        lr = LinearRegression()


        today = datetime.now()
        Family = search_key.Family
        Fab = search_key.Fab
        Lot_Code = search_key.Lot_Code
        Oper_Code = search_key.Oper_Code
        Oper_Desc = search_key.Oper_Desc
        APC_Para = search_key.APC_Para
        Recipe_ID = search_key.Recipe_ID
        FB_Type = search_key.FB_Type
        RR_Para = search_key.RR_Para
        RR_Para_Max = search_key.RR_Para_Max
        if pd.notna(RR_Para_Max):
            RR_Para_Max = float(RR_Para_Max)
        Pre_Target = search_key.Pre_Target
        if pd.notna(Pre_Target):
            Pre_Target = float(Pre_Target)
        Post_Target = float(search_key.Post_Target)
        RR_Period = search_key.RR_Period
        RR_Count = float(search_key.RR_Count)
        RR_Weight = float(search_key.RR_Weight)
        Pad_Seperation = search_key.Pad_Seperation
        Pre_Oper_Code3 = search_key.Pre_Oper_Code3


        Pol_Para = Get_data.APCParaGet(APC_Para, pol_type)
        Head_Para = Get_data.HeadParaGet(APC_Para)
        Pad_Para = Get_data.PadParaGet(APC_Para)
        Disk_Para = Get_data.DiskParaGet(APC_Para)
        RR_Para = RR_Para.upper()


        if 'HEAD' == RR_Para:
            consumable_Para = Head_Para

        elif 'PAD' == RR_Para:
            consumable_Para = Pad_Para

        elif 'DISK' == RR_Para:
            consumable_Para = Disk_Para


        temp_data = merge_df[((merge_df['IDLE'] == '') | (merge_df['IDLE'].isna()))].copy()


        url = 'mongodb://cncmico...'
        db = 'mico-platform-mongodb'
        collection = 'MICO_Removal_Rate_' + Lot_Code + '_' + Oper_Desc + '_' + Fab

        mongo = mongodb_controller(url, db, collection)


        temp_data['eq_recipe'] = temp_data['eqp_id'] + '//' + temp_data['recipe_id']

        temp_data3 = pd.DataFrame()


        temp_data.sort_values(by=('Date'), inplace=True, ascending=False)


        for i in temp_data['eq_recipe'].unique():

            EQP_ID = i.split('//')[0]
            RCP_ID = i.split('//')[1]

            temp_data2 = temp_data[(temp_data['eqp_id'] == EQP_ID) & (temp_data['recipe_id'] == RCP_ID)]

            temp_data2 = temp_data2.reset_index(drop=True)

            temp_data2['SHIFT'] = temp_data2[consumable_Para].shift(-1)
            idx = list(temp_data2[(temp_data2[consumable_Para] - temp_data2['SHIFT']) < -3].index)

            idx.append(len(temp_data2))

            temp_data2['cycle'] = None

            for i in range(len(idx)):

                if i == 0:
                    temp_data2.iloc[0:idx[i], -1] = int(i+1)

                else:
                    temp_data2.iloc[idx[i-1]:idx[i], -1] = int(i+1)

            if temp_data3.empty:
                temp_data3 = temp_data2

            else:
                temp_data3 = pd.concat([temp_data3, temp_data2])


        if temp_data3.empty:

            return None


        for x in temp_data3['eqp_model'].unique():

            temp_data4 = temp_data3[temp_data3['eqp_model'] == x].copy()

            part_max = temp_data4[consumable_Para].max()
            part_min = temp_data4[consumable_Para].min()



            if pd.notna(RR_Para_Max):
                part_max = RR_Para_Max

            part_1q = part_min + (part_max - part_min) / 4
            part_2q = part_min + (part_max - part_min) / 2
            part_3q = part_min + (part_max - part_min) * 3 / 4


            if (Pre_Thk_Para == ''):
                col_list = ['Date', 'substrate_id', 'eqp_id', 'recipe_id', 'process_id', Pad_Para, Head_Para, Disk_Para,
                                  'pre_eq_ch', Thk_Para+'_VM', Thk_Para, 'cycle', 'BIAS'] + Pol_Para

            else:
                col_list = ['Date', 'substrate_id', 'eqp_id', 'recipe_id', 'process_id', Pad_Para, Head_Para, Disk_Para,
                                  'pre_eq_ch', Pre_Thk_Para+'_VM', Thk_Para, 'cycle', 'BIAS'] + Pol_Para

            col_list.append('Group_Name')

            temp_data4 = temp_data4[col_list].copy()


            temp_data4.drop_duplicates(inplace=True)


            for i in range(len(Pol_Para)):
                if i == 0:
                    temp_data4['Pol_Time'] = temp_data4[Pol_Para[0]]
                else:
                    temp_data4['Pol_Time'] += temp_data4[Pol_Para[i]]

            temp_data4.dropna(axis=0, subset=[Thk_Para, consumable_Para], inplace=True)
            temp_data4.drop(temp_data4[temp_data4['Pol_Time'] == 0].index, inplace=True)


            if 'ED' in Thk_Para or 'EX' in Thk_Para or 'CENTER' in Thk_Para or 'Z2' in Thk_Para:
                if (Pre_Thk_Para == '') & ('REV' in Thk_Para):
                    temp_data4.fillna(value={Thk_Para+'_VM': 0}, inplace=True)
                    temp_data4['RR'] = (temp_data4[Thk_Para] + temp_data4['BIAS'] - (Pre_Target - temp_data4[Thk_Para+'_VM'])) / temp_data4['Pol_Time']

                elif ((Pre_Thk_Para == '') | (Pre_Thk_Para == '')):
                    temp_data4.fillna(value={Thk_Para+'_VM': 0}, inplace=True)
                    temp_data4['RR'] = (Pre_Target + temp_data4[Thk_Para+'_VM'] - (Post_Target + temp_data4['BIAS'])) / temp_data4['Pol_Time']

                else:
                    temp_data4.fillna(value={Pre_Thk_Para+'_VM': 0}, inplace=True)
                    temp_data4['RR'] = (Pre_Target + temp_data4[Pre_Thk_Para+'_VM'] - (Post_Target + temp_data4['BIAS'])) / temp_data4['Pol_Time']

            else:
                if (Pre_Thk_Para == '') & ('REV' in Thk_Para):
                    temp_data4.fillna(value={Thk_Para+'_VM': 0}, inplace=True)
                    temp_data4['RR'] = (temp_data4[Thk_Para] - (Pre_Target - temp_data4[Thk_Para+'_VM'])) / temp_data4['Pol_Time']

                elif ((Pre_Thk_Para == '') | (Pre_Thk_Para == '')):
                    temp_data4.fillna(value={Thk_Para+'_VM': 0}, inplace=True)
                    temp_data4['RR'] = (Pre_Target + temp_data4[Thk_Para+'_VM'] - temp_data4[Thk_Para]) / temp_data4['Pol_Time']

                else:
                    temp_data4.fillna(value={Pre_Thk_Para+'_VM': 0}, inplace=True)
                    temp_data4['RR'] = (Pre_Target + temp_data4[Pre_Thk_Para+'_VM'] - temp_data4[Thk_Para]) / temp_data4['Pol_Time']


            temp_data4['rr_key'] = temp_data4['eqp_id'] + '//' + temp_data4['Group_Name']


            rr_avg = temp_data4['RR'].mean()
            rr_std = temp_data4['RR'].std()
            sigma = 6

            temp_data4 = temp_data4[(temp_data4['RR'] < rr_avg + rr_std * sigma)
                                  & (temp_data4['RR'] > rr_avg - rr_std * sigma)].copy()

            print('temp_data4 recipe :', temp_data4['recipe_id'].unique())

            for i in temp_data4['rr_key'].unique():

                temp_data5 = temp_data4[temp_data4['rr_key'] == i].copy()
                Count = len(temp_data5)

                if Count < 10:
                    continue

                EQ = i.split('//')[0]
                # Recipe_ID_List = temp_data4['recipe_id'].unique()


                if RR_Alarm is not None:

                    temp_data5.sort_values(by=('Date'), inplace=True, ascending=False)

                    if 'TIME' in APC_Para:
                        rr_sigma = 3
                        rr_recent = temp_data5['RR'][:3].mean()
                        ucl = temp_data5['RR'].mean() + temp_data5['RR'].std() * rr_sigma
                        lcl = temp_data5['RR'].mean() - temp_data5['RR'].std() * rr_sigma

                        if rr_recent > ucl:
                            Alarm = f'현재 Removal Rate 값이 기준 대비 {rr_sigma}Sigma 이상 올라가고 있습니다.'
                            Get_data.Cube_Msg_RR_Alarm(EQ, Recipe_ID, Alarm)

                        if rr_recent < lcl:
                            Alarm = f'현재 Removal Rate 값이 기준 대비 {rr_sigma}Sigma 이상 내려가고 있습니다.'
                            Get_data.Cube_Msg_RR_Alarm(EQ, Recipe_ID, Alarm)


                temp_data5['group'] = pd.cut(temp_data5['Date'], bins=5, labels=False)

                date_seg = [0, 1, 2, 3, 4]
                part_seg = [0, 1, 2, 3]
                temp_data5['date_seg'] = pd.cut(temp_data5['Date'], bins=5, labels=date_seg).astype('str')
                temp_data5['part_seg'] = pd.cut(temp_data5[consumable_Para], bins=4, labels=part_seg).astype('str')
                temp_data5['date_part_seg'] = temp_data5['date_seg'] + '_' + temp_data5['part_seg']
                grouped_counts = temp_data5.groupby(['eqp_id', 'date_part_seg']).size().reset_index(name='count')
                grouped_counts = grouped_counts.sort_values('date_part_seg')

                temp_data6 = pd.merge(temp_data5, grouped_counts, on=['eqp_id', 'date_part_seg'], how='left')

                def custom_filter(group):
                    if group.name == '4':
                        return group['count'].gt(25).all()
                    return True
                filtered_temp_data6 = temp_data6.groupby('date_seg').filter(custom_filter)


                weight = [1, 2, 3, 4, RR_Weight]

                data_cut = pd.cut(np.array(temp_data5[consumable_Para]), bins=[part_min, part_1q, part_2q, part_3q, part_max], labels=['Q1', 'Q2', 'Q3', 'Q4']).describe()

                Count_min = 25

                print(today, Fab, Lot_Code, Oper_Code, Oper_Desc, APC_Para, EQ, Recipe_ID)


                if (data_cut.loc['Q1', 'counts'] > Count_min) & (data_cut.loc['Q2', 'counts'] > Count_min) & (data_cut.loc['Q3', 'counts'] > Count_min) & (data_cut.loc['Q4', 'counts'] > Count_min):

                    X = temp_data5[consumable_Para].values.reshape(-1, 1)
                    Y = temp_data5['RR'].values.reshape(-1, 1)

                    lr.fit(X, Y)

                    b0 = round(lr.intercept_[0], 4)
                    b1 = round(lr.coef_[0][0], 4)


                    if ('4' in filtered_temp_data6['date_seg'].unique()) & (grouped_counts['date_part_seg'].str.contains('4').sum() == 4):

                        X_weighted = np.repeat(temp_data5[consumable_Para], temp_data5['group'].map(lambda g: weight[g]))
                        y_weighted = np.repeat(temp_data5['RR'], temp_data5['group'].map(lambda g: weight[g]))

                        model = lr.fit(X_weighted.values.reshape(-1, 1), y_weighted)

                        weighted_b0 = round(model.intercept_, 4)
                        weighted_b1 = round(model.coef_[0], 4)

                    else:

                        weighted_b0 = '-'
                        weighted_b1 = '-'

                    today_date = datetime.now()



                    if temp_data5[temp_data5['cycle'] == 1].empty == False:

                        if pd.isna(RR_Period):
                            current_cycle = temp_data5[temp_data5['cycle'] == 1]
                        else:

                            RR_Period = float(RR_Period)

                            current_period = temp_data5[temp_data5['cycle'] == 1][consumable_Para].iloc[0] - RR_Period
                            current_cycle = temp_data5[(temp_data5['cycle'] == 1)
                                                      & (temp_data5[consumable_Para] >= current_period)]
                    else:
                        current_cycle = pd.DataFrame()


                    if current_cycle.empty == False:

                        count = len(current_cycle)

                        current_date = current_cycle['Date'].iloc[0]
                        time_delta = (today_date - current_date)


                        if Maker == 'AMAT':
                            EQPM_df_R1 = EQPM_df[EQPM_df['EQP_ID'] == EQ]
                            min_count = EQPM_df_R1.sort_values(by='EVENT_TM', ascending=False)['rank'].iloc[0]

                        elif Maker == 'EBARA':
                            CH = '_AB' if '_AB' in Recipe_ID else '_CD'
                            EQ_CH = EQ + CH
                            EQPM_df_R1 = EQPM_df[EQPM_df['EQP_ID'] == EQ_CH]
                            min_count = EQPM_df_R1.sort_values(by='EVENT_TM', ascending=False)['rank'].iloc[0]

                        elif Maker == 'KCT':
                            CH = '_L' if '_L' in Recipe_ID else '_R'
                            EQ_CH = EQ + CH
                            EQPM_df_R1 = EQPM_df[EQPM_df['EQP_ID'] == EQ_CH]
                            min_count = EQPM_df_R1.sort_values(by='EVENT_TM', ascending=False)['rank'].iloc[0]

                        print(count, time_delta, min_count)


                        if (count > RR_Count) & (time_delta < timedelta(hours=12)) & (min_count >= 2):

                            Simul_Date = current_cycle['Date'].iloc[0].strftime("%Y-%m-%d %H:%M:%S")

                            X = current_cycle[consumable_Para].values.reshape(-1, 1)
                            Y = current_cycle['RR'].values.reshape(-1, 1)

                            lr.fit(X, Y)

                            current_b0 = round(lr.intercept_[0], 4)
                            current_b1 = round(lr.coef_[0][0], 4)

                            if pd.isna(RR_Period):

                                if weighted_b1 != '-':
                                    range_b1 = weighted_b1
                                    range_b0 = weighted_b0
                                else:
                                    range_b1 = b1
                                    range_b0 = b0

                                if range_b1 >= 0:
                                    current_b1 = min(current_b1, range_b1 * 2)
                                    current_b1 = max(current_b1, 0)
                                else:
                                    current_b1 = max(current_b1, range_b1 * 2)
                                    current_b1 = min(current_b1, 0)

                                lower_bound = range_b0 * 0.9
                                upper_bound = range_b0 * 1.1
                                current_b0 = max(lower_bound, min(current_b0, upper_bound))

                        else:
                            Simul_Date = '-'
                            current_b0 = '-'
                            current_b1 = '-'
                    else:
                        Simul_Date = '-'
                        current_b0 = '-'
                        current_b1 = '-'


                    if pd.notna(Pad_Seperation):
                        Pad_Seperation = int(Pad_Seperation)

                        temp_data7 = temp_data5[temp_data5[consumable_Para] <= Pad_Seperation]
                        temp_data7_len = len(temp_data7)

                        part_max_if = Pad_Seperation
                        part_min_if = 0

                        part_1q_if = part_min_if + (part_max_if - part_min_if) / 4
                        part_2q_if = part_min_if + (part_max_if - part_min_if) / 2
                        part_3q_if = part_min_if + (part_max_if - part_min_if) * 3 / 4

                        data_cut_if = pd.cut(np.array(temp_data7[consumable_Para]), bins=[part_min_if, part_1q_if, part_2q_if, part_3q_if, part_max_if], labels=['Q1', 'Q2', 'Q3', 'Q4']).describe()

                        if_data_Q1 = data_cut_if.loc['Q1', 'counts']
                        if_data_Q2 = data_cut_if.loc['Q2', 'counts']
                        if_data_Q3 = data_cut_if.loc['Q3', 'counts']
                        if_data_Q4 = data_cut_if.loc['Q4', 'counts']

                        print(if_data_Q1, if_data_Q2, if_data_Q3, if_data_Q4)

                        if_judge = (if_data_Q1 >= 25) & (if_data_Q2 >= 25) & (if_data_Q3 >= 25) & (if_data_Q4 >= 25)

                        if (temp_data7_len >= 100) & (if_judge):
                            X_if = temp_data7[consumable_Para].values.reshape(-1, 1)
                            Y_if = temp_data7['RR'].values.reshape(-1, 1)

                            lr.fit(X_if, Y_if)

                            if_b1 = round(lr.coef_[0][0], 4)
                            if_b0 = round(lr.intercept_[0], 4)

                        else:
                            if_b1 = '-'
                            if_b0 = '-'

                    else:
                        if_b1 = '-'
                        if_b0 = '-'



                    report = {'Date': today, 'Fab': Fab, 'Lot_Code': Lot_Code,
                              'Oper_Code': Oper_Code, 'Oper_Desc': Oper_Desc, 'APC_Para': APC_Para,
                              'EQ': EQ, 'Recipe_ID': Recipe_ID, 'Count': Count, 'b1': b1, 'b0': b0,
                              'b1_weighted': weighted_b1, 'b0_weighted': weighted_b0,
                              'Simul_Date': Simul_Date, 'b1_current': current_b1, 'b0_current': current_b0, 'if_b1': if_b1, 'if_b0': if_b0}

                    report = {k: v for k, v in report.items() if v != '-'}

                    mongo.insert_row(report)



                else:
                    print(data_cut)


    def Removal_getdata(merge_df, fab, lot_code, oper_code, pre_oper_code, recipe_id, oper_desc, recipe_info, mico_info_key, ai_studio_url=None):

        Family = mico_info_key['Family'].unique()[0]
        client = MongoClient('mongodb://cncmico...')
        db = client['mico-platform-mongodb']
        collection_name = 'MICO_PRE_THK_' + lot_code + '_' + oper_desc + '_' + fab + '_Period'

        collection = db[collection_name]

        doc = list(collection.find({}, {'_id': False}))
        Pre_Thk_Table = pd.DataFrame(doc)

        Oper_Desc = mico_info_key['Oper_Desc'].unique()[0]

        Pre_Thk_Table.rename(columns={'Pre_Thk_Para': 'Thk_Para'}, inplace=True)



        merge_df.rename(columns={'pre_oper_time': 'Pre_Oper_Date', 'request_dtts': 'Date'}, inplace=True)
        Pre_Thk_Table.rename(columns={'pre_oper_time': 'Pre_Oper_Date'}, inplace=True)

        merge_df.dropna(subset=['Pre_Oper_Date'], inplace=True)
        merge_df['Pre_Oper_Date'] = pd.to_datetime(merge_df['Pre_Oper_Date'])
        Pre_Thk_Table['Pre_Oper_Date'] = pd.to_datetime(Pre_Thk_Table['Pre_Oper_Date'])

        merge_df = merge_df.sort_values(by='Pre_Oper_Date', ascending=True)

        Online_table_names = db.list_collection_names()
        collection_name = 'MICO_PRE_THK_INFO_' + lot_code + '_' + oper_desc + '_' + fab

        if collection_name in Online_table_names:

            collection = db[collection_name]

            doc = list(collection.find({}, {'_id': False}))
            Pre_Thk_info_Table = pd.DataFrame(doc)
            Pre_Thk_info_Table.rename(columns={'samp_matl_if': 'substrate_id'}, inplace=True)

            Pre_Thk_info_Table.replace('-', 0, inplace=True)



            if oper_desc == 'SOURCE OX CMP':
                col_name = [item for item in Pre_Thk_info_Table.columns if item not in {'substrate_id', 'end_tm'}]

                merge_df = pd.merge(merge_df, Pre_Thk_info_Table[col_name], left_on='lot_id', right_on='alias_lot_id', how='left')

            else:
                col_name = [item for item in Pre_Thk_info_Table.columns if item not in {'alias_lot_id', 'end_tm'}]

                merge_df = pd.merge(merge_df, Pre_Thk_info_Table[col_name], on='substrate_id', how='left')


        for Thk_key in Pre_Thk_Table['THK_Para'].unique():

            mico_info_key['Pre_Thk_Para_ITM']

            key = mico_info_key[(mico_info_key['Thk_Para'] == Thk_key) | (mico_info_key['Pre_Thk_Para_ITM'] == Thk_key)].copy()

            Pre_Oper_Desc2 = key['Pre_Oper_Desc2'].unique()[0]
            Pre_Oper_Para2 = key['Pre_Oper_Para2'].unique()[0]
            Pre_Oper_Desc3 = key['Pre_Oper_Desc3'].unique()[0]
            Pre_Oper_Para3 = key['Pre_Oper_Para3'].unique()[0]
            Pre_Oper_Desc4 = key['Pre_Oper_Desc4'].unique()[0]
            Pre_Oper_Para4 = key['Pre_Oper_Para4'].unique()[0]

            temp_pre_thk = Pre_Thk_Table[Pre_Thk_Table['THK_Para'] == Thk_key].drop(columns=['Date', 'THK_Para'])

            temp_pre_thk = temp_pre_thk.sort_values(by='Pre_Oper_Date', ascending=True)

            temp_pre_thk.rename(columns={'Pre_Thk': Thk_key+'_VM', 'Count': Thk_key+'_Count'}, inplace=True)


            cols_to_drop = [c for c in merge_df.columns if c.endswith('_x') or c.endswith('_y')]
            merge_df = merge_df.drop(columns=cols_to_drop)

            merge_df = pd.merge_asof(merge_df, temp_pre_thk, on='Pre_Oper_Date', by=['pre_eq_ch'])
            merge_df.drop_duplicates(subset=['substrate_id'], inplace=True)

            if ai_studio_url != None:

                col_name = [Pre_Oper_Desc2+'.'+Pre_Oper_Para2, Pre_Oper_Desc3+'.'+Pre_Oper_Para3, Pre_Oper_Desc4+'.'+Pre_Oper_Para4]
                col_name = [col for col in col_name if col != '.']
                col_name.insert(0, Thk_key+'_VM')

                Pre_Thk_df = merge_df.dropna(subset=col_name).copy()

                infer_data = Pre_Thk_df[col_name].to_numpy()
                infer_data = infer_data[~np.isnan(infer_data).any(axis=1)]

                if ('EX' in Thk_key) or ('ED2' in Thk_key):
                    url = ai_studio_url['url_ex']
                elif 'ED' in Thk_key:
                    url = ai_studio_url['url_ed']
                else:
                    url = ai_studio_url['url_13p']

                inputs = {
                    "input": [
                        {
                            "name": "AI_STUDIO",
                            "shape": list(infer_data.shape),
                            "datatype": type(infer_data).__name__,
                            "data": infer_data.tolist()
                        }
                    ]
                }

                req_msg = json.dumps(inputs)
                headers = {'Content-Type': 'applications/json'}
                resp = requests.post(url, headers=headers, data=req_msg)

                output = json.loads(resp.content)['output']['aiu_output']

                Pre_Thk_df['output'] = output

                merge_df = pd.merge(merge_df, Pre_Thk_df[['substrate_id', 'output']], on='substrate_id', how='left')

                merge_df[Thk_key+'_VM'] = merge_df['output']

                merge_df.drop(columns=['output'], inplace=True)


            else:

                if Pre_Oper_Desc2 != '':

                    merge_df[['PRE_OPER2_b1', 'PRE_OPER2_b0']] = merge_df[['PRE_OPER2_b1', 'PRE_OPER2_b0']].fillna(merge_df[['PRE_OPER2_b1', 'PRE_OPER2_b0']].mean())

                    if Oper_Desc == 'SOURCE OX CMP':
                        pre_oper2_weight = 2
                    else:
                        pre_oper2_weight = 1

                    pre_oper2_b1_filled = merge_df['PRE_OPER2_b1'].fillna(0)
                    pre_oper2_b0_filled = merge_df['PRE_OPER2_b0'].fillna(0)


                    merge_df[Thk_key+'_VM'] = merge_df[Thk_key+'_VM'] + pre_oper2_weight * (
                        merge_df[Pre_Oper_Desc2 + '.' + Pre_Oper_Para2] * pre_oper2_b1_filled + pre_oper2_b0_filled
                    )

                    merge_df.drop(columns=['PRE_OPER2_b1', 'PRE_OPER2_b0'], inplace=True)

                if Pre_Oper_Desc3 != '':

                    pre_oper3_b1_filled = merge_df['PRE_OPER3_b1'].fillna(0)
                    pre_oper3_b0_filled = merge_df['PRE_OPER3_b0'].fillna(0)

                    pre_oper3_weight = 1


                    merge_df[Thk_key+'_VM'] = merge_df[Thk_key+'_VM'] + pre_oper3_weight * (
                        merge_df[Pre_Oper_Desc3 + '.' + Pre_Oper_Para3] * pre_oper3_b1_filled + pre_oper3_b0_filled
                    )

                    merge_df.drop(columns=['PRE_OPER3_b1', 'PRE_OPER3_b0'], inplace=True)


                if Pre_Oper_Desc4 != '':

                    pre_oper4_b1_filled = merge_df['PRE_OPER4_b1'].fillna(0)
                    pre_oper4_b0_filled = merge_df['PRE_OPER4_b0'].fillna(0)

                    pre_oper4_weight = 1


                    merge_df[Thk_key+'_VM'] = merge_df[Thk_key+'_VM'] + pre_oper4_weight * (
                        merge_df[Pre_Oper_Desc4 + '.' + Pre_Oper_Para4] * pre_oper4_b1_filled + pre_oper4_b0_filled
                    )

                    merge_df.drop(columns=['PRE_OPER4_b1', 'PRE_OPER4_b0'], inplace=True)

        return merge_df
