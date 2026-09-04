"""올린 모델 호출. url 만 채우면 끝.

`mico_upload.py` 가 만든 input_example.json 을 그대로 보낸다.
모델의 serving_input_example.json 과 같은 내용이므로 형식이 어긋날 일이 없다.
"""

import json

import requests

url = "{TODO}"        # 엔드포인트 주소

equipment_ids = ["EQ001", "EQ002", "EQ003"]   # 숫자 배열에 못 넣으니 따로 둔다

with open("input_example.json", "r") as f:
    payload = json.load(f)

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
    preds = body["predictions"] if isinstance(body, dict) else body
    for eq, offset in zip(equipment_ids, preds):
        print(f"  {eq}: offset={offset}")
