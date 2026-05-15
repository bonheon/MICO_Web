import sys, os
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))
from Common.Get_Data import Get_data
from Common.MongoDB_Control import mongodb_controller
from sklearn.linear_model import LinearRegression
from datetime import datetime, timedelta, date
from pymongo import MongoClient
import pandas as pd
import numpy as np
from itertools import product



class OFFSET_Get :


    def Logic(merge_df, search_key, pol_type, Fab) :

        today = datetime.now()
        print('Offset_Logic 시작')
        Family = search_key.Family
        Fab = search_key.Fab
        Lot_Code = search_key.Lot_Code
        Oper_Code = search_key.Oper_Code
        Oper_Desc = search_key.Oper_Desc
        APC_Para = search_key.APC_Para
        Thk_Para = search_key.Thk_Para
        Recipe_ID = search_key.Recipe_ID
        Pre_Target = search_key.Pre_Target
        if pd.notna(Pre_Target) :
            Pre_Target = float(Pre_Target)
        Target = float(search_key.Target)
        FB_Type = search_key.FB_Type

        url = 'mongodb://cncmico...'
        db = 'mico-platform-mongodb'
        collection = 'MICO_OFFSET_' + Lot_Code + '_' + Oper_Desc + '_' + Fab

        mongo = mongodb_controller(url, db, collection)

        Pol_Para = Get_data.APCParaGet(APC_Para, pol_type)
        Pol_Para_OFFSET = [item + '_OFFSET' for item in Pol_Para]

        Pad_Para = Get_data.PadParaGet(APC_Para)
        Head_Para = Get_data.HeadParaGet(APC_Para)
        Disk_Para = Get_data.DiskParaGet(APC_Para)

        temp_data = merge_df[(merge_df['operation_id'] == Oper_Code)
                    & (merge_df['recipe_id'] == Recipe_ID)].copy()


        if temp_data.empty :
            return None

        offset_columns = [col for col in temp_data.columns if 'OFFSET' in col]
        temp_data.fillna(value={col: 0 for col in offset_columns}, inplace=True)

        temp_data['eq_recipe'] = temp_data['eqp_id'] + '//' + temp_data['recipe_id']

        temp_data.drop_duplicates(inplace=True)

        for i in range(len(Pol_Para)) :
            if i == 0 :
                temp_data['Pol_Time'] = temp_data[Pol_Para[0]]
            else :
                temp_data['Pol_Time'] += temp_data[Pol_Para[i]]

        temp_data.dropna(subset=[Thk_Para], inplace=True)

        col_list = [col for col in temp_data.columns if 'B0' in col or 'B1' in col]

        temp_data['eq_recipe'] = temp_data['eqp_id'] + '//' + temp_data['recipe_id']
        temp_data.fillna(temp_data.groupby(['eq_recipe'])[col_list].transform('mean'), inplace=True)

        def fill_na(df, pattern_list):

            filtered_columns = [col for col in df.columns if any(pattern in col for pattern in pattern_list)]

            for col in filtered_columns :

                mean_value = df[col].mean()
                df[col].fillna(mean_value, inplace=True)

            return df

        for col in temp_data.columns :
            if ('_B0' in col) | ('_B1' in col) :
                temp_data[col] = pd.to_numeric(temp_data[col])

        temp_data = fill_na(temp_data, ['B0', 'B1'])


        if 'REV' in Thk_Para :
            temp_data['RR'] = (temp_data[Thk_Para] - Pre_Target) / temp_data['Pol_Time']
        else :
            temp_data['RR'] = (Pre_Target - temp_data[Thk_Para]) / temp_data['Pol_Time']

        b1_col = f"{APC_Para}_B1"
        if b1_col not in temp_data.columns :
            return temp_data
        temp_data['RR_Pad'] = temp_data[Pad_Para] * temp_data[APC_Para + '_B1'] + temp_data[APC_Para + '_B0']

        if 'REV' in Thk_Para :
            temp_data['OFFSET'] = ((Target - Pre_Target) / temp_data['RR']) - ((Target - Pre_Target) / temp_data['RR_Pad'])
        else :
            temp_data['OFFSET'] = ((Pre_Target - Target) / temp_data['RR']) - ((Pre_Target - Target) / temp_data['RR_Pad'])

        temp_data['OFFSET'] = temp_data['OFFSET'].apply(lambda x : min(max(x, -5), 3))

        temp_data.loc[temp_data['IDLE'].str.contains('LC_T_|LC_TB_'), 'OFFSET'] = 0

        temp_data['recipe_group'] = temp_data['recipe_id'].apply(lambda x : '_'.join(x.split('_')[:3]))
        temp_data['APC_Para'] = APC_Para
        temp_data_idle = temp_data[temp_data['IDLE'].str.contains('Idle_') | temp_data['IDLE'].str.contains('Layer_')]

        for i in temp_data_idle['eq_recipe'].unique() :

            temp_data2 = temp_data_idle[temp_data_idle['eq_recipe'] == i]


            grouped = temp_data2.groupby(['eqp_id', 'recipe_id', 'IDLE']).size().reset_index(name='count')
            filtered_groups = grouped[grouped['count'] >= 5]
            filtered_data = temp_data2.merge(filtered_groups[['eqp_id', 'recipe_id', 'IDLE']], on=['eqp_id', 'recipe_id', 'IDLE'])
            IDLE_RR_Table = filtered_data.groupby(['eqp_id', 'recipe_id', 'IDLE'])['OFFSET'].mean().reset_index()

            IDLE_RR_Table['IDLE'].replace('', 'Normal', inplace=True)
            
            print('IDLE_RR_Table',pd.DataFrame(IDLE_RR_Table))

            today = datetime.now()

            for i in range(len(IDLE_RR_Table)) :

                temp_row = IDLE_RR_Table.iloc[i,:]

                dict_list = temp_row.to_dict()
                dict_list['APC_Para'] = APC_Para
                dict_list['Date'] = today


                mongo.insert_row(dict_list)
        print('Offset_Logic 완료')
        return temp_data




    def Offset_getdata(
        merge_df,
        Family,
        Fab,
        Lot_Code,
        Oper_Desc,
        APC_Para_List
        ) :

        print('Offset_getdata 시작')
        url = 'mongodb://cncmico...'
        db = 'mico-platform-mongodb'
        collection = 'MICO_Removal_Rate_' + Lot_Code + '_' + Oper_Desc + '_' + Fab

        mongo = mongodb_controller(url, db, collection)

        RR_Table = mongo.get_df()

        def fill_columns(row) :

            if 'b1_weighted' not in row.index :
                return pd.Series([row['b1'], row['b0']], index=['b1_new', 'b0_new'])

            if pd.isna(row['b1_weighted']) :
                return pd.Series([row['b1'], row['b0']], index=['b1_new', 'b0_new'])
            else :
                return pd.Series([row['b1_weighted'], row['b0_weighted']], index=['b1_new', 'b0_new'])

        print('fill columns 함수 시작')
        RR_Table[['b1_new','b0_new']] = RR_Table.apply(fill_columns, axis=1)
        print('fill columns 함수 완료')
        RR_Table = RR_Table[RR_Table['APC_Para'].isin(APC_Para_List)][['Date','APC_Para','EQ','Recipe_ID','b1_new','b0_new']].copy()
        RR_Table['Date'] = pd.to_datetime(RR_Table['Date'])

        merge_df.rename(columns={'request_dtts': 'Date'}, inplace=True)
        RR_Table.rename(columns={'EQ': 'eqp_id', 'Recipe_ID': 'recipe_id', 'APC_Para': 'input_name'}, inplace=True)


        for col in RR_Table.columns :
            if ('-' not in RR_Table[col].unique().tolist()) & ('_new' in col) :
                RR_Table[col] = pd.to_numeric(RR_Table[col])
            elif (['-'] == RR_Table[col].unique().tolist()) & ('_new' in col) :
                RR_Table.drop(columns=col, inplace=True)

        pivot_col = [col for col in RR_Table.columns.tolist() if '_new' in col]

        RR_pivot = pd.pivot_table(data=RR_Table, index=['Date', 'eqp_id', 'recipe_id'], columns=['input_name'], values=pivot_col).reset_index()

        col_list = []
        for i in RR_pivot.columns :
            if 'b1' in i[0] :
                col_list.append(i[1]+'_B1')
            elif 'b0' in i[0] :
                col_list.append(i[1]+'_B0')
            else :
                col_list.append(i[0])

        RR_pivot.columns = col_list

        RR_pivot['Date'] = pd.to_datetime(RR_pivot['Date'])
        RR_pivot['Date'] = RR_pivot['Date'].astype('datetime64[ns]')

        merge_df = merge_df.sort_values(by='Date', ascending=True)
        RR_pivot = RR_pivot.sort_values(by='Date', ascending=True)

        merge_df = pd.merge_asof(merge_df, RR_pivot, on='Date', by=['eqp_id', 'recipe_id'])

        print('Offset_getdata 완료')
        return merge_df



    def LC_Logic(temp_data, Family, Lot_Code, Oper_Desc, Fab, Offset_Group) :

        print('Offset_L/C Logic 시작')
        url = 'mongodb://cncmico...'
        db_name = 'mico-platform-mongodb'
        collection_name = 'MICO_OFFSET_' + Lot_Code + '_' + Oper_Desc + '_' + Fab

        client = MongoClient(url)
        db = client[db_name]
        collection = db[collection_name]

        lc_offset = pd.DataFrame()
        today = datetime.now()

        temp_data['eq_recipe_apc'] = temp_data['eq_recipe'] + '//' + temp_data['APC_Para']
        temp_data['IDLE'].fillna('Normal', inplace=True)

        temp_data_lc = temp_data[temp_data['IDLE'].str.contains('LC_')
                                & (~temp_data['IDLE'].str.contains('_ADD_')
                                & ~temp_data['IDLE'].str.contains('_T_')
                                & ~temp_data['IDLE'].str.contains('_TB_'))].copy()

        temp_data_tb = temp_data[temp_data['IDLE'].str.contains('_ADD_')
                                | temp_data['IDLE'].str.contains('_T_')
                                | temp_data['IDLE'].str.contains('_TB_')].copy()

        temp_data_lc_merge = pd.concat([temp_data_lc, temp_data_tb], axis=0)


        df_list = [temp_data_lc, temp_data_tb]



        if Offset_Group == 'Y' :
            temp_data_lc['IDLE'] = temp_data_lc['IDLE'].apply(lambda x : '_'.join([x.split('_')[0], x.split('_')[2]]))
            temp_data_tb['IDLE'] = temp_data_tb['IDLE'].apply(lambda x : '_'.join([x.split('_')[0], x.split('_')[3]]))
            temp_data_lc_total = pd.concat([temp_data_lc, temp_data_tb], axis=0)


            IDLE_RR_Table = temp_data_lc_total.groupby(['eq_recipe_apc', 'IDLE'])['OFFSET'].mean().reset_index()



            eqp_recipe_id = IDLE_RR_Table['eq_recipe_apc'].unique()
            params = IDLE_RR_Table['IDLE'].unique()

            all_combination = pd.DataFrame(product(eqp_recipe_id, params), columns=['eq_recipe_apc', 'IDLE'])
            IDLE_RR_Table = pd.merge(all_combination, IDLE_RR_Table, on=['eq_recipe_apc', 'IDLE'], how='left')

            IDLE_RR_Table['eqp_id'] = IDLE_RR_Table['eq_recipe_apc'].str.split('//').str[0]
            IDLE_RR_Table['recipe_id'] = IDLE_RR_Table['eq_recipe_apc'].str.split('//').str[1]
            IDLE_RR_Table['APC_Para'] = IDLE_RR_Table['eq_recipe_apc'].str.split('//').str[2]
            IDLE_RR_Table['recipe_group'] = IDLE_RR_Table['recipe_id'].str.split('_').str[0] + IDLE_RR_Table['recipe_id'].str.split('_').str[1] + IDLE_RR_Table['recipe_id'].str.split('_').str[2]


            IDLE_RR_Table['OFFSET_2'] = IDLE_RR_Table.groupby(['recipe_group', 'IDLE'])['OFFSET'].transform('mean')
            IDLE_RR_Table.rename(columns={'OFFSET': 'OFFSET_Origin',
                                            'OFFSET_2': 'OFFSET'}, inplace=True)

            if lc_offset.empty :
                lc_offset = IDLE_RR_Table

            else :
                lc_offset = pd.concat([lc_offset, IDLE_RR_Table], axis=0)


        else :

            IDLE_RR_Table = temp_data_lc_merge.groupby(['eq_recipe_apc', 'IDLE'])['OFFSET'].mean().reset_index()



            eqp_recipe_id = IDLE_RR_Table['eq_recipe_apc'].unique()
            params = IDLE_RR_Table['IDLE'].unique()

            all_combination = pd.DataFrame(product(eqp_recipe_id, params), columns=['eq_recipe_apc', 'IDLE'])
            IDLE_RR_Table = pd.merge(all_combination, IDLE_RR_Table, on=['eq_recipe_apc', 'IDLE'], how='left')

            IDLE_RR_Table['eqp_id'] = IDLE_RR_Table['eq_recipe_apc'].str.split('//').str[0]
            IDLE_RR_Table['recipe_id'] = IDLE_RR_Table['eq_recipe_apc'].str.split('//').str[1]
            IDLE_RR_Table['APC_Para'] = IDLE_RR_Table['eq_recipe_apc'].str.split('//').str[2]
            IDLE_RR_Table['recipe_group'] = IDLE_RR_Table['recipe_id'].str.split('_').str[0] + IDLE_RR_Table['recipe_id'].str.split('_').str[1] + IDLE_RR_Table['recipe_id'].str.split('_').str[2]


            IDLE_RR_Table['OFFSET_2'] = IDLE_RR_Table.groupby(['recipe_group', 'IDLE'])['OFFSET'].transform('mean')
            IDLE_RR_Table.rename(columns={'OFFSET': 'OFFSET_Origin',
                                            'OFFSET_2': 'OFFSET'}, inplace=True)

            if lc_offset.empty :
                lc_offset = IDLE_RR_Table

            else :
                lc_offset = pd.concat([lc_offset, IDLE_RR_Table], axis=0)

        lc_offset['Date'] = today
        lc_offset = lc_offset[['eqp_id', 'recipe_id', 'IDLE', 'OFFSET', 'APC_Para', 'Date']].copy()
        lc_offset['OFFSET'].fillna(0, inplace=True)

        records = lc_offset.to_dict('records')
        
        print(records)

        if len(records) != 0 :
            collection.insert_many(records)

        print('Offset_L/C Logic 완료')
