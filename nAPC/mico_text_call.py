"""문자 in / 문자 out 모델 호출. url 만 채우면 끝.

`mico_text_upload.py` 가 만든 text_input_example.json 을 그대로 보낸다.
모델의 serving_input_example.json 과 같은 내용이라 형식이 어긋날 일이 없다.

보내는 문자를 바꿔서 시험하려면 --lot 을 쓴다:

    python3 mico_text_call.py                 # 예제 그대로 (E2, NA, AG)
    python3 mico_text_call.py --lot E2 NA     # 원하는 문자열로

응답 형식:
    사내 게이트웨이 : {"output": {"aiu_output": ["E2 | period=3 | ...", ...]}}
    로컬 서빙       : ["E2 | period=3 | ...", ...]      (배열 그대로)
`predictions` 키는 어느 쪽에도 없다.
"""

import argparse
import json

import requests

url = "{TODO}"        # 엔드포인트 주소


def build_payload(lot_codes=None):
    with open("text_input_example.json", "r") as f:
        payload = json.load(f)
    if lot_codes:
        block = payload["input"][0]
        block["data"] = list(lot_codes)     # 전부 문자열이어야 한다
        block["shape"] = [len(lot_codes)]
    return payload


def extract_preds(body):
    """응답 본문에서 결과 배열을 꺼낸다 (mico_call.py 와 동일)."""
    if not isinstance(body, dict):
        return body
    preds = body.get("output", {}).get("aiu_output", [])
    if preds:
        return preds
    return body.get("predictions", [])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lot", nargs="*", help="보낼 문자열 (Lot_Code)")
    ap.add_argument("--url", default=url)
    args = ap.parse_args()

    payload = build_payload(args.lot)
    print("보낸 문자:", payload["input"][0]["data"])

    resp = requests.post(
        args.url,
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload),
        verify=False,
    )
    print("HTTP", resp.status_code)
    print(resp.text)

    if resp.status_code == 200:
        preds = extract_preds(resp.json())
        if not preds:
            print("결과 배열을 못 찾았다. 응답 본문 구조를 확인할 것")
        for line in preds:
            print("  ", line)
