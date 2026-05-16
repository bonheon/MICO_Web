"""
DRAM M1 CU CMP  merge_df  합성 데이터 생성기
=============================================
실제 샘플 데이터 기준 컬럼명 사용

핵심 설계
  - 데이터 단위: wafer 1행
  - rank      : wafer 단위 PM 이후 누적 수
                  rank 1~4 → Idle_X 또는 Layer_X
                  rank > 4 → '' (Normal) + 간헐 LC/SP slot
  - 소모품 PM : wafer 단위 증가, PM 임계 초과 시 리셋
                  PAD/DISK PM : 3 플래튼 동시 리셋 (HEAD 유지)
                  HEAD PM     : PAD/DISK/HEAD 모두 리셋 (주기 가장 길다)
                  HEAD 교체 시 → PAD/DISK 도 동시 교체

장비 구성
  CMP 장비  : KCMP41 ~ KCMP45  (5대)
  전공정 장비: 6KTSD501 ~ 6KTSD508 × ch "1","2"  →  16 조합
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import os

rng = np.random.default_rng(42)

# ── 기본 설정 ─────────────────────────────────────────────────────────
N_TOTAL    = 20_000
START_DATE = datetime(2026,  4, 16)
END_DATE   = datetime(2026,  5, 16, 23, 0, 0)

# ── 장비 / 레시피 ────────────────────────────────────────────────────
EQP_IDS   = ['KCMP41', 'KCMP42', 'KCMP43', 'KCMP44', 'KCMP45']
EQP_MODEL = 'REFLEXION_LK'

RECIPES = [
    'E2_M1CU_R12_TSV.CAS',
    'E2_M1CU_R17_TSV.CAS',
]
OPERATION_ID  = 'V5077000E'
OPER_DET_DESC = 'M1 CU CMP'

# ── 전공정 장비 ────────────────────────────────────────────────────────
PRE_EQPS = [f'6KTSD5{i:02d}' for i in range(1, 9)]   # 6KTSD501~6KTSD508
PRE_CHS  = ['1', '2']

# ── 소모품 증가량 / PM 임계 (wafer 단위) ──────────────────────────────
# PAD / DISK: km 단위  (1 wafer ≈ 0.010~0.022 km, PM at ~20~25 km)
PAD_INC      = (0.010, 0.022)
DISK_INC     = (0.008, 0.018)
PAD_PM_AT    = 22.0     # km (noise ±3)
PAD_PM_NOISE =  3.0

# HEAD: 시간 단위  (1 wafer ≈ 0.09~0.12 hr, PM at ~480~520 hr)
HEAD_INC      = (0.09, 0.12)
HEAD_PM_AT    = 500.0   # hr (noise ±30)
HEAD_PM_NOISE =  30.0

# ── LC / SP slot 발생 확률 (Normal wafer 중) ──────────────────────────
LC_M2CU_P = 0.020
LC_M3CU_P = 0.015
SP_M1CU_P = 0.010

# LC IDLE 포맷: 'LC_{그룹}_{레이어}' (3파트) — Offset_Group='Y' 처리 기준
LC_M2CU_IDLE = 'LC_CMP_M2CU'
LC_M3CU_IDLE = 'LC_CMP_M3CU'
SP_M1CU_IDLE = 'SP_M1CU'

# ── Idle vs Layer 비율 ────────────────────────────────────────────────
IDLE_RATIO = 0.60

# ── P3 보조 파라미터 기준값 ───────────────────────────────────────────
P3_RRING_BASE = 7.3
P3_ZONE_BASE  = [6.4, 2.3, 2.6, 2.4, 2.4]

# ── RR 모델 (PAD 마모 반영) ───────────────────────────────────────────
# P3와 Post-OCD를 독립 난수로 생성하지 않고, PAD 마모 → RR → P3/두께 순으로 역산
#   RR_actual = RR_B0 + RR_B1 * AMAT_PAD_3 + noise
#   P3 = (PRE_TARGET - POST_OCD_TARGET) / RR_actual  ← APC 역산값
#   Post-OCD = PRE_TARGET - RR_actual * P3 + 측정노이즈 ≈ POST_OCD_TARGET
PRE_TARGET      = 2350.0   # Å  (Detail.pre_target)
POST_OCD_TARGET = 1920.0   # Å  (Detail.target 기준)
RR_B0           =   20.0   # Å/s (신품 패드 기준 제거율)
RR_B1           =   -0.40  # Å/s per km (패드 마모에 따른 제거율 감소)
RR_SIGMA        =    0.6   # Å/s (공정 산포)
P3_JITTER       =    1.5   # sec (APC 제어 잔여 오차)
THK_NOISE       =   25.0   # Å  (OCD 측정 노이즈)


def _consumable_series(n, rng):
    """
    wafer n개에 대한 소모품 이력과 rank 반환.
    PAD/DISK: 3 플래튼, HEAD: 4개, wafer 단위로 증가.
    """
    pad  = [0.0, 0.0, 0.0]
    disk = [0.0, 0.0, 0.0]
    head = [0.0, 0.0, 0.0, 0.0]
    rank = 0

    pad_threshold  = PAD_PM_AT  + float(rng.uniform(-PAD_PM_NOISE, PAD_PM_NOISE))
    head_threshold = HEAD_PM_AT + float(rng.uniform(-HEAD_PM_NOISE, HEAD_PM_NOISE))

    records = []
    for _ in range(n):
        if head[0] >= head_threshold:
            pad   = [0.0, 0.0, 0.0]
            disk  = [0.0, 0.0, 0.0]
            head  = [0.0, 0.0, 0.0, 0.0]
            rank  = 0
            pad_threshold  = PAD_PM_AT  + float(rng.uniform(-PAD_PM_NOISE, PAD_PM_NOISE))
            head_threshold = HEAD_PM_AT + float(rng.uniform(-HEAD_PM_NOISE, HEAD_PM_NOISE))
        elif pad[0] >= pad_threshold:
            pad  = [0.0, 0.0, 0.0]
            disk = [0.0, 0.0, 0.0]
            rank = 0
            pad_threshold = PAD_PM_AT + float(rng.uniform(-PAD_PM_NOISE, PAD_PM_NOISE))

        for j in range(3):
            pad[j]  += float(rng.uniform(*PAD_INC))  * (1 + rng.uniform(-0.05, 0.05))
            disk[j] += float(rng.uniform(*DISK_INC)) * (1 + rng.uniform(-0.05, 0.05))
        for j in range(4):
            head[j] += float(rng.uniform(*HEAD_INC)) * (1 + rng.uniform(-0.03, 0.03))
        rank += 1

        records.append({
            'AMAT_PAD_1' : round(pad[0],  4),
            'AMAT_PAD_2' : round(pad[1],  4),
            'AMAT_PAD_3' : round(pad[2],  4),
            'AMAT_DISK_1': round(disk[0], 4),
            'AMAT_DISK_2': round(disk[1], 4),
            'AMAT_DISK_3': round(disk[2], 4),
            'AMAT_HEAD_1': round(head[0], 2),
            'AMAT_HEAD_2': round(head[1], 2),
            'AMAT_HEAD_3': round(head[2], 2),
            'AMAT_HEAD_4': round(head[3], 2),
            'rank'       : rank,
        })
    return records


def _assign_idle(rank_vals, rng):
    result = []
    for rank in rank_vals:
        if rank <= 4:
            label = f"Idle_{rank}" if rng.random() < IDLE_RATIO else f"Layer_{rank}"
        else:
            r = float(rng.random())
            if r < LC_M2CU_P:
                label = LC_M2CU_IDLE
            elif r < LC_M2CU_P + LC_M3CU_P:
                label = LC_M3CU_IDLE
            elif r < LC_M2CU_P + LC_M3CU_P + SP_M1CU_P:
                label = SP_M1CU_IDLE
            else:
                label = ''
        result.append(label)
    return result


def generate():
    rows_per_eqp = N_TOTAL // len(EQP_IDS)
    extra        = N_TOTAL % len(EQP_IDS)
    lots_per_eqp = -(-rows_per_eqp // 25)  # ceiling division
    total_hours  = (END_DATE - START_DATE).total_seconds() / 3600
    all_rows     = []

    for eqp_idx, eqp_id in enumerate(EQP_IDS):
        n = rows_per_eqp + (1 if eqp_idx < extra else 0)

        # 타임스탬프
        step_h  = total_hours / n
        jitter  = rng.normal(0, step_h * 0.04, n)
        offsets = np.clip(np.cumsum(np.full(n, step_h) + jitter), 0, total_hours)
        dates   = [START_DATE + timedelta(hours=float(h)) for h in offsets]

        # 소모품
        cons     = _consumable_series(n, rng)
        rank_arr = [c['rank'] for c in cons]

        # IDLE
        idle_arr = _assign_idle(rank_arr, rng)

        # 전공정 장비/채널
        pre_eqp       = rng.choice(PRE_EQPS, n)
        pre_ch        = rng.choice(PRE_CHS,  n)
        pre_eq_ch_arr = [f'{e}_{c}' for e, c in zip(pre_eqp, pre_ch)]
        pre_oper      = [d - timedelta(hours=float(rng.uniform(1, 6))) for d in dates]

        # lot / wafer
        recipe_arr   = rng.choice(RECIPES, n)
        process_arr  = [f'F_6E2_{(i % 5) + 1:02d}' for i in range(n)]
        lot_start    = eqp_idx * lots_per_eqp
        lot_arr      = [f'LOT{(lot_start + i // 25):04d}' for i in range(n)]
        wf_id_arr    = [str((i % 25) + 1) for i in range(n)]
        r2r_rank_arr = [(i % 20) + 1 for i in range(n)]

        # PAD 마모 기반 실제 RR → P3 역산 → Post-OCD 산출
        pad3_arr = np.array([c['AMAT_PAD_3'] for c in cons])
        rr_true  = RR_B0 + RR_B1 * pad3_arr + rng.normal(0, RR_SIGMA, n)
        rr_true  = np.maximum(rr_true, 3.0)

        p3_ideal = (PRE_TARGET - POST_OCD_TARGET) / rr_true   # APC 역산: 430/RR
        p3       = np.maximum(p3_ideal + rng.normal(0, P3_JITTER, n), 5.0)

        p3_rring = rng.normal(P3_RRING_BASE, 0.8, n)
        p3_zones = [rng.normal(P3_ZONE_BASE[z], 0.4, n) for z in range(5)]

        # Post-OCD: PRE_TARGET - RR*P3 + 측정노이즈 ≈ POST_OCD_TARGET
        avg_thk   = PRE_TARGET - rr_true * p3 + rng.normal(0, THK_NOISE, n)
        ed1_thk   = avg_thk + rng.normal(-10, 15, n)
        zone_thks = [avg_thk + rng.normal(dz, 20, n) for dz in [-30, -10, -30, 0, 20]]
        ran       = np.abs(rng.normal(135, 20, n))
        ran_e     = np.abs(rng.normal(150, 25, n))

        for i in range(n):
            row = {
                'Date'                   : dates[i],
                'process_id'             : process_arr[i],
                'recipe_id'              : recipe_arr[i],
                'eqp_id'                 : eqp_id,
                'eqp_model'              : EQP_MODEL,
                'operation_id'           : OPERATION_ID,
                'oper_id'                : OPERATION_ID,
                'oper_det_desc'          : OPER_DET_DESC,
                'item_name'              : 'FORMULA',
                'r2r_rank'               : r2r_rank_arr[i],
                'qty'                    : 25,
                'wf_id'                  : wf_id_arr[i],
                'wf_count'               : 25,
                'lot_id'                 : lot_arr[i],
                'substrate_id'           : f'{lot_arr[i]}_{wf_id_arr[i]}',
                'pre_eqp_id'             : pre_eqp[i],
                'pre_eqp_ch'             : pre_ch[i],
                'pre_eq_ch'              : pre_eq_ch_arr[i],
                'pre_oper_time'          : pre_oper[i],
                'P3'                     : round(float(p3[i]), 3),
                'P3_R-RING'              : round(float(p3_rring[i]), 2),
                'P3_ZONE1'               : round(float(p3_zones[0][i]), 2),
                'P3_ZONE2'               : round(float(p3_zones[1][i]), 2),
                'P3_ZONE3'               : round(float(p3_zones[2][i]), 2),
                'P3_ZONE4'               : round(float(p3_zones[3][i]), 2),
                'P3_ZONE5'               : round(float(p3_zones[4][i]), 2),
                'POLISH_1_4'             : '-',
                **{k: cons[i][k] for k in [
                    'AMAT_PAD_1','AMAT_PAD_2','AMAT_PAD_3',
                    'AMAT_DISK_1','AMAT_DISK_2','AMAT_DISK_3',
                    'AMAT_HEAD_1','AMAT_HEAD_2','AMAT_HEAD_3','AMAT_HEAD_4',
                ]},
                'AMAT_POST_OCD_AVG'      : round(float(avg_thk[i]), 4),
                'AMAT_POST_OCD_ED1_AVG'  : round(float(ed1_thk[i]), 2),
                'AMAT_POST_OCD_ED1_RAN'  : round(float(ran_e[i]), 3),
                'AMAT_POST_OCD_RAN'      : round(float(ran[i]), 0),
                'AMAT_POST_OCD_Z1_AVG'   : round(float(zone_thks[0][i]), 2),
                'AMAT_POST_OCD_Z2_AVG'   : round(float(zone_thks[1][i]), 2),
                'AMAT_POST_OCD_Z3_AVG'   : round(float(zone_thks[2][i]), 2),
                'AMAT_POST_OCD_Z4_AVG'   : round(float(zone_thks[3][i]), 2),
                'AMAT_POST_OCD_Z5_AVG'   : round(float(zone_thks[4][i]), 2),
                'IDLE'                   : idle_arr[i],
                'rank'                   : rank_arr[i],
                'event_tm'               : '-',
                'before_recipe_id'       : '-',
                'brfore_info'            : '-',
            }
            all_rows.append(row)

    df = pd.DataFrame(all_rows)
    df['Date']          = pd.to_datetime(df['Date'])
    df['pre_oper_time'] = pd.to_datetime(df['pre_oper_time'])
    return df.sort_values('Date').reset_index(drop=True)


if __name__ == '__main__':
    print('merge_df 합성 데이터 생성 중...')
    df = generate()

    print(f'\n── 기본 통계 ────────────────────────────────────────────')
    print(f'총 행 수      : {len(df):,}')
    print(f'기간          : {df["Date"].min().date()} ~ {df["Date"].max().date()}')
    print(f'장비          : {sorted(df["eqp_id"].unique())}  ({df["eqp_id"].nunique()}대)')
    print(f'레시피        : {sorted(df["recipe_id"].unique())}')
    print(f'pre_eq_ch 조합: {df["pre_eq_ch"].nunique()}개')
    print(f'  → {sorted(df["pre_eq_ch"].unique())}')

    print(f'\n── IDLE 분포 ─────────────────────────────────────────────')
    vc = df['IDLE'].replace('', 'Normal').value_counts().sort_index()
    for k, v in vc.items():
        bar = '█' * max(1, v * 40 // len(df))
        print(f'  {k:12s}: {v:6,}건  ({v/len(df)*100:5.2f}%)  {bar}')

    print(f'\n── 소모품 범위 ───────────────────────────────────────────')
    for col in ['AMAT_PAD_1','AMAT_PAD_2','AMAT_PAD_3',
                'AMAT_DISK_1','AMAT_DISK_2','AMAT_DISK_3',
                'AMAT_HEAD_1','AMAT_HEAD_4']:
        print(f'  {col:15s}: {df[col].min():7.3f} ~ {df[col].max():7.3f}')

    print(f'\n── 두께 / P3 ────────────────────────────────────────────')
    print(f'  AMAT_POST_OCD_AVG : mean={df["AMAT_POST_OCD_AVG"].mean():.1f}  '
          f'std={df["AMAT_POST_OCD_AVG"].std():.1f}')
    print(f'  P3                : mean={df["P3"].mean():.3f}  '
          f'std={df["P3"].std():.3f}')

    out = os.path.join(os.path.dirname(__file__), 'merge_df_sample.csv')
    df.to_csv(out, index=False)
    sz = os.path.getsize(out) / 1e6
    print(f'\n저장 완료: {out}  ({sz:.1f} MB)')

    print(f'\n── 컬럼 목록 ({len(df.columns)}개) ─────────────────────────────────')
    print('  ' + ', '.join(df.columns.tolist()))
