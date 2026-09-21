"""사내 DataLake/DataHub 대신 `algorithm_new/merge_df_sample.csv` 를 쓰는 provider.

사내 조회 함수가 아직 비어 있어도 **실제 학습 알고리즘을 끝까지 돌려보기** 위한 것.
샘플 CSV 를 날짜로 잘라 앞쪽을 DataLake(과거), 뒤쪽을 DataHub(최신)로 흉내낸다.
경계에서 몇 건을 일부러 겹치게 해 중복 제거 경로도 함께 지난다.

    from nAPC.mico_train.sample_provider import SampleProvider
    run_training(payload, provider=SampleProvider())

실서버에서는 쓰지 않는다 — `set_provider(사내객체)` 로 교체한다.
"""

from pathlib import Path

import pandas as pd

_CSV = Path(__file__).parents[2] / 'algorithm_new' / 'merge_df_sample.csv'


class SampleProvider:
    """merge_df_sample.csv 를 lake/hub 로 나눠 주는 가짜 조회기.

    Args:
        hub_ratio: 뒤쪽 몇 %를 HUB(최신)로 볼지 (기본 0.2)
        overlap  : lake 와 hub 가 겹치는 행 수 (중복 제거 경로 확인용)
    """

    def __init__(self, csv_path=None, hub_ratio=0.2, overlap=50):
        self.csv_path = Path(csv_path) if csv_path else _CSV
        self.hub_ratio = hub_ratio
        self.overlap = overlap
        self._df = None

    def _load(self):
        if self._df is None:
            if not self.csv_path.exists():
                raise FileNotFoundError(f'샘플 CSV 없음: {self.csv_path}')
            df = pd.read_csv(self.csv_path, parse_dates=['Date', 'pre_oper_time'],
                             low_memory=False)
            # 학습 코드가 빈 문자열을 기대하는 컬럼
            if 'IDLE' in df.columns:
                df['IDLE'] = df['IDLE'].fillna('')
            df = df.sort_values('Date').reset_index(drop=True)
            self._df = df
        return self._df

    def _slice(self, Lot_Code, Oper_Code, Recipe_ID_List):
        df = self._load().copy()
        # 샘플은 한 Lot_Code 분량이라 요청한 키 값으로 덮어써서 재사용한다
        df['Lot_Code'] = Lot_Code
        if 'operation_id' in df.columns and Oper_Code:
            df['operation_id'] = Oper_Code
        # recipe 는 샘플에 있는 것을 그대로 둔다 (recipe 필터 경로를 실제로 태우기 위해)
        return df

    def _split(self, df):
        n   = len(df)
        cut = int(n * (1 - self.hub_ratio))
        lake = df.iloc[:cut]
        hub  = df.iloc[max(0, cut - self.overlap):]      # overlap 만큼 겹치게
        return lake.reset_index(drop=True), hub.reset_index(drop=True)

    # ── 사내 함수와 같은 시그니처 ─────────────────────────────────────────
    def getdatalake(self, Fab, Maker, Lot_Code, Oper_Code, Pre_Oper_Code,
                    Recipe_ID_List, Recipe_info, Days):
        df = self._slice(Lot_Code, Oper_Code, Recipe_ID_List)
        lake, _ = self._split(df)
        # Days 로 과거 기간 자르기 (실제 DataLake 동작과 맞춤)
        if Days and 'Date' in lake.columns and not lake.empty:
            cutoff = lake['Date'].max() - pd.Timedelta(days=Days)
            lake = lake[lake['Date'] >= cutoff]
        return lake

    def getdatahub(self, Fab, Maker, Lot_Code, Oper_Code, Pre_Oper_Code,
                   Recipe_ID_List, Recipe_info, Oper_Desc):
        df = self._slice(Lot_Code, Oper_Code, Recipe_ID_List)
        _, hub = self._split(df)
        return hub


def payload_from_sample(family='DRAM', oper_desc='M1 CU CMP', days=30):
    """샘플 CSV 의 실제 recipe/oper 값으로 payload 를 만든다 (학습 시연용)."""
    from .setup_payload import INFO_COLUMNS, SCHEMA_VERSION

    df = pd.read_csv(_CSV, nrows=20000, low_memory=False)
    recipes = list(df['recipe_id'].dropna().unique())
    oper    = df['operation_id'].dropna().unique()[0]

    rows = []
    for rcp in recipes:
        r = {c: '' for c in INFO_COLUMNS}
        r.update({
            'Family': family, 'Lot_Code': 'E2', 'Product': 'LC',
            'Oper_Code': oper, 'Oper_Desc': oper_desc, 'Channel_ID': '500019173',
            'Fab': 'M10', 'Maker': 'AMAT', 'Recipe_ID': rcp,
            'APC_Para': 'P3', 'Thk_Para': 'AMAT_POST_OCD_AVG',
            'Target': 1000, 'Post_Target': 1000, 'Pre_Target': 2000,
            'Pre_Thk_Period': 3, 'RR_Para': '', 'Offset_Group': 'A',
            'RR_Para_Max': 120, 'RR_Period': 7, 'Pad_Seperation': 1,
            'Pre_Thk_Para_ITM': '', 'Pre_Thk_VM_Source': 'AUTO',
            'RR_Weight': 1, 'RR_Count': 10, 'FB_Type': 'TIME',
            'RR_Alarm_Sigma': 10, 'Pol_Type': 3, 'Group_Name': None,
        })
        rows.append(r)

    return {'schema_version': SCHEMA_VERSION, 'family': family,
            'oper_desc': oper_desc, 'days': days, 'rows': rows}
