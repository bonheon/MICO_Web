"""올린 모델 호출. url 만 채우면 끝.

`mico_upload.py` 가 만든 input_example.json 을 그대로 보낸다.
모델의 serving_input_example.json 과 같은 내용이므로 형식이 어긋날 일이 없다.

응답 형식 주의: 사내 게이트웨이는 MLflow 원본(`{"predictions": [...]}`) 을
그대로 주지 않고 아래처럼 한 번 감싸서 돌려준다.

    {"output": {"aiu_output": [7.0, 12.0, 22.0]}}

그래서 결과는 `body["output"]["aiu_output"]` 에서 꺼내야 한다.
(`_extract_preds` 가 이 형식을 먼저 보고, 없으면 예전 형식으로 넘어간다.)
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


def _extract_preds(body):
    """응답 본문에서 결과 배열을 꺼낸다.

    사내 게이트웨이: {"output": {"aiu_output": [...]}}   <- 실제로 오는 형식
    MLflow 원본:     {"predictions": [...]}
    그 외:           본문 자체가 배열
    """
    if not isinstance(body, dict):
        return body
    preds = body.get("output", {}).get("aiu_output", [])
    if preds:
        return preds
    return body.get("predictions", [])


if resp.status_code == 200:
    body = resp.json()
    preds = _extract_preds(body)
    if not preds:
        print("결과 배열을 못 찾았다. 응답 본문 구조를 확인할 것:", body)
    for eq, offset in zip(equipment_ids, preds):
        print(f"  {eq}: offset={offset}")
