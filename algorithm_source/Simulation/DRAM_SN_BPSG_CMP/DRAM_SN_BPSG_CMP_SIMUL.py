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

Family = 'DRAM'
product_list = ['CP', 'LC', 'SP']
oper_desc = 'SN BPSG CMP'
pol_type = 1

try : 
    for product in product_list : 
        Simul_13P = pd.DataFrame()
        Simul_EDGE = pd.DataFrame()
        Simul_EXED = pd.DataFrame()
        Simul_A1 = pd.DataFrame()
        Simul_A2 = pd.DataFrame()
        Simul_A3 = pd.DataFrame()
        Simul_A4 = pd.DataFrame()
        Simul_A5 = pd.DataFrame()
        Simul_A6 = pd.DataFrame()

        mico_info_table = Get_data.baseinfoGetData(Family = Family, product = product, oper_desc = oper_desc)

        Lot_Code_List = mico_info_table['Lot_Code'].unique()

        for Lot_Code in Lot_Code_List :
            mico_info_filter = mico_info_table[mico_info_table['Lot_Code'] == Lot_Code].copy()

            if product == 'SP' : 
                PRE_ITM_Para  = 'EBARA_PRE_THK2_AVG'
                PRE_ITM_ED1_Para = 'EBARA_PRE_THK_ED1_AVG'
                PRE_ITM_ED2_Para = 'EBARA_PRE_THK_ED2_AVG'

            else :
                PRE_ITM_Para = None 
                PRE_ITM_ED1_Para = None
                PRE_ITM_ED2_Para = None

            Fab_List = mico_info_filter['Fab'].unique()

            for Fab in Fab_List :
 
                try : 

                    mico_info_key = mico_info_filter[mico_info_filter['Fab']==Fab]

                    Oper_Code = mico_info_key['Oper_Code'].unique()[0]
                    Pre_Oper_Code = mico_info_key['Pre_Oper_Code'].unique()[0]
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


                    search_key_time = mico_info_key[mico_info_key['FB_Type']=='TIME']

                    for i in range(len(search_key_time)) :

                        key = search_key_time.iloc[i,:]

                        Thk_Para_13P = key['Thk_Para']
                        Target_13P = float(key['Target'])
                        Pre_Target_13P = float(key['Pre_Target'])

                        Simul_df = Simulation_Get.Logic_Time(
                                                            key,
                                                            merge_df,
                                                            ref_lot_df,
                                                            Pre_VM_df,
                                                            RR_df,
                                                            OFFSET_df,
                                                            online_simul_df,
                                                            pol_type,
                                                            Offset_Group,
                                                            ITM_PRE_Para = PRE_ITM_Para
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


                        if ('ED1' in Thk_Para) : 
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
                                                                pol_type,
                                                                ITM_PRE_Para = PRE_ITM_ED1_Para
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
  
  
                        elif ('ED2' in Thk_Para) : 
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
                                                                pol_type,
                                                                ITM_PRE_Para = PRE_ITM_ED1_Para
                                                                )
                          
                          Pre_Target_Exed = float(key['Pre_Target'])
                          Target_Exed = float(key['Target'])
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
                                                                pol_type,
                                                                ITM_PRE_Para = PRE_ITM_ED1_Para
                                                                )
                          
                          Pre_Target = float(key['Pre_Target'])
                          Thk_Para = key['Thk_Para'] 

                          if Simul_df.empty == False :
                              Simul_df['ZONE'] = Thk_Para[-2:]

                          if (eval(f"Simul_{Thk_Para[-2:]}").empty) : 
                              exec(f"Simul_{Thk_Para[-2:]} = Simul_df")
                          else : 
                              exec(f"Simul_{Thk_Para[-2:]} = pd.concat([Simul_{Thk_Para[-2:]}, Simul_df]) ")

                except Exception as e :
                    tb = traceback.format_exc()
                    c.sendMsg('', '506204179', f"{Fab} {Lot_Code} {oper_desc}, Simul Failed : {e}, {tb}")

        Simul_13P.to_csv(f'/project/day/workSpace/mico-platform/mico-platform-mainvs/pjt_shared_pool/{product}_SN_BPSG_CMP_Simulation/Simul_13P_{product}.csv')
        Simul_EDGE.to_csv(f'/project/day/workSpace/mico-platform/mico-platform-mainvs/pjt_shared_pool/{product}_SN_BPSG_CMP_Simulation/Simul_EDGE_{product}.csv')

        Simul_EXED.to_csv(f'/project/day/workSpace/mico-platform/mico-platform-mainvs/pjt_shared_pool/{product}_SN_BPSG_CMP_Simulation/Simul_EXED_{product}.csv')

        Simul_Other = pd.concat([Simul_A1, Simul_A2, Simul_A3, Simul_A4, Simul_A5, Simul_A6])
        Simul_Other.to_csv(f'/project/day/workSpace/mico-platform/mico-platform-mainvs/pjt_shared_pool/{product}_SN_BPSG_CMP_Simulation/Simul_Other_{product}.csv')

except Exception as e :
    tb = traceback.format_exc()
    c.sendMsg('', '506204179', f"{Family} {oper_desc}, Simul Failed : {e}, {tb}")