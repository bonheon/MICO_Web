"""`mini_upload.py` 로 올린 모델을 호출한다. url 만 채우면 끝.

**짝이 중요하다.** 이 파일은 `mini_upload.py` 모델 전용이다.
  mini_upload.py  -> 숫자 배열 in / 1차원 숫자 out   -> mini_call.py  (이 파일)
  simple_upload.py -> JSON 문자열 in / 문자열 out    -> simple_call.py

보내는 형식이 모델과 다르면 "Failed to enforce schema of data" 가 난다.
어떤 모델이 올라가 있는지 헷갈리면 MLflow UI 의 그 모델 artifact 에서
`serving_input_example.json` 을 열어 확인하면 된다 (없으면 signature 가 없는 것).

한 행 = [a, b, post_thk, pol_time, target]
반환   = [offset, offset, ...]   (행마다 숫자 1개, 1차원)
"""

import json

import requests

url = "{TODO}"        # mini_upload.py 모델을 서빙하는 엔드포인트 주소

equipment_ids = ["EQ001", "EQ002", "EQ003"]   # 숫자 배열에 못 넣으니 따로 둔다

#         a     b   post_thk  pol_time  target
data = [
    [ 1.0,  2.0,  0.0,  1.0,  10.0],
    [ 5.0,  5.0,  2.0,  2.0,  20.0],
    [ 7.0,  3.0,  2.0,  4.0,  30.0],
]

payload = {
    "input": [
        {
            "name": "mico",
            "shape": [len(data), len(data[0])],
            "datatype": "ndarray",
            "data": data,
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
    for eq, offset in zip(equipment_ids, preds):
        print(f"  {eq}: offset={offset}")
