import sys, os
sys.path.append(os.path.dirname(os.path.abspath(oos.path.dirname(os.path.abspath(os.path.dirname(__file__))))))
from Common.MongoDB_Control import mongodb_controller, multi_uploader
from Common.Get_Data import Get_Data
from Common.Merge_GetData import Merge_Get_data
from datetime import datetime, timedelta, date
import pandas as pd
import numpy as np
from pymongo import MongoClient
import os
import time
import cx_Oracle
import traceback
from multiprocessing import Pool
from day.auth.sdk import logon
from day.commc.cube import Cube_Connector

cube_bot_id = "C0000361"
cube_bot_token = "C000036-0D1CHDB40- ... "
c = Cube_Connector(cube_bot_id, cube_bot_token)

start_time = time.time()
Family = 'DRAM'
product_list = ['CP', 'LC', 'SP']
oper_desc = 'M1 CU CMP'
pol_type = 3
Data_lv = 'Wafer'
Days = 30

try :
    mico_info_table = pd.DataFrame()

    for product in product_list :

        mico_info_temp = Get_data.baseinfoGetData(Family = Family, product = product, oper_desc = oper_desc)
        mico_info_table = pd.concat([mico_info_table, mico_info_temp])

    Lot_Code_List = mico_info_table['Lot_Code'].unique()

    for Lot_Code in Lot_Code_List :

        mico_info_key = mico_info_table[mico_info_table['Lot_Copde'] == Lot_Code].copy()


        Oper_Code_List = list(mico_info_key['Oper_Code'].unique())

        for Oper_Code in Oper_Code_List :

            mico_info_key_r2 = mico_info_key[mico_info_key['Oper_Code'] == Oper_Code].copy()

            Fab_List = mico_info_key_r2['Fab'].unique()
            Product = mico_info_key['Product'].unique()[0]
            Maker = mico_info_key_r2['Maker'].unique()[0]
            Pre_Oper_Code = mico_info_key_r2['Pre_Oper_Code'].unique()[0]
            Pre_Oper_Desc = mico_info_key_r2['Pre_Oper_Desc'].uniqeu()[0]
            Pre_Oper_Code2 = mico_info_key_r2['Pre_Oper_Code2'].unique()[0]
            Pre_Oper_Desc2 = mico_info_key_r2['Pre_Oper_Desc2'].unique()[0]
            Pre_Oper_Para2 = mico_info_key_r2['Pre_Oper_Para2'].unique()[0]
            Recipe_ID_List = tuple(mico_info_key_r2['Recipe_iD'].unique())
            APC_Para = mico_info_key_r2['APC_Para'].unique()
            THK_Para_list = list(mico_info_key['Thk_Para'].unique())
            Recipe_info = Recipe_ID_List[0].split('_')[0] + '_' + Recipe_ID_List[0].split('_')[1]
            Oper_Desc = mico_info_key_r2['Oper_Desc'],unique()[0]


            for Fab in Fab_List :

                try :

                    db_url = 'mongodb:// ... '
                    db_name = 'mico-platform-merge-data'
                    collection_name = 'MICO_Merge_df_' + Lot_Code + '_' + Oper_Desc + '_' + Fab
                    mongo_db = mongodb_controller(db_url, db_name, collection_name)


                    if mongo_db.count_row() == 0 : 
                        print('MongoDB 어ㅂㅅ어 DataLake 30이ㄹ치 조호ㅣ 시자ㄱ!!')
                        start_time_lake = datetime.now()
                        merge_df_lake = Merge_Get_data.getdatalake(Fab, Maker, Lot_Code, Oper_Code,
                                                                Pre_Oper_Code, Recipe_ID_List, Recipe_info, Days
                                                                )
 
                        merge_df_lake.rename(columns = {'request_dtts' : 'Date'}, inplace=True)
                        merge_df_lake.sort_values(by='Date', inplace=True)

                      
                        merge_df_lake['Product'] = Product
                        merge_df_lake['OPER_DESC'] = oper_desc
                        merge_df_lake['Fab'] = Fab
                        merge_df_lake['Lot_Code'] = Lot_Code
                        merge_df_lake['eqp_ch'] = merge_df_lake['eqp_id']
      


                        merge_df_lake = merge_df_lake.fillna('-')

                        merge_df.push_df(merge_df_lake)



                        loading_time = datetime.now() - strat_time_lake
          
                        del merge_df_lake, start_time_lake

                    merge_df = Merge_Get_data.getdatahub(
                                                        Fab,
                                                        Maker, 
                                                        Lot_Code,
                                                        Oper_Code,
                                                        Pre_Oper_Code,
                                                        Recipe_ID_List,
                                                        Recipe_info,
                                                        Oper_Desc
                                                        )

                    if merge_df.empty == False :

                        merge_df.rename(columns = {'request_dtts' : 'Date'}, inplace=True)
                        merge_df.sort_values(by='Date', inplace=True)
                        merge_df['Product'] = Product
                        merge_df['OPER_DESC'] = oper_desc
                        merge_df['Fab'] = Fab
                        merge_df['Lot_Code'] = Lot_Code
                        merge_df['eqp_ch'] = merge_df['eqp_id']
                        merge_df = merge_df.fillna('-')




                        try :
                            mongo_db.push_df(merge_df)
                            mongo_db.drop_duplicate()
 

                            try :
                                mongo_db.set_index('Date', 31)
                            except :
                                mongo_db.drop_index('Date')
                                mongo_db.set_index('Date', 31)

                        except Exception as e :
                            tb = traceback.format_exc()
                            c.sendMsg('', '506204179', f"{Fab} {Lot_Code} {Oper_Desc} Merge HUB Failed : {e}, {tb}")


                    end_time = time.time()
                    print(f"{end_time - start_time:.5f} sec")

                    Pre_Oper_Para2_List = tuple(x for x in Pre_Oper_Para2_List if x != '')

                    if len(Pre_Oper_Para2_List) > 0 :

                        client = MongoClient('mongodb://cncmico:/...')
                        db = client['mico-platform-mongodb']
                        collection_name = 'MICO_PRE_THK_INFO_' + Lot_Code + '_' + oper_desc + '_' + Fab

                        db_url = 'mongodb://cncmico...')
                        db_name = 'mico_platform-mongodb'
                        pre_thk_db = mongodb_controller(db_url, db_name, collection_name)

                        try:
                            tmp_db.set_index('end_tm', 31)
                        except:
                            temp_db.drop_index('end_tm')
                            temp_db.set_index('end_tm', 31)

                        collection = db[collection_name]

                        pre_thk_all = pd.DataFrame(collection.find({}, {'_id':0}))

                        for para in Pre_Oper_Para2_List : 
                            if 'ED1' in para or 'EDGE' in para : 
                                Pre_Oper_Para2_ED = para
                            elif 'ED2' in para or 'EXED' in para : 
                                Pre_Oper_Para2_EX = para
                            elif 'Z5' in para : 
                                Pre_Oper_Para2_Z5 = para
                            else : 
                                Pre_Oper_Para2_13P = para 

                        if pre_thk_all.empty : 
                            Pre_info_df = Get_data.PRETHKGetData_SRC(Lot_Code, Pre_Oper_Code2, Pre_Oper_Para2_List)

                            Pre_info_pivot = pd.pivot_table(data=Pre_info_df, index = ['end_tm', 'substrate_id'], columns = 'param_nm', values = 'thk_value')
                            Pre_info_pivot.reset_index(inplace=True)

                            avg_col = [col for col in Pre_info_pivot.columns if '_AVG' in col]
                            new_col_list = ['end_tm', 'substrate_id']

                            Pre_Target_13P = Pre_info_pivot[Pre_Oper_Para2_13P].mean()
                            Pre_Target_ED = Pre_info_pivot[Pre_Oper_Para2_ED].mean()
                            Pre_Target_Z5 = Pre_info_pivot[Pre_Oper_Para2_Z5].mean()

                            for i in avg_col:
  
                                if 'ED1' in i or 'EDGE' in i :
                                    Pre_info_pivot[Pre_Oper_Desc2+'.'+i] = Pre_info_pivot[i] - Pre_info_pivot[Pre_Oper_Para2_13P] - (Pre_Target_ED - Pre_Target_13P)

                                elif 'ED2' in i or 'EXED' in i :
                                    Pre_info_pivot[Pre_Oper_Desc2+'.'+i] = Pre_info_pivot[i] - Pre_info_pivot[Pre_Oper_Para2_13P] - (Pre_Target_EX - Pre_Target_13P)

                                else : 
                                    Pre_info_pivot[Pre_Oper_Desc2+'.'+i] = Pre_info_pivot[Pre_Oper_Para2_13P] - Pre_Target_13P

                            for i in avg_col :
                                Pre_info_pivot.rename(columns={i : Pre_Oper_Desc2 + '_' + i}, inplace=True)

                            Pre_info_pivot = Pre_info_pivot.fillna('-')
                            pre_thk_all = Pre_info_pivot
                            pre_thk_all = pre_thk_all.drop_duplicates(subset='substrate_id', keep='first')

                            collection.insert_many(pre_thk_all.to_dict(orient='records'))

                        else : 

                            pre_thk_all = pre_thk_all.replace('-', np.NaN)
                            pre_thk_all[Pre_Oper_Desc2+"_"+Pre_Oper_Para2_13P] = pd.to_numeric(pre_thk_all[Pre_Oper_Desc2+"_"+Pre_Oper_Para2_13P], error='coerce')
                            pre_thk_all[Pre_Oper_Desc2+"_"+Pre_Oper_Para2_ED] = pd.to_numeric(pre_thk_all[Pre_Oper_Desc2+"_"+Pre_Oper_Para2_ED], error='coerce')
                            pre_thk_all[Pre_Oper_Desc2+"_"+Pre_Oper_Para2_Z5] = pd.to_numeric(pre_thk_all[Pre_Oper_Desc2+"_"+Pre_Oper_Para2_Z5], error='coerce')

                            Pre_Target_13P = Pre_info_pivot[Pre_Oper_Desc2+"_"+Pre_Oper_Para2_13P].mean()
                            Pre_Target_ED = Pre_info_pivot[Pre_Oper_Desc2+"_"+Pre_Oper_Para2_ED].mean()
                            Pre_Target_Z5 = Pre_info_pivot[Pre_Oper_Desc2+"_"+Pre_Oper_Para2_Z5].mean()




                            Pre_info_df_hub = Get_data.PRETHKGetData_SRC_HUB(Lot_Code, Pre_Oper_Code2, Pre_Oper_Para2_List, Data_lv)


                            Pre_info_df_hub.columns = map(str.lower, Pre_info_df_hub.columns)
                            Pre_info_df_hub.rename(columns={'lot_id' : 'alias_lot_id', 'samp_matl_id' : 'substrate_id'}, inplace=True)
                            Pre_info_pivot = pd.pivot_table(data=Pre_info_df_hub, index=['end_tm', 'substrate_id'], columns = 'dcol_item_cd', values = 'rslt_val')
                            Pre_info_pivot.reset_index(inplace=True)
                            print(Pre_info_pivot)

                            avg_col = [col for col in Pre_info_pivot.columns if '_AVG' in col]

                            new_col_list = ['end_tm','substrate_id']

                            for i in avg_col:
  
                                if 'ED1' in i or 'EDGE' in i :
                                    Pre_info_pivot[Pre_Oper_Desc2+'.'+i] = Pre_info_pivot[i] - Pre_info_pivot[Pre_Oper_Para2_13P] - (Pre_Target_ED - Pre_Target_13P)

                                elif 'Z5' in i :
                                    Pre_info_pivot[Pre_Oper_Desc2+'.'+i] = Pre_info_pivot[i] - Pre_info_pivot[Pre_Oper_Para2_13P] - (Pre_Target_Z5 - Pre_Target_13P)

                                else : 
                                    Pre_info_pivot[Pre_Oper_Desc2+'.'+i] = Pre_info_pivot[Pre_Oper_Para2_13P] - Pre_Target_13P

                            for i in avg_col : 
                                Pre_info_pivot.rename(columns = {i : Pre_Oper_Desc2 + '_' + i}, inplace=True)


                            Pre_info_pivot = Pre_info_pivot.fillna('-')
                            if pre_thk_all.empty == False :
                                pre_thk_all = pd.concat([pre_thk_all, Pre_info_pivot])
                            else : 
                                pre_thk_all = Pre_info_pivot

                            pre_thk_all = pre_thk_all.drop_duplicates(subset='substrate_id', keep='first')

                            doc = pre_thk_all.to_dict('records')
                            collection.delete_name({})
                            collection.insert_many(doc)



                    print('report data 조호ㅣ 하ㅁ수 시ㄹ해ㅇ')
                    db_url = 'mongodb://micoweb: ... '
                    db_name = 'mico-platform-web-db'
                    collection_name = 'MICO_Report'
                    report_db = mongodb_controller(db_url, db_name, collection_name)
 
                    today_ = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
                    condition = {'Lot_Code' : Lot_Code, 
                                'OPER_DESC' : Oper_Desc,
                                'Fab' : Fab,
                                'Date' : {'$gte' : today_}
                               }

                    report_df = report_db.get_df(condition)
         
                    if report_df.empty == True :
                        print('report data 새ㅇ서ㅇ', today_)
                        merge_df = mongo_db.get_df()
                        print(merge_df)
                        Get_data().Report(merge_df, Thk_Para_list)
                        print('report Upload 오ㅏㄴ료')

                except Exception as e : 
                    tb = traceback.format_exc()
                    c.sendMsg('', '506204179', f"{Fab} {Lot_Code} {Oper_Desc} Merge HUB Failed : {e}, {tb}")


    print("Completed!!")


except Exception as e : 
    tb = traceback.format_exc()
    c.sendMsg('', '506204179', f"{Family} {oper_desc} Merge HUB Failed : {e}, {tb}")

                          