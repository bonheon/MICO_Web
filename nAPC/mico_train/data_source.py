"""merge_df 를 **DataLake + DataHub 에서 직접** 만든다. MongoDB 를 쓰지 않는다.

기존 HCP 구조는 두 단계였다:

    Merge_Hub : DataLake(과거 N일) + DataHub(최신) -> **MongoDB 적재**
    Module    : MongoDB 조회 -> merge_df -> 학습

nAPC 에서는 MongoDB 를 끼우지 않고 학습 시점에 두 소스를 직접 읽어 합친다:

    DataLake(과거 N일) + DataHub(최신) -> merge_df -> 학습

그래서 이 모듈에는 pymongo 가 없다. Django 도 없다 (컨테이너에 둘 다 없다).

## 사내 조회 함수 연결

실제 조회는 사내 함수 두 개가 한다. 시그니처는 `Common/Merge_Data.py` 의
`Merge_Get_data` 와 동일하게 맞췄다:

    getdatalake(Fab, Maker, Lot_Code, Oper_Code,
                Pre_Oper_Code, Recipe_ID_List, Recipe_info, Days)
    getdatahub (Fab, Maker, Lot_Code, Oper_Code,
                Pre_Oper_Code, Recipe_ID_List, Recipe_info, Oper_Desc)

연결 순서:
  1. `set_provider(obj)` 로 직접 넣은 것
  2. 없으면 `Common.Merge_Data.Merge_Get_data` (사내 서버에 알고리즘 트리가 있을 때)
  3. 그래도 없으면 명확한 에러

테스트는 `set_provider()` 에 가짜 provider 를 넣어 사내 시스템 없이 돌린다.
"""

import pandas as pd

_provider = None


# ── provider 연결 ─────────────────────────────────────────────────────────

def set_provider(provider):
    """DataLake/DataHub 조회 객체를 지정한다 (getdatalake / getdatahub 를 가진 것)."""
    global _provider
    for name in ('getdatalake', 'getdatahub'):
        if not hasattr(provider, name):
            raise ValueError(f'provider 에 {name} 이 없다')
    _provider = provider


def get_provider():
    if _provider is not None:
        return _provider
    try:
        from Common.Merge_Data import Merge_Get_data   # 사내 서버 경로
        return Merge_Get_data
    except Exception as e:
        raise RuntimeError(
            'DataLake/DataHub 조회 함수를 찾지 못했다.\n'
            '  - 사내 서버: algorithm_new 가 sys.path 에 있어야 한다\n'
            '  - 그 외    : set_provider(...) 로 직접 넣을 것\n'
            f'  (원인: {type(e).__name__}: {e})'
        )


# ── merge_df 조립 ─────────────────────────────────────────────────────────

def key_params(info_key):
    """mico_info_key(DataFrame) 에서 조회 인자를 뽑는다.

    Merge_Data.run 이 키마다 뽑던 것과 같은 값들이다.
    """
    def one(col):
        vals = info_key[col].dropna().unique()
        return vals[0] if len(vals) else None

    recipe_ids = tuple(info_key['Recipe_ID'].dropna().unique())
    return {
        'Fab'           : one('Fab'),
        'Maker'         : one('Maker'),
        'Lot_Code'      : one('Lot_Code'),
        'Product'       : one('Product'),
        'Oper_Code'     : one('Oper_Code'),
        'Oper_Desc'     : one('Oper_Desc'),
        'Pre_Oper_Code' : one('Pre_Oper_Code'),
        'Recipe_ID_List': recipe_ids,
        'Recipe_info'   : _recipe_info(recipe_ids),
    }


def _recipe_info(recipe_ids):
    """Recipe_ID 앞 두 토큰 (예: 'E2_M1CU_R12_TSV.CAS' -> 'E2_M1CU').

    Merge_Data.run 은 `split('_')[0] + '_' + split('_')[1]` 로 만든다. 그대로 하면
    '_' 가 없는 recipe_id 에서 IndexError 로 키 하나가 통째로 죽으므로 방어한다.
    """
    if not recipe_ids:
        return None
    parts = str(recipe_ids[0]).split('_')
    return '_'.join(parts[:2]) if len(parts) >= 2 else parts[0]


def fetch_merge_df(info_key, days=30, provider=None, exclude_process_ids=None):
    """DataLake(과거 days 일) + DataHub(최신) 를 읽어 merge_df 를 만든다.

    MongoDB 를 거치지 않는다. 반환은 학습이 바로 쓸 수 있는 형태
    (Date 컬럼, eqp_ch, Product/OPER_DESC/Fab/Lot_Code 채워짐).
    """
    p = provider or get_provider()
    k = key_params(info_key)

    lake = _call(p.getdatalake, 'getdatalake',
                 k['Fab'], k['Maker'], k['Lot_Code'], k['Oper_Code'],
                 k['Pre_Oper_Code'], k['Recipe_ID_List'], k['Recipe_info'], days)

    hub = _call(p.getdatahub, 'getdatahub',
                k['Fab'], k['Maker'], k['Lot_Code'], k['Oper_Code'],
                k['Pre_Oper_Code'], k['Recipe_ID_List'], k['Recipe_info'], k['Oper_Desc'])

    df = combine(lake, hub)
    if df.empty:
        return df

    return prepare(df, Product=k['Product'], Oper_Desc=k['Oper_Desc'],
                   Fab=k['Fab'], Lot_Code=k['Lot_Code'], Maker=k['Maker'],
                   exclude_process_ids=exclude_process_ids)


def _call(fn, name, *args):
    """조회 함수 호출. 미구현({TODO} 스텁)이면 None 을 돌려주므로 그 경우를 구분한다."""
    out = fn(*args)
    if out is None:
        raise RuntimeError(
            f'{name}() 가 None 을 반환했다 — 사내 조회 함수가 아직 비어 있다.\n'
            '  Common/Merge_Data.py 의 Merge_Get_data 에 본문을 채우거나\n'
            '  set_provider(...) 로 실제 구현을 넣을 것'
        )
    if not isinstance(out, pd.DataFrame):
        raise TypeError(f'{name}() 는 DataFrame 을 반환해야 한다 (받은 것: {type(out).__name__})')
    return out


def combine(lake_df, hub_df):
    """DataLake(과거) 와 DataHub(최신) 를 합친다.

    겹치는 구간이 있으므로 substrate_id 기준으로 **HUB 쪽을 남긴다**(최신이 정답).
    substrate_id 가 없으면 중복 제거 없이 이어 붙이기만 한다.
    """
    frames = [d for d in (lake_df, hub_df) if d is not None and not d.empty]
    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    if 'substrate_id' in df.columns:
        # concat 순서가 lake -> hub 라 뒤(hub)를 남기면 최신이 이긴다
        df = df.drop_duplicates(subset='substrate_id', keep='last')
    return df.reset_index(drop=True)


# ── 학습이 쓰는 형태로 정리 ───────────────────────────────────────────────
# Merge_Data._prepare_merge_df / _set_eqp_ch 와 같은 처리다. 저쪽은 pymongo 와
# Django(Get_Data) 를 끌고 들어와 컨테이너에서 import 가 안 되므로 여기 둔다.
# selftest.py 가 두 구현의 결과가 같은지 검사한다.

def set_eqp_ch(df, Maker):
    """장비 채널(eqp_ch) 설정 — web Set-up 의 Maker 기준, 대소문자 무시.

    EBARA : recipe_id 의 AB/CD        -> {eqp_id}_AB / {eqp_id}_CD
    KCT   : recipe_id 의 _L_/_R_ 또는 끝의 _L/_R -> {eqp_id}_L / {eqp_id}_R
            (L/R 표기가 없으면 채널 분리 없이 eqp_id 그대로)
    그 외 : eqp_id 그대로
    """
    maker = str(Maker).upper()
    if 'EBARA' in maker:
        df['CH']     = df['recipe_id'].apply(lambda x: 'AB' if 'AB' in str(x) else 'CD')
        df['eqp_ch'] = df['eqp_id'] + '_' + df['CH']
    elif 'KCT' in maker:
        def _kct_ch(x):
            x = str(x)
            if '_L_' in x or x.endswith('_L'):
                return 'L'
            if '_R_' in x or x.endswith('_R'):
                return 'R'
            return ''
        df['CH']     = df['recipe_id'].apply(_kct_ch)
        has_ch       = df['CH'] != ''
        df['eqp_ch'] = df['eqp_id']
        df.loc[has_ch, 'eqp_ch'] = df.loc[has_ch, 'eqp_id'] + '_' + df.loc[has_ch, 'CH']
    else:
        df['eqp_ch'] = df['eqp_id']
    return df


def prepare(df, Product, Oper_Desc, Fab, Lot_Code, Maker, exclude_process_ids=None):
    """merge_df 공통 정리 (Merge_Data._prepare_merge_df 와 동일)."""
    df = df.rename(columns={'request_dtts': 'Date'})

    # 적재 제외 route: 해당 process_id 행을 학습에서 뺀다
    if exclude_process_ids and 'process_id' in df.columns:
        before = len(df)
        df = df[~df['process_id'].isin(exclude_process_ids)].copy()
        dropped = before - len(df)
        if dropped:
            print(f'    [route 제외] process_id {sorted(exclude_process_ids)} 해당 {dropped}건 제외')

    df = df.sort_values(by='Date')
    df['Product']   = Product
    df['OPER_DESC'] = Oper_Desc
    df['Fab']       = Fab
    df['Lot_Code']  = Lot_Code
    df = set_eqp_ch(df, Maker)
    df = df.fillna('-')
    return df
