import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parents[1]))
from Common.Get_Data import Get_data
from Common.MongoDB_Control import mongodb_controller
from datetime import datetime
from itertools import product
import pandas as pd

_MONGO_URL = 'mongodb://cncmico...'
_MONGO_DB  = 'mico-platform-mongodb'


class OFFSET_Get:

    def _make_offset_mongo(Lot_Code, Oper_Desc, Fab):
        # OFFSET 결과를 저장할 MongoDB 컬렉션 이름 구성 후 controller 반환
        collection = 'MICO_OFFSET_' + Lot_Code + '_' + Oper_Desc + '_' + Fab
        return mongodb_controller(_MONGO_URL, _MONGO_DB, collection)

    def _get_b_coef(row):
        # weighted 계수가 유효하면 weighted 사용, 없으면 일반 계수 사용
        if 'b1_weighted' not in row.index or pd.isna(row['b1_weighted']):
            return pd.Series([row['b1'], row['b0']], index=['b1_new', 'b0_new'])
        return pd.Series([row['b1_weighted'], row['b0_weighted']], index=['b1_new', 'b0_new'])

    def _build_idle_table(combined):
        # eq_recipe_apc / IDLE 기준으로 OFFSET 평균 집계 후 전체 조합 생성
        IDLE_RR_Table = combined.groupby(['eq_recipe_apc', 'IDLE'])['OFFSET'].mean().reset_index()

        all_combination = pd.DataFrame(
            product(IDLE_RR_Table['eq_recipe_apc'].unique(), IDLE_RR_Table['IDLE'].unique()),
            columns=['eq_recipe_apc', 'IDLE']
        )
        IDLE_RR_Table = pd.merge(all_combination, IDLE_RR_Table, on=['eq_recipe_apc', 'IDLE'], how='left')

        IDLE_RR_Table[['eqp_id', 'recipe_id', 'APC_Para']] = IDLE_RR_Table['eq_recipe_apc'].str.split('//', expand=True)
        IDLE_RR_Table['recipe_group'] = IDLE_RR_Table['recipe_id'].str.split('_').str[:3].str.join('_')

        IDLE_RR_Table['OFFSET_2'] = IDLE_RR_Table.groupby(['recipe_group', 'IDLE'])['OFFSET'].transform('mean')
        IDLE_RR_Table.rename(columns={'OFFSET': 'OFFSET_Origin', 'OFFSET_2': 'OFFSET'}, inplace=True)

        return IDLE_RR_Table


    def compute_offset(merge_df, search_key, pol_type, Fab):
        # 단일 Recipe/APC_Para에 대한 Idle OFFSET 학습값 산출 및 MongoDB 저장.
        # 실측 RR과 패드 마모 기반 예측 RR의 차이로 연마 시간 보정량(OFFSET)을 계산하며,
        # Idle_/Layer_ 구간 데이터 중 5건 이상인 그룹만 평균하여 저장.
        Fab        = search_key.Fab
        Lot_Code   = search_key.Lot_Code
        Oper_Code  = search_key.Oper_Code
        Oper_Desc  = search_key.Oper_Desc
        APC_Para   = search_key.APC_Para
        Thk_Para   = search_key.Thk_Para
        Recipe_ID  = search_key.Recipe_ID
        Pre_Target = search_key.Pre_Target
        if pd.notna(Pre_Target):
            Pre_Target = float(Pre_Target)
        Target = float(search_key.Target)

        mongo = OFFSET_Get._make_offset_mongo(Lot_Code, Oper_Desc, Fab)

        Pol_Para = Get_data.APCParaGet(APC_Para, pol_type)
        Pad_Para = Get_data.PadParaGet(APC_Para)

        temp_data = merge_df[
            (merge_df['operation_id'] == Oper_Code) &
            (merge_df['recipe_id']    == Recipe_ID)
        ].copy()

        if temp_data.empty:
            return None

        offset_columns = [col for col in temp_data.columns if 'OFFSET' in col]
        temp_data.fillna(value={col: 0 for col in offset_columns}, inplace=True)

        temp_data['eq_recipe'] = temp_data['eqp_id'] + '//' + temp_data['recipe_id']
        temp_data.drop_duplicates(inplace=True)

        temp_data['Pol_Time'] = temp_data[Pol_Para].sum(axis=1)
        temp_data.dropna(subset=[Thk_Para], inplace=True)

        b_cols = [col for col in temp_data.columns if '_B0' in col or '_B1' in col]
        temp_data.fillna(temp_data.groupby(['eq_recipe'])[b_cols].transform('mean'), inplace=True)
        temp_data[b_cols] = temp_data[b_cols].apply(pd.to_numeric, errors='coerce').fillna(temp_data[b_cols].mean())

        if 'REV' in Thk_Para:
            temp_data['RR'] = (temp_data[Thk_Para] - Pre_Target) / temp_data['Pol_Time']
        else:
            temp_data['RR'] = (Pre_Target - temp_data[Thk_Para]) / temp_data['Pol_Time']

        b1_col = f"{APC_Para}_B1"
        if b1_col not in temp_data.columns:
            return temp_data
        temp_data['RR_Pad'] = temp_data[Pad_Para] * temp_data[APC_Para + '_B1'] + temp_data[APC_Para + '_B0']

        delta = (Target - Pre_Target) if 'REV' in Thk_Para else (Pre_Target - Target)
        temp_data['OFFSET'] = delta / temp_data['RR'] - delta / temp_data['RR_Pad']
        temp_data['OFFSET'] = temp_data['OFFSET'].clip(-5, 3)
        temp_data.loc[temp_data['IDLE'].str.contains('LC_T_|LC_TB_'), 'OFFSET'] = 0

        temp_data['recipe_group'] = temp_data['recipe_id'].apply(lambda x: '_'.join(x.split('_')[:3]))
        temp_data['APC_Para']     = APC_Para
        temp_data_idle = temp_data[
            temp_data['IDLE'].str.contains('Idle_') | temp_data['IDLE'].str.contains('Layer_')
        ]

        grouped         = temp_data_idle.groupby(['eqp_id', 'recipe_id', 'IDLE']).size().reset_index(name='count')
        filtered_groups = grouped[grouped['count'] >= 5]
        filtered_data   = temp_data_idle.merge(filtered_groups[['eqp_id', 'recipe_id', 'IDLE']], on=['eqp_id', 'recipe_id', 'IDLE'])
        idle_table      = filtered_data.groupby(['eqp_id', 'recipe_id', 'IDLE'])['OFFSET'].mean().reset_index()
        idle_table['IDLE'].replace('', 'Normal', inplace=True)
        idle_table['APC_Para'] = APC_Para
        idle_table['Date']     = datetime.now()

        if not idle_table.empty:
            mongo.push_df(idle_table)

        return temp_data


    def load_rr_data(merge_df, Fab, Lot_Code, Oper_Desc, APC_Para_List, mongo_url, mongo_db):
        # MongoDB에서 RR 학습값(B1/B0)을 조회하여 merge_df에 merge_asof로 결합 후 반환.
        # weighted 계수 유효 여부를 판별 후 APC_Para별로 피벗하여 EQP/Recipe/날짜 기준으로 조인.

        collection = 'MICO_Removal_Rate_' + Lot_Code + '_' + Oper_Desc + '_' + Fab
        mongo      = mongodb_controller(mongo_url, mongo_db, collection)
        RR_Table   = mongo.get_df()

        RR_Table[['b1_new', 'b0_new']] = RR_Table.apply(OFFSET_Get._get_b_coef, axis=1)

        RR_Table = RR_Table[RR_Table['APC_Para'].isin(APC_Para_List)][
            ['Date', 'APC_Para', 'EQ', 'Recipe_ID', 'b1_new', 'b0_new']
        ].copy()
        RR_Table['Date'] = pd.to_datetime(RR_Table['Date'])

        merge_df.rename(columns={'request_dtts': 'Date'}, inplace=True)
        RR_Table.rename(columns={'EQ': 'eqp_id', 'Recipe_ID': 'recipe_id', 'APC_Para': 'input_name'}, inplace=True)

        for col in [c for c in RR_Table.columns if '_new' in c]:
            unique_vals = RR_Table[col].unique().tolist()
            if unique_vals == ['-']:
                RR_Table.drop(columns=col, inplace=True)
            elif '-' not in unique_vals:
                RR_Table[col] = pd.to_numeric(RR_Table[col])

        pivot_col = [col for col in RR_Table.columns if '_new' in col]
        RR_pivot  = pd.pivot_table(
            data    = RR_Table,
            index   = ['Date', 'eqp_id', 'recipe_id'],
            columns = ['input_name'],
            values  = pivot_col
        ).reset_index()

        RR_pivot.columns = [
            i[1] + '_B1' if 'b1' in i[0] else
            i[1] + '_B0' if 'b0' in i[0] else
            i[0]
            for i in RR_pivot.columns
        ]

        RR_pivot['Date'] = pd.to_datetime(RR_pivot['Date'])
        merge_df = pd.merge_asof(
            merge_df.sort_values('Date'),
            RR_pivot.sort_values('Date'),
            on='Date', by=['eqp_id', 'recipe_id']
        )

        return merge_df


    def compute_lc_offset(temp_data, Lot_Code, Oper_Desc, Fab, Offset_Group):
        # LC 계열(패드 교체/Truing) IDLE 구간에 대한 OFFSET 학습값 산출 및 MongoDB 저장.
        # Offset_Group='Y'이면 IDLE 레이블을 장비 번호 제거 후 그룹화하여 recipe_group 단위로 평균 집계.
        mongo = OFFSET_Get._make_offset_mongo(Lot_Code, Oper_Desc, Fab)
        today = datetime.now()

        temp_data['eq_recipe_apc'] = temp_data['eq_recipe'] + '//' + temp_data['APC_Para']
        temp_data['IDLE'].fillna('Normal', inplace=True)

        temp_data_lc = temp_data[
            temp_data['IDLE'].str.contains('LC_') &
            ~temp_data['IDLE'].str.contains('_ADD_') &
            ~temp_data['IDLE'].str.contains('_T_') &
            ~temp_data['IDLE'].str.contains('_TB_')
        ].copy()

        temp_data_tb = temp_data[
            temp_data['IDLE'].str.contains('_ADD_') |
            temp_data['IDLE'].str.contains('_T_') |
            temp_data['IDLE'].str.contains('_TB_')
        ].copy()

        if Offset_Group == 'Y':
            temp_data_lc['IDLE'] = temp_data_lc['IDLE'].apply(lambda x: '_'.join([x.split('_')[0], x.split('_')[2]]))
            temp_data_tb['IDLE'] = temp_data_tb['IDLE'].apply(lambda x: '_'.join([x.split('_')[0], x.split('_')[3]]))
        combined = pd.concat([temp_data_lc, temp_data_tb], axis=0)

        lc_offset = OFFSET_Get._build_idle_table(combined)
        lc_offset['Date'] = today
        lc_offset = lc_offset[['eqp_id', 'recipe_id', 'IDLE', 'OFFSET', 'APC_Para', 'Date']].copy()
        lc_offset['OFFSET'].fillna(0, inplace=True)

        if not lc_offset.empty:
            mongo.push_df(lc_offset)
