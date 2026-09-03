"""이미 올라가 있는 모델 호출. url 만 채우면 끝. 재업로드 필요 없다.

payload 는 MLflow UI 의 `serving_input_example.json` 과 같은 형식이다.
그 파일이 곧 "이 모델이 받는 요청 본문" 이므로, 형식이 헷갈리면 그걸 보면 된다.

  datatype = "BYTES"
  data     = set-up 를 JSON **문자열** 로 만든 것 (숫자 배열이 아니다)
  shape    = [행 개수, 1]

반환은 result_json 컬럼 하나짜리이고, 그 안에 JSON 문자열이 들어 있다.
"""

import json

import requests

url = "{TODO}"        # 엔드포인트 주소

setups = [
    {"equipment_id": "EQ001", "a": 1, "b": 2, "post_thk": 0, "pol_time": 1, "target": 10},
    {"equipment_id": "EQ002", "a": 5, "b": 5, "post_thk": 2, "pol_time": 2, "target": 20},
    {"equipment_id": "EQ003", "a": 7, "b": 3, "post_thk": 2, "pol_time": 4, "target": 30},
]

rows = [json.dumps(s) for s in setups]      # 각 행을 JSON 문자열로

payload = {
    "input": [
        {
            "name": "mico_setup",
            "shape": [len(rows), 1],
            "datatype": "BYTES",
            "data": rows,
        }
    ]
}

resp = requests.post(
    url,
    headers={"Content-Type": "application/json"},
    data=json.dumps(payload),
    verify=False,
)

print("HTTP", resp.status_code)
print(resp.text)

if resp.status_code == 200:
    body = resp.json()
    # 서버에 따라 [...] 또는 {"predictions": [...]} 로 온다
    preds = body["predictions"] if isinstance(body, dict) else body
    for row in preds:
        print("  ", json.loads(row["result_json"]))
