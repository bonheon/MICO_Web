import pandas as pd

_STORE: dict = {}


class mongodb_controller:
    """algorithm_source MongoDB Mock — 컬렉션 이름별 공유 저장소"""

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
                      if k not in ('Date', 'Fab', 'Lot_Code', 'Oper_Code', 'Oper_Desc', 'APC_Para')}
            print(f'    [MongoDB mock] insert_row → {self._collection}: {extras}')
        else:
            print(f'    [MongoDB mock] insert_row → {self._collection}: {list(row.keys())}')

    def get_df(self):
        if self._records:
            return pd.DataFrame(self._records)
        return pd.DataFrame(columns=[
            'Date', 'APC_Para', 'EQ', 'Recipe_ID',
            'b1', 'b0', 'b1_weighted', 'b0_weighted',
            'b1_new', 'b0_new',
        ])


def multi_uploader(*args, **kwargs):
    print('    [MongoDB mock] multi_uploader called (no-op)')
