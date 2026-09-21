"""사내 시스템 없이 전체 경로를 돌려 본다.  python3 -m nAPC.mico_train.selftest

Django 도 MongoDB 도 없는 환경(= 컨테이너와 같은 조건)에서
payload -> info_table -> DataLake+DataHub -> merge_df -> 학습 호출까지 확인한다.

검사 항목
  1. INFO_COLUMNS 가 Get_Data.baseinfoGetData 의 컬럼과 같은가 (소스를 읽어 대조)
  2. payload -> info_table 이 제대로 서는가 (for_key_list / Group_Name 포함)
  3. DataLake + DataHub 합치기 — 겹치는 substrate_id 는 HUB 가 이긴다
  4. prepare() 가 Merge_Data._prepare_merge_df 와 같은 결과를 내는가
  5. 단독 / 그룹 두 경로가 학습기까지 도달하는가
  6. 조회 함수가 비어 있을 때(None) 알아볼 수 있는 에러가 나는가
"""

import io
import os
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[2]))

from nAPC.mico_train import data_source, entry
from nAPC.mico_train.result_collector import ResultCollector, _json_safe
from nAPC.mico_train.setup_payload import INFO_COLUMNS, SCHEMA_VERSION, to_info_table

_ALGO = Path(__file__).parents[2] / 'algorithm_new'
_OK   = []


def check(name, cond, detail=''):
    _OK.append(bool(cond))
    print(f'  [{"OK" if cond else "실패"}] {name}' + (f'  {detail}' if detail else ''))


# ── 가짜 Set-up / 데이터 ───────────────────────────────────────────────────

def make_payload():
    def row(device, recipe, oper, group=None, fab='M10'):
        r = {c: '' for c in INFO_COLUMNS}
        r.update({
            'Family': 'DRAM', 'Lot_Code': device, 'Product': 'LC',
            'Oper_Code': oper, 'Oper_Desc': 'M1 CU CMP', 'Channel_ID': '500019173',
            'Fab': fab, 'Maker': 'EBARA', 'Recipe_ID': recipe,
            'APC_Para': 'P3', 'Thk_Para': 'THK', 'Target': 1000,
            'Post_Target': 1000, 'Pre_Target': 2000, 'Pre_Thk_Period': 3,
            'RR_Para': '', 'Offset_Group': 'A', 'RR_Para_Max': 120,
            'RR_Period': 7, 'Pad_Seperation': 1, 'Pre_Thk_Para_ITM': '',
            'Pre_Thk_VM_Source': 'AUTO', 'RR_Weight': 1, 'RR_Count': 10,
            'FB_Type': 'TIME', 'RR_Alarm_Sigma': 10, 'Pol_Type': 3,
            'Group_Name': group,
        })
        return r

    return {
        'schema_version': SCHEMA_VERSION,
        'family': 'DRAM', 'oper_desc': 'M1 CU CMP', 'days': 30,
        'rows': [
            row('E2', 'E2_M1CU_R12_AB.CAS', 'V5077000E'),                  # 단독
            row('NA', 'NA_M1CU_R01_AB.CAS', 'V5077000E', group='G1#7'),    # 그룹
            row('AG', 'AG_M1CU_R02_CD.CAS', 'V5077000E', group='G1#7'),    # 그룹
        ],
    }


def _rows(n, device, recipe, oper, start_id=0):
    return pd.DataFrame({
        'substrate_id': [f'{device}_W{start_id + i}' for i in range(n)],
        'request_dtts': pd.date_range('2026-09-01', periods=n, freq='h'),
        'eqp_id'      : [f'EQ{i % 2 + 1}' for i in range(n)],
        'recipe_id'   : recipe,
        'operation_id': oper,
        'lot_id'      : [f'LOT{i}' for i in range(n)],
        'process_id'  : ['ROUTE_A' if i % 5 else 'ROUTE_X' for i in range(n)],
        'THK'         : [1000 + i for i in range(n)],
    })


class FakeProvider:
    """사내 조회 함수 자리. lake 는 과거, hub 는 최신 + lake 와 2건 겹치게 만든다."""
    calls = []

    @staticmethod
    def getdatalake(Fab, Maker, Lot_Code, Oper_Code, Pre_Oper_Code,
                    Recipe_ID_List, Recipe_info, Days):
        FakeProvider.calls.append(('lake', Lot_Code, Recipe_info, Days))
        return _rows(10, Lot_Code, Recipe_ID_List[0], Oper_Code, start_id=0)

    @staticmethod
    def getdatahub(Fab, Maker, Lot_Code, Oper_Code, Pre_Oper_Code,
                   Recipe_ID_List, Recipe_info, Oper_Desc):
        FakeProvider.calls.append(('hub', Lot_Code, Recipe_info, Oper_Desc))
        df = _rows(4, Lot_Code, Recipe_ID_List[0], Oper_Code, start_id=8)  # 8,9 겹침
        df['THK'] = 9999                                                   # HUB 가 이겨야 함
        return df


# ── 검사 ───────────────────────────────────────────────────────────────────

def test_columns_match_source():
    src  = io.open(_ALGO / 'Common' / 'Get_Data.py', encoding='utf-8').read()
    body = src[src.index('rows.append({'):src.index('df = pd.DataFrame(rows)')]
    cols = re.findall(r"'([A-Za-z_0-9]+)'\s*:", body)
    check('INFO_COLUMNS == baseinfoGetData 컬럼', cols == INFO_COLUMNS,
          f'{len(cols)}개' if cols == INFO_COLUMNS else f'\n      소스:{cols}\n      여기:{INFO_COLUMNS}')


def test_info_table():
    df = to_info_table(make_payload())
    check('info_table 행 수', len(df) == 3, f'{len(df)}행')
    check('for_key_list 생성', 'E2_V5077000E_M10' in set(df['for_key_list']))
    check('Group_Name fillna', (df['Group_Name'] == 'not_group').sum() == 1)
    check('컬럼 순서 유지', list(df.columns)[:len(INFO_COLUMNS)] == INFO_COLUMNS)


def test_combine_hub_wins():
    lake = _rows(10, 'E2', 'R', 'OP', start_id=0)
    hub  = _rows(4, 'E2', 'R', 'OP', start_id=8)
    hub['THK'] = 9999
    out = data_source.combine(lake, hub)
    check('lake10 + hub4 중복2 -> 12행', len(out) == 12, f'{len(out)}행')
    dup = out[out['substrate_id'] == 'E2_W8']
    check('겹치는 substrate_id 는 HUB 가 이긴다', dup['THK'].iloc[0] == 9999,
          f'THK={dup["THK"].iloc[0]}')


def test_prepare_matches_merge_data():
    """prepare() 가 Merge_Data._prepare_merge_df 와 같은 결과인지 대조.

    Merge_Data 는 pymongo/Django 를 끌고 들어와 그냥은 import 가 안 되므로
    소스에서 두 함수만 떼어내 실행한다.
    """
    src = io.open(_ALGO / 'Common' / 'Merge_Data.py', encoding='utf-8').read()
    part = src[src.index('def _set_eqp_ch'):src.index('def _push_with_index')]
    ns = {'pd': pd, 'np': __import__('numpy')}
    exec(part, ns)

    df = _rows(6, 'E2', 'E2_M1CU_R12_AB.CAS', 'OP')
    a = ns['_prepare_merge_df'](df.copy(), 'LC', 'M1 CU CMP', 'M10', 'E2', 'EBARA', ['ROUTE_X'])
    b = data_source.prepare(df.copy(), Product='LC', Oper_Desc='M1 CU CMP',
                            Fab='M10', Lot_Code='E2', Maker='EBARA',
                            exclude_process_ids=['ROUTE_X'])
    same = a.reset_index(drop=True).equals(b.reset_index(drop=True))
    check('prepare() == Merge_Data._prepare_merge_df', same,
          '' if same else f'\n      a:{list(a.columns)}\n      b:{list(b.columns)}')
    check('route 제외 적용', 'ROUTE_X' not in set(b['process_id']))


def test_end_to_end():
    FakeProvider.calls.clear()
    seen = []
    entry.set_trainer(lambda rcp, vm, key, use_group_rr=False: seen.append({
        'lot': list(key['Lot_Code'].unique()), 'rcp': len(rcp), 'vm': len(vm),
        'group': use_group_rr,
    }))
    res = entry.run_training(make_payload(), provider=FakeProvider)

    check('조회가 키마다 lake+hub 둘 다 호출', 
          sum(1 for c in FakeProvider.calls if c[0] == 'lake') == 3 and
          sum(1 for c in FakeProvider.calls if c[0] == 'hub') == 3,
          f'{len(FakeProvider.calls)}회')
    check('Recipe_info 앞 두 토큰', FakeProvider.calls[0][2] == 'E2_M1CU',
          FakeProvider.calls[0][2])
    check('단독 1건 + 그룹 1건 = 결과 2건', len(res) == 2, str([r['key'] for r in res]))
    check('전부 학습됨', all(r['status'] == 'trained' for r in res), str(res))
    check('학습기 호출 3회 (단독1 + 그룹2)', len(seen) == 3, f'{len(seen)}회')
    grouped = [s for s in seen if s['group']]
    check('그룹 경로는 use_group_rr=True', len(grouped) == 2, f'{len(grouped)}건')
    check('그룹은 두 Lot_Code 데이터가 합쳐짐', grouped and grouped[0]['vm'] > grouped[0]['rcp'] or
          (grouped and grouped[0]['rcp'] >= 24), f"rcp={grouped[0]['rcp']} vm={grouped[0]['vm']}")


def test_empty_provider_message():
    class Empty:
        @staticmethod
        def getdatalake(*a): return None      # 사내 코드 미입력 상태(스텁)
        @staticmethod
        def getdatahub(*a): return None
    entry.set_trainer(lambda *a, **k: None)
    res = entry.run_training(make_payload(), provider=Empty)
    check('조회 함수가 비어 있으면 no_data 로 떨어지고 죽지 않는다',
          all(r['status'] == 'no_data' for r in res), str([r['status'] for r in res]))


def test_dry_run():
    entry.set_trainer(lambda *a, **k: (_ for _ in ()).throw(AssertionError('dry_run 인데 학습기 호출됨')))
    res = entry.run_training(make_payload(), provider=FakeProvider, dry_run=True)
    check('dry_run 은 데이터만 모으고 학습을 안 부른다',
          all(r['status'] == 'dry_run' for r in res), str([r['status'] for r in res]))
    check('dry_run 도 행 수를 센다', all(r['rows'] > 0 for r in res),
          str([r['rows'] for r in res]))


def test_result_collector():
    """수집기가 mongodb_controller 를 갈아 끼워 기록하고, 끝나면 되돌리는지."""
    import sys as _sys
    import types

    # 가짜 학습 모듈 두 개를 만들어 Common.Module / Common.OFFSET 자리에 놓는다
    written = []

    class FakeController:
        def __init__(self, url, db, coll): self.coll = coll
        def insert_row(self, row):  written.append(('inner', self.coll, row))
        def push_df(self, df):      written.append(('inner', self.coll, len(df)))
        def count_row(self):        return 7

    made = {}
    for name in ('Common.Module', 'Common.OFFSET'):
        mod = types.ModuleType(name)
        mod.mongodb_controller = FakeController
        _sys.modules[name] = mod
        made[name] = mod

    with ResultCollector() as rc:
        m = made['Common.Module'].mongodb_controller('u', 'd', 'MICO_Removal_Rate_X')
        m.insert_row({'EQ': 'KCMP41', 'b1': 0.5})
        check('위임도 된다 (원본 controller 에 전달)', written and written[0][0] == 'inner')
        check('위임 안 가로챈 메서드도 동작', m.count_row() == 7)
        o = made['Common.OFFSET'].mongodb_controller('u', 'd', 'MICO_OFFSET_X')
        o.push_df(pd.DataFrame([{'eqp_id': 'KCMP41', 'OFFSET': 0.0}]))

    res = rc.results()
    check('두 컬렉션 모두 기록', set(res) == {'MICO_Removal_Rate_X', 'MICO_OFFSET_X'}, str(list(res)))
    check('insert_row 기록', res['MICO_Removal_Rate_X'][0]['EQ'] == 'KCMP41')
    check('push_df 기록', res['MICO_OFFSET_X'][0]['OFFSET'] == 0.0)
    check('counts', rc.counts() == {'MICO_Removal_Rate_X': 1, 'MICO_OFFSET_X': 1}, str(rc.counts()))
    check('빠져나오면 원래 controller 로 복구',
          made['Common.Module'].mongodb_controller is FakeController)

    # delegate=False 면 원본에 안 넘긴다
    written.clear()
    with ResultCollector(delegate=False) as rc2:
        made['Common.Module'].mongodb_controller('u', 'd', 'C').insert_row({'a': 1})
    check('delegate=False 면 Mongo 에 안 쓴다', written == [] and rc2.counts() == {'C': 1})

    for name in made:
        _sys.modules.pop(name, None)


def test_json_safe():
    import numpy as np
    row = _json_safe({
        'ts': pd.Timestamp('2026-09-21 08:00:00'),
        'np_f': np.float64(1.5), 'np_i': np.int64(3),
        'nan': float('nan'), 'inf': float('inf'),
        'txt': 'E2', 'none': None,
    })
    import json
    check('Timestamp -> ISO 문자열', row['ts'].startswith('2026-09-21T'), row['ts'])
    check('numpy 스칼라 -> 파이썬 수', row['np_f'] == 1.5 and row['np_i'] == 3)
    check('NaN/Inf -> None (JSON 표준)', row['nan'] is None and row['inf'] is None)
    check('json.dumps 가능', json.dumps(row) and True)


def test_results_in_response():
    """run_training 반환에 학습값이 실리는지 — 학습기가 쓴 것을 그대로 받아야 한다."""
    import sys as _sys, types
    written = []

    class FakeController:
        def __init__(self, url, db, coll): self.coll = coll
        def insert_row(self, row): written.append(row)
        def push_df(self, df): pass

    mod = types.ModuleType('Common.Module')
    mod.mongodb_controller = FakeController
    _sys.modules['Common.Module'] = mod

    def fake_trainer(rcp, vm, key, use_group_rr=False):
        lot = key['Lot_Code'].unique()[0]
        m = _sys.modules['Common.Module'].mongodb_controller('u', 'd', f'MICO_Removal_Rate_{lot}')
        m.insert_row({'EQ': 'KCMP41', 'b1': 0.5, 'Lot_Code': lot})

    entry.set_trainer(fake_trainer)
    res = entry.run_training(make_payload(), provider=FakeProvider)

    single = [r for r in res if r['key'] == 'E2_V5077000E_M10'][0]
    check('반환에 results 가 붙는다', 'results' in single and single['results'], str(single.get('counts')))
    check('반환에 counts 가 붙는다', single['counts'] == {'MICO_Removal_Rate_E2': 1}, str(single['counts']))
    check('학습값 내용이 실린다',
          single['results']['MICO_Removal_Rate_E2'][0]['b1'] == 0.5)

    # max_rows 로 자르기
    res2 = entry.run_training(make_payload(), provider=FakeProvider, max_rows=0)
    g = [r for r in res2 if r['key'] == 'G1#7'][0]
    check('max_rows=0 이면 값은 비고 counts 는 남는다',
          all(v == [] for v in g['results'].values()) and sum(g['counts'].values()) == 2,
          f"results={g['results']} counts={g['counts']}")

    # 끄기
    res3 = entry.run_training(make_payload(), provider=FakeProvider, collect_results=False)
    check('collect_results=False 면 results 가 없다',
          all('results' not in r for r in res3))

    _sys.modules.pop('Common.Module', None)


if __name__ == '__main__':
    for fn in (test_columns_match_source, test_info_table, test_combine_hub_wins,
               test_prepare_matches_merge_data, test_end_to_end,
               test_empty_provider_message, test_dry_run,
               test_result_collector, test_json_safe, test_results_in_response):
        print(f'\n=== {fn.__name__} ===')
        try:
            fn()
        except Exception as e:
            import traceback
            _OK.append(False)
            print(f'  [실패] 예외: {type(e).__name__}: {e}')
            print(traceback.format_exc())

    print(f'\n{"=" * 60}')
    print(f'  {sum(_OK)}/{len(_OK)} 통과')
    print(f'{"=" * 60}')
    sys.exit(0 if all(_OK) else 1)
