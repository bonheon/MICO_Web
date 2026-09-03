"""엔드포인트가 어떤 payload 를 받는지 알아내는 탐침.

사내 엔드포인트가 HTTP 200 과 함께 이런 걸 돌려줄 때 쓴다.

    {"error_code": "15001", "error_type": "NotImplementedError",
     "hcp_error_type": "NOT_IMPLEMENTED", "error_message": "Inference Error"}

MLflow 표준 서버는 payload 형식을 여러 개 받는다. 사내 서빙 런타임이 그중
어느 걸 기대하는지 모르니, 후보를 순서대로 던져보고 어느 게 통하는지 본다.

    python3 simple_probe.py

[1] 의 endpoint_url 만 채우면 된다.
"""

# %% [1] 설정 ──────────────────────────────────────────────────────────────
endpoint_url = "{TODO}"        # 예: "https://<host>/.../invocations"

# 인증이 걸려 있으면 채운다. 비우면 인증 없이 보낸다.
username = ""
password = ""

timeout_sec = 60               # 엔드포인트는 보통 60초 제한

assert "{TODO}" not in endpoint_url, "endpoint_url 을 채우세요."


# %% [2] 입력 블록 만들기 ──────────────────────────────────────────────────
import json

setups = [
    {"equipment_id": "EQ001", "a": 1, "b": 2, "post_thk": 0, "pol_time": 1, "target": 10},
    {"equipment_id": "EQ002", "a": 5, "b": 5, "post_thk": 2, "pol_time": 2, "target": 20},
]
setup_json = [json.dumps(s, ensure_ascii=False) for s in setups]

# 사내 예제가 쓰는 엔벨로프 블록
block = {
    "name": "mico_setup",
    "shape": [len(setup_json), 1],
    "datatype": "BYTES",
    "data": setup_json,
}


# %% [3] 후보 payload 들 ───────────────────────────────────────────────────
# MLflow 표준 서버가 받는 형식 + 사내 예제 형식. 하나씩 던져본다.
candidates = {
    "1. 사내 예제 엔벨로프  {'input': [...]}":       {"input": [block]},
    "2. inputs 로 감싼 엔벨로프":                     {"inputs": {"input": [block]}},
    "3. dataframe_split (input 컬럼)":                {"dataframe_split": {"columns": ["input"],
                                                                          "data": [[[block]]]}},
    "4. dataframe_records (input 컬럼)":              {"dataframe_records": [{"input": [block]}]},
    "5. inputs 를 리스트로":                          {"inputs": [block]},
    "6. instances (KServe v1 형)":                    {"instances": [block]},
    "7. inputs 복수형 (KServe v2 형)":                {"inputs": [dict(block, datatype="BYTES")]},
    "8. dataframe_split (setup_json 컬럼)":           {"dataframe_split": {"columns": ["setup_json"],
                                                                          "data": [[s] for s in setup_json]}},
}


# %% [4] 서버 정체 확인 ────────────────────────────────────────────────────
# MLflow 표준 서버면 /ping, /health, /version 이 응답한다.
import urllib.parse

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

auth = (username, password) if username else None
base = endpoint_url.rsplit("/", 1)[0]

print("=== 서버 정체 확인 ===")
for path in ("ping", "health", "version"):
    url = urllib.parse.urljoin(base + "/", path)
    try:
        r = requests.get(url, auth=auth, verify=False, timeout=10)
        print(f"  GET {path:8s} -> {r.status_code}  {r.text[:80]!r}")
    except Exception as exc:
        print(f"  GET {path:8s} -> 실패: {type(exc).__name__}")


# %% [5] payload 후보 순서대로 던지기 ──────────────────────────────────────
print("\n=== payload 후보 ===")
headers = {"Content-Type": "application/json"}
results = []

for label, payload in candidates.items():
    try:
        resp = requests.post(
            endpoint_url,
            headers=headers,
            data=json.dumps(payload),   # dict 를 재사용하지 않도록 매번 새로 직렬화
            auth=auth,
            verify=False,
            timeout=timeout_sec,
        )
        body = resp.text
        # 본문에 error_code 가 있으면 200 이어도 실패로 본다
        failed = ("error_code" in body) or ("Error" in body[:200]) or resp.status_code >= 400
        mark = "실패" if failed else "성공"
        print(f"\n[{mark}] {label}")
        print(f"   HTTP {resp.status_code}")
        print(f"   {body[:300]}")
        results.append((label, mark, resp.status_code))
    except Exception as exc:
        print(f"\n[실패] {label}")
        print(f"   예외: {type(exc).__name__}: {exc}")
        results.append((label, "예외", None))


# %% [6] 요약 ──────────────────────────────────────────────────────────────
print("\n=== 요약 ===")
for label, mark, status in results:
    print(f"  {mark}  HTTP {status}  {label}")

ok = [label for label, mark, _ in results if mark == "성공"]
if ok:
    print(f"\n통하는 형식: {ok[0]}")
    print("이 형식을 simple_call.py 의 build_payload() 에 반영하면 된다.")
else:
    print("\n전부 실패했다. payload 형식 문제가 아니라 서빙 런타임이")
    print("모델을 부르는 방식이 다른 것이다. 담당자에게 확인할 것:")
    print("  - aiu_custom 패키지를 어디서 받는지 (사내 예제가 code_paths 로 올리는 폴더)")
    print("  - 서빙 런타임이 pyfunc 의 predict() 를 부르는지, 다른 메서드를 부르는지")
    print("  - 엔드포인트가 기대하는 요청 본문 예시")
