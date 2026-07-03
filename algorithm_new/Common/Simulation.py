import sys, time, traceback
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd
from pymongo import MongoClient

sys.path.append(str(Path(__file__).parents[1]))
from Common.Get_Data import Get_data
from day.commc.cube import Cube_Connector

_MICO_URL = 'mongodb://cncmico:/...'
_MICO_DB  = 'mico-platform-mongodb'

_CUBE_BOT_ID    = 'C0000361'
_CUBE_BOT_TOKEN = 'C000036-0D1CHDB40- ... '

# Spotfire 연동 CSV 출력 기본 경로 (추후 DB 적재로 대체 예정)
_EXPORT_BASE = '/project/day/workSpace/mico-platform/mico-platform-mainvs/pjt_shared_pool'


# ── 학습 테이블 로드 ───────────────────────────────────────────────────────
# (Ref lot 조회 함수 RefGetData / RefGetData_HUB / REFParaGet 은 회사 구조와
#  동일하게 Get_Data.py 의 Get_data 클래스에 위치 — TODO 스텁 참조)

def _load_collection_df(db, coll_name):
    """MongoDB 컬렉션 전체를 DataFrame 으로 반환."""
    return pd.DataFrame(list(db[coll_name].find()))


def _load_learning_tables(Family, Fab, Lot_Code, oper_desc):
    """Module 이 학습·저장한 3종 테이블(Pre VM / RR / OFFSET) + Online Simulation 로드.

    Family == 'TEST' 면 컬렉션 이름에 _TEST suffix (source 동작 동일).
    """
    suffix = '_TEST' if Family == 'TEST' else ''
    client = MongoClient(_MICO_URL)
    try:
        db = client[_MICO_DB]

        Pre_VM_df = _load_collection_df(db, f'MICO_PRE_THK_{Lot_Code}_{oper_desc}_{Fab}_Period{suffix}')
        RR_df     = _load_collection_df(db, f'MICO_Removal_Rate_{Lot_Code}_{oper_desc}_{Fab}{suffix}')
        OFFSET_df = _load_collection_df(db, f'MICO_OFFSET_{Lot_Code}_{oper_desc}_{Fab}{suffix}')
        print(f'    학습 테이블 로드: Pre VM={len(Pre_VM_df)}건 | RR={len(RR_df)}건 | Offset={len(OFFSET_df)}건')

        # Online Simulation 결과: 컬렉션이 있을 때만 로드 후 LOT/SLOT 별 최신 1건 추출
        online_name     = f'MICO_Online_Simulation_{Lot_Code}_{oper_desc}_{Fab}{suffix}'
        online_simul_df = pd.DataFrame()
        if online_name in db.list_collection_names():
            online_simul_df = _load_collection_df(db, online_name)
            if not online_simul_df.empty:
                online_simul_df['substrate_id'] = (
                    online_simul_df['LOT_ID'].str[:7] + '.' + online_simul_df['SLOT_ID']
                )
                online_simul_df['rank'] = (
                    online_simul_df.groupby(['LOT_ID', 'SLOT_ID'])['Date'].rank(ascending=False)
                )
                online_simul_df = online_simul_df[online_simul_df['rank'] == 1]
            print(f'    Online Simulation 로드: {len(online_simul_df)}건')
    finally:
        client.close()

    return Pre_VM_df, RR_df, OFFSET_df, online_simul_df


def _load_ref_lots(Fab, Lot_Code, Oper_Code, Recipe_ID_List, Days=None):
    """Ref lot 데이터 로드 (SRC + HUB 합산, wafer·파라미터 기준 dedup)."""
    ref_lot_df     = Get_data.RefGetData(Fab, Lot_Code, Oper_Code, Recipe_ID_List, Days)
    ref_lot_df_hub = Get_data.RefGetData_HUB(Fab, Lot_Code, Oper_Code, Recipe_ID_List)

    ref_lot_df = pd.concat([ref_lot_df, ref_lot_df_hub])
    ref_lot_df.drop_duplicates(subset=['substrate_id', 'input_name'], inplace=True)
    print(f'    Ref lot 로드: {len(ref_lot_df)}건')
    return ref_lot_df


# ── search_key 파싱 ────────────────────────────────────────────────────────

def _parse_search_key(search_key):
    """Set-up 1행(search_key)에서 시뮬레이션에 필요한 필드를 dict 로 파싱.

    - Pre_Target/Target 은 float 변환, Pad_Seperation 은 미설정 시 -1
    """
    sk = {
        'Fab'              : search_key['Fab'],
        'Lot_Code'         : search_key['Lot_Code'],
        'Oper_Code'        : search_key['Oper_Code'],
        'Oper_Desc'        : search_key['Oper_Desc'],
        'APC_Para'         : search_key['APC_Para'],
        'Thk_Para'         : search_key['Thk_Para'],
        'Recipe_ID'        : search_key['Recipe_ID'],
        'RR_Para'          : str(search_key['RR_Para']).upper(),
        'Pre_Oper_Code2'   : search_key['Pre_Oper_Code2'],
        'Pre_Oper_Desc2'   : search_key['Pre_Oper_Desc2'],
        'Pre_Oper_Para2'   : search_key['Pre_Oper_Para2'],
        'Pre_Oper_Code3'   : search_key['Pre_Oper_Code3'],
        'Pre_Oper_Desc3'   : search_key['Pre_Oper_Desc3'],
        'Pre_Oper_Para3'   : search_key['Pre_Oper_Para3'],
        'Pre_Oper_Code4'   : search_key['Pre_Oper_Code4'],
        'Pre_Oper_Desc4'   : search_key['Pre_Oper_Desc4'],
        'Pre_Oper_Para4'   : search_key['Pre_Oper_Para4'],
        'Pre_Thk_Para_ITM' : search_key['Pre_Thk_Para_ITM'],
        'Pre_Target'       : search_key['Pre_Target'],
        'Target'           : float(search_key['Target']),
        'Pad_Seperation'   : search_key['Pad_Seperation'],
    }
    if pd.notna(sk['Pre_Target']):
        sk['Pre_Target'] = float(sk['Pre_Target'])
    sk['Pad_Seperation'] = -1 if pd.isna(sk['Pad_Seperation']) else float(sk['Pad_Seperation'])
    # ITM set-up 미입력(NaN/None) → '' 로 통일 (빈 문자열 비교 분기 일관성)
    if pd.isna(sk['Pre_Thk_Para_ITM']):
        sk['Pre_Thk_Para_ITM'] = ''
    return sk


def _get_consumable_para(sk, Pad_Para, Disk_Para, Head_Para):
    """RR_Para set-up 값(HEAD/PAD/DISK)에 해당하는 소모품 파라미터 반환."""
    if sk['RR_Para'] == 'HEAD':
        return Head_Para
    if sk['RR_Para'] == 'DISK':
        return Disk_Para
    if sk['RR_Para'] != 'PAD':
        print(f"    ! RR_Para={sk['RR_Para']} 인식 불가 → PAD 로 대체")
    return Pad_Para


# ── 시뮬레이션 파이프라인 단계별 함수 ──────────────────────────────────────

def _build_base_frame(merge_df, sk, Main_Para, Main_Para_formula, Main_Para_OFFSET,
                      Pad_Para, Disk_Para, Head_Para, mode, Thk_Para_13P):
    """merge_df 에서 Oper/Recipe/APC 필터 후 시뮬레이션에 쓸 컬럼만 추출.

    - OFFSET 컬럼 결측 → 0
    - substrate_id 기준 dedup
    """
    temp = merge_df[
        (merge_df['operation_id'] == sk['Oper_Code'])
        & (merge_df['recipe_id'] == sk['Recipe_ID'])
        & pd.notna(merge_df[sk['APC_Para']])
    ].copy()

    if temp.empty:
        return pd.DataFrame()

    # RR/OFFSET 학습값 fill 의 groupby 키 (장비+모델+레시피+세부공정)
    temp['eq_model_recipe'] = (
        temp['eqp_id'] + '//' + temp['eqp_model'] + '//'
        + temp['recipe_id'] + '//' + temp['oper_det_desc']
    )

    col_list = [
        'Fab', 'Date', 'process_id', 'recipe_id', 'eqp_id', 'eqp_model',
        'lot_id', 'substrate_id', 'wf_id', 'IDLE', 'pre_eqp_id', 'pre_eqp_ch',
        'pre_oper_time', 'oper_id', 'oper_det_desc',
        sk['Thk_Para'], Pad_Para, Disk_Para, Head_Para, 'pre_eq_ch', 'eq_model_recipe',
    ] + Main_Para + Main_Para_formula

    if mode == 'PRESSURE':
        col_list.append(Thk_Para_13P)
        # ED2/EXED 존은 ED1/EDGE 계측값도 함께 사용
        if ('ED2' in sk['Thk_Para']) or ('EXED' in sk['Thk_Para']):
            col_list.append(sk['Thk_Para'].replace('ED2', 'ED1').replace('EXED', 'EDGE'))

    # OFFSET 컬럼: merge_df 에 실제 존재하는 것만 추가 (없는 컬럼 선택 시 KeyError 방지)
    for x in Main_Para_OFFSET:
        if x in temp.columns:
            col_list.append(x)

    # _AVG 계측 파라미터는 짝이 되는 _RAN(range) 파라미터도 추가
    if sk['Thk_Para'].endswith('_AVG'):
        ran_para = sk['Thk_Para'][:-4] + '_RAN'
        if ran_para in temp.columns:
            col_list.append(ran_para)

    if sk['Pre_Thk_Para_ITM'] != '' and sk['Pre_Thk_Para_ITM'] in temp.columns:
        col_list.append(sk['Pre_Thk_Para_ITM'])

    # Pre_Oper2~4 계측 컬럼 (PRE_THK_INFO 결합으로 merge_df 에 붙어 있음)
    for i in (2, 3, 4):
        code = sk[f'Pre_Oper_Code{i}']
        if isinstance(code, str) and code != '':
            col_list.append(f"{sk[f'Pre_Oper_Desc{i}']}.{sk[f'Pre_Oper_Para{i}']}")

    col_list = list(set(col_list))
    temp = temp[col_list].copy()

    offset_columns = [col for col in temp.columns if 'OFFSET' in col]
    temp.fillna(value={col: 0 for col in offset_columns}, inplace=True)

    temp.drop_duplicates(subset=['substrate_id'], inplace=True)
    # merge_asof 는 좌측 프레임이 Date 정렬 상태여야 함
    temp = temp.sort_values(by='Date')
    return temp


def _attach_pre_vm(Simul_df, Pre_VM_df, sk):
    """Pre_Thk_VM 학습값을 시점 기준(merge_asof, pre_eq_ch별)으로 결합.

    - Module 이 세 경로(ITM/detrend/회귀전용) 모두 THK_Para 를 저장하므로
      THK_Para 단일 필터로 통일 (ITM 여부 분기 불필요)
    - PRE_OPERn 회귀계수(b1/b0)는 THK_Para 별 평균으로 결측 보정 후 함께 결합
    - 결측 학습값 행은 결합 후 _fill_learning_values 의 ffill/mean/0 보정이 처리
    """
    if Pre_VM_df.empty:
        out = Simul_df.copy()
        out['Pre_Thk'] = 0
        return out

    col_list = ['Date', 'pre_oper_time', 'pre_eq_ch', 'Pre_Thk', 'Count']

    for i in (2, 3, 4):
        b1, b0 = f'PRE_OPER{i}_b1', f'PRE_OPER{i}_b0'
        if b1 in Pre_VM_df.columns:
            col_list.extend([b1, b0])
            Pre_VM_df.fillna(
                Pre_VM_df.groupby(['THK_Para'])[[b1, b0]].transform('mean', numeric_only=True),
                inplace=True,
            )

    # reindex: 회귀전용 문서만 있는 컬렉션은 pre_eq_ch/Pre_Thk/Count 키 자체가 없음 → NaN 컬럼 생성
    Pre_VM_df = Pre_VM_df[Pre_VM_df['THK_Para'] == sk['Thk_Para']].reindex(columns=col_list).copy()
    Pre_VM_df.rename(columns={'pre_oper_time': 'pre_thk_time'}, inplace=True)

    Pre_VM_df['Date'] = pd.to_datetime(Pre_VM_df['Date'])
    Pre_VM_df = Pre_VM_df.sort_values(by='Date')
    return pd.merge_asof(Simul_df, Pre_VM_df, on='Date', by=['pre_eq_ch'])


_RR_COEF_COLS = ('RR_b1', 'RR_b0', 'RR_b1_weighted', 'RR_b0_weighted',
                 'RR_b1_current', 'RR_b0_current', 'RR_if_b1', 'RR_if_b0')


def _attach_rr(Simul_df, RR_df, sk):
    """Removal Rate 학습계수(b1/b0 4종)를 시점 기준으로 결합.

    - weighted/current/if 계수는 컬렉션에 없으면 NaN 컬럼으로 생성 (RR_DB 계산 분기 통일)
    - '-' sentinel → NaN (source Module 이 저장한 과거 문서 호환.
      새 REMOVAL_RATE 는 '-' 항목을 문서에서 제외하고 저장)
    """
    if RR_df.empty:
        print('    ! RR 학습 데이터 없음 → RR 계수 NaN (RR_DB 산출 불가)')
        out = Simul_df.copy()
        for c in _RR_COEF_COLS:
            out[c] = np.nan
        return out

    col_list = ['Date', 'EQ', 'Recipe_ID'] + [c for c in RR_df.columns if 'b1' in c or 'b0' in c]
    RR_df = RR_df[RR_df['APC_Para'] == sk['APC_Para']][col_list].copy()

    for suffix in ('weighted', 'current'):
        if f'b1_{suffix}' not in RR_df.columns:
            RR_df[f'b1_{suffix}'] = np.nan
            RR_df[f'b0_{suffix}'] = np.nan
    if 'if_b1' not in RR_df.columns:
        RR_df['if_b1'] = np.nan
        RR_df['if_b0'] = np.nan

    RR_df.rename(columns={
        'EQ'          : 'eqp_id',
        'Recipe_ID'   : 'recipe_id',
        'b1'          : 'RR_b1',
        'b0'          : 'RR_b0',
        'b1_weighted' : 'RR_b1_weighted',
        'b0_weighted' : 'RR_b0_weighted',
        'b1_current'  : 'RR_b1_current',
        'b0_current'  : 'RR_b0_current',
        'if_b1'       : 'RR_if_b1',
        'if_b0'       : 'RR_if_b0',
    }, inplace=True)

    RR_df['Date'] = pd.to_datetime(RR_df['Date'])
    RR_df.replace('-', np.nan, inplace=True)
    RR_df = RR_df.sort_values(by='Date')

    return pd.merge_asof(Simul_df, RR_df, on='Date', by=['eqp_id', 'recipe_id'])


def _attach_online(Simul_df, online_simul_df):
    """Online Simulation 결과(MICO_* 컬럼)를 substrate_id 기준 left join."""
    if online_simul_df.empty:
        return Simul_df.copy()
    online = online_simul_df[
        ['substrate_id'] + [c for c in online_simul_df.columns if 'MICO' in c]
    ]
    return pd.merge(Simul_df, online, on='substrate_id', how='left')


def _attach_offset(Simul_df, OFFSET_df, sk, mode, Offset_Group):
    """Idle OFFSET 학습값을 시점 기준(merge_asof, eqp/recipe/IDLE별)으로 결합.

    TIME 모드는 IDLE 을 LC 계열 / TB(ADD·T·TB) 계열 / Normal 로 분리 후,
    Offset_Group='Y' 면 IDLE 레이블을 그룹 형태로 재구성해 결합 (OFFSET 학습 저장 형식과 일치).
    """
    if OFFSET_df.empty:
        print('    ! OFFSET 학습 데이터 없음 → Simul_OFFSET NaN (이후 0 보정)')
        out = Simul_df.copy()
        out['Simul_OFFSET'] = np.nan
        return out

    OFFSET_df = OFFSET_df[OFFSET_df['APC_Para'] == sk['APC_Para']][
        ['eqp_id', 'recipe_id', 'IDLE', 'OFFSET', 'Date']
    ].copy()
    OFFSET_df.rename(columns={'OFFSET': 'Simul_OFFSET'}, inplace=True)
    OFFSET_df['Date'] = pd.to_datetime(OFFSET_df['Date'])
    if not OFFSET_df.empty:
        OFFSET_df = OFFSET_df.sort_values(by='Date')

    if mode != 'TIME':
        return pd.merge_asof(Simul_df, OFFSET_df, on='Date', by=['eqp_id', 'recipe_id', 'IDLE'])

    Simul_df['IDLE'] = Simul_df['IDLE'].fillna('Normal')

    is_lc = Simul_df['IDLE'].str.contains('LC_')
    is_tb = (
        Simul_df['IDLE'].str.contains('_ADD_')
        | Simul_df['IDLE'].str.contains('_T_')
        | Simul_df['IDLE'].str.contains('_TB_')
    )

    df_lc     = Simul_df[is_lc & ~is_tb].copy()
    df_tb     = Simul_df[is_tb].copy()
    df_normal = Simul_df[~is_lc].copy()

    if Offset_Group == 'Y':
        # LC_{EQ}_{IDLE구간} → LC_{IDLE구간}, {EQ}_{ADD/T/TB}_{...}_{구간} → 그룹 레이블로 축약
        df_lc['IDLE'] = df_lc['IDLE'].apply(lambda x: '_'.join([x.split('_')[0], x.split('_')[2]]))
        df_tb['IDLE'] = df_tb['IDLE'].apply(lambda x: '_'.join([x.split('_')[0], x.split('_')[3]]))

    merged = pd.concat([df_normal, df_lc, df_tb], axis=0)
    merged.sort_values(by='Date', inplace=True)
    return pd.merge_asof(merged, OFFSET_df, on='Date', by=['eqp_id', 'recipe_id', 'IDLE'])


def _fill_learning_values(df):
    """결합 후 남은 학습값 결측 보정.

    - RR b1/b0 : eq_model_recipe 별 ffill → 평균
    - OFFSET   : eq_model_recipe + IDLE 별 평균
    - Pre_Thk  : pre_eq_ch 별 ffill → 평균 → 0
    """
    # RR 계수는 '-' → NaN 치환 후 결합되므로 coerce 로 안전하게 숫자화
    for col in df.columns:
        if col[0:3] == 'RR_':
            df[col] = pd.to_numeric(df[col], errors='coerce')

    df.fillna(df.groupby(['eq_model_recipe'])[['RR_b0', 'RR_b1']].transform('ffill'), inplace=True)
    df.fillna(df.groupby(['eq_model_recipe'])[['RR_b0', 'RR_b1']].transform('mean', numeric_only=True), inplace=True)
    df.fillna(df.groupby(['eq_model_recipe', 'IDLE'])[['Simul_OFFSET']].transform('mean', numeric_only=True), inplace=True)

    df.fillna(df.groupby(['pre_eq_ch'])[['Pre_Thk']].transform('ffill'), inplace=True)
    df.fillna(df.groupby(['pre_eq_ch'])[['Pre_Thk']].transform('mean', numeric_only=True), inplace=True)
    df.fillna(value={'Pre_Thk': 0}, inplace=True)

    return df


def _resolve_pre_thk_formula(sk, formula):
    """공정별 Pre_Thk 산식 확정. 미지정 항목은 set-up 기준 기본값으로 채움.

    formula 는 각 공정 Simulation_Hub 의 PRE_THK_FORMULA 로 control:
        PRE_THK_FORMULA = {
            'PRE_OPER'  : True,        # moving avg(Pre_Thk 학습값) 사용 여부
            'PRE_OPER2' : 'reg',       # None | 'raw' | 'reg' | (mode, weight)
            'PRE_OPER3' : None,
            'PRE_OPER4' : ('reg', 2),
        }

    항목별 의미:
        'PRE_OPER'  : True  → Pre_Thk 학습값(moving avg / ITM VM)을 베이스로 사용
                      False → 베이스 0 에서 시작 (moving avg 미사용)
        'PRE_OPERn' : None       → 미사용
                      'raw'      → 계측값 그대로 더함
                      'reg'      → 회귀식 (계측값 * b1 + b0) 더함
                      (mode, w)  → weight 지정 (예: ('reg', 2), ('raw', 0.5))
    기본값(항목 미지정 시): set-up 에 Pre_Oper_Code{n} 있으면 'reg'
        (PRE_OPER2 는 SOURCE OX CMP 만 weight 2) → 기존(source) 동작과 동일
    """
    formula  = dict(formula or {})
    resolved = {'PRE_OPER': formula.get('PRE_OPER', True)}

    for i in (2, 3, 4):
        oper = f'PRE_OPER{i}'
        if oper in formula:
            spec = formula[oper]
        else:
            code = sk[f'Pre_Oper_Code{i}']
            has_setup = isinstance(code, str) and code != ''
            spec = 'reg' if has_setup else None
            if spec and i == 2 and sk['Oper_Desc'] == 'SOURCE OX CMP':
                spec = ('reg', 2)

        # (mode, weight) 튜플로 정규화
        if spec is None:
            resolved[oper] = None
        elif isinstance(spec, str):
            resolved[oper] = (spec, 1)
        else:
            resolved[oper] = (spec[0], spec[1])

    return resolved


def _apply_pre_thk_formula(df, sk, formula):
    """확정된 산식(formula)대로 Pre_Thk 조합.

    Pre_Thk = (PRE_OPER 사용 시 moving avg 학습값, 미사용 시 0)
              + Σ weight * (raw: 계측값 | reg: 계측값 * b1 + b0)

    - 계측값 결측 → 평균 보정 (행 전체가 NaN 되는 것 방지)
    - reg 의 b1/b0 결측 → 평균 보정
    - 사용 여부와 무관하게 남은 PRE_OPER*_b* 컬럼은 마지막에 정리
    """
    df['Pre_Thk2'] = df['Pre_Thk']  # 산식 적용 전 moving avg 원값 보존

    if not formula['PRE_OPER']:
        print('    Pre_Thk 산식: PRE_OPER(moving avg) 미사용 → 베이스 0')
        df['Pre_Thk'] = 0

    for i in (2, 3, 4):
        spec = formula[f'PRE_OPER{i}']
        if spec is None:
            continue
        mode, weight = spec

        val_col = f"{sk[f'Pre_Oper_Desc{i}']}.{sk[f'Pre_Oper_Para{i}']}"
        if val_col not in df.columns:
            print(f'    ! Pre_Thk 산식 PRE_OPER{i}({mode}) — 계측 컬럼 없음({val_col}) → 항 제외')
            continue
        val = df[val_col].fillna(df[val_col].mean())

        if mode == 'raw':
            term = val
        elif mode == 'reg':
            b1_col, b0_col = f'PRE_OPER{i}_b1', f'PRE_OPER{i}_b0'
            if b1_col not in df.columns:
                print(f'    ! Pre_Thk 산식 PRE_OPER{i}(reg) — 회귀계수 없음({b1_col}) → 항 제외')
                continue
            b1   = df[b1_col].fillna(df[b1_col].mean())
            b0   = df[b0_col].fillna(df[b0_col].mean())
            term = val * b1 + b0
        else:
            raise ValueError(f'Pre_Thk 산식 mode 인식 불가: {mode}')

        print(f'    Pre_Thk 산식 적용: PRE_OPER{i} {mode} (weight={weight})')
        df['Pre_Thk'] = df['Pre_Thk'] + weight * term

    # 회귀계수 컬럼 정리 (미사용 항 포함)
    b_cols = [c for c in df.columns if c.startswith('PRE_OPER') and ('_b1' in c or '_b0' in c)]
    if b_cols:
        df.drop(columns=b_cols, inplace=True)

    return df


def _attach_ref_lots(df, ref_lot_df, sk, mode, Thk_Para_13P, ITM_PRE_Para, pol_type):
    """Ref lot(기준 wafer) 정보를 결합.

    - item_value(';' 구분 substrate_id 목록)를 Ref_1~N 컬럼으로 분리
    - 각 Ref_i 에 해당 wafer 의 Post/Pre_VM/APC/OFFSET 값을 붙임
    """
    ref_lot_df = ref_lot_df.copy()
    ref_lot_df.drop_duplicates(inplace=True)

    Ref_Para = Get_data.REFParaGet(sk['APC_Para'], pol_type, sk['Oper_Desc'], sk['Fab'])
    input_name = Ref_Para if Ref_Para is not None else sk['APC_Para']

    ref_temp_df = ref_lot_df[
        (ref_lot_df['operation_id'] == sk['Oper_Code'])
        & (ref_lot_df['input_name'] == input_name)
    ].copy()

    if ref_temp_df.empty:
        return df

    col_num  = len(list(ref_temp_df['item_value'].str.split(';', expand=True).columns))
    ref_cols = [f'Ref_{i}' for i in range(1, col_num + 1)]
    ref_temp_df[ref_cols] = ref_temp_df['item_value'].str.split(';', expand=True)
    ref_temp_df['Ref_Count'] = ref_temp_df['item_value'].str.count(';')
    # NOTE: source 원본 그대로 Ref_YN == Ref_Count (Y/N 의도 여부 회사 확인 예정)
    ref_temp_df['Ref_YN'] = ref_temp_df['item_value'].str.count(';')

    ref_data_cols = ['Date', 'substrate_id', sk['Thk_Para'], 'Pre_Thk', sk['APC_Para'], 'Simul_OFFSET']
    if mode == 'PRESSURE':
        ref_data_cols.insert(2, Thk_Para_13P)
    if ITM_PRE_Para is not None:
        ref_data_cols.append(ITM_PRE_Para)

    ref_data = df[ref_data_cols].copy()
    ref_data.dropna(axis=0, how='any', inplace=True)

    if mode == 'TIME':
        base_cols = ['{}_Date', '{}', '{}_Post', '{}_Pre_VM', '{}_APC', '{}_OFFSET']
    else:
        base_cols = ['{}_Date', '{}', '{}_13P', '{}_Post', '{}_Pre_VM', '{}_APC', '{}_OFFSET']
    if ITM_PRE_Para is not None:
        base_cols = base_cols + ['{}_Pre_ITM']

    for i in range(1, 5):
        merge_col = f'Ref_{i}'
        if merge_col not in ref_temp_df.columns:
            continue
        r = ref_data.copy()
        r.columns = [c.format(merge_col) for c in base_cols]
        ref_temp_df = pd.merge(ref_temp_df, r, on=merge_col, how='left')

    final_cols = ['substrate_id']
    for i in range(1, 5):
        if f'Ref_{i}' not in ref_temp_df.columns:
            continue
        final_cols.extend([c.format(f'Ref_{i}') for c in base_cols])
    final_cols.extend(['Ref_Count', 'Ref_YN'])

    ref_temp_df = ref_temp_df[[c for c in final_cols if c in ref_temp_df.columns]].copy()
    ref_temp_df.drop_duplicates(inplace=True)

    return pd.merge(df, ref_temp_df, on='substrate_id', how='left')


def _finalize(df, sk, Main_Para, Pad_Para, Disk_Para, Head_Para, Consumable_Para, mode):
    """공통 출력 컬럼 구성 + RR_DB(시뮬레이션 RR) 산출.

    RR_DB 우선순위: IF 모델(Pad_Seperation 이하) → current → weighted → 전체 회귀
    """
    if mode == 'TIME':
        for i, para in enumerate(Main_Para):
            if i == 0:
                df['Pol_Time'] = df[para]
            else:
                df['Pol_Time'] += df[para]
            df[f'Pol_Time_{i + 1}'] = df[para]
    else:
        for i, para in enumerate(Main_Para):
            df[f'Pressure_{i + 1}'] = df[para]

    df['PAD_TIME']  = df[Pad_Para]
    df['DISK_TIME'] = df[Disk_Para]
    df['HEAD_TIME'] = df[Head_Para]
    df['THK']       = df[sk['Thk_Para']]

    Pad_Seperation = sk['Pad_Seperation']

    def RR(consumable, b1_weighted, b0_weighted, b1, b0, b1_current, b0_current, if_b1, if_b0):
        # 계수는 _fill_learning_values 에서 숫자화됨 ('-' sentinel 은 NaN 처리)
        if (pd.isna(if_b1) == False) and (consumable <= Pad_Seperation):
            return consumable * if_b1 + if_b0
        elif pd.isna(b1_current) == False:
            return consumable * b1_current + b0_current
        elif pd.isna(b1_weighted) == False:
            return consumable * b1_weighted + b0_weighted
        else:
            return consumable * b1 + b0

    df['RR_DB'] = np.vectorize(RR)(
        df[Consumable_Para],
        df['RR_b1_weighted'], df['RR_b0_weighted'],
        df['RR_b1'], df['RR_b0'],
        df['RR_b1_current'], df['RR_b0_current'],
        df['RR_if_b1'], df['RR_if_b0'],
    )
    return df


# ── 시뮬레이션 모듈 ────────────────────────────────────────────────────────

class Simulation_Get:

    def fetch_simulation_data(mico_info_key, Days=None):
        # Set-up 키 기준으로 시뮬레이션 입력 데이터 일괄 로드:
        # merge_df(실측) / ref_lot_df / 학습 3종(Pre VM·RR·OFFSET) / Online Simulation
        Family         = mico_info_key['Family'].unique()[0]
        Fab            = mico_info_key['Fab'].unique()[0]
        Lot_Code       = mico_info_key['Lot_Code'].unique()[0]
        Oper_Code      = mico_info_key['Oper_Code'].unique()[0]
        Oper_Desc      = mico_info_key['Oper_Desc'].unique()[0]
        Recipe_ID_List = tuple(mico_info_key['Recipe_ID'].unique())

        print(f'    [데이터 조회] {Fab} | {Lot_Code} | {Oper_Desc}')
        merge_df = Get_data.MongoDB_GetData(Family, Fab, Lot_Code, Oper_Desc)
        merge_df['Fab'] = Fab
        merge_df = merge_df.sort_values(by='Date')
        print(f'    merge_df: {len(merge_df)}행')

        ref_lot_df = _load_ref_lots(Fab, Lot_Code, Oper_Code, Recipe_ID_List, Days)
        Pre_VM_df, RR_df, OFFSET_df, online_simul_df = _load_learning_tables(
            Family, Fab, Lot_Code, Oper_Desc
        )

        return merge_df, ref_lot_df, Pre_VM_df, RR_df, OFFSET_df, online_simul_df

    def merge_pre_oper_info(merge_df, mico_info_key):
        # Pre_Oper2 set-up 이 있으면 PRE_THK_INFO 컬렉션(사전공정 계측)을 merge_df 에 결합.
        # set-up 없으면 그대로 반환 → 공정별 분기 없이 자동 처리 (Merge_Data 패턴)
        #
        # wafer 단위(substrate_id) join — 학습측 REMOVAL_RATE.apply_pre_oper2_correction 과 동일.
        # (source 는 substrate_id 를 버리고 alias_lot_id(lot 단위)로 결합해
        #  wafer 별 계측 차이가 lot 첫 행 값으로 뭉개지는 문제가 있었음)
        pre2_vals = mico_info_key['Pre_Oper_Code2'].dropna()
        if len(pre2_vals[pre2_vals != '']) == 0:
            return merge_df

        Fab       = mico_info_key['Fab'].unique()[0]
        Lot_Code  = mico_info_key['Lot_Code'].unique()[0]
        Oper_Desc = mico_info_key['Oper_Desc'].unique()[0]

        client = MongoClient(_MICO_URL)
        try:
            coll = client[_MICO_DB][f'MICO_PRE_THK_INFO_{Lot_Code}_{Oper_Desc}_{Fab}']
            pre2_df = pd.DataFrame(coll.find({}, {'_id': 0}))
        finally:
            client.close()

        if pre2_df.empty:
            print('    PRE_THK_INFO 데이터 없음 → 결합 skip')
            return merge_df

        # 구(samp_matl_id) / 신(substrate_id) 키 공존 컬렉션 → 단일 substrate_id 로 병합
        pre2_df = Get_data.coalesce_substrate_id(pre2_df)
        # 같은 웨이퍼가 구/신 문서로 중복될 수 있으므로 최신 1건만 유지 (merge 시 행 증식 방지)
        pre2_df = pre2_df.drop_duplicates(subset='substrate_id', keep='last')
        # Merge_Data 가 결측을 '-' 로 저장 → NaN 복원 (산식의 평균 보정이 처리)
        pre2_df.replace('-', np.nan, inplace=True)
        # merge_df 와 겹치는 컬럼(wf_id/end_tm/alias_lot_id 등)은 제거 — suffix 충돌 방지
        overlap = [c for c in pre2_df.columns if c in merge_df.columns and c != 'substrate_id']
        pre2_df.drop(columns=overlap, inplace=True)

        print(f'    PRE_THK_INFO 결합: {len(pre2_df)}건 (substrate_id 기준)')
        return pd.merge(merge_df, pre2_df, on='substrate_id', how='left')

    def simulate(search_key, merge_df, ref_lot_df, Pre_VM_df, RR_df, OFFSET_df,
                 online_simul_df, pol_type, mode,
                 Offset_Group=None, Thk_Para_13P=None, pre_thk_formula=None):
        # 시뮬레이션 파이프라인 실행 (TIME / PRESSURE 공통 코어)
        # 실측 → Pre VM → RR → Online → OFFSET → 결측 보정 → Pre_Thk 산식 → Ref lot → 최종 산출
        sk = _parse_search_key(search_key)

        # ITM 사전 계측 para: web Set-up 의 Pre_Thk_Para_ITM 값 사용 (별도 config 없음)
        ITM_PRE_Para = sk['Pre_Thk_Para_ITM'] if sk['Pre_Thk_Para_ITM'] != '' else None

        Main_Para         = Get_data.APCParaGet(sk['APC_Para'], pol_type)
        Main_Para_formula = [x + '_formula' for x in Main_Para]
        Main_Para_OFFSET  = [x + '_OFFSET' for x in Main_Para]
        Pad_Para          = Get_data.PadParaGet(sk['APC_Para'])
        Disk_Para         = Get_data.DiskParaGet(sk['APC_Para'])
        Head_Para         = Get_data.HeadParaGet(sk['APC_Para'])
        Consumable_Para   = _get_consumable_para(sk, Pad_Para, Disk_Para, Head_Para)

        if sk['APC_Para'] not in merge_df.columns:
            print(f"    ! APC_Para={sk['APC_Para']} merge_df 에 없음 → skip")
            return pd.DataFrame()

        df = _build_base_frame(
            merge_df, sk, Main_Para, Main_Para_formula, Main_Para_OFFSET,
            Pad_Para, Disk_Para, Head_Para, mode, Thk_Para_13P,
        )
        if df.empty:
            print(f"    ! 필터 후 데이터 없음 (Recipe={sk['Recipe_ID']}) → skip")
            return pd.DataFrame()

        df = _attach_pre_vm(df, Pre_VM_df, sk)
        df = _attach_rr(df, RR_df, sk)
        df = _attach_online(df, online_simul_df)
        df = _attach_offset(df, OFFSET_df, sk, mode, Offset_Group)
        df = _fill_learning_values(df)
        df = _apply_pre_thk_formula(df, sk, _resolve_pre_thk_formula(sk, pre_thk_formula))

        df.fillna(value={'Simul_OFFSET': 0, 'Pre_Thk': 0}, inplace=True)
        df.drop_duplicates(subset=['Date', 'substrate_id'], inplace=True)

        df = _attach_ref_lots(df, ref_lot_df, sk, mode, Thk_Para_13P, ITM_PRE_Para, pol_type)
        df = _finalize(df, sk, Main_Para, Pad_Para, Disk_Para, Head_Para, Consumable_Para, mode)
        return df

    def simulate_time(search_key, data, pol_type, Offset_Group, pre_thk_formula=None):
        # TIME(13P) 시뮬레이션. data = fetch_simulation_data 반환 tuple
        merge_df, ref_lot_df, Pre_VM_df, RR_df, OFFSET_df, online_simul_df = data
        return Simulation_Get.simulate(
            search_key, merge_df, ref_lot_df, Pre_VM_df, RR_df, OFFSET_df,
            online_simul_df, pol_type, mode='TIME',
            Offset_Group=Offset_Group, pre_thk_formula=pre_thk_formula,
        )

    def simulate_pressure(search_key, data, pol_type, Thk_Para_13P, pre_thk_formula=None):
        # PRESSURE(EDGE/EXED/존별) 시뮬레이션. 13P Thk_Para 를 기준 컬럼으로 함께 사용
        merge_df, ref_lot_df, Pre_VM_df, RR_df, OFFSET_df, online_simul_df = data
        return Simulation_Get.simulate(
            search_key, merge_df, ref_lot_df, Pre_VM_df, RR_df, OFFSET_df,
            online_simul_df, pol_type, mode='PRESSURE',
            Thk_Para_13P=Thk_Para_13P, pre_thk_formula=pre_thk_formula,
        )


# ── Runner helpers ─────────────────────────────────────────────────────────

def _zone_label(thk_para, extra_zones):
    """Thk_Para → zone 라벨 분류 (Merge_Data._classify_para_zones 와 동일 기준).

    - ED1/EDGE → 'EDGE', ED2/EXED → 'EXED'
    - 그 외    → extra_zones 중 Thk_Para 에 포함된 라벨 반환
                 (예: ['Z5'] → ..._Z5_AVG 는 'Z5', ['CENTER', 'Z1', 'Z2'] 등 확장 가능)
    - 매칭 없으면 None(처리 제외)
    """
    if 'ED1' in thk_para or 'EDGE' in thk_para:
        return 'EDGE'
    if 'ED2' in thk_para or 'EXED' in thk_para:
        return 'EXED'
    for zone in extra_zones:
        if zone in thk_para:
            return zone
    return None


def _append_zone(zones, zone, Simul_df):
    """zone 별 DataFrame 누적 (source 의 eval/exec 동적 변수 대체)."""
    if Simul_df.empty:
        return
    zones[zone].append(Simul_df)


def _run_key(mico_info_key, zones, extra_zones, pre_thk_formula, c):
    """for_key(Lot_Code+Oper_Code+Fab) 하나에 대한 시뮬레이션 실행 → zones 에 누적."""
    Fab       = mico_info_key['Fab'].unique()[0]
    Lot_Code  = mico_info_key['Lot_Code'].unique()[0]
    Oper_Desc = mico_info_key['Oper_Desc'].unique()[0]

    pol_type_vals = mico_info_key['Pol_Type'].dropna().unique()
    pol_type      = int(pol_type_vals[0]) if len(pol_type_vals) > 0 else None

    # Offset_Group 은 TIME set-up 값 사용 (unique()[0] 스칼라 — 배열 비교 버그 방지)
    offset_vals  = mico_info_key[mico_info_key['FB_Type'] == 'TIME']['Offset_Group'].dropna().unique()
    Offset_Group = offset_vals[0] if len(offset_vals) > 0 else None

    try:
        data     = Simulation_Get.fetch_simulation_data(mico_info_key)
        merge_df = Simulation_Get.merge_pre_oper_info(data[0], mico_info_key)
        data     = (merge_df,) + data[1:]

        # ── TIME(13P) ────────────────────────────────────────────────
        info_time    = mico_info_key[mico_info_key['FB_Type'] == 'TIME']
        Thk_Para_13P = None
        Target_13P   = None

        for i in range(len(info_time)):
            key            = info_time.iloc[i, :]
            Thk_Para_13P   = key['Thk_Para']
            Target_13P     = float(key['Target'])
            Pre_Target_13P = float(key['Pre_Target'])

            print(f"    [TIME] APC_Para={key['APC_Para']} | Thk_Para={Thk_Para_13P}")
            Simul_df = Simulation_Get.simulate_time(
                key, data, pol_type, Offset_Group, pre_thk_formula=pre_thk_formula,
            )
            if not Simul_df.empty:
                Simul_df['Pre_Target_13P'] = Pre_Target_13P
                Simul_df['Target_13P']     = Target_13P
            _append_zone(zones, '13P', Simul_df)

        # ── PRESSURE (EDGE / EXED / extra zones) ─────────────────────
        info_pressure = mico_info_key[mico_info_key['FB_Type'] == 'PRESSURE']

        if len(info_pressure) > 0 and Thk_Para_13P is None:
            print('    ! TIME set-up 없음 (Thk_Para_13P 미확보) → PRESSURE 시뮬레이션 skip')
            return

        for i in range(len(info_pressure)):
            key      = info_pressure.iloc[i, :]
            Thk_Para = key['Thk_Para']
            zone     = _zone_label(Thk_Para, extra_zones)

            if zone is None:
                print(f"    [PRESSURE] Thk_Para={Thk_Para} → 처리 대상 zone 아님, 제외")
                continue

            print(f"    [PRESSURE] APC_Para={key['APC_Para']} | Thk_Para={Thk_Para} | zone={zone}")
            Simul_df = Simulation_Get.simulate_pressure(
                key, data, pol_type, Thk_Para_13P, pre_thk_formula=pre_thk_formula,
            )
            if Simul_df.empty:
                continue

            if zone in ('EDGE', 'EXED'):
                Simul_df[f'Pre_Target_{zone}'] = float(key['Pre_Target'])
                Simul_df[f'Target_{zone}']     = float(key['Target'])
            else:
                Simul_df['ZONE'] = zone

            _append_zone(zones, zone, Simul_df)

    except Exception as e:
        tb = traceback.format_exc()
        c.sendMsg('', '506204179', f'{Fab} {Lot_Code} {Oper_Desc}, Simul Failed : {e}, {tb}')


def _export_results(zones, Product, export_oper, file_labels, extra_zones, export_dir):
    """zone 별 누적 결과를 Product 단위 CSV 로 출력 (Spotfire 연동, 기존 파일명 유지).

    - 13P / EDGE / EXED : 개별 파일 (file_labels 로 파일명 라벨 치환 가능)
    - extra_zones       : 통합하여 Simul_Other 로 출력 (ZONE 컬럼으로 구분)
    """
    out_dir = f'{export_dir}/{Product}_{export_oper}_Simulation'

    def _concat(zone_list):
        frames = [f for z in zone_list for f in zones.get(z, [])]
        return pd.concat(frames) if frames else pd.DataFrame()

    for zone in ('13P', 'EDGE', 'EXED'):
        df    = _concat([zone])
        label = file_labels.get(zone, zone)
        path  = f'{out_dir}/Simul_{label}_{Product}.csv'
        df.to_csv(path)
        print(f'  [출력] {path} ({len(df)}행)')

    if extra_zones:
        df   = _concat(extra_zones)
        path = f'{out_dir}/Simul_Other_{Product}.csv'
        df.to_csv(path)
        print(f'  [출력] {path} ({len(df)}행, zones={list(extra_zones)})')


# ── 메인 실행 ──────────────────────────────────────────────────────────────

def run(Family, oper_desc,
        extra_zones=None,
        file_labels=None,
        pre_thk_formula=None,
        export_dir=_EXPORT_BASE,
        export_oper=None):
    """Simulation 메인 실행

    기본 처리 zone 은 13P / EDGE(ED1) / EXED(ED2) 3종.
    그 외 zone 은 extra_zones 에 라벨을 등록한 공정만 처리 (예: M1 CU 의 ['Z5']).

    Args:
        Family          : 'NAND' or 'DRAM'
        oper_desc       : 공정 이름 (예: 'M1 CU CMP')
        extra_zones     : EDGE/EXED 외 추가 처리할 zone 라벨 리스트
                          (Thk_Para 포함 문자열 매칭, 예: ['Z5'], ['CENTER', 'Z1', 'Z2'])
                          결과는 통합하여 Simul_Other 출력, 미등록 zone 은 처리 제외
        file_labels     : CSV 파일명 라벨 치환 dict (예: {'EDGE': 'ED1', 'EXED': 'ED2'})
        pre_thk_formula : Pre_Thk 산식 조합 dict — 각 공정 Hub 의 PRE_THK_FORMULA
                          {'PRE_OPER': True|False,          # moving avg 사용 여부
                           'PRE_OPER2': None|'raw'|'reg'|(mode, weight),
                           'PRE_OPER3': ..., 'PRE_OPER4': ...}
                          미지정(None) 시 set-up 기준 기본값 (기존 source 동작)
        export_dir      : CSV 출력 기본 경로
        export_oper     : CSV 폴더명 공정 토큰 (기본 oper_desc 의 공백 → '_')

    (PRE_THK_INFO 결합은 web Set-up 의 Pre_Oper_Code2 유무로 키별 자동 처리,
     pol_type 은 web Set-up 의 Pol_Type, ITM para 는 Pre_Thk_Para_ITM 에서 자동으로 읽어옴)
    """
    if extra_zones is None:
        extra_zones = []
    if file_labels is None:
        file_labels = {}
    if export_oper is None:
        export_oper = oper_desc.replace(' ', '_')

    c          = Cube_Connector(_CUBE_BOT_ID, _CUBE_BOT_TOKEN)
    start_time = time.time()

    print(f'\n{"#" * 60}')
    print(f'  Simulation 시작: Family={Family} | Oper_Desc={oper_desc}')
    print(f'{"#" * 60}')

    try:
        mico_info_table = Get_data.baseinfoGetData(Family=Family, oper_desc=oper_desc)
        mico_info_table['for_key'] = (
            mico_info_table['Lot_Code'] + '_' +
            mico_info_table['Oper_Code'] + '_' +
            mico_info_table['Fab']
        )

        key_list = mico_info_table['for_key'].unique()
        print(f'  처리 키 목록 ({len(key_list)}개):')
        for k in key_list:
            print(f'    - {k}')

        # Product 단위로 zone 결과 누적 → CSV 파일명은 기존(source)과 동일하게
        # {Product}_..._Simulation/Simul_*_{Product}.csv 유지
        # (Lot_Code 는 Product 보다 작은 단위 — 같은 Product 의 여러 Lot_Code 가 한 파일에 합산)
        zones_by_product = defaultdict(lambda: defaultdict(list))

        for key in key_list:
            mico_info_key = mico_info_table[mico_info_table['for_key'] == key].copy()
            Product       = mico_info_key['Product'].unique()[0]
            print(f'\n  [{key}] (Product={Product})')
            _run_key(mico_info_key, zones_by_product[Product], extra_zones, pre_thk_formula, c)

        for Product, zones in zones_by_product.items():
            _export_results(zones, Product, export_oper, file_labels, extra_zones, export_dir)

    except Exception as e:
        tb = traceback.format_exc()
        c.sendMsg('', '506204179', f'{Family} {oper_desc}, Simul Failed : {e}, {tb}')

    print(f'\n{"#" * 60}')
    print(f'  Simulation 완료: Family={Family} | Oper_Desc={oper_desc} '
          f'({time.time() - start_time:.1f}s)')
    print(f'{"#" * 60}')
