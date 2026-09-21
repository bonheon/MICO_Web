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
| `result_collector.py` | 컨테이너 | 학습값을 가로채 응답에 싣는다 |
| `sample_provider.py` | 테스트 | `merge_df_sample.csv` 를 DataLake/DataHub 대역으로 |
| `run_sample.py` | 테스트 | 샘플로 **실제 학습 파이프라인**까지 한 번 돌리기 |
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

## 샘플로 실제 학습까지 돌려보기

사내 조회 함수가 비어 있어도 `algorithm_new/merge_df_sample.csv` 를 DataLake/DataHub
대역으로 써서 **진짜 학습 파이프라인**(`Common.Module._run_pipeline`)까지 태울 수 있다.

```bash
cd /path/to/MICO_Web
python3 -m nAPC.mico_train.run_sample            # 학습까지
python3 -m nAPC.mico_train.run_sample --dry-run  # 데이터 경로만
```

확인된 결과 (Django 없이, pymongo 만 설치된 상태):

```
[1/1] E2_V5077000E_M10
    [데이터] DataLake(30일) + DataHub 조회 ... 20000행
    Oper 필터 후: 20000행 / recipe 필터 후: 20000행
  [Pre_Thk_VM]   시작 -> 완료
  [Removal Rate] 시작 -> E2_M1CU_R17_TSV.CAS / E2_M1CU_R12_TSV.CAS 둘 다 학습 -> 완료
  [Offset]       시작 -> RR 데이터 없음(MongoDB) 스킵
  [Alarm 점검]   시작 -> MongoDB 연결 없음
```

MongoDB 가 없어 **Offset 과 Alarm 은 끝까지 못 간다** — RR 학습 결과를 Mongo 에서
다시 읽는 구조이기 때문이다. 데이터가 흘러 학습 모듈이 실제로 도는지 확인하는 용도다.

## 주고받는 데이터 예시 (실제 실행값)

### 보내는 것 — Set-up payload

한 행 = **SubCategory × Detail 한 조합**. 컬럼 40개 전부 들어간다(빈 값도 키는 유지).

```json
{
  "schema_version": 1,
  "family": "DRAM",
  "oper_desc": "M1 CU CMP",
  "days": 30,
  "rows": [
    {
      "Family": "DRAM", "Lot_Code": "E2", "Product": "LC",
      "Oper_Code": "V5077000E", "Oper_Desc": "M1 CU CMP", "Channel_ID": "500019173",
      "Fab": "M10", "Maker": "AMAT", "Recipe_ID": "E2_M1CU_R17_TSV.CAS",
      "APC_Para": "P3", "Thk_Para": "AMAT_POST_OCD_AVG",
      "Target": 1901, "Post_Target": 1901, "Pre_Target": 2001,
      "Pre_Thk_Period": 3, "RR_Para": "PAD", "Offset_Group": "A",
      "RR_Para_Max": 25, "RR_Period": 7, "Pad_Seperation": 1,
      "Pre_Thk_Para_ITM": "", "Pre_Thk_VM_Source": "AUTO",
      "Pre_Oper_Code": "", "Pre_Oper_Desc": "", "Pre_Oper_Para": "",
      "Pre_Oper_Code2": "", "Pre_Oper_Desc2": "", "Pre_Oper_Para2": "",
      "Pre_Oper_Code3": "", "Pre_Oper_Desc3": "", "Pre_Oper_Para3": "",
      "Pre_Oper_Code4": "", "Pre_Oper_Desc4": "", "Pre_Oper_Para4": "",
      "RR_Weight": 1, "RR_Count": 10, "FB_Type": "TIME",
      "RR_Alarm_Sigma": 10, "Pol_Type": 3, "Group_Name": null
    }
  ]
}
```

**merge_df 는 보내지 않는다.** 컨테이너가 DataLake+DataHub 에서 직접 읽는다
(샘플 기준 20,000행 / 52컬럼 — HTTP 로 보낼 크기가 아니다).

엔드포인트로 부를 때는 사내 엔벨로프로 한 번 감싼다 (`{"input": ...}`):

```json
{"input": [{"name": "mico_train", "shape": [1], "datatype": "ndarray",
            "data": [{ ...위 payload... }]}]}
```

### 돌아오는 것 — 키별 요약 + 학습값

```json
[{
  "key": "E2_V5077000E_M10",
  "status": "trained",
  "rows": 20000,
  "counts": {"MICO_Removal_Rate_E2_M1 CU CMP_M10": 10,
             "MICO_OFFSET_E2_M1 CU CMP_M10": 20},
  "results": {
    "MICO_Removal_Rate_E2_M1 CU CMP_M10": [
      {"Date": "2026-09-21T08:41:20.066035", "Fab": "M10", "Lot_Code": "E2",
       "Oper_Code": "V5077000E", "Oper_Desc": "M1 CU CMP", "APC_Para": "P3",
       "EQ": "KCMP43", "Recipe_ID": "E2_M1CU_R17_TSV.CAS", "Count": 1901,
       "b1": -0.0891, "b0": 4.5078, "b1_weighted": -0.0876, "b0_weighted": 4.472}
    ],
    "MICO_OFFSET_E2_M1 CU CMP_M10": [
      {"eqp_id": "KCMP41", "recipe_id": "E2_M1CU_R12_TSV.CAS",
       "IDLE": "LC_CMP_M2CU", "OFFSET": 0.0, "APC_Para": "P3",
       "Date": "2026-09-21T08:41:20.579"}
    ]
  }
}]
```

`counts` 는 **잘라서 보내도 원래 건수**를 알 수 있게 항상 전체 수다.
샘플 실행 기준 한 키(RR 10 + OFFSET 20)에 **5,849 bytes** — 엔드포인트로 충분하다.

| status | 뜻 |
|---|---|
| `trained` | 학습 실행됨 |
| `no_data` | 조회 0행 또는 필터 후 0행 (사내 조회 함수가 비어 있을 때도 이것) |
| `failed` | 학습 중 예외 |
| `dry_run` | 데이터만 모으고 학습 안 함 |

엔드포인트 응답은 여기에 `aiu_output` 이 씌워진다:

```json
{"output": {"aiu_output": [{"key": "E2_V5077000E_M10", "status": "trained", "rows": 20000}]}}
```

### 학습값은 어떻게 응답에 실리나

학습 코드는 결과를 `mongodb_controller` 로 쓴다. 값을 돌려주려고 알고리즘을
고치는 대신 **그 controller 를 감싸서 쓰는 내용을 기록**한다
(`result_collector.py`). 알고리즘은 한 줄도 바뀌지 않는다.

기본은 **tee** 다 — 기록하면서 원래 controller 에 그대로 넘긴다.
그래서 **MongoDB 적재는 기존대로 일어나고 응답에도 값이 실린다.**

```python
run_training(payload)                        # 적재 + 응답 (기본)
run_training(payload, keep_mongo=False)      # 응답만, Mongo 에 안 씀
run_training(payload, max_rows=50)           # 컬렉션마다 50건까지만 싣기
run_training(payload, collect_results=False) # 예전처럼 요약만
```

> `Module.py` / `OFFSET.py` 가 `from ... import mongodb_controller` 로 **import
> 시점에 이름을 묶어** 두기 때문에, `Common.MongoDB_Control` 쪽을 바꿔선 안 먹는다.
> 쓰는 쪽 모듈의 속성을 직접 갈아 끼우고 끝나면 되돌린다.

⚠️ `keep_mongo=False` 는 주의 — Offset 이 RR 결과를 Mongo 에서 **되읽는** 경로가
있어서, 적재를 끄면 그 경로가 막힌다.

샘플 실행 실측 (컬렉션에 쌓인 것 = 응답에 실린 것):

```
MICO_PRE_THK_E2_M1 CU CMP_M10_Period :  0건   (Pre_Oper_Code 미설정이라 학습 없음)
MICO_Removal_Rate_E2_M1 CU CMP_M10   : 10건
MICO_OFFSET_E2_M1 CU CMP_M10         : 20건
```

**Removal Rate 한 건** — 장비×recipe 별 RR 기울기/절편:

```json
{
  "Date": "2026-09-21 08:37:17.371774",
  "Fab": "M10", "Lot_Code": "E2",
  "Oper_Code": "V5077000E", "Oper_Desc": "M1 CU CMP",
  "APC_Para": "P3", "EQ": "KCMP43", "Recipe_ID": "E2_M1CU_R17_TSV.CAS",
  "Count": 1901,
  "b1": -0.0891, "b0": 4.5078,
  "b1_weighted": -0.0876, "b0_weighted": 4.472
}
```

`b1`/`b0` 이 RR 회귀식 계수, `Count` 는 학습에 쓰인 표본 수,
`*_weighted` 는 최근 구간 가중 적용분(조건을 만족한 장비에만 붙는다).

**OFFSET 한 건** — 장비×recipe×직전공정(IDLE) 별 보정값:

```json
{
  "eqp_id": "KCMP41", "recipe_id": "E2_M1CU_R12_TSV.CAS",
  "IDLE": "LC_CMP_M2CU", "OFFSET": 0.0,
  "APC_Para": "P3", "Date": "2026-09-21 08:37:17.884640"
}
```

직접 보려면:

```bash
python3 -m nAPC.mico_train.run_sample --show-results
```

### ⚠️ Set-up 값이 데이터와 안 맞으면 조용히 0건이 된다

`RR_Para_Max` 를 실제 소모품 범위보다 크게 두면 RR 이 **에러 없이 0건**이 된다.
`_process_models` 가 소모품 범위를 4분위로 나눠 각 구간에 25건 넘게 있어야
저장하는데, 범위가 과도하면 데이터가 첫 구간에 몰려 조건을 못 넘기 때문이다.

실제로 처음 시연할 때 `RR_Para_Max=120`(실제 PAD 범위 0~24.8)으로 두어
"Removal Rate 완료" 가 찍히는데 저장은 0건이었다. `payload_from_sample()` 은
이제 이 값들을 데이터에서 뽑아 맞춘다.

## algorithm_new import 조건

`Get_Data.py` 가 import 시점에 `django.setup()` 을 불러서, Django 가 없으면
`Common` 트리 전체를 import 조차 못 했다. **Django 가 필요한 곳은 `baseinfoGetData`
하나뿐**이라 그 함수 안에서만 초기화하도록 바꿨다(`_ensure_django()`).
사내 서버 동작은 그대로다.

바꾼 뒤 Django 없이 import 되는 것:

| 모듈 | Django 없이 | 비고 |
|---|---|---|
| `Common.Get_Data` | OK | |
| `Common.PRE_THK_VM` | OK | 원래부터 순수 (pandas/numpy/sklearn) |
| `Common.OFFSET` | OK | |
| `Common.REMOVAL_RATE` | pymongo 필요 | |
| `Common.Module` | pymongo 필요 | |
| `Common.Simulation` | pymongo 필요 | |

→ 컨테이너에는 **pymongo 를 설치**해야 한다. merge_df 를 Mongo 에서 가져오지
않더라도 학습 결과 저장·RR 재조회가 아직 Mongo 경로라 import 가 필요하다.

## 발견한 것 — RR_Para 가 비면 RR 학습이 통째로 날아간다

`REMOVAL_RATE.compute_rr` (300행 근처)는 `RR_Para` 를 네 값
(`HEAD`/`PAD`/`DISK`/`DRESSER_CUTTING_RATE`)으로 분기해 `consumable_Para` 를 정하는데
**`else` 가 없다.**

```python
if RR_Para == 'HEAD':      consumable_Para = Head_Para
elif RR_Para == 'PAD':     consumable_Para = Pad_Para
elif RR_Para == 'DISK':    consumable_Para = Disk_Para
elif RR_Para == 'DRESSER_CUTTING_RATE': consumable_Para = Dresser_Para
...
temp_data3 = Removal_Rate_Get._detect_cycles(temp_data, consumable_Para)   # UnboundLocalError
```

web 의 `Detail.rr_para` 는 `blank=True, default=''` 라 **빈 값이 정상적인 Set-up
상태**다. 그 키는 `UnboundLocalError` 로 RR 학습이 통째로 빠지는데,
`compute_removal_rate` 의 try/except 가 Cube 메시지로 삼켜서 **로그를 안 보면
모르고 지나간다**. 실제로 샘플 실행에서 재현했다.

```
[Cube] ... Module RR Failed : cannot access local variable 'consumable_Para'
```

의도한 동작(스킵인지, 기본값을 쓸지)이 무엇인지에 따라 고칠 방향이 갈려서
여기서는 고치지 않았다.

## 아직 안 된 것

- **사내 `getdatalake` / `getdatahub` 본문** — 이게 들어와야 실제 데이터가 흐른다
- **사전공정(PRE_THK_INFO)** — `Merge_Data` 의 `_process_pre_oper` 계열은 MongoDB
  upsert 전제라 그대로는 못 쓴다. Pre_Thk_VM 의 ITM/detrend 경로와 Pre_Oper2~4
  회귀에 필요하므로 다음 단계에서 같은 방식(직접 조회)으로 옮긴다
- **MongoDB 적재를 끊을지** — 지금은 적재와 응답 둘 다 한다(`keep_mongo=True`).
  끊으려면 Offset 이 RR 을 되읽는 경로를 먼저 정리해야 한다
- **RR_Para 빈 값 처리** — 위 `consumable_Para` 건. 스킵인지 기본값인지 결정 필요
