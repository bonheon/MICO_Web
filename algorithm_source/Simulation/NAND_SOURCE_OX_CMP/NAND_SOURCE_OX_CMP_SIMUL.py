import os, sys
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))))
from Common.Get_Data import Get_data
from Common.MongoDB_Control import mongodb_controller
from Common.Simulation import Simulation_Get
from datetime import datetime, timedelta, date
import pandas as pd
import numpy as np
from pymongo import MongoClient
import traceback
from day.commc.cube import Cube_Connector

cube_bot_id = "C0000361"
cube_bot_token = "C000...."
c = Cube_Connector(cube_bot_id, cube_bot_token)

Family = 'NAND'
product_list = ['PE', 'CL', 'OP']
oper_desc = 'SOURCE OX CMP'
pol_type = 2

try : 
    for product in product_list : 

        Simul_13P = pd.DataFrame()
        Simul_EDGE = pd.DataFrame()
        Simul_EXED = pd.DataFrame()

        mico_info_table = Get_data.baseinfoGetData(Family = Family, product = product, oper_desc = oper_desc)

        Lot_Code_List = mico_info_table['Lot_Code'].unique()

        for Lot_Code in Lot_Code_List :
            mico_info_filter = mico_info_table[mico_info_table['Lot_Code'] == Lot_Code].copy()

            Fab_List = mico_info_filter['Fab'].unique()

            for Fab in Fab_List :
 
                try : 

                    client = MongoClient('mongodb://cncmico:,...')
                    db = client['mico-platform-mongodb']
                    collection = db['MICO_PRE_THK_INFO_' + Lot_Code + '_' + oper_desc + '_' + Fab]

                    mico_info_key = mico_info_filter[mico_info_filter['Fab']==Fab]

                    Lot_Code = mico_info_key['Lot_Code'].unique()[0]
                    Oper_Code = mico_info_key['Oper_Code'].unique()[0]
                    Pre_Oper_Code = mico_info_key['Pre_Oper_Code'].unique()[0]
                    Pre_Oper_Code2 = mico_info_key['Pre_Oper_Code2'].unique()[0]
                    Pre_Oper_Para2 = tuple(mico_info_key['Pre_Oper_Para2'].unique())
                    Recipe_ID_List = tuple(mico_info_key['Recipe_ID'].unique())
                    APC_Para = mico_info_key['APC_Para'].unique()
                    Thk_Para = mico_info_key['Thk_Para'].unique()
                    Pre_Target = float(mico_info_key['Pre_Target'].unique()[0])
                    Target = float(mico_info_key['Target'].unique()[0])
                    Recipe_info = Recipe_ID_List[0].split('_')[0] + '_' + Recipe_ID_List[0].split('_')[1]

                    offset_info_table = mico_info_key[(mico_info_key['FB_Type']=='TIME')]

                    Offset_Group = offset_info_table['Offset_Group'].unique()

                    (merge_df,
                    ref_lot_df,
                    Pre_VM_df,
                    RR_df,
                    OFFSET_df,
                    online_simul_df) = Simulation_Get.getdata(
                                                          Family,
                                                          Fab,
                                                          Lot_Code,
                                                          Oper_Code,
                                                          Recipe_ID_List,
                                                          oper_desc
                                                          )

                    merge_df['Fab'] = Fab 

                    if (type(Pre_Oper_Code2) == str) & (Pre_Oper_Code2 != '') :

                        raw_data = collection.find({}, {'_id':0})

                        pre2_df = pd.DataFrame(raw_data)
                        pre2_df.rename(columns={'samp_matl_id': 'substrate_id'}, inplace=True)
                        pre2_df.drop_duplicates(subset=['substrate_id'], inplace=True)

                        pre2_df.drop(columns=['substrate_id', 'wf_id', 'end_tm'], inplace=True)

                        merge_df = pd.merge(merge_df, pre2_df, on = 'alias_lot_id', how='left')


                    mico_info_time = mico_info_key[mico_info_key['FB_Type']=='TIME']

                    for i in range(len(mico_info_time)) :

                        search_key = mico_info_time.iloc[i,:]

                        Thk_Para_13P = search_key['Thk_Para']
                        Target_13P = float(search_key['Target'])
                        Pre_Target_13P = float(search_key['Pre_Target'])

                        Simul_df = Simulation_Get.Logic_Time(
                                                            search_key,
                                                            merge_df,
                                                            ref_lot_df,
                                                            Pre_VM_df,
                                                            RR_df,
                                                            OFFSET_df,
                                                            online_simul_df,
                                                            pol_type,
                                                            Offset_Group
                                                            )

                        Simul_df['Pre_Target_13P'] = Pre_Target_13P
                        Simul_df['Target_13P'] = Target_13P
                        if Simul_13P.empty :
                            Simul_13P = Simul_df
                        else : 
                            Simul_13P = pd.concat([Simul_13P, Simul_df])

                    search_key_pressure = mico_info_key[mico_info_key['FB_Type']=='PRESSURE']

                    for i in range(len(search_key_pressure)) : 

                        key = search_key_pressure.iloc[i,:]
                        Thk_Para = key['Thk_Para']
                        Target_EDGE = key['Target']
                        print(key)


                        if ('EDGE' in Thk_Para) : 
                          Simul_df = Simulation_Get.Logic_Pressure(
                                                                key,
                                                                merge_df,
                                                                Thk_Para_13P,
                                                                Target_13P,
                                                                ref_lot_df,
                                                                Pre_VM_df,
                                                                RR_df,
                                                                OFFSET_df,
                                                                online_simul_df,
                                                                pol_type
                                                                )

                          Pre_Target_Edge = float(key['Pre_Target'])
                          Target_Edge = float(key['Target'])
                          Thk_Para_Edge = key['Thk_Para']

                          Simul_df['Pre_Target_EDGE'] = Pre_Target_Edge
                          Simul_df['Target_EDGE'] = Target_Edge

                          if Simul_EDGE.empty :
                              Simul_EDGE = Simul_df
                          else : 
                              Simul_EDGE = pd.concat([Simul_EDGE, Simul_df])
  
  
                        elif ('EXED' in Thk_Para) : 
                          Pre_Target_Exed = float(key['Pre_Target'])
                          Target_Exed = float(key['Target'])
                          Simul_df = Simulation_Get.Logic_Pressure(
                                                                key,
                                                                merge_df,
                                                                Thk_Para_13P,
                                                                Target_13P,
                                                                ref_lot_df,
                                                                Pre_VM_df,
                                                                RR_df,
                                                                OFFSET_df,
                                                                online_simul_df,
                                                                pol_type
                                                                )

                          Thk_Para_Exed = key['Thk_Para']

                          Simul_df['Pre_Target_EXED'] = Pre_Target_Exed
                          Simul_df['Target_EXED'] = Target_Exed

                          if Simul_EXED.empty :
                              Simul_EXED = Simul_df
                          else : 
                              Simul_EXED = pd.concat([Simul_EXED, Simul_df])

                        else : 
                          Simul_df = Simulation_Get.Logic_Pressure(
                                                                key,
                                                                merge_df,
                                                                Thk_Para_13P,
                                                                Target_13P,
                                                                ref_lot_df,
                                                                Pre_VM_df,
                                                                RR_df,
                                                                OFFSET_df,
                                                                online_simul_df,
                                                                pol_type
                                                                )

                          Pre_Target = float(key['Pre_Target'])
                          Thk_Para = key['Thk_Para'] 
                          Simul_df['ZONE'] = Thk_Para.split('_')[4]
                          if (eval(f"Simul_{Thk_Para.split('_')[4]}").empty) : 
                              exec(f"Simul_{Thk_Para.split('_')[4]} = Simul_df")
                          else : 
                              exec(f"Simul_{Thk_Para.split('_')[4]} = pd.concat([Simul_{Thk_Para.split('_')[4]}, Simul_df]) ")

                except Exception as e :
                    tb = traceback.format_exc()
                    c.sendMsg('', '506204179', f"{Fab} {Lot_Code} {oper_desc}, Simul Failed : {e}, {tb}")

        Simul_13P.to_csv(f'/project/day/workSpace/mico-platform/mico-platform-mainvs/pjt_shared_pool/{product}_SOURCE_OX_CMP_Simulation/Simul_13P_{product}.csv')
        Simul_EDGE.to_csv(f'/project/day/workSpace/mico-platform/mico-platform-mainvs/pjt_shared_pool/{product}_SOURCE_OX_CMP_Simulation/Simul_EDGE_{product}.csv')

        Simul_EXED.to_csv(f'/project/day/workSpace/mico-platform/mico-platform-mainvs/pjt_shared_pool/{product}_SOURCE_OX_CMP_Simulation/Simul_EXED_{product}.csv')

except Exception as e :
    tb = traceback.format_exc()
    c.sendMsg('', '506204179', f"{Family} {oper_desc}, Simul Failed : {e}, {tb}")