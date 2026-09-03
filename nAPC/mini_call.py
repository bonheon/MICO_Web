"""올린 모델 호출. url 만 채우면 끝.

payload 는 사내 예제와 같은 형식. datatype 이 "ndarray" 인 게 핵심.

한 행 = [a, b, post_thk, pol_time, target]
반환   = [pre_thk, rr, offset]
"""

import json

import requests

url = "{TODO}"        # 엔드포인트 주소

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
    for eq, row in zip(equipment_ids, resp.json()):
        print(f"  {eq}: pre_thk={row[0]}, rr={row[1]}, offset={row[2]}")
