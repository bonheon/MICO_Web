"""web Set-up(SubCategory + Detail) 을 학습 컨테이너로 넘기는 형태로 직렬화한다.

기존 HCP 는 학습 코드가 `Get_data.baseinfoGetData()` 로 **Django DB 를 직접** 읽었다.
nAPC 컨테이너에는 Django 도 web DB 도 없다. 그래서 web 이 Set-up 을 통째로 직렬화해
넘기고, 컨테이너는 그걸 그대로 DataFrame 으로 세운다.

    [web]        build_payload(family, oper_desc)   -> payload(dict, JSON 안전)
    [컨테이너]    to_info_table(payload)             -> mico_info_table(DataFrame)

**핵심 규칙: payload 의 행은 알고리즘 컬럼명을 그대로 쓴다.**
그래야 컨테이너 쪽이 `pd.DataFrame(rows)` 한 줄이면 끝나고, 매핑이 한 곳
(`build_payload`)에만 있어 web 과 알고리즘이 어긋날 일이 없다.

컬럼 집합은 `Get_data.baseinfoGetData()` 와 **정확히 같아야** 한다. 하나라도 빠지면
하류(Module / REMOVAL_RATE / OFFSET / Simulation)가 KeyError 로 죽는다.
`selftest.py` 가 이 일치를 검사한다.

이 모듈은 Django 없이 import 된다 (Django 는 build_payload 안에서만 쓴다).
"""

import json

SCHEMA_VERSION = 1

# baseinfoGetData 가 만드는 컬럼 — 순서까지 동일하게 유지한다
INFO_COLUMNS = [
    'Family', 'Lot_Code', 'Product', 'Oper_Code', 'Oper_Desc', 'Channel_ID',
    'Fab', 'Maker', 'Recipe_ID',
    'APC_Para', 'Thk_Para', 'Target', 'Post_Target', 'Pre_Target',
    'Pre_Thk_Period', 'RR_Para', 'Offset_Group', 'RR_Para_Max', 'RR_Period',
    'Pad_Seperation', 'Pre_Thk_Para_ITM', 'Pre_Thk_VM_Source',
    'Pre_Oper_Code', 'Pre_Oper_Desc', 'Pre_Oper_Para',
    'Pre_Oper_Code2', 'Pre_Oper_Desc2', 'Pre_Oper_Para2',
    'Pre_Oper_Code3', 'Pre_Oper_Desc3', 'Pre_Oper_Para3',
    'Pre_Oper_Code4', 'Pre_Oper_Desc4', 'Pre_Oper_Para4',
    'RR_Weight', 'RR_Count', 'FB_Type', 'RR_Alarm_Sigma', 'Pol_Type',
    'Group_Name',
]


def _row_from_setup(cat, sub, det, group_name):
    """Category / SubCategory / Detail 한 조합 -> 알고리즘 행 하나.

    baseinfoGetData 의 rows.append({...}) 와 같은 매핑이다.
    여기만 고치면 web·컨테이너 양쪽에 동시에 반영된다.
    """
    return {
        'Family'           : cat.family,
        # 회사 스키마는 Product/Lot_Code 가 별도 컬럼이고 Lot_Code 가 하위 단위다.
        #   Product  = Category.product   (예: LC)
        #   Lot_Code = SubCategory.device (예: E2)  <- recipe_id 접두어와 일치
        'Lot_Code'         : sub.device,
        'Product'          : cat.product,
        'Oper_Code'        : cat.oper_id,
        'Oper_Desc'        : cat.oper_desc,
        'Channel_ID'       : cat.channel_id,
        'Fab'              : sub.fab,
        'Maker'            : sub.maker,
        'Recipe_ID'        : sub.recipe_id,
        'APC_Para'         : det.apc_para,
        'Thk_Para'         : det.thk_para,
        'Target'           : det.target,
        'Post_Target'      : det.target,     # source 코드 호환 alias
        'Pre_Target'       : det.pre_target,
        'Pre_Thk_Period'   : det.pre_thk_period,
        'RR_Para'          : det.rr_para,
        'Offset_Group'     : det.offset_group,
        'RR_Para_Max'      : det.rr_max,
        'RR_Period'        : det.rr_period,
        'Pad_Seperation'   : det.rr_if,
        'Pre_Thk_Para_ITM' : det.pre_thk_para_itm,
        'Pre_Thk_VM_Source': det.pre_thk_vm_source,
        'Pre_Oper_Code'    : det.pre_oper_code,
        'Pre_Oper_Desc'    : det.pre_oper_desc,
        'Pre_Oper_Para'    : det.pre_oper_para,
        'Pre_Oper_Code2'   : det.pre_oper_code2,
        'Pre_Oper_Desc2'   : det.pre_oper_desc2,
        'Pre_Oper_Para2'   : det.pre_oper_para2,
        'Pre_Oper_Code3'   : det.pre_oper_code3,
        'Pre_Oper_Desc3'   : det.pre_oper_desc3,
        'Pre_Oper_Para3'   : det.pre_oper_para3,
        'Pre_Oper_Code4'   : det.pre_oper_code4,
        'Pre_Oper_Desc4'   : det.pre_oper_desc4,
        'Pre_Oper_Para4'   : det.pre_oper_para4,
        'RR_Weight'        : det.rr_weight,
        'RR_Count'         : det.rr_count,
        'FB_Type'          : det.fb_type,
        'RR_Alarm_Sigma'   : det.rr_alarm_sigma,
        'Pol_Type'         : cat.pol_type,
        'Group_Name'       : group_name,
    }


def build_payload(family, oper_desc, days=30):
    """[web 에서 실행] Set-up 전체를 payload 로 직렬화한다. Django 가 필요하다.

    SubCategory 와 Detail 의 모든 조합을 담는다 — 컨테이너가 web DB 를 못 보므로
    학습에 쓰일 값은 여기서 전부 넘어가야 한다.
    """
    from setup_mico.models import Category   # Django 는 여기서만 필요

    rows = []
    for cat in Category.objects.filter(family=family, oper_desc=oper_desc):
        for sub in cat.subcategories.all():
            rg = sub.recipe_groups.filter(category=cat).first()
            # 같은 이름의 그룹이 Category 마다 있을 수 있어 pk 를 붙여 유일하게 만든다
            # (Group_Name 은 실행 중에만 쓰는 키라 접미사가 무해하다)
            group_name = f'{rg.name}#{rg.pk}' if rg else None
            for det in sub.details.all():
                rows.append(_row_from_setup(cat, sub, det, group_name))

    if not rows:
        raise ValueError(f'Set-up 정보 없음: Family={family}, oper_desc={oper_desc}')

    return {
        'schema_version': SCHEMA_VERSION,
        'family'        : family,
        'oper_desc'     : oper_desc,
        'days'          : days,          # DataLake 조회 기간
        'rows'          : _json_safe(rows),
    }


def _json_safe(rows):
    """JSON 으로 못 싣는 값(Decimal, date 등)을 문자열로 낮춘다. None 은 유지."""
    out = []
    for r in rows:
        clean = {}
        for k, v in r.items():
            if v is None or isinstance(v, (str, int, float, bool)):
                clean[k] = v
            else:
                clean[k] = str(v)
        out.append(clean)
    return out


def to_info_table(payload):
    """[컨테이너에서 실행] payload -> mico_info_table DataFrame. Django 가 필요 없다.

    baseinfoGetData 의 반환과 같은 모양이어야 하므로,
      - 컬럼 집합/순서를 INFO_COLUMNS 로 맞추고
      - Module.run 이 하던 Group_Name fillna / for_key_list 생성까지 여기서 한다
        (컨테이너는 Module.run 을 그대로 못 쓰므로 이 전처리가 유실되면 안 된다)
    """
    import pandas as pd

    _validate(payload)
    df = pd.DataFrame(payload['rows'])

    missing = [c for c in INFO_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f'payload 에 빠진 컬럼: {missing}\n'
            '  -> web 쪽 build_payload 와 버전이 어긋났다. 같이 배포할 것'
        )
    df = df[INFO_COLUMNS].copy()

    # Module.run 과 동일한 전처리
    df['Group_Name']   = df['Group_Name'].fillna('not_group')
    df['for_key_list'] = (
        df['Lot_Code'].astype(str) + '_' +
        df['Oper_Code'].astype(str) + '_' +
        df['Fab'].astype(str)
    )
    return df


def _validate(payload):
    if not isinstance(payload, dict):
        raise ValueError(f'payload 는 dict 여야 한다 (받은 것: {type(payload).__name__})')
    if payload.get('schema_version') != SCHEMA_VERSION:
        raise ValueError(
            f'payload schema_version={payload.get("schema_version")} '
            f'(이 컨테이너는 {SCHEMA_VERSION})'
        )
    if not payload.get('rows'):
        raise ValueError('payload 에 rows 가 비어 있다')


def dumps(payload):
    return json.dumps(payload, ensure_ascii=False, indent=2)
