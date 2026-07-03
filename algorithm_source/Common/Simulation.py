import sys, os
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))
from Common.Get_Data import Get_data
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from datetime import datetime, timedelta, date
import pandas as pd
import numpy as np
from pymongo import MongoClient
import requests
import json


class Simulation_Get:

    @staticmethod
    def getdata(Family, Fab, Lot_Code, Oper_Code, Recipe_ID_List, oper_desc, Days=None):
    
        merge_df = Get_data.MongoDB_GetData(Family, Fab, Lot_Code, oper_desc)

        ref_lot_df = Get_data.RefGetData(Fab, Lot_Code, Oper_Code, Recipe_ID_List, Days)
        ref_lot_df_hub = Get_data.RefGetData_HUB(Fab, Lot_Code, Oper_Code, Recipe_ID_List)

        ref_lot_df = pd.concat([ref_lot_df, ref_lot_df_hub])
        ref_lot_df.drop_duplicates(subset = ['substrate_id', 'input_name'], inplace=True)

        
        url = 'mongodb://cncmico:...'
        db = 'mico-platform-mongodb'

        client = MongoClient(url)
        db_name = client[db]



        collection_name = 'MICO_PRE_THK_' + Lot_Code + '_' + oper_desc + '_' + Fab + '_Period'
        if Family == 'TEST' :
            collection_name += '_TEST'

        collection = db_name[collection_name]
        data = list(collection.find())
        Pre_VM_df = pd.DataFrame(data)
        print('Pre Len :', len(Pre_VM_df))

        collection_name = 'MICO_Removal_Rate_' + Lot_Code + '_' + oper_desc + '_' + Fab
        if Family == 'TEST' :
            collection_name += '_TEST'

        collection = db_name[collection_name]
        data = list(collection.find())
        RR_df = pd.DataFrame(data)
        print('RR Len :', len(RR_df))

        collection_name = 'MICO_OFFSET_' + Lot_Code + '_' + oper_desc + '_' + Fab
        if Family == 'TEST' :
            collection_name += '_TEST'

        collection = db_name[collection_name]
        data = list(collection.find())
        OFFSET_df = pd.DataFrame(data)
        print('Offset Len :', len(OFFSET_df))

        Online_table_names = db_name.list_collection_names()

        Online_table_name = 'MICO_Online_Simulation_' + Lot_Code + '_' + oper_desc + '_' + Fab
        if Family == 'TEST' :
            Online_table_name += '_TEST'

        online_simul_df = pd.DataFrame()

        if Online_table_name in Online_table_names : 

            print('Simulation DB 조회')

            collection_name = db_name[Online_table_name]
            data = list(collection_name.find())
            online_simul_df = pd.DataFrame(data)

            if not online_simul_df.empty :
                online_simul_df['substrate_id'] = online_simul_df['LOT_ID'].str[:7] + '.' + online_simul_df['SLOT_ID']
                online_simul_df['rank'] = online_simul_df.groupby(['LOT_ID','SLOT_ID'])['Date'].rank(ascending=False)
                online_simul_df = online_simul_df[online_simul_df['rank'] == 1]

        merge_df = merge_df.sort_values(by= 'Date', ascending= True)

        return merge_df, ref_lot_df, Pre_VM_df, RR_df, OFFSET_df, online_simul_df





    @staticmethod
    def _logic_core(
        search_key,
        merge_df,
        ref_lot_df,
        Pre_VM_df,
        RR_df,
        OFFSET_df,
        online_simul_df,
        pol_type,
        mode,
        Offset_Group=None,
        Thk_Para_13P=None,
        Target_13P=None,
        ITM_PRE_Para=None,
        ai_studio_url=None,
    ):


        Fab = search_key.Fab
        Lot_Code = search_key.Lot_Code
        Oper_Code = search_key.Oper_Code
        Oper_Desc = search_key.Oper_Desc
        APC_Para = search_key.APC_Para
        Thk_Para = search_key.Thk_Para
        Recipe_ID = search_key.Recipe_ID
        RR_Para = search_key.RR_Para
        Pre_Oper_Code2 = search_key.Pre_Oper_Code2
        Pre_Oper_Desc2 = search_key.Pre_Oper_Desc2
        Pre_Oper_Para2 = search_key.Pre_Oper_Para2
        Pre_Oper_Code3 = search_key.Pre_Oper_Code3
        Pre_Oper_Desc3 = search_key.Pre_Oper_Desc3
        Pre_Oper_Para3 = search_key.Pre_Oper_Para3
        Pre_Oper_Code4 = search_key.Pre_Oper_Code4
        Pre_Oper_Desc4 = search_key.Pre_Oper_Desc4
        Pre_Oper_Para4 = search_key.Pre_Oper_Para4
        Pre_Thk_Para_ITM = search_key.Pre_Thk_Para_ITM
        Pre_Target = search_key.Pre_Target
        if pd.notna(Pre_Target):
            Pre_Target = float(Pre_Target)
        Target = float(search_key.Target)
        Pad_Seperation = search_key.Pad_Seperation

        if pd.isna(Pad_Seperation):
            Pad_Seperation = -1
        else : 
            Pad_Seperation = float(Pad_Seperation)


        Main_Para = Get_data.APCParaGet(APC_Para, pol_type)
        Main_Para_formula = [x + '_formula' for x in Main_Para]
        Main_Para_OFFSET = [x + '_OFFSET' for x in Main_Para]

        Pad_Para = Get_data.PadParaGet(APC_Para)
        Disk_Para = Get_data.DiskParaGet(APC_Para)
        Head_Para = Get_data.HeadParaGet(APC_Para)

        RR_Para = RR_Para.upper()

        if 'HEAD' == RR_Para :
            Consumable_Para = Head_Para
        elif 'PAD' == RR_Para : 
            Consumable_Para = Pad_Para
        elif 'DISK' == RR_Para : 
            Consumable_Para = Disk_Para

        Ref_Para = Get_data.REFParaGet(APC_Para, pol_type, Oper_Desc, Fab)

        if APC_Para not in merge_df.columns : 
            return pd.DataFrame()


        temp_data1 = merge_df[
            (merge_df['operation_id'] == Oper_Code)
            & (merge_df['recipe_id'] == Recipe_ID)
            & pd.notna(merge_df[APC_Para])
        ].copy()

        if temp_data1.empty:
            return pd.DataFrame()

        temp_data1['eq_model_recipe'] = (
            temp_data1['eqp_id'] + '//' + temp_data1['eqp_model'] + '//'
            + temp_data1['recipe_id'] + '//' + temp_data1['oper_det_desc']
        )


        col_list = [
            'Fab', 'Date', 'process_id', 'recipe_id', 'eqp_id', 'eqp_model',
            'lot_id', 'substrate_id', 'wf_id', 'IDLE', 'pre_eqp_id', 'pre_eqp_ch',
            'pre_oper_time', 'oper_id', 'oper_det_desc',
            Thk_Para, Pad_Para, Disk_Para, Head_Para, 'pre_eq_ch', 'eq_model_recipe'
            ] + Main_Para + Main_Para_formula


        if mode == 'PRESSURE':
            col_list.append(Thk_Para_13P)
            if ('ED2' in Thk_Para) or ('EXED' in Thk_Para):
                Thk_ED_Para = Thk_Para.replace('ED2', 'ED1').replace('EXED', 'EDGE')
                col_list.append(Thk_ED_Para)


        for x in Main_Para_OFFSET:
            if x in temp_data1.columns:
                col_list.append(x)


        for x in Main_Para_OFFSET:
            if '_PRE_' in x : 
                col_list.append(x)


        if Thk_Para.endswith('_AVG'):
            Thk_Ran_Para = Thk_Para[:-4] + '_RAN'
            col_list.append(Thk_Ran_Para)


        if Pre_Thk_Para_ITM != '':
            col_list.append(Pre_Thk_Para_ITM)


        if (type(Pre_Oper_Code2) == str) and (Pre_Oper_Code2 != ''):
            col_list.append(f"{Pre_Oper_Desc2}.{Pre_Oper_Para2}")
        if (type(Pre_Oper_Code3) == str) and (Pre_Oper_Code3 != ''):
            col_list.append(f"{Pre_Oper_Desc3}.{Pre_Oper_Para3}")
        if (type(Pre_Oper_Code4) == str) and (Pre_Oper_Code4 != ''):
            col_list.append(f"{Pre_Oper_Desc4}.{Pre_Oper_Para4}")

        col_list = list(set(col_list))

        temp_data2 = temp_data1[col_list].copy()


        offset_columns = [col for col in temp_data2.columns if 'OFFSET' in col]
        temp_data2.fillna(value={col: 0 for col in offset_columns}, inplace=True)


        temp_data2.drop_duplicates(subset=['substrate_id'], inplace=True)

        Simul_df1 = temp_data2.copy()


        col_list = ['Date', 'pre_oper_time', 'pre_eq_ch' ,'Pre_Thk', 'Count']

        if not Pre_VM_df.empty: 
            if 'PRE_OPER2_b1' in Pre_VM_df.columns:
                col_list.extend(['PRE_OPER2_b1', 'PRE_OPER2_b0'])
                Pre_VM_df.fillna(
                    Pre_VM_df.groupby(['THK_Para'])[['PRE_OPER2_b1', 'PRE_OPER2_b0']].transform('mean', numeric_only=True), 
                    inplace=True
                )
            if 'PRE_OPER3_b1' in Pre_VM_df.columns:
                col_list.extend(['PRE_OPER3_b1', 'PRE_OPER3_b0'])
                Pre_VM_df.fillna(
                    Pre_VM_df.groupby(['THK_Para'])[['PRE_OPER3_b1', 'PRE_OPER3_b0']].transform('mean', numeric_only=True), 
                    inplace=True
                )
            if 'PRE_OPER4_b1' in Pre_VM_df.columns:
                col_list.extend(['PRE_OPER4_b1', 'PRE_OPER4_b0'])
                Pre_VM_df.fillna(
                    Pre_VM_df.groupby(['THK_Para'])[['PRE_OPER4_b1', 'PRE_OPER4_b0']].transform('mean', numeric_only=True), 
                    inplace=True
                )

            if 'Pre_THK_Para' in Pre_VM_df.columns:
                Pre_VM_df = Pre_VM_df[Pre_VM_df['Pre_THK_Para'] == Pre_Thk_Para_ITM][col_list].copy()
                Pre_VM_df.rename(columns={'pre_oper_time' : 'pre_thk_time' , 'Pre_Thk' : 'PRE_THK_VM'}, inplace=True)
            else :
                Pre_VM_df = Pre_VM_df[Pre_VM_df['THK_Para'] == Thk_Para][col_list].copy()
                Pre_VM_df.rename(columns={'pre_oper_time' : 'pre_thk_time'}, inplace=True)

            Pre_VM_df['Date'] = pd.to_datetime(Pre_VM_df['Date'])


            if mode == 'TIME' : 
                Pre_VM_df.dropna(inplace=True)
            else : 
                Pre_VM_df.dropna(axis=1, inplace=True)

            Pre_VM_df = Pre_VM_df.sort_values(by='Date', ascending=True)
            Simul_df2 = pd.merge_asof(Simul_df1, Pre_VM_df, on = 'Date', by=['pre_eq_ch'])
        else : 
            Simul_df2 = Simul_df1.copy()
            Simul_df2['Pre_Thk'] = 0


        col_list = ['Date', 'EQ', 'Recipe_ID'] + [col for col in RR_df.columns if 'b1' in col or 'b0' in col]
        RR_df = RR_df[RR_df['APC_Para'] == APC_Para][col_list].copy()

        for suffix in ['weighted', 'current'] :
            if f'b1_{suffix}' not in RR_df.columns:
                RR_df[f'b1_{suffix}'] = np.nan
                RR_df[f'b0_{suffix}'] = np.nan

        if 'if_b1' not in RR_df.columns: 
            RR_df['if_b1'] = np.nan
            RR_df['if_b0'] = np.nan

        rename_map = {
            'EQ' : 'eqp_id',
            'Recipe_ID' : 'recipe_id',
            'b1' : 'RR_b1',
            'b0' : 'RR_b0',
            'b1_weighted' : 'RR_b1_weighted',
            'b0_weighted' : 'RR_b0_weighted',
            'b1_current' : 'RR_b1_current',
            'b0_current' : 'RR_b0_current',
            'if_b1' : 'RR_if_b1',
            'if_b0' : 'RR_if_b0'
        }
        RR_df.rename(columns=rename_map, inplace=True)

        RR_df['Date'] = pd.to_datetime(RR_df['Date'])
        if mode == 'TIME' :
            RR_df.replace('-', '', inplace=True)
        RR_df = RR_df.sort_values(by='Date', ascending=True)

        Simul_df3 = pd.merge_asof(Simul_df2, RR_df, on='Date', by=['eqp_id', 'recipe_id'])


        if not online_simul_df.empty:
            online_simul_df = online_simul_df[['substrate_id'] + [col for col in online_simul_df.columns if 'MICO' in col]]
            Simul_df4 = pd.merge(Simul_df3, online_simul_df, on ='substrate_id', how='left')
        else : 
            Simul_df4 = Simul_df3.copy()


        OFFSET_df = OFFSET_df[OFFSET_df['APC_Para'] == APC_Para][['eqp_id', 'recipe_id', 'IDLE', 'OFFSET', 'Date']].copy()
        OFFSET_df.rename(columns={'OFFSET' : 'Simul_OFFSET'}, inplace=True)
        OFFSET_df['Date'] = pd.to_datetime(OFFSET_df['Date'])

        if not OFFSET_df.empty :
            OFFSET_df = OFFSET_df.sort_values(by='Date', ascending=True)

 
        if mode == 'TIME' :
            Simul_df4['IDLE'].fillna('Normal', inplace=True)

            Simul_df4_lc = Simul_df4[
                Simul_df4['IDLE'].str.contains('LC_')
                & (~Simul_df4['IDLE'].str.contains('_ADD_'))
                & (~Simul_df4['IDLE'].str.contains('_T_'))
                & (~Simul_df4['IDLE'].str.contains('_TB_'))
            ].copy()

            Simul_df4_tb = Simul_df4[
                Simul_df4['IDLE'].str.contains('_ADD_')
                | Simul_df4['IDLE'].str.contains('_T_')
                | Simul_df4['IDLE'].str.contains('_TB_')
            ].copy()

            Simul_df4_normal = Simul_df4[~Simul_df4['IDLE'].str.contains('LC_')].copy()

            if Offset_Group == 'Y' :
                Simul_df4_lc['IDLE'] = Simul_df4_lc['IDLE'].apply(lambda x: '_'.join([x.split('_')[0], x.split('_')[2]]))
                Simul_df4_tb['IDLE'] = Simul_df4_tb['IDLE'].apply(lambda x: '_'.join([x.split('_')[0], x.split('_')[3]]))
                Simul_df4_lc_merge = pd.concat([Simul_df4_normal, Simul_df4_lc, Simul_df4_tb], axis=0)
            else : 
                Simul_df4_lc_merge = pd.concat([Simul_df4_normal, Simul_df4_lc, Simul_df4_tb], axis=0)

            Simul_df4_lc_merge.sort_values(by='Date', inplace=True)
            temp_data3 = pd.merge_asof(Simul_df4_lc_merge, OFFSET_df, on='Date', by=['eqp_id', 'recipe_id', 'IDLE'])
        else : 
            temp_data3 = pd.merge_asof(Simul_df4, OFFSET_df, on='Date', by=['eqp_id', 'recipe_id', 'IDLE'])


        for col in temp_data3.columns:
            if (col[0:3] == 'RR_') and ('-' not in temp_data3[col].unique().tolist()):
                temp_data3[col] = pd.to_numeric(temp_data3[col])

        temp_data3.fillna(temp_data3.groupby(['eq_model_recipe'])[['RR_b0', 'RR_b1']].transform('ffill'), inplace=True)
        temp_data3.fillna(temp_data3.groupby(['eq_model_recipe'])[['RR_b0', 'RR_b1']].transform('mean', numeric_only=True), inplace=True)
        temp_data3.fillna(temp_data3.groupby(['eq_model_recipe', 'IDLE'])[['Simul_OFFSET']].transform('mean', numeric_only=True), inplace=True)


        if Pre_Thk_Para_ITM == '':
            temp_data3.fillna(temp_data3.groupby(['pre_eq_ch'])[['Pre_Thk']].transform('ffill'), inplace=True)
            temp_data3.fillna(temp_data3.groupby(['pre_eq_ch'])[['Pre_Thk']].transform('mean', numeric_only=True), inplace=True)
            temp_data3.fillna(value={'Pre_Thk': 0}, inplace=True)
        else :
            temp_data3.fillna(temp_data3.groupby(['pre_eq_ch'])[['PRE_THK_VM']].transform('ffill'), inplace=True)
            temp_data3.fillna(temp_data3.groupby(['pre_eq_ch'])[['PRE_THK_VM']].transform('mean', numeric_only=True), inplace=True)
            temp_data3.fillna(value={'PRE_THK_VM': 0}, inplace=True)
            temp_data3['Pre_Thk'] = temp_data3['PRE_THK_VM']


        if ai_studio_url is not None : 
            temp_data3['Pre_Thk2'] = temp_data3['Pre_Thk']
            col_name = ['Pre_Thk']

            if Pre_Oper_Desc2 != '' : 
                col_name.append(Pre_Oper_Desc2 +'.'+Pre_Oper_Para2)
            if Pre_Oper_Desc3 != '' : 
                col_name.append(Pre_Oper_Desc3 +'.'+Pre_Oper_Para3)            
            if Pre_Oper_Desc4 != '' : 
                col_name.append(Pre_Oper_Desc4 +'.'+Pre_Oper_Para4)

            Pre_Thk_df = temp_data3.dropna(subset=col_name).copy()
            infer_data = Pre_Thk_df[col_name].to_numpy()
            infer_data = infer_data[~np.isnan(infer_data).any(axis=1)]

            if ('EX' in Thk_Para) or ('ED2' in Thk_Para) : 
                url = ai_studio_url['url_ex']
            elif 'ED' in Thk_Para :
                url = ai_studio_url['url_ed']
            else:
                url = ai_studio_url['url_13p']

            inputs = {
                "input" : [
                    { 
                        "name" : "AI_STUDIO",
                        "shape" : list(infer_data.shape),
                        "datatype": type(infer_data).__name__,
                        "data": infer_data.tolist()
                    }
                ]
            }

            req_msg = json.dumps(inputs)
            headers = {'Content-Type': 'application/json'}
            resp = requests.post(url, headers=headers, data=req_msg)

            output = json.loads(resp.content)['output']['aiu_output']
            Pre_Thk_df['output'] = output
    
            temp_data3 = pd.merge(temp_data3, Pre_Thk_df[['substrate_id', 'output']], on='substrate_id', how='left')
            temp_data3['Pre_Thk'] = temp_data3['output']
            temp_data3.drop(columns=['output'], inplace=True)

        else :
            
            if 'PRE_OPER2_b1' in temp_data3.columns:
                temp_data3[['PRE_OPER2_b1', 'PRE_OPER2_b0']] = temp_data3[
                    ['PRE_OPER2_b1', 'PRE_OPER2_b0']
                ].fillna(temp_data3[['PRE_OPER2_b1', 'PRE_OPER2_b0']].mean())

                temp_data3['Pre_Thk2'] = temp_data3['Pre_Thk']
                pre_oper2_weight = 2 if Oper_Desc == 'SOURCE OX CMP' else 1

                temp_data3['Pre_Thk'] = temp_data3['Pre_Thk'] + pre_oper2_weight * (
                    temp_data3[Pre_Oper_Desc2 + '.' + Pre_Oper_Para2] * temp_data3['PRE_OPER2_b1'] + temp_data3['PRE_OPER2_b0']
                )
                temp_data3.drop(columns=['PRE_OPER2_b1', 'PRE_OPER2_b0'], inplace=True)


            if Pre_Oper_Desc3 != '':
                pre_oper3_b1_filled = temp_data3['PRE_OPER3_b1'].fillna(value=temp_data3['PRE_OPER3_b1'].mean())
                pre_oper3_b0_filled = temp_data3['PRE_OPER3_b0'].fillna(value=temp_data3['PRE_OPER3_b0'].mean())
                pre_oper3_weight = 1
                temp_data3['Pre_Thk'] = temp_data3['Pre_Thk'] + pre_oper3_weight * (
                    temp_data3[Pre_Oper_Desc3 + '.' + Pre_Oper_Para3] * pre_oper3_b1_filled + pre_oper3_b0_filled
                )
                temp_data3.drop(columns=['PRE_OPER3_b1','PRE_OPER3_b0'], inplace=True)

    
            if Pre_Oper_Desc4 != '' : 
                pre_oper4_b1_filled = temp_data3['PRE_OPER4_b1'].fillna(0)
                pre_oper4_b0_filled = temp_data3['PRE_OPER4_b0'].fillna(0)
                fill_mean = temp_data3[Pre_Oper_Desc4 + '.' + Pre_Oper_Para4].mean()
                temp_data3[Pre_Oper_Desc4 + '.' + Pre_Oper_Para4] = temp_data3[Pre_Oper_Desc4 + '.' + Pre_Oper_Para4].fillna(fill_mean)
                pre_oper4_weight = 1
                temp_data3['Pre_Thk'] = temp_data3['Pre_Thk'] + pre_oper4_weight * (
                    temp_data3[Pre_Oper_Desc4 + '.' + Pre_Oper_Para4] * pre_oper4_b1_filled + pre_oper4_b0_filled
                )
                temp_data3.drop(columns=['PRE_OPER4_b1', 'PRE_OPER4_b0'], inplace=True)

        temp_data3.fillna(value={'Simul_OFFSET' : 0, 'Pre_Thk': 0}, inplace=True)
        temp_data3.drop_duplicates(subset=['Date', 'substrate_id'], inplace=True)


        ref_lot_df.drop_duplicates(inplace=True)

        if Ref_Para is not None :
            ref_temp_df = ref_lot_df[
                (ref_lot_df['operation_id'] == Oper_Code)
                & (ref_lot_df['input_name'] == Ref_Para)
            ].copy()
        else : 
            ref_temp_df = ref_lot_df[
                (ref_lot_df['operation_id'] == Oper_Code)
                & (ref_lot_df['input_name'] == APC_Para)
            ].copy()

        col_num = len(list(ref_temp_df['item_value'].str.split(';', expand=True).columns))
        col_list = [f'Ref_{i}' for i in range(1, col_num + 1)]
        ref_temp_df[col_list] = ref_temp_df['item_value'].str.split(';', expand=True)
        ref_temp_df['Ref_Count'] = ref_temp_df['item_value'].str.count(';')
        ref_temp_df['Ref_YN'] = ref_temp_df['item_value'].str.count(';')


        ref_data_cols = ['Date', 'substrate_id', Thk_Para, 'Pre_Thk', APC_Para, 'Simul_OFFSET']
        if mode == 'PRESSURE':
            ref_data_cols.insert(2, Thk_Para_13P)

        if ITM_PRE_Para is not None:
            ref_data_cols.append(ITM_PRE_Para)

        ref_data = temp_data3[ref_data_cols].copy()
        ref_data.dropna(axis=0, how='any', inplace=True)

    
        if mode == 'TIME' :
            base_cols = ['{}_Date', '{}', '{}_Post', '{}_Pre_VM', '{}_APC', '{}_OFFSET']
        else:
            base_cols = ['{}_Date', '{}', '{}_13P', '{}_Post', '{}_Pre_VM', '{}_APC', '{}_OFFSET']

        itm_cols = base_cols + ['{}_Pre_ITM']

        def merge_ref_data(df, r_data, ref_num, itm_para):
            merge_col = f'Ref_{ref_num}'
            if itm_para is not None : 
                cols = [c.format(merge_col) for c in itm_cols]
            else : 
                cols = [c.format(merge_col) for c in base_cols]
            r_data.columns = cols
            return pd.merge(df, r_data, on=merge_col, how='left')

        for i in range(1, 5):
            if f'Ref_{i}' not in ref_temp_df.columns:
                continue
            ref_temp_df = merge_ref_data(ref_temp_df, ref_data, i, ITM_PRE_Para)


        final_cols = ['substrate_id']
        for i in range(1, 5):
            if f'Ref_{i}' not in ref_temp_df.columns:
                continue
            if ITM_PRE_Para is not None:
                if mode == 'TIME' : 
                    final_cols.extend([
                        f'Ref_{i}_Date', f'Ref_{i}', f'Ref_{i}_Post',
                        f'Ref_{i}_Pre_VM', f'Ref_{i}_APC', f'Ref_{i}_OFFSET', f'Ref_{i}_Pre_ITM'
                    ])
                else :
                    final_cols.extend([
                        f'Ref_{i}_Date', f'Ref_{i}', f'Ref_{i}_13P', f'Ref_{i}_Post',
                        f'Ref_{i}_Pre_VM', f'Ref_{i}_APC', f'Ref_{i}_OFFSET', f'Ref_{i}_Pre_ITM'
                    ])
            else :
                if mode == 'TIME' : 
                    final_cols.extend([
                        f'Ref_{i}_Date', f'Ref_{i}', f'Ref_{i}_Post',
                        f'Ref_{i}_Pre_VM', f'Ref_{i}_APC', f'Ref_{i}_OFFSET',
                    ])
                else :
                    final_cols.extend([
                        f'Ref_{i}_Date', f'Ref_{i}', f'Ref_{i}_13P', f'Ref_{i}_Post',
                        f'Ref_{i}_Pre_VM', f'Ref_{i}_APC', f'Ref_{i}_OFFSET',
                    ])

        final_cols.extend(['Ref_Count', 'Ref_YN'])
        ref_temp_df = ref_temp_df[[col for col in final_cols if col in ref_temp_df.columns]].copy()
        ref_temp_df.drop_duplicates(inplace=True)

        temp_data4 = pd.merge(temp_data3, ref_temp_df, on='substrate_id', how='left')


        if mode == 'TIME' :
            for i in range(len(Main_Para)):
                if i == 0:
                    temp_data4['Pol_Time'] = temp_data4[Main_Para[0]]
                else :
                    temp_data4['Pol_Time'] += temp_data4[Main_Para[i]]
                temp_data4[f'Pol_Time_{i+1}'] = temp_data4[Main_Para[i]]
        else :
            for i in range(len(Main_Para)):
                temp_data4[f'Pressure_{i+1}'] = temp_data4[Main_Para[i]]

        temp_data4['PAD_TIME'] = temp_data4[Pad_Para]
        temp_data4['DISK_TIME'] = temp_data4[Disk_Para]
        temp_data4['HEAD_TIME'] = temp_data4[Head_Para]
        temp_data4['THK'] = temp_data4[Thk_Para]
  

        def RR(Consumable_Para, RR_b1_weighted, RR_b0_weighted, RR_b1, RR_b0,
              RR_b1_current, RR_b0_current, RR_if_b1, RR_if_b0):
            if (pd.isna(RR_if_b1) == False) and (RR_if_b1 != '-') and (Consumable_Para <= Pad_Seperation):
                return Consumable_Para * RR_if_b1 + RR_if_b0
            elif pd.isna(RR_b1_current) == False:
                return Consumable_Para * RR_b1_current + RR_b0_current
            elif pd.isna(RR_b1_weighted) == False:
                return Consumable_Para * RR_b1_weighted + RR_b0_weighted
            else :
                return Consumable_Para * RR_b1 + RR_b0

        RR_vector = np.vectorize(RR)
 
        temp_data4['RR_DB'] = RR_vector(
            temp_data4[Consumable_Para], 
            temp_data4['RR_b1_weighted'], temp_data4['RR_b0_weighted'],
            temp_data4['RR_b1'], temp_data4['RR_b0'],
            temp_data4['RR_b1_current'], temp_data4['RR_b0_current'],
            temp_data4['RR_if_b1'], temp_data4['RR_if_b0'],
        )

        return temp_data4





    @staticmethod
    def Logic_Time(
        search_key,
        merge_df,
        ref_lot_df,
        Pre_VM_df,
        RR_df,
        OFFSET_df,
        online_simul_df,
        pol_type,
        Offset_Group,
        ITM_PRE_Para=None,
        ai_studio_url=None,
    ):
        return Simulation_Get._logic_core(
            search_key=search_key,
            merge_df=merge_df,
            ref_lot_df=ref_lot_df,
            Pre_VM_df=Pre_VM_df,
            RR_df=RR_df,
            OFFSET_df=OFFSET_df,
            online_simul_df=online_simul_df,
            pol_type=pol_type,
            mode='TIME',
            Offset_Group=Offset_Group,
            ITM_PRE_Para=ITM_PRE_Para,
            ai_studio_url=ai_studio_url,
        )

    
    @staticmethod
    def Logic_Pressure(
        search_key,
        merge_df,
        Thk_Para_13P,
        Target_13P,
        ref_lot_df,
        Pre_VM_df,
        RR_df,
        OFFSET_df,
        online_simul_df,
        pol_type,
        ITM_PRE_Para=None,
        ai_studio_url=None,
    ):
        return Simulation_Get._logic_core(
            search_key=search_key,
            merge_df=merge_df,
            ref_lot_df=ref_lot_df,
            Pre_VM_df=Pre_VM_df,
            RR_df=RR_df,
            OFFSET_df=OFFSET_df,
            online_simul_df=online_simul_df,
            pol_type=pol_type,
            mode='PRESSURE',
            Thk_Para_13P=Thk_Para_13P,
            Target_13P=Target_13P,
            ITM_PRE_Para=ITM_PRE_Para,
            ai_studio_url=ai_studio_url,
        )

    