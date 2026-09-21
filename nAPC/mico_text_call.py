"""문자 in / 문자 out 모델 호출. url 만 채우면 끝.

`mico_text_upload.py` 가 만든 text_input_example.json 을 그대로 보낸다.
모델의 serving_input_example.json 과 같은 내용이라 형식이 어긋날 일이 없다.

## 터미널에서

    python3 mico_text_call.py                       # 예제 그대로 (E2, NA, AG)
    python3 mico_text_call.py --lot E2 NA           # 원하는 문자열로

## Jupyter 노트북에서  <- 여기서는 call() 을 직접 부를 것

    from mico_text_call import call
    call(["E2", "NA"], url="https://...")

노트북에서 이 파일을 통째로 실행(%run, 셀 붙여넣기)해도 되게는 해 뒀지만
(argparse 가 커널의 `-f kernel.json` 을 무시한다), call() 을 쓰는 쪽이 낫다.
argparse 를 그냥 쓰면 노트북에서는 아래처럼 죽는다:

    ipykernel_launcher.py: error: unrecognized arguments: -f /home/.../kernel.json
    SystemExit: 2

MLflow 에러가 아니다. 노트북 커널이 자기 인자(`-f`)를 물고 있어서 나는 것이다.

## 응답 형식

    사내 게이트웨이 : {"output": {"aiu_output": ["E2 | period=3 | ...", ...]}}
    로컬 서빙       : ["E2 | period=3 | ...", ...]      (배열 그대로)
`predictions` 키는 어느 쪽에도 없다.
"""

import argparse
import json
import os
import sys

import requests

url = "{TODO}"        # 엔드포인트 주소

# input_example 파일 경로 — 노트북에서 다른 폴더에 있어도 찾도록 이 파일 기준으로도 본다
EXAMPLE_NAME = "text_input_example.json"


def _find_example():
    here = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else "."
    for path in (EXAMPLE_NAME, os.path.join(here, EXAMPLE_NAME)):
        if os.path.exists(path):
            return path
    raise FileNotFoundError(
        f"{EXAMPLE_NAME} 이 없다. mico_text_upload.py 를 먼저 실행할 것"
    )


def build_payload(lot_codes=None):
    with open(_find_example(), "r") as f:
        payload = json.load(f)
    if lot_codes:
        block = payload["input"][0]
        block["data"] = [str(x) for x in lot_codes]   # 전부 문자열이어야 한다
        block["shape"] = [len(block["data"])]
    return payload


def extract_preds(body):
    """응답 본문에서 결과 배열을 꺼낸다 (mico_call.py 와 동일)."""
    if not isinstance(body, dict):
        return body
    out = body.get("output")
    if isinstance(out, dict) and out.get("aiu_output"):
        return out["aiu_output"]
    return body.get("predictions", [])


def error_in(body):
    """본문이 결과가 아니라 에러면 그 내용을 돌려준다.

    게이트웨이는 에러도 **HTTP 200** 으로 준다. 그래서 상태코드만 보면 성공처럼
    보이는데 결과 배열이 없다. 이 경우를 "응답 구조를 확인할 것" 으로 뭉뚱그리면
    추출 코드가 틀린 줄 알고 엉뚱한 데를 보게 된다.

        {"error_code":"15001","error_type":"NotImplementedError",
         "hcp_error_type":"NOT_IMPLEMENTED","error_message":"Inference Error"}
    """
    if not isinstance(body, dict):
        return None
    if not any(k in body for k in ("error_code", "error_type", "hcp_error_type")):
        return None
    return {k: body.get(k) for k in
            ("error_code", "error_type", "hcp_error_type", "error_message")
            if body.get(k) is not None}


def call(lot_codes=None, url=url, verbose=True):
    """문자열 리스트를 보내고 결과 리스트를 돌려준다. 노트북에서는 이걸 쓴다."""
    payload = build_payload(lot_codes)
    if verbose:
        print("보낸 문자:", payload["input"][0]["data"])

    resp = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload),
        verify=False,
    )
    if verbose:
        print("HTTP", resp.status_code)
        print(resp.text)

    if resp.status_code != 200:
        return []

    body = resp.json()

    # 에러도 HTTP 200 으로 온다 — 결과 없음과 구분해서 알려 준다
    err = error_in(body)
    if err:
        if verbose:
            print("서버가 에러를 돌려줬다 (HTTP 200 이지만 결과가 아니다):")
            for k, v in err.items():
                print(f"    {k}: {v}")
            if err.get("hcp_error_type") == "NOT_IMPLEMENTED":
                print("    -> 배포된 클래스에 predict_stream 이 없다.")
                print("       python3 mico_check_model.py --model <모델 URI> 로 확인할 것")
        return []

    preds = extract_preds(body)
    if verbose:
        if not preds:
            print("결과 배열이 비어 있다. 응답 본문 구조를 확인할 것:", body)
        for line in preds:
            print("  ", line)
    return preds


def _parse_args():
    """노트북 커널의 `-f kernel.json` 같은 남의 인자는 무시한다."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--lot", nargs="*", help="보낼 문자열 (Lot_Code)")
    ap.add_argument("--url", default=url)
    if "ipykernel" in sys.modules:        # 노트북이면 CLI 인자를 읽지 않는다
        return ap.parse_args([])
    args, _unknown = ap.parse_known_args()
    return args


if __name__ == "__main__":
    args = _parse_args()
    call(args.lot, url=args.url)
