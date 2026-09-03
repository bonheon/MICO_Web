"""올린 모델 호출. req_url 만 채우면 끝."""

import json

import requests

req_url = "{TODO}"

with open("input_example.json", "r") as f:
    data = json.load(f)

headers = {"Content-Type": "application/json"}
resp = requests.post(req_url, headers=headers, data=json.dumps(data), verify=False)

print("HTTP", resp.status_code)
print(resp.text)
