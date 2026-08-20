# ════════════════════════════════════════════════════════════════════
# [TEST 삭제] 이 파일 전체 삭제 대상
# 로컬 환경 전용 Simulation 검증 러너. 회사 실서버에서는 불필요.
# ════════════════════════════════════════════════════════════════════

"""
DRAM M1 CU CMP Simulation 로컬 검증 러너
========================================
실행 위치: algorithm_new/
  python3 test_dram_m1cu_simul.py

목적
  사내 MongoDB(학습 테이블) / Ref lot 조회 / Cube 없이도
  Simulation 파이프라인 + 결과 DB 적재(MICO_Simulation_*)를 로컬에서 검증한다.

동작
  1. merge_df_sample.csv + web Set-up 으로 학습 테이블 3종의 '샘플'을 일자별
     스냅샷으로 생성 — 사내에서는 Module.py 가 학습해 MongoDB 에 쌓는 값이다.
       · MICO_PRE_THK_..._Period : pre chamber 별 Pre_Thk_VM 이동평균
       · MICO_Removal_Rate_...   : EQ/Recipe 별 RR 회귀계수 4종
                                   (normal / weighted / current / if)
       · MICO_OFFSET_...         : EQ/Recipe/IDLE 별 Idle OFFSET
  2. Simulation._load_learning_tables 를 위 샘플 반환 함수로 교체
  3. Common.Simulation.run() 실행
     → 결과가 Set-up 과 같은 DB 의 MICO_Simulation_{Lot_Code}_{Oper_Desc}_{Fab} 에 적재

사내 전환 시
  이 파일을 쓰지 않고 simulation/DRAM_M1_CU_CMP/Simulation_Hub.py 를 그대로 실행하면
  실제 MongoDB 학습 테이블을 읽어 동일한 테이블에 결과가 적재된다.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

# ── 1. MongoClient 전역 Mock (pymongo 임포트 전에 교체) ─────────────────────
import pymongo as _pymongo

_mock_collection = MagicMock()
_mock_collection.find.return_value = iter([])

_mock_db = MagicMock()
_mock_db.__getitem__.return_value = _mock_collection
_mock_db.list_collection_names.return_value = []

_mock_client = MagicMock()
_mock_client.__getitem__.return_value = _mock_db
_mock_client.close.return_value = None

_pymongo.MongoClient = MagicMock(return_value=_mock_client)

from Common.Get_Data import Get_data
import Common.Simulation as SIM

FAMILY    = 'DRAM'
OPER_DESC = 'M1 CU CMP'

# DRAM_M1_CU_CMP/Simulation_Hub.py 와 동일한 Pre_Thk 산식 control
PRE_THK_FORMULA = {
    'PRE_OPER'  : True,
    'PRE_OPER2' : 'reg',
    'PRE_OPER3' : None,
    'PRE_OPER4' : None,
}

# 샘플 학습값 생성 파라미터
_SNAPSHOT_FREQ   = '1D'   # 학습 주기 (사내 Module 은 1일 1회 실행)
_CURRENT_WINDOW  = 7      # current 모델 학습 구간(일)
_WEIGHT_HALFLIFE = 7      # weighted 모델 지수가중 반감기(일)
_PRE_VM_WINDOW   = 5      # Pre_Thk_VM 이동평균 구간(일)
_OFFSET_WINDOW   = 14     # OFFSET 평균 구간(일)
_MIN_FIT_COUNT   = 30     # 회귀 최소 건수


# ── 회귀 helper ────────────────────────────────────────────────────────────

def _fit(x, y, w=None):
    """가중 최소제곱 1차 회귀 → (b1, b0). 데이터 부족 시 (nan, nan)."""
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if w is not None:
        w = w[mask]
    if len(x) < _MIN_FIT_COUNT or np.ptp(x) == 0:
        return np.nan, np.nan
    b1, b0 = np.polyfit(x, y, 1, w=None if w is None else np.sqrt(w))
    return float(b1), float(b0)


def _consumable_col(rr_para, apc_para):
    rr_para = str(rr_para).upper()
    if rr_para == 'HEAD':
        return Get_data.HeadParaGet(apc_para)
    if rr_para == 'DISK':
        return Get_data.DiskParaGet(apc_para)
    if rr_para == 'DRESSER_CUTTING_RATE':
        return Get_data.DresserParaGet(apc_para)
    return Get_data.PadParaGet(apc_para)


def _offset_idle_label(idle, offset_group):
    """Simulation._attach_offset 의 IDLE 재구성 규칙과 동일하게 라벨 변환."""
    idle = '' if pd.isna(idle) else str(idle)
    is_lc = 'LC_' in idle
    is_tb = ('_ADD_' in idle) or ('_T_' in idle) or ('_TB_' in idle)
    if offset_group != 'Y':
        return idle
    parts = idle.split('_')
    if is_tb and len(parts) > 3:
        return '_'.join([parts[0], parts[3]])
    if is_lc and not is_tb and len(parts) > 2:
        return '_'.join([parts[0], parts[2]])
    return idle


# ── 샘플 학습 테이블 생성 ──────────────────────────────────────────────────

def _build_sample_learning(Family, Fab, Lot_Code, Oper_Desc):
    """merge_df 샘플에서 학습 테이블 3종(일자별 스냅샷)을 만들어 반환."""
    info = Get_data.baseinfoGetData(Family=Family, oper_desc=Oper_Desc)
    info = info[(info['Fab'] == Fab) & (info['Lot_Code'] == Lot_Code)]
    time_rows = info[info['FB_Type'] == 'TIME']
    if time_rows.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    merge_df = Get_data.MongoDB_GetData(Family, Fab, Lot_Code, Oper_Desc)
    merge_df['Date'] = pd.to_datetime(merge_df['Date'])

    days = pd.date_range(merge_df['Date'].min().normalize(),
                         merge_df['Date'].max().normalize() + pd.Timedelta(days=1),
                         freq=_SNAPSHOT_FREQ)

    pre_vm_rows, rr_rows, offset_rows = [], [], []

    for _, key in time_rows.iterrows():
        APC_Para   = key['APC_Para']
        Thk_Para   = key['Thk_Para']
        Pre_Target = float(key['Pre_Target'])
        Target     = float(key['Target'])
        Pad_Sep    = -1 if pd.isna(key['Pad_Seperation']) else float(key['Pad_Seperation'])
        cons_col   = _consumable_col(key['RR_Para'], APC_Para)
        off_group  = key['Offset_Group']

        need = [APC_Para, Thk_Para, cons_col]
        if any(c not in merge_df.columns for c in need):
            print(f'  ! 샘플 학습값 생성 skip (컬럼 없음): {need}')
            continue

        d = merge_df[
            (merge_df['operation_id'] == key['Oper_Code'])
            & (merge_df['recipe_id']  == key['Recipe_ID'])
        ].dropna(subset=[APC_Para, Thk_Para, cons_col]).copy()
        if d.empty:
            continue

        d['Pol_Time'] = d[APC_Para]
        d = d[d['Pol_Time'] > 0]
        # 실제 RR (REMOVAL_RATE 의 정의 — VM 이 아직 없으므로 Pre_Target 기준)
        d['RR']    = (Pre_Target - d[Thk_Para]) / d['Pol_Time']
        d['_idle'] = d['IDLE'].apply(lambda v: _offset_idle_label(v, off_group))

        for day in days:
            hist = d[d['Date'] <= day]
            if len(hist) < _MIN_FIT_COUNT:
                continue
            recent = hist[hist['Date'] > day - pd.Timedelta(days=_CURRENT_WINDOW)]
            age_d  = (day - hist['Date']).dt.total_seconds() / 86400
            w_exp  = np.power(0.5, age_d / _WEIGHT_HALFLIFE).to_numpy()

            for (eq, rcp), g in hist.groupby(['eqp_id', 'recipe_id']):
                x, y = g[cons_col].to_numpy(float), g['RR'].to_numpy(float)
                b1, b0 = _fit(x, y)
                if not np.isfinite(b1):
                    continue

                gw = w_exp[hist.index.get_indexer(g.index)]
                w1, w0 = _fit(x, y, gw)

                gr = recent[(recent['eqp_id'] == eq) & (recent['recipe_id'] == rcp)]
                c1, c0 = _fit(gr[cons_col].to_numpy(float), gr['RR'].to_numpy(float))

                gi = g[g[cons_col] <= Pad_Sep] if Pad_Sep > 0 else g.iloc[0:0]
                i1, i0 = _fit(gi[cons_col].to_numpy(float), gi['RR'].to_numpy(float))

                rr_rows.append({
                    'Date': day, 'Fab': Fab, 'Lot_Code': Lot_Code,
                    'Oper_Code': key['Oper_Code'], 'Oper_Desc': Oper_Desc,
                    'APC_Para': APC_Para, 'EQ': eq, 'Recipe_ID': rcp, 'Count': len(g),
                    'b1': b1, 'b0': b0,
                    'b1_weighted': w1, 'b0_weighted': w0,
                    'b1_current' : c1, 'b0_current' : c0,
                    'if_b1'      : i1, 'if_b0'      : i0,
                })

            # ── Pre_Thk_VM: 모델이 설명하지 못한 두께 편차의 chamber 별 이동평균 ──
            b1_all, b0_all = _fit(hist[cons_col].to_numpy(float), hist['RR'].to_numpy(float))
            if np.isfinite(b1_all):
                win = hist[hist['Date'] > day - pd.Timedelta(days=_PRE_VM_WINDOW)].copy()
                if not win.empty:
                    rr_pred = win[cons_col] * b1_all + b0_all
                    win['_dev'] = (win['RR'] - rr_pred) * win['Pol_Time']
                    for ch, gch in win.groupby('pre_eq_ch'):
                        if len(gch) < 10:
                            continue
                        pre_vm_rows.append({
                            'Date': day, 'pre_oper_time': day,
                            'pre_eq_ch': ch, 'Pre_Thk': float(gch['_dev'].mean()),
                            'Count': len(gch), 'THK_Para': Thk_Para,
                            'Oper_Code': key['Oper_Code'],
                        })

                # ── OFFSET: 실제 RR 과 모델 RR 의 차이에서 나오는 시간 보정량 ──
                delta = Pre_Target - Target
                owin  = hist[hist['Date'] > day - pd.Timedelta(days=_OFFSET_WINDOW)].copy()
                if not owin.empty:
                    owin['_rr_pad'] = owin[cons_col] * b1_all + b0_all
                    owin['_offset'] = (delta / owin['RR'] - delta / owin['_rr_pad']).clip(-5, 3)
                    grp = owin.groupby(['eqp_id', 'recipe_id', '_idle'])['_offset']
                    for (eq, rcp, idle), val in grp.mean().items():
                        if grp.size()[(eq, rcp, idle)] < 5 or not np.isfinite(val):
                            continue
                        offset_rows.append({
                            'Date': day, 'eqp_id': eq, 'recipe_id': rcp,
                            'IDLE': idle, 'OFFSET': float(val), 'APC_Para': APC_Para,
                        })

    return (pd.DataFrame(pre_vm_rows), pd.DataFrame(rr_rows), pd.DataFrame(offset_rows))


# ── 2. 학습 테이블 로더 교체 ───────────────────────────────────────────────

_CACHE = {}


def _mock_load_learning_tables(Family, Fab, Lot_Code, oper_desc):
    cache_key = (Family, Fab, Lot_Code, oper_desc)
    if cache_key not in _CACHE:
        print('    [sample] 학습 테이블 생성 중...')
        _CACHE[cache_key] = _build_sample_learning(Family, Fab, Lot_Code, oper_desc)
    pre_vm, rr, offset = _CACHE[cache_key]
    print(f'    [sample] 학습 테이블: Pre VM={len(pre_vm)}건 | RR={len(rr)}건 | Offset={len(offset)}건')
    return pre_vm.copy(), rr.copy(), offset.copy(), pd.DataFrame()


SIM._load_learning_tables = _mock_load_learning_tables


# ── 2-2. Ref lot 로더 교체 ─────────────────────────────────────────────────
# 사내에서는 Get_Data.RefGetData / RefGetData_HUB 가 MES 에서 Ref lot 을 읽어온다.
# 로컬에는 그 조회가 없으므로, 같은 EQ/Recipe 의 직전 웨이퍼들을 Ref 로 삼아
# APC 산식(FB)의 Ref_1~4 경로를 검증할 수 있는 샘플을 만든다.

_REF_MAX      = 4    # 웨이퍼당 Ref 최대 개수
_REF_N_CYCLE  = 17   # 이 주기마다 Ref_YN='N' → Linear 산식 분기 검증


def _mock_ref_lots(Fab, Lot_Code, Oper_Code, Recipe_ID_List, Days=None):
    info = Get_data.baseinfoGetData(Family=FAMILY, oper_desc=OPER_DESC)
    info = info[(info['Fab'] == Fab)
                & (info['Lot_Code'] == Lot_Code)
                & (info['Oper_Code'] == Oper_Code)]
    if info.empty:
        return pd.DataFrame(columns=['substrate_id', 'input_name', 'operation_id', 'item_value'])

    merge_df = Get_data.MongoDB_GetData(FAMILY, Fab, Lot_Code, OPER_DESC)
    merge_df['Date'] = pd.to_datetime(merge_df['Date'])
    merge_df = merge_df[merge_df['operation_id'] == Oper_Code]

    rows = []
    for apc_para in sorted(info['APC_Para'].dropna().unique()):
        if apc_para not in merge_df.columns:
            continue
        for recipe_id, g in merge_df.groupby('recipe_id'):
            if recipe_id not in Recipe_ID_List:
                continue
            ids = g.sort_values('Date')['substrate_id'].dropna().tolist()
            for i, substrate_id in enumerate(ids):
                if i == 0:
                    continue
                n_ref = min(1 + (i % _REF_MAX), i)          # Ref 1~4개를 골고루
                refs  = ids[i - n_ref:i][::-1]              # 최근 웨이퍼부터
                rows.append({
                    'substrate_id': substrate_id,
                    'input_name'  : apc_para,
                    'operation_id': Oper_Code,
                    'item_value'  : ';'.join(refs),
                    'Ref_Count'   : n_ref - 1,              # source 정의(';' 개수)와 동일
                    'Ref_YN'      : 'N' if i % _REF_N_CYCLE == 0 else 'Y',
                })

    df = pd.DataFrame(rows)
    print(f'    [sample] Ref lot 생성: {len(df)}건')
    return df


SIM._load_ref_lots = _mock_ref_lots


# ── 2-3. PRESSURE set-up 을 샘플 CSV 컬럼으로 매핑 ─────────────────────────
# web Set-up 의 PRESSURE 행은 사내 계측/APC 파라미터(P3_04_Z1, ..._EDGE_AVG)를 쓰는데
# 로컬 샘플 CSV 에는 그 컬럼이 없어 PRESSURE 시뮬레이션이 통째로 skip 된다.
# Set-up DB 는 그대로 두고, 이 러너에서만 샘플에 있는 컬럼으로 바꿔 파이프라인을 검증한다.

_SAMPLE_CSV = str(Path(__file__).parent / 'merge_df_sample.csv')

_PRESSURE_COLUMN_MAP = {
    'APC_Para': 'P3_ZONE1',                 # 압력 (샘플 CSV 존재)
    'Thk_Para': 'AMAT_POST_OCD_ED1_AVG',    # ED1 → EDGE zone
}

_orig_baseinfo = Get_data.baseinfoGetData


def _baseinfo_with_pressure(Family, oper_desc):
    info = _orig_baseinfo(Family=Family, oper_desc=oper_desc)

    sample_cols = set(pd.read_csv(_SAMPLE_CSV, nrows=1).columns)
    mask = info['FB_Type'] == 'PRESSURE'
    if not mask.any():
        return info

    for col, replacement in _PRESSURE_COLUMN_MAP.items():
        missing = mask & ~info[col].isin(sample_cols)
        if missing.any():
            print(f'  [sample] PRESSURE set-up {col}: '
                  f'{sorted(info.loc[missing, col].unique())} → {replacement}')
            info.loc[missing, col] = replacement

    # EDGE zone 은 13P 보다 얇게 나오는 편 — Target 을 낮춰 편차가 0 이 아니게 둔다
    info.loc[mask, 'Target'] = 1850
    return info


Get_data.baseinfoGetData = _baseinfo_with_pressure


# ── 3. 실행 ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    SIM.run(
        FAMILY, OPER_DESC,
        extra_zones=['Z5'],
        file_labels={'EDGE': 'ED1', 'EXED': 'ED2'},
        pre_thk_formula=PRE_THK_FORMULA,
        save_db=True,       # → MICO_Simulation_{Lot_Code}_{Oper_Desc}_{Fab}
        export_csv=False,   # 로컬에는 Spotfire 공유 폴더가 없으므로 CSV 출력 생략
    )

    from Common import Result_DB
    print('\n저장된 Simulation 테이블:')
    for t in Result_DB.list_simulation_tables():
        print(f'  - {t}')
