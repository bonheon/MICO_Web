"""대조 실험 호출 — iris_upload.py 가 만든 input_example.json 을 그대로 POST."""

import json

import requests

url = "{TODO}"        # IRIS_Control 을 서빙하는 엔드포인트 주소

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
