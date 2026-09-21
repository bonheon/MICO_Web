# mico_train — nAPC 학습 구조 (1단계: 데이터 경로)

web Set-up 을 통째로 넘겨받아, merge_df 를 **DataLake + DataHub 에서 직접** 만들어
학습한다. **Django 도 MongoDB 도 쓰지 않는다** (컨테이너에 둘 다 없다).

## 무엇이 바뀌었나

| | HCP (기존) | nAPC (여기) |
|---|---|---|
| Set-up | 학습 코드가 Django DB 직접 조회 | web 이 payload 로 넘김 |
| merge_df | Merge_Hub 가 MongoDB 에 적재 → 학습이 조회 | 학습이 DataLake+DataHub 직접 조회 |
| 학습 본체 | `Common/Module.py` | 그대로 사용 |

학습 순서(키 생성 → 그룹 분기 → oper/recipe 필터 → 파이프라인)는 원본과 같다.
바뀐 것은 **Set-up 을 어디서 얻나**와 **merge_df 를 어디서 얻나** 둘뿐이다.

## 파일

| 파일 | 실행 위치 | 하는 일 |
|---|---|---|
| `setup_payload.py` | 양쪽 | `build_payload`(web, Django) / `to_info_table`(컨테이너) |
| `data_source.py` | 컨테이너 | DataLake+DataHub → merge_df. pymongo 없음 |
| `entry.py` | 컨테이너 | payload → 키별 merge_df → 학습 호출 |
| `export_setup.py` | web | payload JSON 뽑기 (CLI) |
| `selftest.py` | 아무데나 | 사내 시스템 없이 전 경로 검증 |

## 쓰는 법

### 1. web 에서 Set-up 뽑기

```bash
cd /path/to/MICO_Web
python3 -m nAPC.mico_train.export_setup --family DRAM --oper-desc "M1 CU CMP" \
    --out payload_dram_m1cu.json
```

payload 한 행 = **SubCategory × Detail 한 조합**. 학습에 쓰이는 값이 전부 들어간다
(`INFO_COLUMNS` 40개 — `Get_data.baseinfoGetData` 와 **같은 컬럼**).

```json
{
  "schema_version": 1,
  "family": "DRAM",
  "oper_desc": "M1 CU CMP",
  "days": 30,
  "rows": [{"Family":"DRAM","Lot_Code":"E2","Product":"LC","Oper_Code":"V5077000E", ...}]
}
```

### 2. 컨테이너에서 학습

```python
from nAPC.mico_train import run_training
import json

payload = json.load(open("payload_dram_m1cu.json"))
run_training(payload)                  # 사내 서버: Merge_Get_data 자동 연결
run_training(payload, dry_run=True)    # 데이터만 모으고 학습은 안 함 (경로 점검)
```

## 사내 조회 함수 연결

실제 조회는 사내 함수 두 개가 한다. 시그니처는 `Common/Merge_Data.py` 의
`Merge_Get_data` 와 동일하다.

```python
getdatalake(Fab, Maker, Lot_Code, Oper_Code, Pre_Oper_Code, Recipe_ID_List, Recipe_info, Days)
getdatahub (Fab, Maker, Lot_Code, Oper_Code, Pre_Oper_Code, Recipe_ID_List, Recipe_info, Oper_Desc)
```

연결 순서: `set_provider(obj)` → `Common.Merge_Data.Merge_Get_data` → 에러.

```python
from nAPC.mico_train import set_provider
set_provider(우리회사조회객체)
```

**두 함수는 아직 `{TODO}` 스텁이다**(`pass` → None 반환). 그 상태에서는 키마다
`no_data` 로 떨어지며 아래 메시지가 뜬다 — 전체가 죽지는 않는다.

```
getdatalake() 가 None 을 반환했다 — 사내 조회 함수가 아직 비어 있다.
```

## DataLake 와 DataHub 를 합치는 규칙

```
DataLake(과거 days 일) ─┐
                        ├─ concat → substrate_id 중복 제거(HUB 우선) → 정리 → merge_df
DataHub(최신)         ─┘
```

겹치는 `substrate_id` 는 **HUB 가 이긴다**(최신이 정답). `substrate_id` 컬럼이
없으면 중복 제거 없이 이어 붙인다.

정리 단계(`prepare`)는 `Merge_Data._prepare_merge_df` 와 같다 — `request_dtts`→`Date`
rename, route 제외, 정렬, Product/OPER_DESC/Fab/Lot_Code 채우기, `eqp_ch`(Maker 별
EBARA AB/CD · KCT L/R), `fillna('-')`. 저쪽은 pymongo 와 Django 를 끌고 들어와
컨테이너에서 import 가 안 되므로 여기 다시 뒀고, **두 구현의 결과가 같은지
`selftest.py` 가 대조한다.**

## 검증

```bash
cd /path/to/MICO_Web
python3 -m nAPC.mico_train.selftest
```

Django·pymongo 없는 환경(= 컨테이너와 같은 조건)에서 19개 항목 통과 확인:

- `INFO_COLUMNS` 가 `baseinfoGetData` 컬럼 40개와 일치 (소스를 읽어 대조)
- payload → info_table (`for_key_list` / `Group_Name` 전처리 포함)
- lake10 + hub4(2건 중복) → 12행, 중복은 HUB 값이 남음
- `prepare()` == `Merge_Data._prepare_merge_df` (같은 입력 → 같은 DataFrame)
- 단독 1건 + 그룹 1건 → 학습기 3회 호출, 그룹은 `use_group_rr=True`
- 조회 함수가 비어 있어도 `no_data` 로 넘어가고 죽지 않음
- `dry_run` 은 행 수만 세고 학습기를 안 부름

## 아직 안 된 것

- **사내 `getdatalake` / `getdatahub` 본문** — 이게 들어와야 실제 데이터가 흐른다
- **사전공정(PRE_THK_INFO)** — `Merge_Data` 의 `_process_pre_oper` 계열은 MongoDB
  upsert 전제라 그대로는 못 쓴다. Pre_Thk_VM 의 ITM/detrend 경로와 Pre_Oper2~4
  회귀에 필요하므로 다음 단계에서 같은 방식(직접 조회)으로 옮긴다
- **학습 결과 저장** — 지금은 기존 `_run_pipeline` 에 맡긴다(MongoDB 에 쓴다).
  결과도 nAPC 쪽으로 옮길지는 별도 결정
- **`Common/Module.py` 의 Django 의존** — `Get_Data.py` 가 import 시점에
  `django.setup()` 을 부른다. 사내 서버에서는 문제없지만 컨테이너로 옮기려면
  이 부분을 지연 초기화로 바꿔야 한다 (`set_trainer()` 로 우회 가능)
