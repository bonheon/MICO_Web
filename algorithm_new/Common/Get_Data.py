import sys
import os
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

_ALGO_DIR  = str(Path(__file__).parents[1])   # algorithm_new/
_MICO_WEB  = str(Path(__file__).parents[2])   # MICO_Web/ (Django root)
_CSV_PATH  = os.path.join(_ALGO_DIR, 'merge_df_sample.csv')  # [TEST 삭제] 샘플 CSV 경로 — MongoDB_GetData 와 함께 삭제

# ── Django setup (읽기 전용 DB 조회용) ────────────────────────────────────
if _MICO_WEB not in sys.path:
    sys.path.insert(0, _MICO_WEB)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()


def _coalesce_substrate_id(df):
    """구컬럼(samp_matl_id/samp_matl_if)과 substrate_id 를 하나의 substrate_id 로 병합.

    기존 DB 는 samp_matl_id 로 저장, 신규는 substrate_id 로 저장하므로 한 INFO
    컬렉션에 두 컬럼이 공존할 수 있다. 이때 단순 rename 을 하면 substrate_id 가
    '중복 컬럼'이 되어 merge(on='substrate_id') 에서 오류가 발생한다.
    → 두 컬럼이 함께 있으면 coalesce(우선순위: substrate_id 값, 없으면 구컬럼 값)해
       substrate_id 단일 컬럼으로 만들고 구컬럼은 제거한다.

    (Module.py / REMOVAL_RATE.py 등 pre_thk 관련 여러 모듈이 공통 사용.
     Get_Data 는 이들의 하위 계층이라 순환 import 없이 top-level import 가능.)
    """
    legacy_cols = [c for c in ('samp_matl_id', 'samp_matl_if') if c in df.columns]
    if not legacy_cols:
        return df

    if 'substrate_id' not in df.columns:
        # substrate_id 없이 구컬럼만 존재 → 첫 구컬럼을 substrate_id 로 rename
        df = df.rename(columns={legacy_cols[0]: 'substrate_id'})
        legacy_cols = legacy_cols[1:]
    else:
        # substrate_id + 구컬럼 공존 → substrate_id 결측을 구컬럼 값으로 채움
        for lc in legacy_cols:
            df['substrate_id'] = df['substrate_id'].where(df['substrate_id'].notna(), df[lc])

    drop_cols = [c for c in legacy_cols if c in df.columns]
    if drop_cols:
        df = df.drop(columns=drop_cols)
    return df


class Get_data:

    def baseinfoGetData(Family, oper_desc):
        """
        Django DB(Category / SubCategory / Detail / RecipeGroup)에서
        Set-up 정보를 읽어 mico_info_table DataFrame으로 반환.
        """
        from setup_mico.models import Category, SubCategory, Detail, RecipeGroup

        cats = Category.objects.filter(family=Family, oper_desc=oper_desc)
        rows = []
        for cat in cats:
            for sub in cat.subcategories.all():
                rg = sub.recipe_groups.filter(category=cat).first()
                group_name = rg.name if rg else None

                for det in sub.details.all():
                    rows.append({
                        'Family'          : cat.family,
                        'Lot_Code'        : cat.product,
                        'Oper_Code'       : cat.oper_id,
                        'Oper_Desc'       : cat.oper_desc,
                        'Channel_ID'      : cat.channel_id,
                        'Fab'             : sub.fab,
                        'Maker'           : sub.maker,
                        'Recipe_ID'       : sub.recipe_id,
                        'APC_Para'        : det.apc_para,
                        'Thk_Para'        : det.thk_para,
                        'Target'          : det.target,
                        'Post_Target'     : det.target,   # source 코드 호환 alias
                        'Pre_Target'      : det.pre_target,
                        'Pre_Thk_Period'  : det.pre_thk_period,
                        'RR_Para'         : det.rr_para,
                        'Offset_Group'    : det.offset_group,
                        'RR_Para_Max'     : det.rr_max,
                        'RR_Period'       : det.rr_period,
                        'Pad_Seperation'  : det.rr_if,
                        'Pre_Thk_Para_ITM': det.pre_thk_para_itm,
                        'Pre_Oper_Code'   : det.pre_oper_code,
                        'Pre_Oper_Desc'   : det.pre_oper_desc,
                        'Pre_Oper_Para'   : det.pre_oper_para,
                        'Pre_Oper_Code2'  : det.pre_oper_code2,
                        'Pre_Oper_Desc2'  : det.pre_oper_desc2,
                        'Pre_Oper_Para2'  : det.pre_oper_para2,
                        'Pre_Oper_Code3'  : det.pre_oper_code3,
                        'Pre_Oper_Desc3'  : det.pre_oper_desc3,
                        'Pre_Oper_Para3'  : det.pre_oper_para3,
                        'Pre_Oper_Code4'  : det.pre_oper_code4,
                        'Pre_Oper_Desc4'  : det.pre_oper_desc4,
                        'Pre_Oper_Para4'  : det.pre_oper_para4,
                        'RR_Weight'       : det.rr_weight,
                        'RR_Count'        : det.rr_count,
                        'FB_Type'         : det.fb_type,
                        'RR_Alarm_Sigma'  : det.rr_alarm_sigma,
                        'Pol_Type'        : cat.pol_type,
                        'Group_Name'      : group_name,
                    })

        df = pd.DataFrame(rows)
        if df.empty:
            raise ValueError(f'Set-up 정보 없음: Family={Family}, oper_desc={oper_desc}')
        return df


    # ── [TEST 삭제] MongoDB_GetData ──────────────────────────────────────
    # CSV 파일(merge_df_sample.csv)로 MongoDB를 대체하는 테스트 전용 구현.
    # 회사 실서버에서는 실제 MongoDB 쿼리 함수로 교체.
    def MongoDB_GetData(Family, Fab, Lot_Code, Oper_Desc):
        """CSV(merge_df_sample.csv)를 merge_df로 반환 (MongoDB 대체)."""
        df = pd.read_csv(_CSV_PATH, parse_dates=['Date', 'pre_oper_time'])
        df['IDLE'] = df['IDLE'].fillna('')
        df['Lot_Code'] = Lot_Code
        return df
    # ── [TEST 삭제 끝] ────────────────────────────────────────────────────


    def APCParaGet(APC_Para, pol_type):
        """pol_type에 따른 APC 파라미터 컬럼명 리스트 반환."""
        if pol_type == 3:
            return [APC_Para]   # P3 단일 플래튼
        if pol_type == 13:
            return [APC_Para]
        return [APC_Para]


    def PadParaGet(APC_Para):
        """APC 파라미터에 대응하는 PAD 소모품 컬럼명 반환."""
        mapping = {
            'P1': 'AMAT_PAD_1',
            'P2': 'AMAT_PAD_2',
            'P3': 'AMAT_PAD_3',
        }
        return mapping.get(APC_Para, 'AMAT_PAD_3')


    def HeadParaGet(APC_Para):
        """APC 파라미터에 대응하는 HEAD 소모품 컬럼명 반환."""
        mapping = {
            'P1': 'AMAT_HEAD_1',
            'P2': 'AMAT_HEAD_2',
            'P3': 'AMAT_HEAD_1',
        }
        return mapping.get(APC_Para, 'AMAT_HEAD_1')


    def DiskParaGet(APC_Para):
        """APC 파라미터에 대응하는 DISK 소모품 컬럼명 반환."""
        mapping = {
            'P1': 'AMAT_DISK_1',
            'P2': 'AMAT_DISK_2',
            'P3': 'AMAT_DISK_3',
        }
        return mapping.get(APC_Para, 'AMAT_DISK_3')


    # ── [TEST 삭제] EQPMGetData_HUB ─────────────────────────────────────
    # 고정 더미 이벤트 로그를 반환하는 테스트 전용 구현.
    # 회사 실서버에서는 MES HUB API 실제 호출 함수로 교체.
    def EQPMGetData_HUB(Fab, eqp_id_list, recipe_id_list):
        """
        CSV 데이터 기반으로 장비별 PM/EndLot 이벤트 로그를 구성하여 반환.
        실제 환경에서는 MES HUB API 호출로 대체.
        """
        now = datetime.now()
        events = []
        for eqp_id in eqp_id_list:
            # 마지막 PM 이후 10건 EndLot (rank 재계산 기준)
            events.append({
                'EQP_ID'  : eqp_id,
                'EVENT_TM': now - timedelta(days=30),
                'EVENT_CD': 'PadPM',
            })
            for j in range(10):
                events.append({
                    'EQP_ID'  : eqp_id,
                    'EVENT_TM': now - timedelta(days=29) + timedelta(hours=j),
                    'EVENT_CD': 'EndLot',
                })
        return pd.DataFrame(events)
    # ── [TEST 삭제 끝] ────────────────────────────────────────────────────

    # ── [TEST 삭제] Cube 메시지 Mock ─────────────────────────────────────
    # print 로 대체한 테스트 전용 구현.
    # 회사 실서버에서는 day.auth.sdk / day.commc.cube 를 이용한 실제 메시지 발송 함수로 교체.
    def Cube_Msg(lot, oper, module, e, tb):
        print(f'  [Cube] {lot}/{oper}/{module} 오류: {e}')

    def Cube_Alarm_Msg(channel_id, message):
        print(f'  [Cube Alarm] ch={channel_id}: {message}')

    def Cube_Msg_RR_Alarm(EQ, rcp_id, message):
        print(f'  [Cube RR Alarm] {EQ}/{rcp_id}: {message}')
    # ── [TEST 삭제 끝] ────────────────────────────────────────────────────
