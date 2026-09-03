"""올린 모델 호출. url 만 채우면 끝.

payload 는 사내 예제와 같은 형식이다. datatype 이 "ndarray" 인 게 핵심.
data 는 2차원 숫자 배열, shape 는 [행, 열].
"""

import json

import requests

url = "{TODO}"        # 엔드포인트 주소

data = [
    [1.0, 2.0],
    [3.0, 4.0],
    [10.0, 5.0],
]

payload = {
    "input": [
        {
            "name": "mico_example",
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
