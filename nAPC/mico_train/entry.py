"""학습 진입점 — payload(Set-up) 를 받아 키마다 merge_df 를 만들고 학습을 돌린다.

`Common/Module.py` 의 `run(family, oper_desc)` 가 하던 일을 nAPC 용으로 다시 세운 것.
바뀐 것은 두 군데뿐이고, 나머지 순서(키 생성 → 그룹 분기 → oper/recipe 필터 →
파이프라인)는 원본과 같게 유지했다.

    Set-up   : Django DB 직접 조회   ->  payload 로 받는다   (setup_payload.py)
    merge_df : MongoDB 조회          ->  DataLake+DataHub    (data_source.py)

학습 본체(`_run_pipeline`)는 그대로 쓴다. 다만 `Common.Module` 은 import 만 해도
Django 를 부르므로(`Get_Data.py` 가 module 레벨에서 `django.setup()`),
**미리 import 하지 않고 실행 시점에 붙인다.** 학습기를 직접 넣을 수도 있다
(`set_trainer`) — 테스트와 단계적 이관에 쓴다.
"""

import traceback

import pandas as pd

from . import data_source
from .result_collector import ResultCollector
from .setup_payload import to_info_table

_trainer = None


def set_trainer(fn):
    """학습 함수를 지정한다.  fn(merge_df_rcp, merge_df_vm, info_key, use_group_rr)"""
    global _trainer
    _trainer = fn


def get_trainer():
    if _trainer is not None:
        return _trainer
    # 사내 서버: 기존 학습 파이프라인을 그대로 쓴다 (Django 필요)
    from Common.Module import _run_pipeline
    return lambda rcp, vm, key, use_group_rr=False: _run_pipeline(rcp, vm, key, use_group_rr)


# ── 메인 ──────────────────────────────────────────────────────────────────

def run_training(payload, provider=None, days=None, exclude_process_ids=None,
                 trainer=None, dry_run=False,
                 collect_results=True, max_rows=None, keep_mongo=True):
    """payload 하나를 학습한다.

    Args:
        payload        : build_payload() 결과 (Set-up 전체)
        provider       : DataLake/DataHub 조회 객체 (없으면 data_source 기본 경로)
        days           : DataLake 조회 기간. 없으면 payload['days']
        dry_run        : 데이터만 모으고 학습은 돌리지 않는다 (데이터 경로 점검용)
        collect_results: 학습값을 응답에 실어 돌려준다 (기본 True)
        max_rows       : 컬렉션마다 응답에 실을 최대 건수. None 이면 전부.
                         잘려도 `counts` 로 원래 건수는 알 수 있다
        keep_mongo     : True 면 기존대로 MongoDB 에도 적재하고 응답에도 싣는다.
                         False 면 적재 없이 응답으로만 돌려준다
                         (주의: Offset 이 RR 결과를 되읽는 경로가 막힌다)

    Returns:
        키마다 무슨 일이 있었는지 담은 리스트. 한 키가 실패해도 나머지는 계속한다.
        collect_results 면 각 항목에 `results`(컬렉션별 학습값)와 `counts` 가 붙는다.
    """
    info_table = to_info_table(payload)
    days       = days if days is not None else payload.get('days', 30)
    trainer    = trainer or (None if dry_run else get_trainer())

    print(f'{"#" * 60}')
    print(f'  MICO 학습 시작: Family={payload["family"]} | '
          f'Oper_Desc={payload["oper_desc"]} | Set-up {len(info_table)}행')
    print(f'  merge_df 소스: DataLake({days}일) + DataHub  (MongoDB 미사용)')
    print(f'{"#" * 60}')

    collect = collect_results and not dry_run
    opts = {'collect': collect, 'max_rows': max_rows, 'keep_mongo': keep_mongo}

    results = []
    for group_name in info_table['Group_Name'].unique():
        keys = info_table[info_table['Group_Name'] == group_name]['for_key_list'].unique()
        if group_name == 'not_group':
            results += _run_single(info_table, keys, days, provider,
                                   exclude_process_ids, trainer, dry_run, opts)
        else:
            results.append(_run_grouped(info_table, group_name, days, provider,
                                        exclude_process_ids, trainer, dry_run, opts))

    ok = sum(1 for r in results if r['status'] == 'trained')
    print(f'\n{"#" * 60}')
    print(f'  학습 완료: {ok}/{len(results)} 키')
    if collect:
        total = sum(sum(r.get('counts', {}).values()) for r in results)
        print(f'  학습값 {total}건을 응답에 실음')
    print(f'{"#" * 60}')
    return results


def _run_single(info_table, keys, days, provider, exclude, trainer, dry_run, opts):
    """그룹 미지정: 키마다 독립적으로 merge_df 를 만들어 학습한다."""
    out = []
    for idx, key in enumerate(keys, 1):
        info_key = info_table[
            (info_table['for_key_list'] == key) &
            (info_table['Group_Name']   == 'not_group')
        ].copy()
        if info_key.empty:
            continue

        print(f'\n[{idx}/{len(keys)}] {key}')
        out.append(_one_key(key, info_key, info_key['Recipe_ID'].dropna().unique(),
                            days, provider, exclude, trainer, dry_run, opts,
                            label='단독', use_group_rr=False))
    return out


def _run_grouped(info_table, group_name, days, provider, exclude, trainer, dry_run, opts):
    """그룹 지정: 그룹의 모든 키 데이터를 합친 뒤 키마다 같은 merge_df 로 학습한다."""
    rows = info_table[info_table['Group_Name'] == group_name]
    keys = rows['for_key_list'].unique()
    # 필터 기준은 개별 키가 아니라 **그룹 전체 recipe** 다
    group_recipes = rows['Recipe_ID'].dropna().unique()

    print(f'\n[그룹: {group_name}] 키 {len(keys)}개 통합')

    info_keys  = []
    merge_dfs  = []
    for key in keys:
        info_key = info_table[
            (info_table['for_key_list'] == key) &
            (info_table['Group_Name']   == group_name)
        ].copy()
        if info_key.empty:
            continue
        info_keys.append(info_key)

        df = _fetch(info_key, days, provider, exclude, key)
        if df is not None and not df.empty:
            df['Fab'] = info_key['Fab'].dropna().unique()[0]
            merge_dfs.append(df)

    if not merge_dfs:
        print('  -> 그룹 통합 데이터 없음, 스킵')
        return {'key': group_name, 'status': 'no_data', 'rows': 0}

    merge_df_vm = pd.concat(merge_dfs, ignore_index=True)

    # oper 필터: 그룹 안에서도 키마다 Oper_Code 가 다를 수 있어 그룹 전체 집합으로 거른다
    oper_codes  = rows['Oper_Code'].dropna().unique()
    merge_df_vm = _filter_oper(merge_df_vm, oper_codes)
    if merge_df_vm.empty:
        print('  -> Oper 필터 후 0행, 스킵')
        return {'key': group_name, 'status': 'no_data', 'rows': 0}

    merge_df_rcp = _filter_recipes(merge_df_vm, group_recipes, f'그룹 {group_name}')
    if merge_df_rcp.empty:
        print('  -> recipe 필터 후 0행, 스킵')
        return {'key': group_name, 'status': 'no_data', 'rows': 0}
    merge_df_rcp['Group_Name'] = group_name

    print(f'  그룹 통합 완료: {len(merge_df_rcp)}행')
    if dry_run:
        return {'key': group_name, 'status': 'dry_run', 'rows': len(merge_df_rcp)}

    out = {'key': group_name, 'status': 'trained', 'rows': len(merge_df_rcp)}
    with _collector(opts) as rc:
        for info_key in info_keys:
            _train(trainer, merge_df_rcp, merge_df_vm, info_key, True, group_name)
    _attach(out, rc, opts)
    return out


def _one_key(key, info_key, recipes, days, provider, exclude, trainer, dry_run, opts,
             label, use_group_rr):
    # merge_df_vm : recipe 필터 전(= 이 Lot_Code 전체) -> Pre_Thk_VM 용
    merge_df_vm = _fetch(info_key, days, provider, exclude, key)
    if merge_df_vm is None or merge_df_vm.empty:
        print('    -> 조회 데이터 없음, 스킵')
        return {'key': key, 'status': 'no_data', 'rows': 0}

    # for_key_list 를 되쪼개면 Oper_Code 에 '_' 가 있을 때 잘못 나뉘므로 원본 컬럼에서 읽는다
    oper_codes  = info_key['Oper_Code'].dropna().unique()
    merge_df_vm = _filter_oper(merge_df_vm, oper_codes)
    print(f'    Oper 필터 후: {len(merge_df_vm)}행')
    if merge_df_vm.empty:
        return {'key': key, 'status': 'no_data', 'rows': 0}

    # merge_df_rcp : 학습 대상 recipe 로 좁힌 것 -> RR / Offset 용
    merge_df_rcp = _filter_recipes(merge_df_vm, recipes, label)
    if merge_df_rcp.empty:
        return {'key': key, 'status': 'no_data', 'rows': 0}

    if dry_run:
        return {'key': key, 'status': 'dry_run', 'rows': len(merge_df_rcp)}

    with _collector(opts) as rc:
        ok = _train(trainer, merge_df_rcp, merge_df_vm, info_key, use_group_rr, key)
    out = {'key': key, 'status': 'trained' if ok else 'failed', 'rows': len(merge_df_rcp)}
    _attach(out, rc, opts)
    return out


def _collector(opts):
    """학습값을 모을 수집기. collect=False 면 아무것도 안 하는 것으로 대체한다."""
    if not opts.get('collect'):
        return _NullCollector()
    return ResultCollector(delegate=opts.get('keep_mongo', True))


class _NullCollector:
    def __enter__(self): return self
    def __exit__(self, *e): return False
    def results(self, max_rows=None): return {}
    def counts(self): return {}
    def is_empty(self): return True


def _attach(out, rc, opts):
    """학습 결과를 반환 dict 에 붙인다."""
    if not opts.get('collect'):
        return
    out['results'] = rc.results(max_rows=opts.get('max_rows'))
    out['counts']  = rc.counts()
    if out['counts']:
        summary = ', '.join(f'{k.split("_")[1]}={v}' for k, v in out['counts'].items())
        print(f'    학습값: {summary}')


def _fetch(info_key, days, provider, exclude, key):
    """이 키의 merge_df 를 DataLake+DataHub 에서 만든다. 실패해도 다른 키는 계속."""
    print(f'    [데이터] DataLake({days}일) + DataHub 조회', end=' ... ', flush=True)
    try:
        df = data_source.fetch_merge_df(info_key, days=days, provider=provider,
                                        exclude_process_ids=exclude)
        print(f'{len(df)}행')
        return df
    except Exception as e:
        print('실패')
        print(f'      {type(e).__name__}: {e}')
        return None


def _filter_oper(df, oper_codes):
    if 'operation_id' not in df.columns or len(oper_codes) == 0:
        return df
    return df[df['operation_id'].isin(list(oper_codes))].copy()


def _filter_recipes(df, recipes, label):
    if 'recipe_id' not in df.columns or len(recipes) == 0:
        return df
    out = df[df['recipe_id'].isin(list(recipes))].copy()
    print(f'    recipe 필터({label}) 후: {len(out)}행')
    return out


def _train(trainer, merge_df_rcp, merge_df_vm, info_key, use_group_rr, key):
    try:
        trainer(merge_df_rcp, merge_df_vm, info_key, use_group_rr)
        return True
    except Exception as e:
        print(f'    학습 실패 [{key}] {type(e).__name__}: {e}')
        print(traceback.format_exc())
        return False
