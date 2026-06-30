import sys, os
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))))
from Common.MongoDB_Control import mongodb_controller, multi_uploader
from Common.Get_Data import Get_data
from Common.Merge_GetData import Merge_Get_Data
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
Family = 'NAND'
product_list = ['CL', 'OP']
oper_desc = 'M0C FILL OX CMP'
pol_type = 2
Data_lv = 'Wafer'
Days = 30

try :
    mico_info_table = pd.DataFrame()

    for product in product_list :
        mico_info_temp = Get_data.baseinfoGetData(Family = Family, product = product, oper_desc = oper_desc)
        mico_info_table = pd.concat([mico_info_table, mico_info_temp])

    Lot_Code_List = mico_info_table['Lot_Code'].unique()

    for Lot_Code in Lot_Code_List :

        mico_info_key = mico_info_table[mico_info_table['Lot_Code'] == Lot_Code].copy()

        Fab_List = mico_info_key['Fab'].unique()
        Product = mico_info_key['Product'].unique()[0]
        Maker = mico_info_key['Maker'].unique()[0]
        Lot_Code_List = mico_info_key['Lot_Code'].unique()
        Oper_Code = mico_info_key['Ope_Code'].unique()[0]
        Pre_Oper_Code = mico_info_key['Pre_Oper_Code'].unique()[0]
        Pre_Oper_Desc = mico_info_key['Pre_Oper_Desc'].unique()[0]
        Pre_Oper_Code2 = mico_info_key['Pre_Oper_Code2'].unique()[0]
        Pre_Oper_Desc2 = mico_info_key['Pre_Oper_Desc2'].unique()[0]
        Pre_Oper_Para2_List = tuple(mico_info_key['Pre_Oper_Para2'].unique())
        Pre_Oper_Code3 = [x for x in mico_info_key['Pre_Oper_Code3'].unique() if x][0]
        Pre_Oper_Desc3 = [x for x in mico_info_key['Pre_Oper_Desc3'].unique() if x][0]
        Pre_Oper_Para3 = [x for x in mico_info_key['Pre_Oper_Para3'].unique() if x][0]
        Recipe_ID_List = tuple(mico_info_key['Recipe_ID'].unique())
        APC_Para = mico_info_key['APC_Para'].unique()
        THK_Para_list = list(mico_info_key['Thk_Para'].unique())
        Recipe_info = Recipe_ID_List[0].split('_')[0] + '_' + Recipe_ID_List[0].split('_')[1]
        Oper_Desc = mico_info_key['Oper_Desc'].unique()[0]







        for Fab in Fab_List :
            try :

                db_url = 'mongodb:// ... '
                db_name = 'mico-platform-merge-data'
                collection_name = 'MICO_Merge_df_' + Lot_Code + '_' + Oper_Desc + '_' + Fab
                mongo_db = mongodb_controller(db_url, db_name, collection_name)


                if mongo_db.count_row() == 0 : 
                    print('MongoDB 없어 DataLake 30일치 조회 시작!!')
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
                    #에바라 코드
                    merge_df_lake['CH'] = merge_df_lake['recipe_id'].apply(lambda x : 'AB' if 'AB' in x else 'CD')
                    merge_df_lake['eqp_ch'] = merge_df_lake['eqp_id'] + '_' + merge_df_lake['CH']
                    merge_df_lake = merge_df_lake.fillna('-')
  
                    mongo_db.push_df(merge_df_lake)

                    loading_time = datetime.now() - start_time_lake
      
                    del merge_df_lake


                merge_df = Merge_Get_data.getdatahub(Fab, Maker, Lot_Code, Oper_Code, 
                                                        Pre_Oper_Code, Recipe_ID_List, Recipe_info, Oper_Desc)

                if merge_df.empty == False :

                    merge_df.rename(columns = {'request_dtts' : 'Date'}, inplace=True)
                    merge_df.sort_values(by='Date', inplace=True)
                    merge_df['Product'] = Product
                    merge_df['OPER_DESC'] = oper_desc
                    merge_df['Fab'] = Fab
                    merge_df['Lot_Code'] = Lot_Code
                    #에바라 코드
                    merge_df['CH'] = merge_df['recipe_id'].apply(lambda x : 'AB' if 'AB' in x else 'CD')
                    merge_df['eqp_ch'] = merge_df['eqp_id'] + '_' + merge_df['CH']
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

                print(f"{time.time() - start_time:.5f} sec")



                client = MongoClient('mongodb://cncmico:/...')
                db = client['mico-platform-mongodb']
                collection_name = 'MICO_PRE_THK_INFO_' + Lot_Code + '_' + oper_desc + '_' + Fab

                db_url = 'mongodb://cncmico...'
                db_name = 'mico-platform-mongodb'
                pre_thk_db = mongodb_controller(db_url, db_name, collection_name)


                try:
                    pre_thk_db.set_index('end_tm', 31)
                except:
                    pre_thk_db.drop_index('end_tm')
                    pre_thk_db.set_index('end_tm', 31)

                collection = db[collection_name]

                pre_thk_all = pd.DataFrame(collection.find({}, {'_id':0}))


                for para in Pre_Oper_Para2_List : 
                    if 'ED1' in para or 'EDGE' in para : 
                        Pre_Oper_Para2_ED = para
                    elif 'ED2' in para or 'EXED' in para : 
                        Pre_Oper_Para2_EX = para
                    else : 
                        Pre_Oper_Para2_13P = para 
  
                if pre_thk_all.empty : 
                    Pre_info_df = Get_data.PRETHKGetData_SRC(Lot_Code, Pre_Oper_Code2, Pre_Oper_Para2_List)
                    Pre_info_df3 = Get_data.PRETHKGetData_SRC(Lot_Code, Pre_Oper_Code2, Pre_Oper_Para3)

                    Pre_info_pivot = pd.pivot_table(data=Pre_info_df, index = ['end_tm', 'substrate_id'], columns = 'param_nm', values = 'thk_value')
                    Pre_info_pivot.reset_index(inplace=True)

                    avg_col = [col for col in Pre_info_pivot.columns if '_AVG' in col]
                    new_col_list = ['end_tm', 'substrate_id']

                    Pre_Target_13P = Pre_info_pivot[Pre_Oper_Para2_13P].mean()
                    Pre_Target_ED = Pre_info_pivot[Pre_Oper_Para2_ED].mean()
                    Pre_Target_EX = Pre_info_pivot[Pre_Oper_Para2_EX].mean()

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
                    Pre_info_df3.rename(columns = {'thk_value' : Pre_Oper_Desc3+'.'+Pre_Oper_Para3}, inplace=True)
                    Pre_info_df3['substrate_id'] = Pre_info_df3['alias_lot_id'] + '.' + Pre_info_df3['wf_id']
                    Pre_info_df3 = Pre_info_df3[['substrate_id' , Pre_Oper_Desc3+'.'+Pre_Oper_Para3]]

                    pre_thk_all = Pre_info_pivot.merge(Pre_info_df3, on='substrate_id', how='left')
                    pre_thk_all = pre_thk_all.drop_duplicates(subset='substrate_id', keep='first')

                    collection.insert_many(pre_thk_all.to_dict(orient='records'))

                pre_thk_all = pre_thk_all.replace('-', np.NaN)
                pre_thk_all[Pre_Oper_Desc2+"_"+Pre_Oper_Para2_13P] = pd.to_numeric(pre_thk_all[Pre_Oper_Desc2+"_"+Pre_Oper_Para2_13P], errors='coerce')
                pre_thk_all[Pre_Oper_Desc2+"_"+Pre_Oper_Para2_ED] = pd.to_numeric(pre_thk_all[Pre_Oper_Desc2+"_"+Pre_Oper_Para2_ED], errors='coerce')
                pre_thk_all[Pre_Oper_Desc2+"_"+Pre_Oper_Para2_EX] = pd.to_numeric(pre_thk_all[Pre_Oper_Desc2+"_"+Pre_Oper_Para2_EX], errors='coerce')

                Pre_Target_13P = Pre_info_pivot[Pre_Oper_Desc2+"_"+Pre_Oper_Para2_13P].mean()
                Pre_Target_ED = Pre_info_pivot[Pre_Oper_Desc2+"_"+Pre_Oper_Para2_ED].mean()
                Pre_Target_EX = Pre_info_pivot[Pre_Oper_Desc2+"_"+Pre_Oper_Para2_EX].mean()




                Pre_info_df_hub = Get_data.PRETHKGetData_SRC_HUB(Lot_Code, Pre_Oper_Code2, Pre_Oper_Para2_List, Data_lv)

                if not Pre_info_df_hub.empty :

                    Pre_info_df_hub.columns = map(str.lower, Pre_info_df_hub.columns)
                    Pre_info_df_hub.rename(columns={'lot_id' : 'alias_lot_id', 'samp_matl_id' : 'substrate_id'}, inplace=True)
                    Pre_info_pivot = pd.pivot_table(data=Pre_info_df_hub, index=['end_tm', 'substrate_id'], columns = 'dcol_item_cd', values = 'rslt_val')
                    Pre_info_pivot.reset_index(inplace=True)

                    avg_col = [col for col in Pre_info_pivot.columns if '_AVG' in col]

                    new_col_list = ['end_tm','substrate_id']

                    for i in avg_col:
    
                        if 'ED1' in i or 'EDGE' in i :
                            Pre_info_pivot[Pre_Oper_Desc2+'.'+i] = Pre_info_pivot[i] - Pre_info_pivot[Pre_Oper_Para2_13P] - (Pre_Target_ED - Pre_Target_13P)
    
                        elif 'ED2' in i or 'EXED' in i :
                            Pre_info_pivot[Pre_Oper_Desc2+'.'+i] = Pre_info_pivot[i] - Pre_info_pivot[Pre_Oper_Para2_13P] - (Pre_Target_EX - Pre_Target_13P)
    
                        else : 
                            Pre_info_pivot[Pre_Oper_Desc2+'.'+i] = Pre_info_pivot[Pre_Oper_Para2_13P] - Pre_Target_13P
    
                    for i in avg_col : 
                        Pre_info_pivot.rename(columns = {i : Pre_Oper_Desc2 + '_' + i}, inplace=True)
    
                    for index, row in Pre_info_pivot.iterrows():

                         query = {
                            "substrate_id" : row['substrate_id']
                        }
    
                        doc = collection.find_one(query)
    
                        if doc and (f"{Pre_Oper_Desc2}.{Pre_Oper_Para2_13P}" not in doc) : 
                            update_doc = doc
                            update_doc[f"{Pre_Oper_Desc2}.{Pre_Oper_Para2_13P}"] = row[f"{Pre_Oper_Desc2}.{Pre_Oper_Para2_13P}"]
                            update_doc[f"{Pre_Oper_Desc2}.{Pre_Oper_Para2_ED}"] = row[f"{Pre_Oper_Desc2}.{Pre_Oper_Para2_ED}"]
                            update_doc[f"{Pre_Oper_Desc2}.{Pre_Oper_Para2_EX}"] = row[f"{Pre_Oper_Desc2}.{Pre_Oper_Para2_EX}"]
    
                            # update = {"$set" : update_doc}
                            collection.delete_one({"_id" : doc["_id"]})
                            collection.insert_one(update_doc)
    
                        elif doc and (f"{Pre_Oper_Desc2}.{Pre_Oper_Para2_13P}" in doc) :
    
                            if (pd.isna(doc[f"{Pre_Oper_Desc2}.{Pre_Oper_Para2_13P}"])) : 
                                update_doc = doc
                                update_doc[f"{Pre_Oper_Desc2}.{Pre_Oper_Para2_13P}"] = row[f"{Pre_Oper_Desc2}.{Pre_Oper_Para2_13P}"]
                                update_doc[f"{Pre_Oper_Desc2}.{Pre_Oper_Para2_ED}"] = row[f"{Pre_Oper_Desc2}.{Pre_Oper_Para2_ED}"]
                                update_doc[f"{Pre_Oper_Desc2}.{Pre_Oper_Para2_EX}"] = row[f"{Pre_Oper_Desc2}.{Pre_Oper_Para2_EX}"]
    
                                collection.delete_one({"_id" : doc["_id"]})
                                collection.insert_one(update_doc)
    
                        else :
                            collection.insert_one(row.to_dict())
    
                    
                Pre_info_df3 = Get_data.PRETHKGetData_SRC_HUB(Lot_Code, Pre_Oper_Code3, Pre_Oper_Para3, Data_lv)
                Pre_info_df3.columns = map(str.lower, Pre_info_df3.columns)
                Pre_info_df3.rename(columns={'lot_id' : 'alias_lot_id', 'rslt_val' : f"{Pre_Oper_Desc3}.{Pre_Oper_Para3}", 'samp_matl_id' : 'substrate_id'}, inplace=True)

                Pre_info_df3 = Pre_info_df3[['substrate_id', f"{Pre_Oper_Desc3}.{Pre_Oper_Para3}"]].copy()

                if not Pre_info_df3.empty:
                    for index, row in Pre_info_df3.iterrows():

                         query = {
                            "substrate_id" : row['substrate_id']
                        }
    
                        doc = collection.find_one(query)
    
                        if doc and (f"{Pre_Oper_Desc3}.{Pre_Oper_Para3}" not in doc) : 
                            update_doc = doc
                            update_doc[f"{Pre_Oper_Desc3}.{Pre_Oper_Para3}"] = row[f"{Pre_Oper_Desc3}.{Pre_Oper_Para3}"]
                            # update = {"$set" : update_doc}
                            collection.delete_one({"_id" : doc["_id"]})
                            collection.insert_one(update_doc)
    
                        elif doc and (f"{Pre_Oper_Desc3}.{Pre_Oper_Para3}" in doc) :
    
                            if (pd.isna(doc[f"{Pre_Oper_Desc3}.{Pre_Oper_Para3}"])) : 
                                update_doc = doc
                                update_doc[f"{Pre_Oper_Desc3}.{Pre_Oper_Para3}"] = row[f"{Pre_Oper_Desc3}.{Pre_Oper_Para3}"]

                                collection.delete_one({"_id" : doc["_id"]})
                                collection.insert_one(update_doc)
    
                        else :
                            collection.insert_one(row.to_dict())
    

 
                print('report data 조회 함수 실행')
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
                    print('report data 생성', today_)
                    merge_df = mongo_db.get_df()
                    print(merge_df)
                    Get_data.Report(merge_df, THK_Para_list)
                    print('report Upload 완료')

            except Exception as e : 
                tb = traceback.format_exc()
                c.sendMsg('', '506204179', f"{Fab} {Lot_Code} {Oper_Desc} Merge HUB Failed : {e}, {tb}")


    print("Completed!!")


except Exception as e : 
    tb = traceback.format_exc()
    c.sendMsg('', '506204179', f"{Family} {oper_desc} Merge HUB Failed : {e}, {tb}")

                          