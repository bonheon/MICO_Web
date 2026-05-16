"""
algorithm_new vs algorithm_source — Removal Rate 상세 비교
실행: python3 compare_rr.py  (MICO_Web/ 루트에서)
"""

import sys, io, contextlib
from pathlib import Path
from unittest.mock import MagicMock
import pandas as pd

REPO = Path(__file__).parent

results_new = {}   # (EQ, Recipe_ID) → report dict
results_src = {}

# ─────────────────────────────────────────────────────────
# 공통 캡처 헬퍼
# ─────────────────────────────────────────────────────────
FIELDS = ['Count', 'b1', 'b0', 'b1_weighted', 'b0_weighted',
          'b1_current', 'b0_current', 'if_b1', 'if_b0']

def _capture(store, report):
    key = (report.get('EQ', ''), report.get('Recipe_ID', ''))
    store[key] = {f: report.get(f, '-') for f in FIELDS}

# =========================================================
# 1. algorithm_NEW
# =========================================================
sys.path.insert(0, str(REPO / 'algorithm_new'))

import pymongo as _pymongo
_mock = MagicMock()
_mock.__getitem__.return_value = MagicMock()
_pymongo.MongoClient = MagicMock(return_value=_mock)

import Common.REMOVAL_RATE as _rr_new
import Common.OFFSET        as _offset_new
import Common.MongoDB_Control as _mdb_new

# load_pre_thk_data: Mock 없이 실제 함수 실행 (Excel 캐시 자동 사용)

# RR data Mock
def _rr_data_new(merge_df, Fab, Lot_Code, Oper_Desc, APC_Para_List, mongo_url, mongo_db):
    out = merge_df.copy()
    for p in APC_Para_List:
        out[f'{p}_B1'] = 0.80; out[f'{p}_B0'] = 5.00
    return out
_offset_new.OFFSET_Get.load_rr_data = staticmethod(_rr_data_new)

# mongodb_controller 패치
class _MongoNew:
    def __init__(self, *a, **kw): pass
    def insert_row(self, report): _capture(results_new, report)
    def push_df(self, *a, **kw): pass
_mdb_new.mongodb_controller = _MongoNew
# REMOVAL_RATE 모듈 내부에 이미 바인딩된 이름도 교체
_rr_new.mongodb_controller = _MongoNew

from Common.Module import run as _run_new

print("=" * 70)
print("  [algorithm_new] 실행 중...")
with contextlib.redirect_stdout(io.StringIO()):
    _run_new('DRAM', 'M1 CU CMP', 3)
print(f"  → RR 결과 {len(results_new)}건 캡처")

# =========================================================
# 2. algorithm_SOURCE
# =========================================================
for k in list(sys.modules.keys()):
    if k.startswith('Common') or k == 'Common':
        del sys.modules[k]
# _new 경로는 제거
if str(REPO / 'algorithm_new') in sys.path:
    sys.path.remove(str(REPO / 'algorithm_new'))

sys.path.insert(0, str(REPO / 'algorithm_source'))

import Common.REMOVAL_RATE as _rr_src
import Common.OFFSET        as _offset_src
import Common.MongoDB_Control as _mdb_src

def _removal_src(merge_df, fab, lot_code, oper_code, pre_oper_code,
                  recipe_id, oper_desc, recipe_info, mico_info_key, ai_studio_url=None):
    cache_file = REPO / 'algorithm_source' / 'pre_thk_cache' / f'{lot_code}_{oper_desc.replace(" ", "_")}_{fab}.xlsx'
    out = merge_df.copy()
    out.rename(columns={'pre_oper_time': 'Pre_Oper_Date', 'request_dtts': 'Date'}, inplace=True)
    out['Pre_Oper_Date'] = pd.to_datetime(out['Pre_Oper_Date'], errors='coerce')
    out.dropna(subset=['Pre_Oper_Date'], inplace=True)
    out = out.sort_values(by='Pre_Oper_Date', ascending=True)
    if cache_file.exists():
        tbl = pd.read_excel(cache_file, parse_dates=['pre_oper_time'])
        tbl.rename(columns={'pre_oper_time': 'Pre_Oper_Date'}, inplace=True)
        tbl['Pre_Oper_Date'] = pd.to_datetime(tbl['Pre_Oper_Date'])
        for thk_key in tbl['THK_Para'].unique():
            tmp = tbl[tbl['THK_Para'] == thk_key].drop(
                columns=[c for c in ['Date', 'THK_Para', 'Oper_Code'] if c in tbl.columns])
            tmp = tmp.sort_values(by='Pre_Oper_Date', ascending=True)
            tmp = tmp.rename(columns={'Pre_Thk': thk_key + '_VM', 'Count': thk_key + '_Count'})
            out = out.drop(columns=[c for c in out.columns if c.endswith('_x') or c.endswith('_y')])
            out = pd.merge_asof(out, tmp, on='Pre_Oper_Date', by=['pre_eq_ch'])
            out.drop_duplicates(subset=['substrate_id'], inplace=True)
    else:
        for k in mico_info_key['Thk_Para'].unique():
            out[f'{k}_VM'] = 0.0
    return out
_rr_src.Removal_Rate_Get.Removal_getdata = staticmethod(_removal_src)

def _offset_src_fn(merge_df, Family, Fab, Lot_Code, Oper_Desc, APC_Para_List):
    out = merge_df.copy()
    for p in APC_Para_List:
        out[f'{p}_B1'] = 0.80; out[f'{p}_B0'] = 5.00
    return out
_offset_src.OFFSET_Get.Offset_getdata = staticmethod(_offset_src_fn)
_offset_src.OFFSET_Get.offset_getdata  = staticmethod(_offset_src_fn)

class _MongoSrc:
    def __init__(self, *a, **kw): pass
    def insert_row(self, report): _capture(results_src, report)
    def push_df(self, *a, **kw): pass
_mdb_src.mongodb_controller = _MongoSrc
# REMOVAL_RATE 내부 바인딩 교체
_rr_src.mongodb_controller = _MongoSrc

import Common.Module as _src_module_mod
from Common.Get_Data import Get_data as _gd_src
from Common.Module  import Module_Get as _mod_src

# mongodb_controller 를 Module.py 내부에서 사용하는 것도 패치
_src_module_mod.mongodb_controller = _MongoSrc

print("\n  [algorithm_source] 실행 중...")

mico_info = _gd_src.baseinfoGetData(Family='DRAM', oper_desc='M1 CU CMP')
mico_info['Group_Name']   = mico_info['Group_Name'].fillna('not_group')
mico_info['for_key_list'] = (mico_info['Lot_Code'] + '_' +
                              mico_info['Oper_Code'] + '_' + mico_info['Fab'])

with contextlib.redirect_stdout(io.StringIO()):
    for grp in mico_info['Group_Name'].unique():
        key_list = mico_info[mico_info['Group_Name'] == grp]['for_key_list'].unique()

        if grp == 'not_group':
            for key in key_list:
                lc, oc, fab = key.split('_')
                mik = mico_info[mico_info['for_key_list'] == key].copy()
                df  = _gd_src.MongoDB_GetData('DRAM', fab, lc, 'M1 CU CMP')
                df  = df[df['operation_id'] == oc].copy()
                try: _mod_src.Module_Get_Pre_VM(lc, 'M1 CU CMP', df, fab, 3, mik)
                except: pass
                try: _mod_src.Module_Get_RR(df, lc, 'M1 CU CMP', 3, fab, mik)
                except: pass
        else:
            merged = pd.DataFrame()
            infos  = []
            for key in key_list:
                lc, oc, fab = key.split('_')
                mik = mico_info[mico_info['for_key_list'] == key].copy()
                infos.append({'lc': lc, 'oc': oc, 'fab': fab, 'mik': mik})
                tmp = _gd_src.MongoDB_GetData(mik['Family'].unique()[0], fab, lc, grp)
                if tmp is not None and not tmp.empty:
                    merged = pd.concat([merged, tmp])
            merged['Group_Name'] = grp
            for info in infos:
                try: _mod_src.Module_Get_Pre_VM(info['lc'], 'M1 CU CMP', merged, info['fab'], 3, info['mik'])
                except: pass
                try: _mod_src.Module_Get_RR_Group(merged, info['lc'], 'M1 CU CMP', 3, info['fab'], info['mik'])
                except: pass

print(f"  → RR 결과 {len(results_src)}건 캡처")

# =========================================================
# 3. 비교 출력
# =========================================================
all_keys = sorted(set(results_new) | set(results_src))

print("\n" + "=" * 90)
print("  REMOVAL RATE 비교  (algorithm_new  vs  algorithm_source)")
print("=" * 90)

any_diff = False
for k in all_keys:
    eq, rcp = k
    n = results_new.get(k, {f: '(없음)' for f in FIELDS})
    s = results_src.get(k, {f: '(없음)' for f in FIELDS})
    diffs = [f for f in FIELDS if str(n.get(f, '-')) != str(s.get(f, '-'))]
    if diffs:
        any_diff = True

    print(f"\n  EQ={eq}  |  Recipe={rcp}")
    print(f"  {'항목':<14} {'_new':>14}  {'_source':>14}  {'비고'}")
    print(f"  {'-'*60}")
    for f in FIELDS:
        nv  = str(n.get(f, '-'))
        sv  = str(s.get(f, '-'))
        mark = ' ◀ 불일치' if f in diffs else ''
        print(f"  {f:<14} {nv:>14}  {sv:>14}{mark}")

print("\n" + "=" * 90)
if any_diff:
    print("  ※ 불일치 항목 있음  (◀ 표시 확인)")
else:
    print("  ✓ 모든 항목 일치")
print("=" * 90)
