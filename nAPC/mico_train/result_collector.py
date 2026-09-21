"""학습 결과를 가로채 응답으로 돌려줄 수 있게 모은다.

학습 코드(`Common/Module.py`, `Common/OFFSET.py`)는 결과를 `mongodb_controller`
로 쓴다. 값을 돌려주려고 알고리즘을 고치는 대신, **그 controller 를 감싸서
쓰는 내용을 기록**한다. 알고리즘은 한 줄도 바뀌지 않는다.

    with ResultCollector() as rc:
        _run_pipeline(...)
    rc.results()   # {컬렉션명: [레코드, ...]}

기본은 **tee** 다 — 기록하면서 원래 controller 에 그대로 넘긴다. 그래서 사내
서버에서는 MongoDB 적재가 기존대로 일어나고, 응답에도 값이 실린다.
`delegate=False` 로 두면 기록만 하고 Mongo 에는 쓰지 않는다.

## 왜 모듈 속성을 바꾸나

`Module.py` 와 `OFFSET.py` 가 `from Common.MongoDB_Control import mongodb_controller`
로 **import 시점에 이름을 묶어** 둔다. 그래서 `Common.MongoDB_Control` 쪽을 바꿔도
이미 묶인 이름은 안 바뀐다. 쓰는 쪽 모듈의 속성을 직접 갈아 끼워야 한다.
"""

import datetime
import math

_TARGET_MODULES = ('Common.Module', 'Common.OFFSET')


class _Recorder:
    """mongodb_controller 를 감싼 프록시. insert_row / push_df 만 가로채고 나머지는 위임."""

    def __init__(self, inner, collection, sink):
        self._inner = inner
        self._collection = collection
        self._sink = sink

    def _record(self, rows):
        self._sink.setdefault(self._collection, []).extend(rows)

    def insert_row(self, row):
        self._record([dict(row)])
        if self._inner is not None:
            return self._inner.insert_row(row)

    def push_df(self, df):
        if df is not None and not df.empty:
            self._record(df.to_dict('records'))
        if self._inner is not None:
            return self._inner.push_df(df)

    def __getattr__(self, name):
        # get_df / count_row / set_index ... 는 원래 controller 가 처리한다
        if self._inner is None:
            raise AttributeError(
                f'{name}: delegate=False 라 원본 controller 가 없다. '
                '학습이 결과를 되읽어야 하면 delegate=True 로 둘 것'
            )
        return getattr(self._inner, name)


class ResultCollector:
    """학습이 쓰는 결과를 모은다.

    Args:
        delegate: True 면 원래 controller 에도 그대로 넘긴다(MongoDB 적재 유지).
                  False 면 기록만 한다 — 단, 학습이 결과를 되읽는 경로
                  (Offset 이 RR 을 다시 읽는 등)가 막히므로 주의.
        modules : 속성을 갈아 끼울 모듈 이름들. 기본은 결과를 쓰는 두 곳.
    """

    def __init__(self, delegate=True, modules=_TARGET_MODULES):
        self.delegate = delegate
        self.modules = modules
        self._sink = {}
        self._saved = {}

    def __enter__(self):
        import importlib
        for mod_name in self.modules:
            try:
                mod = importlib.import_module(mod_name)
            except Exception:
                continue                      # 그 모듈이 없으면 그냥 넘어간다
            original = getattr(mod, 'mongodb_controller', None)
            if original is None:
                continue
            self._saved[mod_name] = (mod, original)
            setattr(mod, 'mongodb_controller', self._factory(original))
        return self

    def __exit__(self, *exc):
        for mod, original in self._saved.values():
            setattr(mod, 'mongodb_controller', original)
        self._saved.clear()
        return False

    def _factory(self, original):
        sink, delegate = self._sink, self.delegate

        def make(mongo_url, mongo_db, collection):
            inner = original(mongo_url, mongo_db, collection) if delegate else None
            return _Recorder(inner, collection, sink)

        return make

    # ── 결과 꺼내기 ───────────────────────────────────────────────────────

    def results(self, max_rows=None):
        """{컬렉션명: [레코드, ...]} — JSON 으로 바로 실을 수 있는 형태.

        max_rows: 컬렉션마다 이 개수까지만 싣는다 (None 이면 전부).
                  엔드포인트 응답이 커질 때 쓴다. 잘린 경우 counts 로 원래 수를 안다.
        """
        out = {}
        for coll, rows in self._sink.items():
            picked = rows if max_rows is None else rows[:max_rows]
            out[coll] = [_json_safe(r) for r in picked]
        return out

    def counts(self):
        """{컬렉션명: 건수} — 잘라서 보낼 때도 전체 수는 알 수 있게."""
        return {coll: len(rows) for coll, rows in self._sink.items()}

    def is_empty(self):
        return not any(self._sink.values())


def _json_safe(row):
    """Timestamp / numpy 스칼라 / NaN 등을 JSON 에 실을 수 있게 낮춘다."""
    return {k: _scalar(v) for k, v in row.items()}


def _scalar(v):
    if v is None or isinstance(v, (str, bool)):
        return v
    if isinstance(v, (int, float)):
        # NaN/Inf 는 JSON 표준이 아니라 None 으로 (json.dumps 는 NaN 을 그냥 쓴다)
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return v
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.isoformat()
    # numpy 스칼라 등 item() 을 가진 것
    item = getattr(v, 'item', None)
    if callable(item):
        try:
            return _scalar(item())
        except Exception:
            pass
    return str(v)
