# ════════════════════════════════════════════════════════════════════
# [TEST 삭제] 이 파일 전체 삭제 대상
#
# 로컬 테스트용 인메모리 MongoDB Mock 구현.
# push_df / insert_row / get_df 로 _STORE dict 에 데이터를 저장하고,
# 콘솔에 저장 결과를 출력한다.
#
# 회사 실서버에서는 실제 pymongo.MongoClient 를 사용하는
# MongoDB_Control.py 로 교체할 것.
# ════════════════════════════════════════════════════════════════════

import pandas as pd


# 컬렉션명을 키로 데이터를 공유하는 인메모리 저장소
_STORE: dict = {}


class mongodb_controller:
    """MongoDB 컨트롤러 Mock — 컬렉션 이름별로 데이터를 공유 저장하고 콘솔에 출력."""

    def __init__(self, mongo_url, mongo_db, collection):
        self._collection = collection
        if collection not in _STORE:
            _STORE[collection] = []

    @property
    def _records(self):
        return _STORE[self._collection]

    def push_df(self, df):
        if df is not None and not df.empty:
            self._records.extend(df.to_dict('records'))
        n = len(df) if df is not None else 0
        print(f'    [MongoDB mock] push_df  → {self._collection}: {n}건 저장')

    def insert_row(self, row):
        self._records.append(row)
        if 'EQ' in row and 'b1' in row:
            extras = {k: f'{v:.4f}' if isinstance(v, float) else v
                      for k, v in row.items()
                      if k not in ('Date','Fab','Lot_Code','Oper_Code','Oper_Desc','APC_Para')}
            print(f'    [MongoDB mock] insert_row → {self._collection}: {extras}')
        else:
            print(f'    [MongoDB mock] insert_row → {self._collection}: {list(row.keys())}')

    def get_df(self):
        if self._records:
            return pd.DataFrame(self._records)
        # 빈 DataFrame 반환 (load_rr_data가 pivot 실패하지 않도록 필요 컬럼 포함)
        return pd.DataFrame(columns=[
            'Date', 'APC_Para', 'EQ', 'Recipe_ID',
            'b1', 'b0', 'b1_weighted', 'b0_weighted',
            'b1_new', 'b0_new',
        ])


def multi_uploader(*args, **kwargs):
    print('    [MongoDB mock] multi_uploader called (no-op)')
